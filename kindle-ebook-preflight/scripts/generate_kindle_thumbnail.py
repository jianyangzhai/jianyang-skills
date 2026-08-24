#!/usr/bin/env python3
"""Generate a Kindle library thumbnail from an ebook's embedded cover.

Run through Calibre's Python runtime:
  calibre-debug -e generate_kindle_thumbnail.py -- BOOK OUTPUT_DIRECTORY
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path

from calibre.devices.kindle.driver import thumbnail_filename
from calibre.ebooks.metadata.meta import get_metadata
from calibre.utils.img import scale_image


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("book", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--height", type=int, default=500)
    parser.add_argument("--quality", type=int, default=75)
    args = parser.parse_args()

    book = args.book.expanduser().resolve()
    output_dir = args.output_directory.expanduser().resolve()
    if not book.is_file():
        raise SystemExit(f"Book does not exist: {book}")
    if book.suffix.lower() not in {".azw", ".azw3", ".mobi"}:
        raise SystemExit("Kindle thumbnails require an AZW/AZW3/MOBI file")
    if not 50 <= args.quality <= 99:
        raise SystemExit("Quality must be between 50 and 99")

    original_hash = sha256_file(book)
    with book.open("rb") as stream:
        name = thumbnail_filename(stream)
    if not name:
        raise SystemExit("Book has no stable Kindle thumbnail identifier")
    with book.open("rb") as stream:
        metadata = get_metadata(stream, book.suffix.lower().lstrip("."))
    cover_data = getattr(metadata, "cover_data", None)
    cover = cover_data[1] if cover_data and len(cover_data) > 1 else None
    if not cover:
        raise SystemExit("Book has no embedded cover")
    if sha256_file(book) != original_hash:
        raise SystemExit("Book changed while extracting its cover")

    width, height, jpeg = scale_image(
        cover,
        width=args.height,
        height=args.height,
        compression_quality=args.quality,
        preserve_aspect_ratio=True,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / name
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite: {destination}")
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.partial")
    try:
        with temporary.open("xb") as handle:
            handle.write(jpeg)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    print(json.dumps({
        "book": str(book),
        "book_sha256": original_hash,
        "thumbnail": str(destination),
        "thumbnail_name": name,
        "thumbnail_width": width,
        "thumbnail_height": height,
        "thumbnail_bytes": len(jpeg),
        "thumbnail_sha256": sha256_file(destination),
        "compression_quality": args.quality,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
