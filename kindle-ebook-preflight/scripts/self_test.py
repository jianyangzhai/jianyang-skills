#!/usr/bin/env python3
"""Build local synthetic EPUB fixtures and test the complete safe workflow."""

from __future__ import annotations

import json
import struct
import tempfile
import zipfile
from pathlib import Path

from ebook_pipeline import (
    PipelineError,
    TOOL_IDENTITY,
    approve_book,
    find_tool,
    inspect_epub,
    inspect_mobi_header,
    prepare_book,
    prepare_legacy_mobi,
    record_device_check,
    run_process,
    sha256_file,
    transfer_book,
)
from serve_lan import validate_approved_book


MIMETYPE = b"application/epub+zip"
CONTAINER = b"""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
OPF = b"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:uuid:kindle-preflight-test</dc:identifier>
    <dc:title>Kindle Preflight Test Book</dc:title>
    <dc:creator>Local Test</dc:creator>
    <dc:language>zh-CN</dc:language>
    <meta property="dcterms:modified">2026-08-16T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="style" href="style.css" media-type="text/css"/>
    <item id="cover" href="cover.svg" media-type="image/svg+xml" properties="cover-image"/>
  </manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
NAV = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN">
  <head><title>Contents</title></head>
  <body><nav epub:type="toc"><h1>Contents</h1><ol><li><a href="chapter.xhtml#start">Test Chapter</a></li></ol></nav></body>
</html>
"""
CHAPTER = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN">
  <head><title>Test Chapter</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
  <body><section id="start"><h1>Test Chapter</h1>
  <p>This synthetic public-domain-style fixture contains enough text to test reflow, navigation, metadata, conversion, approval, and verified copying without using a real book.</p>
  <p>这是一段本地生成的测试文本，用于确认中文字符、目录、换行和字号在电子书转换后仍然可以正常阅读。</p>
  </section></body>
</html>
""".encode("utf-8")
BROKEN_CHAPTER = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN">
  <head><title>Broken</title><script type="text/javascript">alert('x')</script></head>
  <body><p id="start">Broken fixture with a missing image and active content.<img src="missing.png" alt="missing"/></p></body>
</html>
"""
CSS = b"body { margin: 0; line-height: 1.5; } img { max-width: 100%; height: auto; }"
COVER = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900" viewBox="0 0 600 900">
  <title>Test cover</title><rect width="600" height="900" fill="#eeeeee"/><text x="60" y="450" font-size="36">Test Book</text>
</svg>
"""


def build_epub(path: Path, *, broken: bool = False) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", OPF, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", NAV, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr(
            "OEBPS/chapter.xhtml",
            BROKEN_CHAPTER if broken else CHAPTER,
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr("OEBPS/style.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/cover.svg", COVER, compress_type=zipfile.ZIP_DEFLATED)


def assert_no_tool_brand_in_ebook(path: Path) -> None:
    terms = [
        TOOL_IDENTITY["author"],
        "jianyangzhai",
        TOOL_IDENTITY["homepage"],
    ]
    payloads = [path.read_bytes()]
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            payloads.extend(archive.read(info) for info in archive.infolist() if info.file_size < 8 * 1024 * 1024)
    for term in terms:
        encoded = [term.encode("utf-8"), term.encode("utf-16le"), term.encode("utf-16be")]
        assert not any(value in payload for value in encoded for payload in payloads), (path, term)
    ebook_meta = find_tool("ebook-meta")
    assert ebook_meta
    metadata = run_process([ebook_meta, str(path)], timeout=60)
    assert metadata.returncode == 0
    shown = (metadata.stdout + metadata.stderr).casefold()
    assert all(term.casefold() not in shown for term in terms), (path, shown)


def main() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="kindle-preflight-self-test-") as tmp:
        root = Path(tmp)
        valid = root / "valid.epub"
        broken = root / "broken.epub"
        unsafe = root / "unsafe.epub"
        build_epub(valid)
        build_epub(broken, broken=True)
        build_epub(unsafe)
        with zipfile.ZipFile(unsafe, "a") as archive:
            archive.writestr("../payload.txt", "unsafe test member")

        valid_report = inspect_epub(valid)
        assert valid_report["status"] in {"PASS", "REVIEW"}, json.dumps(valid_report, indent=2)
        checks.append("valid EPUB inspection")

        broken_report = inspect_epub(broken)
        assert broken_report["status"] == "BLOCKED", json.dumps(broken_report, indent=2)
        assert any(item["code"] == "ACTIVE_CONTENT" for item in broken_report["findings"])
        checks.append("unsafe EPUB blocking")

        unsafe_report = inspect_epub(unsafe)
        assert unsafe_report["status"] == "BLOCKED"
        assert any(item["code"] == "UNSAFE_ARCHIVE_PATH" for item in unsafe_report["findings"])
        checks.append("ZIP path traversal blocking")

        encrypted_mobi = root / "encrypted.mobi"
        mobi_bytes = bytearray(512)
        mobi_bytes[78:82] = struct.pack(">I", 100)
        mobi_bytes[112:114] = struct.pack(">H", 2)
        mobi_bytes[116:120] = b"MOBI"
        encrypted_mobi.write_bytes(mobi_bytes)
        mobi_report = inspect_mobi_header(encrypted_mobi)
        assert mobi_report["status"] == "BLOCKED"
        assert any(item["code"] == "MOBI_DRM" for item in mobi_report["findings"])
        checks.append("MOBI/AZW encryption blocking")

        output_dir = root / "output"
        original_hash = sha256_file(valid)
        try:
            manifest = prepare_book(valid, output_dir)
        except Exception:
            report_path = output_dir / "valid.preflight.md"
            if report_path.is_file():
                print(report_path.read_text(encoding="utf-8"))
            raise
        assert manifest["status"] in {"PASS", "REVIEW"}
        assert "preflight_findings" in manifest
        assert manifest["typography_profile"] == "reader"
        assert manifest["conversion_settings"]["output_profile"] == "kindle_oasis"
        epub = Path(manifest["outputs"]["epub"]["path"])
        azw3 = Path(manifest["outputs"]["azw3"]["path"])
        manifest_path = Path(manifest["manifest_path"])
        assert epub.is_file() and azw3.is_file() and manifest_path.is_file()
        assert sha256_file(valid) == original_hash
        checks.append("EPUB normalization and AZW3 conversion")

        assert manifest["generator"] == TOOL_IDENTITY
        report_text = Path(manifest["report_markdown"]).read_text(encoding="utf-8")
        assert report_text.count("Generated by [kindle-ebook-preflight]") == 1
        assert_no_tool_brand_in_ebook(epub)
        assert_no_tool_brand_in_ebook(azw3)
        checks.append("single report attribution and zero ebook brand injection")

        try:
            prepare_book(valid, output_dir)
        except PipelineError:
            pass
        else:
            raise AssertionError("prepare_book should refuse to overwrite existing outputs")
        checks.append("output overwrite refusal")

        fake_mount = root / "Kindle-Test"
        (fake_mount / "documents").mkdir(parents=True)
        (fake_mount / "system" / "thumbnails").mkdir(parents=True)
        (fake_mount / "amazon-cover-bug").mkdir()
        try:
            transfer_book(
                azw3,
                manifest_path,
                fake_mount,
                execute=False,
                require_volumes=False,
            )
        except PipelineError:
            pass
        else:
            raise AssertionError("transfer should require visual approval")
        checks.append("unapproved transfer blocking")

        approved = approve_book(
            manifest_path,
            azw3,
            "Synthetic cover, TOC, first/middle/last content and font resizing reviewed.",
            True,
        )
        assert approved["approval"]["book_sha256"] == sha256_file(azw3)
        checks.append("hash-bound visual approval")

        device_check = record_device_check(
            manifest_path,
            azw3,
            "opened-ok",
            "Synthetic device result recorded by the test harness.",
            "Kindle-Test",
        )
        assert device_check["result"] == "opened-ok"
        recorded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert recorded_manifest["device_checks"][-1]["book_sha256"] == sha256_file(azw3)
        checks.append("actual-device result recording")

        legacy_dir = root / "legacy-output"
        legacy_manifest = prepare_legacy_mobi(epub, legacy_dir)
        legacy_mobi = Path(legacy_manifest["outputs"]["legacy_mobi"]["path"])
        legacy_manifest_path = Path(legacy_manifest["manifest_path"])
        assert legacy_mobi.is_file()
        try:
            validate_approved_book(legacy_mobi, legacy_manifest_path)
        except PipelineError:
            pass
        else:
            raise AssertionError("LAN serving should require visual approval")
        approve_book(
            legacy_manifest_path,
            legacy_mobi,
            "Synthetic legacy MOBI cover, TOC, content, reflow, and ending reviewed.",
            True,
        )
        served_book, served_hash = validate_approved_book(legacy_mobi, legacy_manifest_path)
        assert served_book == legacy_mobi.resolve() and served_hash == sha256_file(legacy_mobi)
        checks.append("legacy MOBI6 conversion, round-trip inspection, and LAN approval gate")

        try:
            transfer_book(
                epub,
                manifest_path,
                fake_mount,
                execute=False,
                require_volumes=False,
            )
        except PipelineError:
            pass
        else:
            raise AssertionError("legacy direct transfer should reject EPUB")
        checks.append("legacy USB EPUB rejection")

        dry_run = transfer_book(
            azw3,
            manifest_path,
            fake_mount,
            execute=False,
            require_volumes=False,
        )
        assert dry_run["status"] == "DRY_RUN"
        assert not Path(dry_run["destination"]).exists()
        checks.append("default transfer dry-run")

        copied = transfer_book(
            azw3,
            manifest_path,
            fake_mount,
            execute=True,
            require_volumes=False,
        )
        destination = Path(copied["destination"])
        assert copied["status"] == "COPIED_AND_VERIFIED"
        assert "macos_metadata" in copied
        assert "known_xattrs_remaining" in copied["macos_metadata"]
        assert copied["macos_metadata"]["xattr_inspection_method"] in {
            "python-os",
            "xattr-cli",
            "unavailable",
        }
        assert destination.is_file() and sha256_file(destination) == sha256_file(azw3)
        assert copied["library_cover"]["status"] == "INSTALLED_AND_VERIFIED"
        assert len(copied["library_cover"]["targets"]) == 2
        assert all(Path(item["path"]).is_file() for item in copied["library_cover"]["targets"])
        checks.append("atomic book copy, dual-cache cover install, and post-copy hash verification")

    print(json.dumps({"status": "PASS", "checks": checks, "count": len(checks)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
