"""Import and geocode trips from the Travelogue workbook."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim


PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKBOOK_PATH = PROJECT_DIR / "data" / "Travelogue Data.xlsx"
CACHE_PATH = PROJECT_DIR / "data" / "geocode_cache.json"
OUTPUT_PATH = PROJECT_DIR / "output" / "trips.json"
USER_AGENT = "travelogue-personal-travel-atlas/0.1 (local trip importer)"


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

    return {
        "trip_id": text_value(row.get("Trip ID")),
        "title": text_value(row.get("Trip Title")),
        "start_date": date_value(row.get("Start Date")),
        "end_date": date_value(row.get("End Date")),
        "travel_mode": text_value(row.get("Travel Mode")),
        "category": text_value(row.get("Category")),
        "borders_crossed": integer_value(row.get("Borders Crossed")),
        "favorite": boolean_value(row.get("Favorite")),
        "public": boolean_value(row.get("Public")),
        "summary": text_value(row.get("Summary")),
        "stops": stops,
    }


def main() -> None:
    """Read, geocode, and export all complete trip rows."""
    header_row = find_header_row(WORKBOOK_PATH)
    dataframe = pd.read_excel(WORKBOOK_PATH, header=header_row)
    rows = dataframe.to_dict(orient="records")

    cache = load_geocode_cache()
    geolocator = Nominatim(user_agent=USER_AGENT, timeout=10)
    geocode = RateLimiter(
        geolocator.geocode,
        min_delay_seconds=1.0,
        max_retries=0,
        swallow_exceptions=False,
    )

    trips = [
        build_trip(row, cache, geocode)
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
