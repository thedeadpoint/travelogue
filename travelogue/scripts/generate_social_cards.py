#!/usr/bin/env python3
"""Generate Travelogue social cards from the sanitized site data and real photos."""

from __future__ import annotations

import json
import math
from pathlib import Path

import shapefile
from PIL import Image, ImageDraw, ImageFont, ImageOps


WIDTH, HEIGHT = 1200, 630
CREAM = "#f7f5ef"
PAPER = "#fffefa"
INK = "#183229"
FOREST = "#264d3f"
MUTED = "#617269"
SAND = "#e9e2d4"
TERRACOTTA = "#b9583f"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HERO_PATH = PROJECT_ROOT / "photos" / "processed" / "hero.jpg"
TRIPS_PATH = PROJECT_ROOT / "public" / "trips.json"
OUTPUT_DIR = PROJECT_ROOT / "social"
MAP_SHAPEFILE = PROJECT_ROOT / "data" / "map" / "ne_10m_admin_0_countries.shp"


def find_font(candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise FileNotFoundError(f"Could not find a suitable font: {', '.join(candidates)}")


SERIF = find_font(
    (
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    )
)
SANS = find_font(
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
)
SANS_BOLD = find_font(
    (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    )
)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def tracked_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    value: str,
    typeface: ImageFont.FreeTypeFont,
    fill: str,
    spacing: int = 3,
) -> None:
    x, y = position
    for character in value:
        draw.text((x, y), character, font=typeface, fill=fill)
        x += int(draw.textlength(character, font=typeface)) + spacing


def rounded_cover(image_path: Path, size: tuple[int, int], radius: int) -> Image.Image:
    with Image.open(image_path) as source:
        image = ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    image.putalpha(mask)
    return image


def read_statistics() -> dict[str, int]:
    with TRIPS_PATH.open(encoding="utf-8") as source:
        trips = json.load(source)

    countries: set[str] = set()
    for trip in trips:
        for stop in trip.get("stops", []):
            parts = stop.get("name", "").split(",")
            if len(parts) > 1 and parts[-1].strip():
                countries.add(parts[-1].strip())

    return {
        "trips": len(trips),
        "countries": len(countries),
        "stops": sum(len(trip.get("stops", [])) for trip in trips),
        "travel_days": round(sum(float(trip.get("travel_days") or 0) for trip in trips)),
        "borders": round(sum(float(trip.get("borders_crossed") or 0) for trip in trips)),
        "km": round(sum(float(trip.get("estimated_distance_km") or 0) for trip in trips)),
        "miles": round(sum(float(trip.get("estimated_distance_miles") or 0) for trip in trips)),
    }


def read_stops() -> list[tuple[float, float]]:
    with TRIPS_PATH.open(encoding="utf-8") as source:
        trips = json.load(source)
    return [
        (float(stop["longitude"]), float(stop["latitude"]))
        for trip in trips
        for stop in trip.get("stops", [])
        if stop.get("longitude") is not None and stop.get("latitude") is not None
    ]


def mercator_y(latitude: float) -> float:
    latitude = max(-85.0, min(85.0, latitude))
    radians = math.radians(latitude)
    return math.log(math.tan(math.pi / 4 + radians / 2))


def generate_map_card(statistics: dict[str, int]) -> Path:
    stops = read_stops()
    if not stops:
        raise ValueError(f"No stop coordinates found in {TRIPS_PATH}")

    canvas = Image.new("RGB", (WIDTH, HEIGHT), CREAM)
    draw = ImageDraw.Draw(canvas)
    tracked_text(draw, (56, 22), "OUR TRAVEL ATLAS", font(SANS_BOLD, 14), TERRACOTTA, 4)
    draw.text((53, 45), "Two Years Exploring Europe", font=font(SERIF, 42), fill=INK)
    stat_line = (
        f"{statistics['trips']} trips  ·  {statistics['countries']} countries  ·  "
        f"{statistics['stops']} stops"
    )

    map_box = (48, 104, 1152, 548)
    map_width = map_box[2] - map_box[0]
    map_height = map_box[3] - map_box[1]
    layer = Image.new("RGB", (map_width, map_height), "#e5edef")
    map_draw = ImageDraw.Draw(layer)

    longitudes = [math.radians(point[0]) for point in stops]
    projected_latitudes = [mercator_y(point[1]) for point in stops]
    west, east = min(longitudes) - math.radians(2.0), max(longitudes) + math.radians(2.0)
    south, north = min(projected_latitudes) - 0.035, max(projected_latitudes) + 0.035

    # Preserve the Mercator projection's aspect ratio while fitting the stop extent.
    scale = min(map_width / (east - west), map_height / (north - south))
    visible_longitude_span = map_width / scale
    visible_latitude_span = map_height / scale
    longitude_center = (west + east) / 2
    latitude_center = (south + north) / 2
    west = longitude_center - visible_longitude_span / 2
    east = longitude_center + visible_longitude_span / 2
    south = latitude_center - visible_latitude_span / 2
    north = latitude_center + visible_latitude_span / 2

    def project(longitude: float, latitude: float) -> tuple[int, int]:
        x = (math.radians(longitude) - west) / (east - west) * map_width
        y = (north - mercator_y(latitude)) / (north - south) * map_height
        return round(x), round(y)

    reader = shapefile.Reader(str(MAP_SHAPEFILE))
    for shape in reader.iterShapes():
        shape_west, shape_south, shape_east, shape_north = shape.bbox
        if math.radians(shape_east) < west or math.radians(shape_west) > east:
            continue
        if mercator_y(shape_north) < south or mercator_y(shape_south) > north:
            continue
        part_ends = list(shape.parts[1:]) + [len(shape.points)]
        for start, end in zip(shape.parts, part_ends):
            polygon = [project(longitude, latitude) for longitude, latitude in shape.points[start:end]]
            if len(polygon) >= 3:
                map_draw.polygon(polygon, fill="#eef1e8", outline="#9eafa5", width=1)

    for longitude, latitude in stops:
        x, y = project(longitude, latitude)
        map_draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=PAPER)
        map_draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=TERRACOTTA, outline=FOREST, width=1)

    callouts = (
        ("Norway", 6.1889721, 58.9868297, 16, 18),
        ("Baltics", 24.1051846, 56.9493977, 17, -34),
        ("Porto", -8.6103497, 41.1502195, 16, -36),
        ("Dolomites", 11.8548454, 46.5543844, 16, 21),
        ("Croatia", 16.6520192, 43.2605186, 18, 18),
    )
    label_font = font(SANS_BOLD, 13)
    for label, longitude, latitude, offset_x, offset_y in callouts:
        anchor_x, anchor_y = project(longitude, latitude)
        label_width = round(map_draw.textlength(label, font=label_font)) + 18
        label_height = 25
        label_x = max(8, min(map_width - label_width - 8, anchor_x + offset_x))
        label_y = max(8, min(map_height - label_height - 8, anchor_y + offset_y))
        line_end_x = label_x if label_x > anchor_x else label_x + label_width
        line_end_y = label_y + label_height // 2
        map_draw.line((anchor_x, anchor_y, line_end_x, line_end_y), fill=FOREST, width=1)
        map_draw.rounded_rectangle(
            (label_x, label_y, label_x + label_width, label_y + label_height),
            radius=12,
            fill=PAPER,
            outline="#c8d2ca",
            width=1,
        )
        map_draw.text((label_x + 9, label_y + 5), label, font=label_font, fill=FOREST)

    mask = Image.new("L", (map_width, map_height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, map_width - 1, map_height - 1), radius=22, fill=255)
    canvas.paste(layer, (map_box[0], map_box[1]), mask)
    draw.rounded_rectangle(map_box, radius=22, outline="#cbd7d0", width=2)

    draw.rounded_rectangle((48, 563, 1152, 614), radius=15, fill=PAPER, outline="#e6e0d4", width=1)
    draw.ellipse((72, 582, 82, 592), fill=TERRACOTTA)
    draw.text((95, 577), stat_line, font=font(SANS_BOLD, 18), fill=FOREST)
    source_text = "Map: Natural Earth"
    source_width = draw.textlength(source_text, font=font(SANS, 11))
    draw.text((1126 - source_width, 581), source_text, font=font(SANS, 11), fill=MUTED)

    output = OUTPUT_DIR / "map-card.png"
    canvas.save(output, "PNG", optimize=True)
    return output


def generate_hero_card(statistics: dict[str, int]) -> Path:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle((699, 73, 1125, 597), radius=42, fill="#dfe7df")
    photo = rounded_cover(HERO_PATH, (426, 524), 42)
    canvas.paste(photo, (680, 52), photo)
    draw.rounded_rectangle((680, 52, 1106, 576), radius=42, outline="#ffffff", width=2)

    tracked_text(draw, (82, 74), "OUR TRAVEL ATLAS", font(SANS_BOLD, 18), TERRACOTTA, 4)
    draw.text((78, 125), "Two Years", font=font(SERIF, 76), fill=INK)
    draw.text((78, 202), "Exploring", font=font(SERIF, 76), fill=INK)
    draw.text((78, 279), "Europe", font=font(SERIF, 76), fill=INK)

    draw.line((82, 390, 132, 390), fill=TERRACOTTA, width=5)
    draw.text((82, 414), "August 2024 – August 2026", font=font(SERIF, 28), fill=MUTED)
    stat_line = (
        f"{statistics['trips']} trips  ·  {statistics['countries']} countries  ·  "
        f"{statistics['stops']} stops"
    )
    draw.text((82, 500), stat_line, font=font(SANS_BOLD, 22), fill=FOREST)

    output = OUTPUT_DIR / "hero-card.png"
    canvas.save(output, "PNG", optimize=True)
    return output


def generate_stats_card(statistics: dict[str, int]) -> Path:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), CREAM)
    draw = ImageDraw.Draw(canvas)

    tracked_text(draw, (72, 48), "THE JOURNEY SO FAR", font(SANS_BOLD, 17), TERRACOTTA, 4)
    draw.text((68, 82), "By the numbers", font=font(SERIF, 58), fill=INK)
    draw.line((72, 157, 1128, 157), fill=SAND, width=2)

    cards = [
        (str(statistics["trips"]), "TRIPS"),
        (str(statistics["countries"]), "COUNTRIES"),
        (str(statistics["stops"]), "STOPS"),
        (str(statistics["travel_days"]), "TRAVEL DAYS"),
        (str(statistics["borders"]), "BORDERS CROSSED"),
        (f"{statistics['km']:,} km\n{statistics['miles']:,} mi", "APPROX. DISTANCE TRAVELED"),
    ]
    card_width, card_height = 336, 164
    for index, (value, label) in enumerate(cards):
        column, row = index % 3, index // 3
        x = 72 + column * 360
        y = 188 + row * 188
        draw.rounded_rectangle(
            (x, y, x + card_width, y + card_height),
            radius=18,
            fill=PAPER,
            outline="#e6e0d4",
            width=2,
        )
        if "\n" in value:
            first, second = value.splitlines()
            draw.text((x + 25, y + 23), first, font=font(SERIF, 39), fill=FOREST)
            draw.text((x + 25, y + 68), second, font=font(SERIF, 31), fill=FOREST)
        else:
            draw.text((x + 25, y + 22), value, font=font(SERIF, 66), fill=FOREST)
        tracked_text(draw, (x + 25, y + 128), label, font(SANS_BOLD, 13), MUTED, 2)

    output = OUTPUT_DIR / "stats-card.png"
    canvas.save(output, "PNG", optimize=True)
    return output


def main() -> None:
    if not HERO_PATH.is_file():
        raise FileNotFoundError(f"Hero image not found: {HERO_PATH}")
    if not TRIPS_PATH.is_file():
        raise FileNotFoundError(f"Trip data not found: {TRIPS_PATH}")
    if not MAP_SHAPEFILE.is_file():
        raise FileNotFoundError(f"Natural Earth basemap not found: {MAP_SHAPEFILE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    statistics = read_statistics()
    outputs = (
        generate_hero_card(statistics),
        generate_stats_card(statistics),
        generate_map_card(statistics),
    )
    print("Generated " + ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in outputs))


if __name__ == "__main__":
    main()
