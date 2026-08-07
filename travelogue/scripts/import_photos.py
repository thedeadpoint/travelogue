"""Prepare full-resolution photos for use on the Travelogue website."""

from __future__ import annotations

import re
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError as error:
    raise SystemExit(
        "Pillow is required. Install dependencies with: "
        "pip install -r requirements.txt"
    ) from error

try:
    from pillow_heif import register_heif_opener
except ImportError:
    register_heif_opener = None


PROJECT_DIR = Path(__file__).resolve().parent.parent
INBOX_DIR = PROJECT_DIR / "photos" / "inbox"
PROCESSED_DIR = PROJECT_DIR / "photos" / "processed"
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
HEIF_SUFFIXES = {".heic", ".heif"}
MAX_EDGE = 1600
JPEG_QUALITY = 85


def output_stem(source: Path) -> str:
    """Return a lowercase, filesystem-friendly version of a photo name."""
    stem = re.sub(r"\s+", "_", source.stem.strip().lower())
    stem = re.sub(r"[^a-z0-9._-]+", "_", stem).strip("._-")
    return stem or "photo"


def available_output_path(source: Path) -> Path:
    """Return an unused JPEG path without overwriting an existing photo."""
    stem = output_stem(source)
    candidate = PROCESSED_DIR / f"{stem}.jpg"
    suffix = 2

    while candidate.exists():
        candidate = PROCESSED_DIR / f"{stem}_{suffix}.jpg"
        suffix += 1

    return candidate


def rgb_image(image: Image.Image) -> Image.Image:
    """Convert an image to RGB, placing transparent pixels on white."""
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba_image = image.convert("RGBA")
        background = Image.new("RGB", rgba_image.size, "white")
        background.paste(rgba_image, mask=rgba_image.getchannel("A"))
        return background

    return image.convert("RGB")


def process_photo(source: Path) -> Path:
    """Orient, resize, and save one source photo as a web-ready JPEG."""
    destination = available_output_path(source)

    with Image.open(source) as image:
        oriented_image = ImageOps.exif_transpose(image)
        oriented_image.thumbnail(
            (MAX_EDGE, MAX_EDGE),
            Image.Resampling.LANCZOS,
        )
        web_image = rgb_image(oriented_image)
        web_image.save(
            destination,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )

    return destination


def main() -> None:
    """Process supported images in the photo inbox."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if register_heif_opener is not None:
        register_heif_opener()

    processed = 0
    skipped = 0
    failed = 0

    for source in sorted(INBOX_DIR.iterdir(), key=lambda path: path.name.lower()):
        if not source.is_file() or source.name.startswith("."):
            continue

        suffix = source.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            skipped += 1
            continue

        if suffix in HEIF_SUFFIXES and register_heif_opener is None:
            print(
                f"Warning: Could not process {source.name}: "
                "install pillow-heif for HEIC/HEIF support."
            )
            failed += 1
            continue

        try:
            process_photo(source)
            processed += 1
        except Exception as error:
            print(f"Warning: Could not process {source.name}: {error}")
            failed += 1

    print(f"Processed {processed} photo{'s' if processed != 1 else ''}.")
    print(f"Skipped {skipped} unsupported file{'s' if skipped != 1 else ''}.")
    if failed:
        print(f"Failed to process {failed} file{'s' if failed != 1 else ''}.")
    print("Output: photos/processed/")


if __name__ == "__main__":
    main()
