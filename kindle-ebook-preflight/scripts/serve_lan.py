#!/usr/bin/env python3
"""Serve one hash-approved MOBI/AZW3 file to a Kindle on the local network."""

from __future__ import annotations

import argparse
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from ebook_pipeline import (
    PipelineError,
    find_manifest_output,
    load_manifest,
    sha256_file,
)


MIME_TYPES = {
    ".mobi": "application/x-mobipocket-ebook",
    ".azw3": "application/vnd.amazon.ebook",
}


def validate_approved_book(book: Path, manifest_path: Path) -> tuple[Path, str]:
    book = book.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    if not book.is_file():
        raise PipelineError(f"Book does not exist: {book}")
    if book.suffix.lower() not in MIME_TYPES:
        raise PipelineError("LAN transfer accepts only MOBI or AZW3 Kindle derivatives.")
    manifest = load_manifest(manifest_path)
    output = find_manifest_output(manifest, book)
    actual_hash = sha256_file(book)
    if output.get("sha256") != actual_hash:
        raise PipelineError("Book hash no longer matches the preflight manifest.")
    approval = manifest.get("approval")
    if not approval or approval.get("book_sha256") != actual_hash:
        raise PipelineError("This exact book has not been approved after visual review.")
    if Path(approval.get("book_path", "")).expanduser().resolve() != book:
        raise PipelineError("Approval path does not match the requested LAN file.")
    return book, actual_hash


def build_handler(book: Path, expected_sha256: str):
    book_name = book.name
    encoded_name = quote(book_name)
    book_size = book.stat().st_size
    suffix = book.suffix.lower()
    format_label = "AZW3 / KF8" if suffix == ".azw3" else "MOBI（旧 Kindle 兼容版）"

    class KindleHandler(BaseHTTPRequestHandler):
        server_version = "KindleLocalTransfer/1.1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = unquote(urlsplit(self.path).path)
            if path in {"", "/"}:
                page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kindle 本地传书</title>
</head>
<body>
  <h1>Kindle 本地传书</h1>
  <p><a href="/{encoded_name}">下载《{html.escape(book.stem)}》</a></p>
  <p>格式：{format_label}；大小：{book_size:,} 字节</p>
  <p>下载完成后即可离开此页面。</p>
</body>
</html>
""".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(page)
                return

            if path == "/healthz":
                body = f"OK {expected_sha256}\n".encode("ascii")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=ascii")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == f"/{book_name}":
                if sha256_file(book) != expected_sha256:
                    self.send_error(409, "Book hash changed; transfer refused")
                    return
                self.send_response(200)
                self.send_header("Content-Type", MIME_TYPES[suffix])
                self.send_header("Content-Length", str(book_size))
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename*=UTF-8''{encoded_name}",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    with book.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(64 * 1024), b""):
                            self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            self.send_error(404)

        def log_message(self, format_string: str, *args: object) -> None:
            print(f"{self.address_string()} - {format_string % args}", flush=True)

    return KindleHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--host", required=True, help="Explicit LAN address of this Mac, never 0.0.0.0 by default.")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    try:
        book, actual_hash = validate_approved_book(args.book, args.manifest)
    except PipelineError as exc:
        parser.error(str(exc))
    server = ThreadingHTTPServer((args.host, args.port), build_handler(book, actual_hash))
    print(f"Serving only: {book}", flush=True)
    print(f"Approved SHA-256: {actual_hash}", flush=True)
    print(f"Listening on: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
