# Travelogue

Travelogue is a starter project for collecting trip data and presenting it on a
simple website. The project is intentionally scaffold-only: data importing and
website behavior have not been implemented yet.

## Project layout

- `data/` contains the source Excel workbook.
- `scripts/` contains Python utilities for working with trip data.
- `website/` contains the static website files.
- `output/` is reserved for generated files.

## Getting started

1. Create and activate a Python virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Add trip data to `data/Travelogue Data.xlsx`.

## Photo workflow

- Drop full-resolution photos into `photos/inbox/`.
- Run `python scripts/import_photos.py`.
- Use the website-ready files from `photos/processed/` in the website.

The import script currently prints a placeholder message and does not read or
write any data.

Known issue:
When a trip with multiple stops is selected, clicking another stop from the same trip may clear the highlight before a second click restores it.
