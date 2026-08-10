"""Import and geocode trips from the Travelogue workbook."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim


PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKBOOK_PATH = PROJECT_DIR / "data" / "Travelogue Data.xlsx"
CACHE_PATH = PROJECT_DIR / "data" / "geocode_cache.json"
SETTINGS_PATH = PROJECT_DIR / "config" / "settings.json"
OUTPUT_PATH = PROJECT_DIR / "output" / "trips.json"
PROCESSED_PHOTOS_DIR = PROJECT_DIR / "photos" / "processed"
USER_AGENT = "travelogue-personal-travel-atlas/0.1 (local trip importer)"
EARTH_RADIUS_KM = 6371.0088
KM_TO_MILES = 0.621371
TRAVEL_MODE_MULTIPLIERS = {
    "car": 1.20,
    "train": 1.15,
    "plane": 1.00,
}


def find_header_row(workbook_path: Path) -> int:
    """Return the zero-based row containing the workbook's column names."""
    preview = pd.read_excel(workbook_path, header=None, nrows=20)

    for row_number, row in preview.iterrows():
        if "Trip ID" in row.values:
            return int(row_number)

    raise ValueError("Could not find a header row containing 'Trip ID'.")


def load_geocode_cache() -> dict[str, dict[str, float]]:
    """Load coordinates saved by previous imports."""
    if not CACHE_PATH.exists():
        return {}

    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        print(f"Warning: Could not read geocode cache: {error}")
        return {}


def save_geocode_cache(cache: dict[str, dict[str, float]]) -> None:
    """Persist successful geocoding results."""
    CACHE_PATH.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_home_base() -> tuple[float, float]:
    """Load and validate the configured home-base coordinates."""
    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        home_base = settings["home_base"]
        latitude = float(home_base["latitude"])
        longitude = float(home_base["longitude"])
    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            f"Could not load home base from {SETTINGS_PATH}: {error}"
        ) from error

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError(f"Home-base coordinates in {SETTINGS_PATH} are out of range.")
    return latitude, longitude


def text_value(value: Any) -> str:
    """Convert a spreadsheet value to clean text, treating empty cells as blank."""
    return "" if pd.isna(value) else str(value).strip()


def date_value(value: Any) -> str:
    """Convert a spreadsheet date to an ISO-formatted date string."""
    return "" if pd.isna(value) else pd.Timestamp(value).date().isoformat()


def boolean_value(value: Any) -> bool:
    """Convert common spreadsheet representations to a Boolean value."""
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"yes", "true", "1", "y"}


def integer_value(value: Any) -> int:
    """Convert a numeric spreadsheet value to an integer."""
    return 0 if pd.isna(value) else int(value)


def optional_number(value: Any) -> float | None:
    """Convert an optional spreadsheet number, returning None for blank cells."""
    if pd.isna(value) or str(value).strip() == "":
        return None
    return float(str(value).replace(",", "").strip())


def great_circle_km(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    """Calculate great-circle distance between two latitude/longitude pairs."""
    first_latitude, first_longitude = map(math.radians, first)
    second_latitude, second_longitude = map(math.radians, second)
    latitude_delta = second_latitude - first_latitude
    longitude_delta = second_longitude - first_longitude
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude)
        * math.cos(second_latitude)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, haversine)))


def estimated_trip_distance_km(
    row: dict[str, Any],
    stops: list[dict[str, Any]],
    home_base: tuple[float, float],
) -> float:
    """Return a manual distance override or an approximate round-trip distance."""
    manual_override = optional_number(row.get("Estimated Distance (km)"))
    if manual_override is not None:
        return manual_override

    trip_id = text_value(row.get("Trip ID"))
    coordinates = []
    for stop in stops:
        if stop["latitude"] is None or stop["longitude"] is None:
            print(
                f"Warning: Could not calculate distance for {trip_id}: "
                f"'{stop['name']}' has no coordinates."
            )
            return 0.0
        coordinates.append((stop["latitude"], stop["longitude"]))

    if not coordinates:
        print(f"Warning: Could not calculate distance for {trip_id}: no stops found.")
        return 0.0

    modes = [
        mode.strip()
        for mode in text_value(row.get("Travel Mode")).split(";")
        if mode.strip()
    ]
    if len(modes) > 1:
        print(
            f"Warning: {trip_id} is a mixed-mode trip ({'; '.join(modes)}); "
            f"using {modes[0]} for the distance estimate. Manual review recommended."
        )

    primary_mode = modes[0].lower() if modes else ""
    multiplier = TRAVEL_MODE_MULTIPLIERS.get(primary_mode)
    if multiplier is None:
        print(
            f"Warning: {trip_id} has no supported travel mode; "
            "using a 1.00 distance multiplier."
        )
        multiplier = 1.0

    route = [home_base, *coordinates, home_base]
    great_circle_total = sum(
        great_circle_km(start, end)
        for start, end in zip(route, route[1:])
    )
    return great_circle_total * multiplier


def photo_stem(filename: str) -> str:
    """Return the normalized stem used by the photo import script."""
    stem = Path(filename).stem.strip().lower()
    stem = re.sub(r"\s+", "_", stem)
    return re.sub(r"[^a-z0-9._-]+", "_", stem).strip("._-")


def processed_photo_path(value: Any) -> str:
    """Match a workbook photo filename to its processed JPEG URL."""
    filename = text_value(value)
    if not filename or not PROCESSED_PHOTOS_DIR.exists():
        return ""

    expected_name = f"{photo_stem(filename)}.jpg"
    matches = {
        path.name.lower(): path.name
        for path in PROCESSED_PHOTOS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() == ".jpg"
    }
    matched_name = matches.get(expected_name.lower())
    return f"../photos/processed/{matched_name}" if matched_name else ""


def geocode_stop(
    stop_name: str,
    cache: dict[str, dict[str, float]],
    geocode: RateLimiter,
) -> dict[str, float] | None:
    """Return cached coordinates or request them from Nominatim."""
    if stop_name in cache:
        return cache[stop_name]

    try:
        location = geocode(stop_name)
    except Exception as error:
        print(f"Warning: Could not geocode '{stop_name}': {error}")
        return None

    if location is None:
        print(f"Warning: Could not geocode '{stop_name}': no result found.")
        return None

    coordinates = {
        "latitude": float(location.latitude),
        "longitude": float(location.longitude),
    }
    cache[stop_name] = coordinates
    save_geocode_cache(cache)
    return coordinates


def build_trip(
    row: dict[str, Any],
    cache: dict[str, dict[str, float]],
    geocode: RateLimiter,
    home_base: tuple[float, float],
) -> dict[str, Any]:
    """Convert one workbook row into the Travel Atlas trip structure."""
    stops = []

    for raw_stop in text_value(row.get("Stops")).split(";"):
        stop_name = raw_stop.strip()
        if not stop_name:
            continue

        coordinates = geocode_stop(stop_name, cache, geocode)
        stops.append(
            {
                "name": stop_name,
                "latitude": coordinates["latitude"] if coordinates else None,
                "longitude": coordinates["longitude"] if coordinates else None,
            }
        )

    estimated_distance_km = estimated_trip_distance_km(row, stops, home_base)

    return {
        "trip_id": text_value(row.get("Trip ID")),
        "title": text_value(row.get("Trip Title")),
        "public_title": text_value(row.get("Public Trip Title")) or None,
        "start_date": date_value(row.get("Start Date")),
        "end_date": date_value(row.get("End Date")),
        "travel_mode": text_value(row.get("Travel Mode")),
        "category": text_value(row.get("Category")),
        "borders_crossed": integer_value(row.get("Borders Crossed")),
        "favorite": boolean_value(row.get("Favorite")),
        "public": boolean_value(row.get("Public")),
        "summary": text_value(row.get("Summary")),
        "estimated_distance_km": round(estimated_distance_km, 1),
        "estimated_distance_miles": round(estimated_distance_km * KM_TO_MILES, 1),
        "highlight": boolean_value(row.get("Highlight")),
        "highlight_title": text_value(row.get("Highlight Title")),
        "highlight_note": text_value(row.get("Highlight Note")),
        # The workbook currently labels this column "Photo"; retain support for
        # the more explicit name in case the sheet is updated later.
        "highlight_photo": processed_photo_path(
            row.get("Highlight Photo", row.get("Photo"))
        ),
        "stops": stops,
    }


def main() -> None:
    """Read, geocode, and export all complete trip rows."""
    header_row = find_header_row(WORKBOOK_PATH)
    dataframe = pd.read_excel(WORKBOOK_PATH, header=header_row)
    rows = dataframe.to_dict(orient="records")
    home_base = load_home_base()

    cache = load_geocode_cache()
    geolocator = Nominatim(user_agent=USER_AGENT, timeout=10)
    geocode = RateLimiter(
        geolocator.geocode,
        min_delay_seconds=1.0,
        max_retries=0,
        swallow_exceptions=False,
    )

    trips = [
        build_trip(row, cache, geocode, home_base)
        for row in rows
        if text_value(row.get("Trip Title"))
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(trips, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Imported {len(trips)} trips.")


if __name__ == "__main__":
    main()
