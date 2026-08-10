"""Build a sanitized, deployable copy of the public Travelogue site."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
SOURCE_TRIPS_PATH = PROJECT_DIR / "output" / "trips.json"
WEBSITE_DIR = PROJECT_DIR / "website"
PROCESSED_PHOTOS_DIR = PROJECT_DIR / "photos" / "processed"
PUBLIC_DIR = PROJECT_DIR / "public"
PRIVATE_TRIPS_FETCH = 'fetch("../output/trips.json")'
PUBLIC_TRIPS_FETCH = 'fetch("./trips.json", { cache: "no-store" })'


def public_trip(trip: dict[str, Any]) -> dict[str, Any]:
    """Return a public trip without private title metadata."""
    sanitized = dict(trip)
    public_title = str(sanitized.pop("public_title", "") or "").strip()
    sanitized["title"] = public_title or sanitized["title"]
    sanitized.pop("public", None)

    highlight_photo = sanitized.get("highlight_photo")
    if isinstance(highlight_photo, str):
        sanitized["highlight_photo"] = highlight_photo.removeprefix("../")

    return sanitized


def main() -> None:
    """Export public trips and the static files needed to display them."""
    trips = json.loads(SOURCE_TRIPS_PATH.read_text(encoding="utf-8"))
    public_trips = [public_trip(trip) for trip in trips if trip.get("public") is True]

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    for filename in ("index.html", "style.css"):
        shutil.copy2(WEBSITE_DIR / filename, PUBLIC_DIR / filename)

    app_javascript = (WEBSITE_DIR / "app.js").read_text(encoding="utf-8")
    if app_javascript.count(PRIVATE_TRIPS_FETCH) != 1:
        raise ValueError("Could not identify the private trip-data fetch exactly once.")
    app_javascript = app_javascript.replace(PRIVATE_TRIPS_FETCH, PUBLIC_TRIPS_FETCH)
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
    for photo_path in PROCESSED_PHOTOS_DIR.glob("*.jpg"):
        shutil.copy2(photo_path, public_photos_dir / photo_path.name)

    (PUBLIC_DIR / "trips.json").write_text(
        json.dumps(public_trips, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Built public site with {len(public_trips)} trips.")


if __name__ == "__main__":
    main()
