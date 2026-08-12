"""Build a sanitized, deployable copy of the public Travelogue site."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
SOURCE_TRIPS_PATH = PROJECT_DIR / "output" / "trips.json"
WEBSITE_DIR = PROJECT_DIR / "website"
PROCESSED_PHOTOS_DIR = PROJECT_DIR / "photos" / "processed"
PUBLIC_DIR = PROJECT_DIR / "public"
PRIVATE_TRIPS_FETCH = 'fetch("../output/trips.json")'
PUBLIC_TRIPS_FETCH = 'fetch("./trips.json", { cache: "no-store" })'
PUBLIC_APP_REPLACEMENTS = {
    """function countTravelDays(startDate, endDate) {
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);

  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return 0;
  }

  return Math.floor((end - start) / millisecondsPerDay) + 1;
}

""": "",
    "travelDays += countTravelDays(trip.start_date, trip.end_date);":
        "travelDays += Number(trip.travel_days) || 0;",
    """    ["Start date", trip.start_date],
    ["End date", trip.end_date],""": """    ["Date", tripMonthYear(trip.start_date)],
    ["Travel days", trip.travel_days],""",
    """    allTrips = await response.json();
    populateFilters(allTrips);""": """    const publicTrips = await response.json();
    allTrips = publicTrips.map((trip) => ({
      ...trip,
      start_date: `${trip.year}-${String(trip.month).padStart(2, "0")}-01`,
    }));
    populateFilters(allTrips);""",
}


def public_text(value: Any) -> str | None:
    """Return trimmed public copy, or null when the public field is blank."""
    text = str(value or "").strip()
    return text or None


def public_stops(stops: Any) -> list[dict[str, Any]]:
    """Allowlist the city-level stop fields used by the public map."""
    if not isinstance(stops, list):
        return []

    return [
        {
            "name": stop.get("name"),
            "latitude": stop.get("latitude"),
            "longitude": stop.get("longitude"),
        }
        for stop in stops
        if isinstance(stop, dict)
    ]


def public_trip(trip: dict[str, Any]) -> dict[str, Any]:
    """Build one public trip from an explicit field allowlist."""
    start_date = date.fromisoformat(str(trip["start_date"]))
    end_date = date.fromisoformat(str(trip["end_date"]))
    travel_days = (end_date - start_date).days + 1
    if travel_days < 1:
        raise ValueError(f"Trip {trip.get('trip_id')} ends before it starts.")

    highlight_photo = public_text(trip.get("highlight_photo"))
    if trip.get("highlight") is True and highlight_photo:
        highlight_photo = f"photos/processed/{Path(highlight_photo).name}"
    else:
        highlight_photo = None

    return {
        "trip_id": trip.get("trip_id"),
        "title": public_text(trip.get("public_title")),
        "month": start_date.month,
        "year": start_date.year,
        "travel_days": travel_days,
        "category": trip.get("category"),
        "travel_mode": trip.get("travel_mode"),
        "borders_crossed": trip.get("borders_crossed"),
        "estimated_distance_km": trip.get("estimated_distance_km"),
        "estimated_distance_miles": trip.get("estimated_distance_miles"),
        "stops": public_stops(trip.get("stops")),
        "favorite": trip.get("favorite"),
        "highlight": trip.get("highlight"),
        "highlight_title": public_text(trip.get("highlight_title")),
        "summary": public_text(trip.get("public_summary")),
        "highlight_note": public_text(trip.get("public_highlight_note")),
        "highlight_photo": highlight_photo,
    }


def main() -> None:
    """Export public trips and the static files needed to display them."""
    trips = json.loads(SOURCE_TRIPS_PATH.read_text(encoding="utf-8"))
    public_trips = [public_trip(trip) for trip in trips if trip.get("public") is True]

    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True)
    for filename in ("index.html", "style.css"):
        shutil.copy2(WEBSITE_DIR / filename, PUBLIC_DIR / filename)

    app_javascript = (WEBSITE_DIR / "app.js").read_text(encoding="utf-8")
    if app_javascript.count(PRIVATE_TRIPS_FETCH) != 1:
        raise ValueError("Could not identify the private trip-data fetch exactly once.")
    app_javascript = app_javascript.replace(PRIVATE_TRIPS_FETCH, PUBLIC_TRIPS_FETCH)
    for private_code, public_code in PUBLIC_APP_REPLACEMENTS.items():
        if app_javascript.count(private_code) != 1:
            raise ValueError("Could not apply a public frontend privacy transform.")
        app_javascript = app_javascript.replace(private_code, public_code)
    if "output/trips.json" in app_javascript:
        raise ValueError("The generated public JavaScript references private trip data.")
    (PUBLIC_DIR / "app.js").write_text(app_javascript, encoding="utf-8")

    index_html_path = PUBLIC_DIR / "index.html"
    index_html = index_html_path.read_text(encoding="utf-8").replace(
        'src="../photos/processed/',
        'src="photos/processed/',
    )
    index_html = index_html.replace(
        'src="app.js"',
        'src="app.js?v=public-data-v1"',
    )
    index_html_path.write_text(index_html, encoding="utf-8")

    public_photos_dir = PUBLIC_DIR / "photos" / "processed"
    public_photos_dir.mkdir(parents=True, exist_ok=True)
    referenced_photos = {
        Path(trip["highlight_photo"]).name
        for trip in public_trips
        if trip["highlight"] is True and trip["highlight_photo"]
    }
    referenced_photos.add("hero.jpg")
    for photo_name in sorted(referenced_photos):
        photo_path = PROCESSED_PHOTOS_DIR / photo_name
        if not photo_path.is_file():
            raise FileNotFoundError(f"Referenced public photo not found: {photo_path}")
        shutil.copy2(photo_path, public_photos_dir / photo_name)

    (PUBLIC_DIR / "trips.json").write_text(
        json.dumps(public_trips, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    available_photos = {path.name for path in PROCESSED_PHOTOS_DIR.glob("*.jpg")}
    excluded_photos = available_photos - referenced_photos
    print(f"Trips exported: {len(public_trips)}")
    print("Exact dates removed: yes")
    print(f"Referenced photos copied: {len(referenced_photos)}")
    print(f"Unreferenced photos excluded: {len(excluded_photos)}")


if __name__ == "__main__":
    main()
