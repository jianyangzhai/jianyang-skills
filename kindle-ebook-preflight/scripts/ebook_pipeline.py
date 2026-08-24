#!/usr/bin/env python3
"""Local-only ebook preflight, conversion, approval, and Kindle transfer.

The script never downloads books, never removes DRM, never overwrites an input
or destination file, and never copies to a Kindle unless --execute is supplied.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from xml.etree import ElementTree as ET


SUPPORTED_INPUTS = {".epub", ".mobi", ".azw", ".azw3"}
DIRECT_USB_FORMATS = {".azw3", ".mobi", ".pdf", ".txt"}
CALIBRE_DIR = Path("/Applications/calibre.app/Contents/MacOS")
CALIBRE_TOOLS = {"calibre-debug", "ebook-convert", "ebook-meta", "ebook-viewer"}
MAX_ARCHIVE_FILES = 20_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000
SEVERITY_ORDER = {"INFO": 0, "WARN": 1, "ERROR": 2, "BLOCK": 3}
SAFE_FONT_OBFUSCATION = {
    "http://www.idpf.org/2008/embedding",
    "http://ns.adobe.com/pdf/enc#RC",
}
DANGEROUS_TAGS = {"script", "iframe", "object", "embed", "form"}
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "div", "figcaption",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "li",
    "main", "nav", "p", "pre", "section", "td", "th",
}
TOOL_IDENTITY = {
    "name": "kindle-ebook-preflight",
    "version": "1.0.0",
    "author": "Jianyang Zhai",
    "homepage": "https://github.com/jianyangzhai/jianyang-skills",
}


class PipelineError(RuntimeError):
    """Expected user-facing pipeline failure."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def safe_output_stem(value: str) -> str:
    cleaned = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", value, flags=re.UNICODE)
    cleaned = cleaned.strip("._-")[:120]
    return cleaned or "ebook"


def find_tool(name: str) -> str | None:
    # Prefer the signed Calibre application bundle over a same-named executable
    # earlier on PATH. PATH remains a fallback for non-Calibre tools and for
    # installations that intentionally expose Calibre only through CLI links.
    if name in CALIBRE_TOOLS:
        bundled = CALIBRE_DIR / name
        if bundled.is_file():
            return str(bundled)
    return shutil.which(name)


def calibre_environment(config_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["CALIBRE_CONFIG_DIRECTORY"] = str(config_dir)
    return env


def run_process(
    argv: list[str],
    *,
    timeout: int = 300,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def tool_version(name: str) -> dict[str, Any]:
    path = find_tool(name)
    if not path:
        return {"available": False, "path": None, "version": None}
    if name == "ebook-viewer":
        return {
            "available": True,
            "path": path,
            "version": None,
            "note": "GUI viewer is present; doctor does not launch it in the background.",
        }
    flag = "--version"
    try:
        with tempfile.TemporaryDirectory(prefix="kindle-preflight-config-") as tmp:
            result = run_process(
                [path, flag],
                timeout=30,
                env=calibre_environment(Path(tmp)),
            )
        output = clean_text((result.stdout + " " + result.stderr).strip())
        return {
            "available": result.returncode == 0,
            "path": path,
            "version": output[:300] or None,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "path": path, "version": str(exc)}


def new_report(path: Path, detected_format: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "generator": dict(TOOL_IDENTITY),
        "input": {
            "path": str(path.resolve()),
            "format": detected_format,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        },
        "status": "PASS",
        "metadata": {},
        "statistics": {},
        "tools": {},
        "findings": [],
    }


def add_finding(
    report: dict[str, Any],
    severity: str,
    code: str,
    message: str,
    location: str | None = None,
) -> None:
    report["findings"].append(
        {
            "severity": severity,
            "code": code,
            "message": message,
            "location": location,
        }
    )


def finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    levels = {item["severity"] for item in report["findings"]}
    if "BLOCK" in levels:
        report["status"] = "BLOCKED"
    elif "ERROR" in levels:
        report["status"] = "NEEDS_REPAIR"
    elif "WARN" in levels:
        report["status"] = "REVIEW"
    else:
        report["status"] = "PASS"
    report["findings"].sort(
        key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["code"], item.get("location") or "")
    )
    return report


def has_severity(report: dict[str, Any], *levels: str) -> bool:
    wanted = set(levels)
    return any(item["severity"] in wanted for item in report["findings"])


def archive_name_is_safe(name: str) -> bool:
    if not name or name.startswith(("/", "\\")) or "\\" in name:
        return False
    parts = PurePosixPath(name).parts
    return all(part not in {"", ".", ".."} for part in parts)


def resolve_archive_reference(base_member: str, reference: str) -> tuple[str | None, str | None, bool]:
    parsed = urllib.parse.urlsplit(reference.strip())
    if parsed.scheme or parsed.netloc:
        return None, parsed.fragment or None, True
    raw_path = urllib.parse.unquote(parsed.path)
    if not raw_path:
        return base_member, parsed.fragment or None, False
    candidate = posixpath.normpath(posixpath.join(posixpath.dirname(base_member), raw_path))
    if candidate == ".." or candidate.startswith("../") or candidate.startswith("/"):
        return None, parsed.fragment or None, False
    return candidate, parsed.fragment or None, False


def parse_xml_member(
    archive: zipfile.ZipFile,
    member: str,
    report: dict[str, Any],
    *,
    severity: str = "ERROR",
) -> ET.Element | None:
    try:
        raw = archive.read(member)
    except KeyError:
        add_finding(report, severity, "MISSING_XML", "Required XML file is missing.", member)
        return None
    if b"<!ENTITY" in raw.upper():
        add_finding(report, "BLOCK", "XML_ENTITY_DECLARATION", "XML entity declarations are not accepted.", member)
        return None
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        add_finding(report, severity, "MALFORMED_XML", f"XML is not well formed: {exc}", member)
        return None


def extract_blocks(root: ET.Element) -> list[str]:
    blocks: list[str] = []
    for element in root.iter():
        if local_name(element.tag) in BLOCK_TAGS:
            value = clean_text("".join(element.itertext()))
            if value:
                blocks.append(value)
    return blocks


def check_css(
    css_text: str,
    member: str,
    members: set[str],
    report: dict[str, Any],
) -> None:
    lowered = css_text.lower()
    patterns = {
        "CSS_FIXED_POSITION": r"position\s*:\s*(?:fixed|absolute)",
        "CSS_OVERFLOW_HIDDEN": r"overflow\s*:\s*hidden",
        "CSS_FIXED_BODY_SIZE": r"(?:font-size|line-height)\s*:\s*\d{2,}px",
        "CSS_FIXED_WIDTH": r"(?:^|[;{])\s*(?:width|min-width)\s*:\s*\d{3,}px",
        "CSS_WHITE_SPACE_PRE": r"white-space\s*:\s*pre(?:-wrap)?",
    }
    for code, pattern in patterns.items():
        count = len(re.findall(pattern, lowered, flags=re.MULTILINE))
        if count:
            add_finding(
                report,
                "WARN",
                code,
                f"Found {count} potentially rigid CSS declaration(s); inspect on a small Kindle screen.",
                member,
            )

    for match in re.finditer(r"url\(\s*['\"]?([^)'\"]+)", css_text, flags=re.IGNORECASE):
        value = match.group(1).strip()
        target, _, external = resolve_archive_reference(member, value)
        if external:
            add_finding(report, "ERROR", "REMOTE_CSS_RESOURCE", "CSS depends on an external resource.", member)
        elif target and not value.startswith("data:") and target not in members:
            add_finding(report, "ERROR", "BROKEN_CSS_RESOURCE", f"Missing CSS resource: {value}", member)


def run_epubcheck(path: Path, report: dict[str, Any]) -> None:
    tool = find_tool("epubcheck")
    report["tools"]["epubcheck"] = tool_version("epubcheck")
    if not tool:
        add_finding(report, "ERROR", "EPUBCHECK_MISSING", "EPUBCheck is required for a release-quality result.")
        return
    with tempfile.TemporaryDirectory(prefix="kindle-epubcheck-") as tmp:
        output_path = Path(tmp) / "epubcheck.json"
        try:
            result = run_process([tool, str(path), "--json", str(output_path), "--quiet"], timeout=240)
        except (OSError, subprocess.SubprocessError) as exc:
            add_finding(report, "ERROR", "EPUBCHECK_FAILED", f"EPUBCheck could not run: {exc}")
            return
        if not output_path.is_file():
            detail = clean_text((result.stderr or result.stdout)[-1000:])
            add_finding(report, "ERROR", "EPUBCHECK_NO_REPORT", f"EPUBCheck produced no JSON report: {detail}")
            return
        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            add_finding(report, "ERROR", "EPUBCHECK_BAD_REPORT", f"Cannot parse EPUBCheck output: {exc}")
            return

    messages = data.get("messages", []) if isinstance(data, dict) else []
    counts = Counter()
    for message in messages:
        severity_raw = str(message.get("severity") or message.get("type") or "INFO").upper()
        if severity_raw in {"FATAL", "ERROR"}:
            severity = "ERROR"
        elif severity_raw in {"WARNING", "WARN"}:
            severity = "WARN"
        else:
            severity = "INFO"
        counts[severity_raw] += 1
        locations = message.get("locations") or []
        location = None
        if locations and isinstance(locations[0], dict):
            first = locations[0]
            location = str(first.get("path") or first.get("context") or "") or None
            if location and first.get("line"):
                location = f"{location}:{first['line']}"
        code = str(message.get("ID") or message.get("id") or "MESSAGE")
        text = str(message.get("message") or message.get("text") or message)
        add_finding(report, severity, f"EPUBCHECK_{code}", text, location)
    report["statistics"]["epubcheck_messages"] = dict(sorted(counts.items()))
    if result.returncode != 0 and not messages:
        detail = clean_text((result.stderr or result.stdout)[-1000:])
        add_finding(report, "ERROR", "EPUBCHECK_EXIT", f"EPUBCheck exited {result.returncode}: {detail}")


def inspect_epub(path: Path) -> dict[str, Any]:
    report = new_report(path, "epub")
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        add_finding(report, "BLOCK", "INVALID_ZIP", f"EPUB container cannot be opened: {exc}")
        return finalize_report(report)

    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        members = set(names)
        report["statistics"]["archive_files"] = len(infos)
        report["statistics"]["compressed_bytes"] = sum(info.compress_size for info in infos)
        report["statistics"]["uncompressed_bytes"] = sum(info.file_size for info in infos)

        if len(infos) > MAX_ARCHIVE_FILES:
            add_finding(report, "BLOCK", "ARCHIVE_FILE_COUNT", f"Archive has {len(infos)} files; safety limit is {MAX_ARCHIVE_FILES}.")
        if len(names) != len(members):
            add_finding(report, "ERROR", "DUPLICATE_ARCHIVE_NAMES", "Archive contains duplicate member names.")
        for info in infos:
            if not archive_name_is_safe(info.filename):
                add_finding(report, "BLOCK", "UNSAFE_ARCHIVE_PATH", "Archive member path is unsafe.", info.filename)
            if info.file_size > MAX_UNCOMPRESSED_BYTES:
                add_finding(report, "BLOCK", "ARCHIVE_MEMBER_TOO_LARGE", "Archive member exceeds the safety limit.", info.filename)
            ratio = info.file_size / max(info.compress_size, 1)
            if info.file_size > 1024 * 1024 and ratio > MAX_COMPRESSION_RATIO:
                add_finding(report, "BLOCK", "SUSPICIOUS_COMPRESSION", f"Compression ratio {ratio:.0f}:1 is suspicious.", info.filename)
        if report["statistics"]["uncompressed_bytes"] > MAX_UNCOMPRESSED_BYTES:
            add_finding(report, "BLOCK", "ARCHIVE_TOO_LARGE", "Total expanded archive size exceeds 2 GiB.")

        if not infos or infos[0].filename != "mimetype":
            add_finding(report, "ERROR", "MIMETYPE_NOT_FIRST", "The mimetype file must be the first ZIP member.")
        elif infos[0].compress_type != zipfile.ZIP_STORED:
            add_finding(report, "ERROR", "MIMETYPE_COMPRESSED", "The mimetype file must be uncompressed.")
        try:
            mimetype = archive.read("mimetype")
            if mimetype != b"application/epub+zip":
                add_finding(report, "ERROR", "BAD_MIMETYPE", "The mimetype content is invalid.", "mimetype")
        except KeyError:
            add_finding(report, "ERROR", "MISSING_MIMETYPE", "The EPUB has no mimetype member.")

        encryption_root = None
        if "META-INF/encryption.xml" in members:
            encryption_root = parse_xml_member(archive, "META-INF/encryption.xml", report, severity="BLOCK")
        if encryption_root is not None:
            algorithms = {
                element.attrib.get("Algorithm", "")
                for element in encryption_root.iter()
                if local_name(element.tag) == "encryptionmethod"
            }
            unsafe_algorithms = sorted(value for value in algorithms if value and value not in SAFE_FONT_OBFUSCATION)
            if unsafe_algorithms:
                add_finding(
                    report,
                    "BLOCK",
                    "EPUB_ENCRYPTED_CONTENT",
                    "Encrypted publication content is not processed; DRM removal is out of scope.",
                    "META-INF/encryption.xml",
                )
            elif algorithms:
                add_finding(report, "INFO", "FONT_OBFUSCATION", "EPUB uses standard font obfuscation.", "META-INF/encryption.xml")
        if "META-INF/rights.xml" in members:
            add_finding(report, "WARN", "RIGHTS_METADATA", "Publication contains rights-management metadata; review before conversion.", "META-INF/rights.xml")

        container_root = parse_xml_member(archive, "META-INF/container.xml", report)
        if container_root is None:
            run_epubcheck(path, report)
            return finalize_report(report)
        rootfiles = [element for element in container_root.iter() if local_name(element.tag) == "rootfile"]
        if not rootfiles:
            add_finding(report, "ERROR", "NO_ROOTFILE", "container.xml does not identify an OPF package document.")
            run_epubcheck(path, report)
            return finalize_report(report)
        opf_path = rootfiles[0].attrib.get("full-path", "")
        if not archive_name_is_safe(opf_path) or opf_path not in members:
            add_finding(report, "ERROR", "BAD_ROOTFILE", "The OPF package path is missing or unsafe.", opf_path)
            run_epubcheck(path, report)
            return finalize_report(report)
        opf_root = parse_xml_member(archive, opf_path, report)
        if opf_root is None:
            run_epubcheck(path, report)
            return finalize_report(report)

        metadata_values: dict[str, list[str]] = defaultdict(list)
        for element in opf_root.iter():
            key = local_name(element.tag)
            if key in {"title", "creator", "language", "identifier", "publisher"}:
                value = clean_text("".join(element.itertext()))
                if value:
                    metadata_values[key].append(value)
        report["metadata"] = {key: values for key, values in sorted(metadata_values.items())}
        for required in ("title", "creator", "language"):
            if not metadata_values.get(required):
                add_finding(report, "WARN", f"MISSING_{required.upper()}", f"Metadata field '{required}' is missing.", opf_path)

        manifest: dict[str, dict[str, str]] = {}
        for element in opf_root.iter():
            if local_name(element.tag) != "item":
                continue
            item_id = element.attrib.get("id", "")
            href = element.attrib.get("href", "")
            target, _, external = resolve_archive_reference(opf_path, href)
            if external or not target:
                add_finding(report, "ERROR", "BAD_MANIFEST_HREF", f"Manifest item has unsupported href: {href}", opf_path)
                continue
            manifest[item_id] = {
                "href": href,
                "path": target,
                "media_type": element.attrib.get("media-type", ""),
                "properties": element.attrib.get("properties", ""),
            }
            if target not in members:
                add_finding(report, "ERROR", "MISSING_MANIFEST_ITEM", f"Manifest resource is missing: {href}", opf_path)

        spine_ids = [
            element.attrib.get("idref", "")
            for element in opf_root.iter()
            if local_name(element.tag) == "itemref"
        ]
        if not spine_ids:
            add_finding(report, "ERROR", "EMPTY_SPINE", "The reading order is empty.", opf_path)
        for item_id in spine_ids:
            if item_id not in manifest:
                add_finding(report, "ERROR", "BROKEN_SPINE", f"Spine references unknown item: {item_id}", opf_path)

        nav_items = [item for item in manifest.values() if "nav" in item["properties"].split()]
        ncx_items = [item for item in manifest.values() if item["media_type"] == "application/x-dtbncx+xml"]
        if not nav_items and not ncx_items:
            add_finding(report, "ERROR", "MISSING_TOC", "No EPUB navigation document or NCX table of contents was found.")
        cover_items = [item for item in manifest.values() if "cover-image" in item["properties"].split()]
        if not cover_items:
            cover_ids = {
                element.attrib.get("content", "")
                for element in opf_root.iter()
                if local_name(element.tag) == "meta" and element.attrib.get("name", "").lower() == "cover"
            }
            cover_items = [manifest[item_id] for item_id in cover_ids if item_id in manifest]
        if not cover_items:
            add_finding(report, "WARN", "MISSING_COVER", "No cover image is identified in package metadata.")

        parsed_roots: dict[str, ET.Element] = {}
        ids_by_member: dict[str, set[str]] = {}
        blocks_by_member: dict[str, list[str]] = {}
        links: list[tuple[str, str, str, str]] = []
        xhtml_items = [
            item for item in manifest.values()
            if item["media_type"] in {"application/xhtml+xml", "text/html"} and item["path"] in members
        ]
        for item in xhtml_items:
            member = item["path"]
            root = parse_xml_member(archive, member, report)
            if root is None:
                continue
            parsed_roots[member] = root
            ids_by_member[member] = {
                element.attrib["id"] for element in root.iter() if element.attrib.get("id")
            }
            blocks = extract_blocks(root)
            blocks_by_member[member] = blocks
            visible_text = "\n".join(blocks) or clean_text("".join(root.itertext()))
            if member in {manifest[item_id]["path"] for item_id in spine_ids if item_id in manifest}:
                properties = item["properties"].split()
                if len(visible_text) < 80 and "nav" not in properties and "cover-image" not in properties and "cover" not in member.lower():
                    add_finding(report, "WARN", "SHORT_SPINE_DOCUMENT", f"Reading-order document has only {len(visible_text)} visible characters.", member)
            replacement_count = visible_text.count("\ufffd")
            if replacement_count:
                add_finding(report, "ERROR", "REPLACEMENT_CHARACTERS", f"Found {replacement_count} Unicode replacement character(s).", member)
            if "\x00" in visible_text:
                add_finding(report, "ERROR", "NULL_CHARACTERS", "Visible text contains null characters.", member)
            zero_width = sum(visible_text.count(char) for char in ("\u200b", "\u200c", "\u200d", "\ufeff"))
            if zero_width > 20:
                add_finding(report, "WARN", "ZERO_WIDTH_CHARACTERS", f"Found {zero_width} zero-width characters.", member)
            if re.search(r"(?:[\u3400-\u9fff]\s+){6,}[\u3400-\u9fff]", visible_text):
                add_finding(report, "WARN", "SPACED_CJK_TEXT", "Detected unusually spaced Chinese text; inspect for OCR/layout damage.", member)

            raw = archive.read(member).decode("utf-8", errors="replace")
            if len(re.findall(r"<br\b[^>]*>\s*(?:<br\b[^>]*>\s*){2,}", raw, flags=re.IGNORECASE)):
                add_finding(report, "WARN", "EXCESSIVE_BREAKS", "Found runs of three or more line breaks.", member)
            style_text = "\n".join(element.attrib.get("style", "") for element in root.iter() if element.attrib.get("style"))
            if style_text:
                check_css(style_text, member, members, report)

            for element in root.iter():
                tag = local_name(element.tag)
                if tag in DANGEROUS_TAGS:
                    add_finding(report, "BLOCK", "ACTIVE_CONTENT", f"Active/interactive element <{tag}> is not accepted for this reading workflow.", member)
                for attribute in ("href", "src", "poster", "data"):
                    value = element.attrib.get(attribute)
                    if value:
                        links.append((member, tag, attribute, value))

        for member, tag, attribute, value in links:
            parsed = urllib.parse.urlsplit(value.strip())
            if parsed.scheme.lower() == "javascript":
                add_finding(report, "BLOCK", "JAVASCRIPT_LINK", "javascript: links are not accepted.", member)
                continue
            target, fragment, external = resolve_archive_reference(member, value)
            if external:
                if tag != "a" or attribute != "href":
                    add_finding(report, "ERROR", "REMOTE_RESOURCE", f"Embedded resource is remote: {value}", member)
                continue
            if target and target not in members:
                add_finding(report, "ERROR", "BROKEN_INTERNAL_LINK", f"Missing internal target: {value}", member)
            elif target and fragment and target in ids_by_member and fragment not in ids_by_member[target]:
                add_finding(report, "WARN", "BROKEN_FRAGMENT", f"Missing fragment target: {value}", member)

        css_items = [item for item in manifest.values() if item["media_type"] == "text/css" and item["path"] in members]
        for item in css_items:
            css_text = archive.read(item["path"]).decode("utf-8", errors="replace")
            if "\ufffd" in css_text:
                add_finding(report, "ERROR", "CSS_DECODE_DAMAGE", "CSS contains Unicode replacement characters.", item["path"])
            check_css(css_text, item["path"], members, report)

        block_occurrences: Counter[str] = Counter()
        block_documents: dict[str, set[str]] = defaultdict(set)
        for member, blocks in blocks_by_member.items():
            for block in set(blocks):
                if 4 <= len(block) <= 80:
                    block_occurrences[block] += 1
                    block_documents[block].add(member)
        repeated = [
            block for block, count in block_occurrences.most_common()
            if count >= 3 and len(block_documents[block]) >= 3
        ][:10]
        if repeated:
            add_finding(
                report,
                "WARN",
                "REPEATED_SHORT_BLOCKS",
                "Potential repeated page headers/footers: " + " | ".join(repeated),
            )

        toc_entries = 0
        for item in nav_items:
            root = parsed_roots.get(item["path"])
            if root is not None:
                toc_entries += sum(1 for element in root.iter() if local_name(element.tag) == "a")
        for item in ncx_items:
            root = parse_xml_member(archive, item["path"], report)
            if root is not None:
                toc_entries += sum(1 for element in root.iter() if local_name(element.tag) == "navpoint")
        report["statistics"].update(
            {
                "manifest_items": len(manifest),
                "spine_items": len(spine_ids),
                "xhtml_items": len(xhtml_items),
                "toc_entries": toc_entries,
                "visible_characters": sum(len("\n".join(blocks)) for blocks in blocks_by_member.values()),
            }
        )
        if toc_entries == 0:
            add_finding(report, "ERROR", "EMPTY_TOC", "The table of contents has no entries.")

    run_epubcheck(path, report)
    return finalize_report(report)


def inspect_mobi_header(path: Path) -> dict[str, Any]:
    report = new_report(path, path.suffix.lower().lstrip("."))
    with path.open("rb") as handle:
        header = handle.read(4096)
    if header.startswith((b"TPZ", b"TOPAZ")):
        add_finding(report, "BLOCK", "TOPAZ_FORMAT", "Topaz/AZW1 content is not supported and is often DRM-protected.")
        return finalize_report(report)
    if len(header) < 96:
        add_finding(report, "BLOCK", "TRUNCATED_MOBI", "File is too small to contain a valid MOBI/AZW header.")
        return finalize_report(report)
    try:
        first_record_offset = struct.unpack(">I", header[78:82])[0]
    except struct.error:
        add_finding(report, "BLOCK", "INVALID_MOBI_HEADER", "Cannot read the Palm database record table.")
        return finalize_report(report)
    if first_record_offset + 18 > len(header):
        with path.open("rb") as handle:
            header = handle.read(first_record_offset + 128)
    if first_record_offset + 18 > len(header):
        add_finding(report, "BLOCK", "INVALID_MOBI_OFFSET", "First MOBI record is outside the readable header.")
        return finalize_report(report)
    encryption_type = struct.unpack(">H", header[first_record_offset + 12:first_record_offset + 14])[0]
    mobi_magic = header[first_record_offset + 16:first_record_offset + 20]
    report["statistics"]["mobi_encryption_type"] = encryption_type
    report["statistics"]["mobi_magic"] = mobi_magic.decode("ascii", errors="replace")
    if encryption_type != 0:
        add_finding(
            report,
            "BLOCK",
            "MOBI_DRM",
            f"MOBI/AZW encryption type is {encryption_type}; DRM removal is out of scope.",
        )
    if mobi_magic != b"MOBI":
        add_finding(report, "WARN", "UNEXPECTED_MOBI_MAGIC", "Expected MOBI marker was not found at the standard offset.")
    return finalize_report(report)


def inspect_book(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise PipelineError(f"Input file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_INPUTS:
        raise PipelineError(f"Unsupported input format: {suffix}; expected one of {sorted(SUPPORTED_INPUTS)}")
    if suffix == ".epub":
        return inspect_epub(path)

    report = inspect_mobi_header(path)
    if has_severity(report, "BLOCK"):
        return report
    converter = find_tool("ebook-convert")
    report["tools"]["ebook_convert"] = tool_version("ebook-convert")
    if not converter:
        add_finding(report, "ERROR", "CALIBRE_MISSING", "Calibre ebook-convert is required to inspect MOBI/AZW content.")
        return finalize_report(report)
    with tempfile.TemporaryDirectory(prefix="kindle-inspect-") as tmp:
        temp_dir = Path(tmp)
        converted = temp_dir / "inspection.epub"
        config_dir = temp_dir / "calibre-config"
        config_dir.mkdir()
        try:
            result = run_process(
                [converter, str(path), str(converted), "--output-profile", "kindle", "--preserve-cover-aspect-ratio"],
                timeout=600,
                env=calibre_environment(config_dir),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            add_finding(report, "ERROR", "CALIBRE_INSPECTION_FAILED", f"Temporary EPUB conversion failed: {exc}")
            return finalize_report(report)
        if result.returncode != 0 or not converted.is_file():
            detail = clean_text((result.stderr or result.stdout)[-1500:])
            add_finding(report, "ERROR", "CALIBRE_INSPECTION_FAILED", f"Temporary EPUB conversion failed: {detail}")
            return finalize_report(report)
        epub_report = inspect_epub(converted)
    report["metadata"] = epub_report["metadata"]
    report["statistics"]["temporary_epub"] = epub_report["statistics"]
    report["tools"].update(epub_report["tools"])
    for finding in epub_report["findings"]:
        copied = dict(finding)
        copied["location"] = f"temporary EPUB: {finding['location']}" if finding.get("location") else "temporary EPUB"
        report["findings"].append(copied)
    add_finding(report, "INFO", "TEMPORARY_CONVERSION", "MOBI/AZW content was converted to a temporary EPUB for structural inspection.")
    return finalize_report(report)


def render_report_markdown(report: dict[str, Any], title: str = "Ebook preflight report") -> str:
    lines = [f"# {title}", "", f"- Status: **{report.get('status', 'UNKNOWN')}**", f"- Generated: `{report.get('created_at', '')}`"]
    source = report.get("input", {})
    if source:
        lines.extend(
            [
                f"- Source: `{source.get('path', '')}`",
                f"- SHA-256: `{source.get('sha256', '')}`",
                f"- Size: {source.get('bytes', 0):,} bytes",
            ]
        )
    metadata = report.get("metadata") or {}
    if metadata:
        lines.extend(["", "## Metadata", ""])
        for key, value in metadata.items():
            shown = ", ".join(value) if isinstance(value, list) else str(value)
            lines.append(f"- {key}: {shown}")
    outputs = report.get("outputs") or {}
    if outputs:
        lines.extend(["", "## Outputs", ""])
        for key, value in outputs.items():
            lines.append(f"- {key}: `{value['path']}` (`{value['sha256']}`, {value['bytes']:,} bytes)")
    lines.extend(["", "## Findings", ""])
    findings = report.get("findings") or []
    if not findings:
        lines.append("- No findings.")
    else:
        for finding in findings:
            location = f" — `{finding['location']}`" if finding.get("location") else ""
            lines.append(f"- **{finding['severity']} {finding['code']}**: {finding['message']}{location}")
    preflight_findings = report.get("preflight_findings")
    if preflight_findings is not None and preflight_findings != findings:
        lines.extend(["", "## Findings before normalization", ""])
        if not preflight_findings:
            lines.append("- No findings before normalization.")
        else:
            for finding in preflight_findings:
                location = f" — `{finding['location']}`" if finding.get("location") else ""
                lines.append(f"- **{finding['severity']} {finding['code']}**: {finding['message']}{location}")
    approval = report.get("approval")
    lines.extend(["", "## Transfer approval", ""])
    if approval:
        lines.append(f"Approved at `{approval['approved_at']}` for `{approval['book_sha256']}`. Note: {approval['note']}")
    else:
        lines.append("Not approved. Complete visual review before approving transfer.")
    device_checks = report.get("device_checks") or []
    lines.extend(["", "## Actual Kindle checks", ""])
    if not device_checks:
        lines.append("No actual-device result has been recorded.")
    else:
        for check in device_checks:
            model = f" on {check['model']}" if check.get("model") else ""
            lines.append(
                f"- `{check['confirmed_at']}`: **{check['result']}**{model}; "
                f"evidence `{check['evidence']}`. {check['note']}"
            )
    generator = report.get("generator") or TOOL_IDENTITY
    lines.extend(
        [
            "",
            "---",
            (
                f"Generated by [{generator['name']}]({generator['homepage']}) "
                f"v{generator['version']} · {generator['author']}"
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_copy_no_overwrite(source: Path, destination: Path) -> None:
    if destination.exists():
        raise PipelineError(f"Refusing to overwrite existing file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.partial")
    try:
        with source.open("rb") as src, temp.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_replace_file(source: Path, destination: Path) -> None:
    """Atomically install a verified auxiliary file, allowing a backed-up replacement."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.partial")
    try:
        with source.open("rb") as src, temp.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()


def clear_transfer_macos_metadata(destination: Path, *, sidecar_preexisting: bool) -> dict[str, Any]:
    """Remove macOS-only metadata created with a new Kindle transfer.

    FAT volumes store extended attributes in `._` AppleDouble files. Strip only
    known macOS metadata from the newly created destination and never remove a
    sidecar that existed before this transfer.
    """
    removable = {
        "com.apple.FinderInfo",
        "com.apple.ResourceFork",
        "com.apple.macl",
        "com.apple.provenance",
        "com.apple.quarantine",
    }
    removed: set[str] = set()
    xattr_tool = find_tool("xattr")
    inspection_method = "python-os"
    try:
        for name in os.listxattr(destination):
            if name in removable:
                os.removexattr(destination, name)
                removed.add(name)
    except (AttributeError, OSError):
        # Some macOS Python builds omit the xattr APIs. Fall back to Apple's
        # CLI rather than importing an extra package solely for USB cleanup.
        inspection_method = "xattr-cli"
        if xattr_tool:
            try:
                listed = subprocess.run(
                    [xattr_tool, str(destination)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if listed.returncode == 0:
                    for name in listed.stdout.splitlines():
                        name = name.strip()
                        if name in removable:
                            deleted = subprocess.run(
                                [xattr_tool, "-d", name, str(destination)],
                                capture_output=True,
                                text=True,
                                timeout=30,
                                check=False,
                            )
                            if deleted.returncode == 0:
                                removed.add(name)
            except (OSError, subprocess.SubprocessError):
                inspection_method = "unavailable"
        else:
            inspection_method = "unavailable"
    sidecar = destination.with_name(f"._{destination.name}")
    sidecar_removed = False
    if not sidecar_preexisting and sidecar.is_file():
        sidecar.unlink()
        sidecar_removed = True
    remaining: set[str] = set()
    try:
        remaining.update(name for name in os.listxattr(destination) if name in removable)
    except (AttributeError, OSError):
        if xattr_tool:
            try:
                relisted = subprocess.run(
                    [xattr_tool, str(destination)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if relisted.returncode == 0:
                    remaining.update(
                        name.strip()
                        for name in relisted.stdout.splitlines()
                        if name.strip() in removable
                    )
            except (OSError, subprocess.SubprocessError):
                pass
    return {
        "xattrs_removed": sorted(removed),
        "known_xattrs_remaining": sorted(remaining),
        "xattr_inspection_method": inspection_method,
        "appledouble_sidecar": str(sidecar),
        "appledouble_sidecar_preexisting": sidecar_preexisting,
        "appledouble_sidecar_removed": sidecar_removed,
    }


def save_manifest(manifest: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    manifest.setdefault("generator", dict(TOOL_IDENTITY))
    manifest["manifest_path"] = str(json_path.resolve())
    manifest["report_markdown"] = str(markdown_path.resolve())
    atomic_write_text(json_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(markdown_path, render_report_markdown(manifest, "Kindle ebook preflight"))


def prepare_book(
    source: Path,
    output_dir: Path,
    *,
    profile: str = "kindle_oasis",
    title: str | None = None,
    authors: str | None = None,
    language: str | None = None,
    cover: Path | None = None,
    typography_profile: str = "reader",
    output_stem: str | None = None,
) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    cover = cover.expanduser().resolve() if cover is not None else None
    if cover is not None and not cover.is_file():
        raise PipelineError(f"Cover image does not exist: {cover}")
    if typography_profile not in {"preserve", "reader"}:
        raise PipelineError("Typography profile must be 'preserve' or 'reader'.")
    skill_root = Path(__file__).resolve().parent.parent
    if output_dir == source.parent:
        raise PipelineError("Output directory must be separate from the source directory.")
    try:
        output_dir.relative_to(skill_root)
    except ValueError:
        pass
    else:
        raise PipelineError("Output directory must be outside the Skill package.")
    preflight = inspect_book(source)
    stem = safe_output_stem(output_stem or source.stem)
    json_path = output_dir / f"{stem}.preflight.json"
    markdown_path = output_dir / f"{stem}.preflight.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    for candidate in (json_path, markdown_path):
        if candidate.exists():
            raise PipelineError(f"Refusing to overwrite existing report: {candidate}")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_at": utc_now(),
        "input": preflight["input"],
        "status": preflight["status"],
        "metadata": preflight.get("metadata", {}),
        "statistics": {"preflight": preflight.get("statistics", {})},
        "tools": preflight.get("tools", {}),
        "preflight_findings": preflight["findings"],
        "findings": preflight["findings"],
        "outputs": {},
        "postflight": None,
        "approval": None,
        "transfers": [],
        "device_checks": [],
        "typography_profile": typography_profile,
        "conversion_settings": {
            "output_profile": profile,
            "typography_profile": typography_profile,
            "metadata_overrides": {
                "title": title,
                "authors": authors,
                "language": language,
                "cover": (
                    {"path": str(cover), "bytes": cover.stat().st_size, "sha256": sha256_file(cover)}
                    if cover is not None else None
                ),
            },
        },
    }
    if has_severity(preflight, "BLOCK"):
        save_manifest(manifest, json_path, markdown_path)
        raise PipelineError(f"Input is blocked. Review {markdown_path}")

    converter = find_tool("ebook-convert")
    if not converter:
        add_finding(manifest, "ERROR", "CALIBRE_MISSING", "Calibre ebook-convert is required for preparation.")
        finalize_report(manifest)
        save_manifest(manifest, json_path, markdown_path)
        raise PipelineError(f"Calibre is missing. Review {markdown_path}")

    epub_destination = output_dir / f"{stem}.kindle.epub"
    azw3_destination = output_dir / f"{stem}.kindle.azw3"
    for candidate in (epub_destination, azw3_destination, json_path, markdown_path):
        if candidate.exists():
            raise PipelineError(f"Refusing to overwrite existing output: {candidate}")

    with tempfile.TemporaryDirectory(prefix="kindle-prepare-") as tmp:
        temp_dir = Path(tmp)
        config_dir = temp_dir / "calibre-config"
        config_dir.mkdir()
        normalized_epub = temp_dir / "normalized.epub"
        final_azw3 = temp_dir / "kindle.azw3"
        common = ["--output-profile", profile, "--pretty-print"]
        if typography_profile == "reader":
            common.extend(
                [
                    "--change-justification",
                    "left",
                    "--filter-css",
                    "font-family,line-height,letter-spacing,word-spacing",
                ]
            )
        if title:
            common.extend(["--title", title])
        if authors:
            common.extend(["--authors", authors])
        if language:
            common.extend(["--language", language])
        if cover is not None:
            common.extend(["--cover", str(cover)])
        result = run_process(
            [
                converter,
                str(source),
                str(normalized_epub),
                *common,
                "--preserve-cover-aspect-ratio",
                "--epub-version",
                "3",
            ],
            timeout=900,
            env=calibre_environment(config_dir),
        )
        if result.returncode != 0 or not normalized_epub.is_file():
            detail = clean_text((result.stderr or result.stdout)[-2000:])
            add_finding(manifest, "ERROR", "EPUB_NORMALIZATION_FAILED", f"Calibre normalization failed: {detail}")
            finalize_report(manifest)
            save_manifest(manifest, json_path, markdown_path)
            raise PipelineError(f"Normalization failed. Review {markdown_path}")

        postflight = inspect_epub(normalized_epub)
        manifest["postflight"] = postflight
        manifest["statistics"]["postflight"] = postflight.get("statistics", {})
        manifest["metadata"] = postflight.get("metadata", {})
        manifest["tools"].update(postflight.get("tools", {}))
        manifest["findings"] = postflight["findings"]
        manifest["status"] = postflight["status"]
        if has_severity(postflight, "BLOCK", "ERROR"):
            save_manifest(manifest, json_path, markdown_path)
            raise PipelineError(f"Normalized EPUB still has blocking/error findings. Review {markdown_path}")

        result = run_process(
            [converter, str(normalized_epub), str(final_azw3), *common],
            timeout=900,
            env=calibre_environment(config_dir),
        )
        if result.returncode != 0 or not final_azw3.is_file():
            detail = clean_text((result.stderr or result.stdout)[-2000:])
            add_finding(manifest, "ERROR", "AZW3_CONVERSION_FAILED", f"Calibre AZW3 conversion failed: {detail}")
            finalize_report(manifest)
            save_manifest(manifest, json_path, markdown_path)
            raise PipelineError(f"AZW3 conversion failed. Review {markdown_path}")
        azw3_header = inspect_mobi_header(final_azw3)
        if has_severity(azw3_header, "BLOCK", "ERROR"):
            manifest["findings"].extend(azw3_header["findings"])
            finalize_report(manifest)
            save_manifest(manifest, json_path, markdown_path)
            raise PipelineError(f"Generated AZW3 failed validation. Review {markdown_path}")

        metadata_tool = find_tool("ebook-meta")
        if metadata_tool:
            meta_result = run_process(
                [metadata_tool, str(final_azw3)],
                timeout=120,
                env=calibre_environment(config_dir),
            )
            if meta_result.returncode != 0:
                add_finding(manifest, "ERROR", "AZW3_METADATA_FAILED", "Calibre could not read metadata from generated AZW3.")
                finalize_report(manifest)
                save_manifest(manifest, json_path, markdown_path)
                raise PipelineError(f"Generated AZW3 metadata check failed. Review {markdown_path}")

        atomic_copy_no_overwrite(normalized_epub, epub_destination)
        atomic_copy_no_overwrite(final_azw3, azw3_destination)

    manifest["outputs"] = {
        "epub": {
            "path": str(epub_destination),
            "bytes": epub_destination.stat().st_size,
            "sha256": sha256_file(epub_destination),
            "use": "master / Send to Kindle / visual preview",
        },
        "azw3": {
            "path": str(azw3_destination),
            "bytes": azw3_destination.stat().st_size,
            "sha256": sha256_file(azw3_destination),
            "use": "legacy USB mass-storage Kindle",
        },
    }
    finalize_report(manifest)
    save_manifest(manifest, json_path, markdown_path)
    return manifest


def prepare_legacy_mobi(
    source: Path,
    output_dir: Path,
    *,
    profile: str = "kindle_oasis",
) -> dict[str, Any]:
    """Create an old-style MOBI6 derivative and reject broken round trips."""
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    skill_root = Path(__file__).resolve().parent.parent
    if source.suffix.lower() != ".epub":
        raise PipelineError("Legacy MOBI preparation requires the reviewed normalized EPUB as input.")
    if output_dir == source.parent:
        raise PipelineError("Output directory must be separate from the source directory.")
    try:
        output_dir.relative_to(skill_root)
    except ValueError:
        pass
    else:
        raise PipelineError("Output directory must be outside the Skill package.")

    preflight = inspect_epub(source)
    stem = safe_output_stem(source.stem)
    mobi_destination = output_dir / f"{stem}.legacy.mobi"
    json_path = output_dir / f"{stem}.legacy.preflight.json"
    markdown_path = output_dir / f"{stem}.legacy.preflight.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    for candidate in (mobi_destination, json_path, markdown_path):
        if candidate.exists():
            raise PipelineError(f"Refusing to overwrite existing output: {candidate}")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_at": utc_now(),
        "input": preflight["input"],
        "status": preflight["status"],
        "metadata": preflight.get("metadata", {}),
        "statistics": {"source_epub": preflight.get("statistics", {})},
        "tools": preflight.get("tools", {}),
        "findings": preflight["findings"],
        "outputs": {},
        "postflight": None,
        "approval": None,
        "transfers": [],
        "device_checks": [],
    }
    if has_severity(preflight, "BLOCK", "ERROR"):
        save_manifest(manifest, json_path, markdown_path)
        raise PipelineError(f"Source EPUB is not eligible for legacy conversion. Review {markdown_path}")

    converter = find_tool("ebook-convert")
    if not converter:
        add_finding(manifest, "ERROR", "CALIBRE_MISSING", "Calibre ebook-convert is required for legacy MOBI preparation.")
        finalize_report(manifest)
        save_manifest(manifest, json_path, markdown_path)
        raise PipelineError(f"Calibre is missing. Review {markdown_path}")

    with tempfile.TemporaryDirectory(prefix="kindle-legacy-mobi-") as tmp:
        temp_dir = Path(tmp)
        config_dir = temp_dir / "calibre-config"
        config_dir.mkdir()
        temp_mobi = temp_dir / "legacy.mobi"
        result = run_process(
            [
                converter,
                str(source),
                str(temp_mobi),
                "--output-profile",
                profile,
                "--mobi-file-type",
                "old",
                "--mobi-toc-at-start",
                "--max-toc-links",
                "200",
            ],
            timeout=900,
            env=calibre_environment(config_dir),
        )
        if result.returncode != 0 or not temp_mobi.is_file():
            detail = clean_text((result.stderr or result.stdout)[-2000:])
            add_finding(manifest, "ERROR", "LEGACY_MOBI_CONVERSION_FAILED", f"Calibre legacy MOBI conversion failed: {detail}")
            finalize_report(manifest)
            save_manifest(manifest, json_path, markdown_path)
            raise PipelineError(f"Legacy MOBI conversion failed. Review {markdown_path}")

        postflight = inspect_book(temp_mobi)
        manifest["postflight"] = postflight
        manifest["statistics"]["legacy_mobi"] = postflight.get("statistics", {})
        manifest["metadata"] = postflight.get("metadata", {})
        manifest["tools"].update(postflight.get("tools", {}))
        manifest["findings"] = postflight["findings"]
        manifest["status"] = postflight["status"]
        if has_severity(postflight, "BLOCK", "ERROR"):
            save_manifest(manifest, json_path, markdown_path)
            raise PipelineError(
                "Legacy MOBI failed its MOBI-to-EPUB round-trip inspection. "
                f"Do not transfer it; review {markdown_path}"
            )
        atomic_copy_no_overwrite(temp_mobi, mobi_destination)

    manifest["outputs"] = {
        "legacy_mobi": {
            "path": str(mobi_destination),
            "bytes": mobi_destination.stat().st_size,
            "sha256": sha256_file(mobi_destination),
            "use": "local USB or explicitly authorized LAN download for an old Kindle",
        }
    }
    save_manifest(manifest, json_path, markdown_path)
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Cannot read manifest {path}: {exc}") from exc
    if value.get("schema_version") != 1:
        raise PipelineError("Unsupported manifest schema version.")
    return value


def find_manifest_output(manifest: dict[str, Any], book: Path) -> dict[str, Any]:
    book_resolved = book.expanduser().resolve()
    for output in manifest.get("outputs", {}).values():
        if Path(output["path"]).resolve() == book_resolved:
            return output
    raise PipelineError("Book is not an output recorded in this manifest.")


def approve_book(manifest_path: Path, book: Path, note: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise PipelineError("Approval requires --confirm-reviewed after an actual visual review.")
    manifest_path = manifest_path.expanduser().resolve()
    manifest = load_manifest(manifest_path)
    output = find_manifest_output(manifest, book)
    book = book.expanduser().resolve()
    actual_hash = sha256_file(book)
    if actual_hash != output["sha256"]:
        raise PipelineError("Book hash no longer matches the preflight manifest.")
    if manifest.get("status") not in {"PASS", "REVIEW"}:
        raise PipelineError(f"Manifest status {manifest.get('status')} is not eligible for approval.")
    manifest["approval"] = {
        "approved_at": utc_now(),
        "book_path": str(book),
        "book_sha256": actual_hash,
        "note": note.strip() or "Visual review completed.",
    }
    markdown_path = Path(manifest.get("report_markdown") or manifest_path.with_suffix(".md"))
    save_manifest(manifest, manifest_path, markdown_path)
    return manifest


def record_device_check(
    manifest_path: Path,
    book: Path,
    result: str,
    note: str,
    model: str | None = None,
) -> dict[str, Any]:
    """Record an explicit user-reported result from the actual Kindle."""
    manifest_path = manifest_path.expanduser().resolve()
    manifest = load_manifest(manifest_path)
    output = find_manifest_output(manifest, book)
    book = book.expanduser().resolve()
    actual_hash = sha256_file(book)
    if actual_hash != output["sha256"]:
        raise PipelineError("Book hash no longer matches the preflight manifest.")
    approval = manifest.get("approval")
    if not approval or approval.get("book_sha256") != actual_hash:
        raise PipelineError("This exact book has not been approved after visual review.")
    if not note.strip():
        raise PipelineError("Device check requires a concrete user-reported note.")
    event = {
        "confirmed_at": utc_now(),
        "result": result,
        "evidence": "user_report",
        "book_path": str(book),
        "book_sha256": actual_hash,
        "model": model.strip() if model else None,
        "note": note.strip(),
    }
    manifest.setdefault("device_checks", []).append(event)
    markdown_path = Path(manifest.get("report_markdown") or manifest_path.with_suffix(".md"))
    save_manifest(manifest, manifest_path, markdown_path)
    return event


def detect_kindle_mounts(volumes_root: Path = Path("/Volumes")) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not volumes_root.is_dir():
        return candidates
    for volume in sorted(volumes_root.iterdir(), key=lambda item: item.name.lower()):
        if not volume.is_dir() or volume.is_symlink():
            continue
        documents = volume / "documents"
        signature = "kindle" in volume.name.lower() or (volume / "system").is_dir()
        if documents.is_dir() and signature:
            usage = shutil.disk_usage(volume)
            candidates.append(
                {
                    "mount": str(volume.resolve()),
                    "documents": str(documents.resolve()),
                    "free_bytes": usage.free,
                    "volume_name": volume.name,
                }
            )
    return candidates


def validate_kindle_mount(mount: Path, *, require_volumes: bool = True) -> tuple[Path, Path]:
    mount = mount.expanduser().resolve()
    if require_volumes:
        volumes = Path("/Volumes").resolve()
        try:
            mount.relative_to(volumes)
        except ValueError as exc:
            raise PipelineError("Kindle mount must be an explicit child of /Volumes.") from exc
    documents = mount / "documents"
    signature = "kindle" in mount.name.lower() or (mount / "system").is_dir()
    if not mount.is_dir() or not documents.is_dir() or not signature:
        raise PipelineError("Target does not look like a mounted Kindle with a documents directory.")
    if mount.is_symlink() or documents.is_symlink():
        raise PipelineError("Symlinked mount/documents paths are not accepted.")
    return mount, documents


def generate_kindle_thumbnail(book: Path, output_dir: Path) -> dict[str, Any] | None:
    """Generate a Calibre-compatible library thumbnail for Kindle ebook formats."""
    if book.suffix.lower() not in {".azw", ".azw3", ".mobi"}:
        return None
    calibre_debug = find_tool("calibre-debug")
    if not calibre_debug:
        raise PipelineError("Calibre calibre-debug is required to generate the Kindle library cover.")
    helper = Path(__file__).resolve().parent / "generate_kindle_thumbnail.py"
    if not helper.is_file():
        raise PipelineError(f"Kindle thumbnail helper is missing: {helper}")
    result = run_process(
        [calibre_debug, "-e", str(helper), "--", str(book), str(output_dir)],
        timeout=180,
    )
    if result.returncode != 0:
        detail = clean_text((result.stderr or result.stdout)[-1500:])
        raise PipelineError(f"Could not generate a Kindle library cover: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PipelineError("Kindle thumbnail helper returned invalid evidence.") from exc
    thumbnail = Path(payload["thumbnail"])
    if payload.get("book_sha256") != sha256_file(book):
        raise PipelineError("Kindle thumbnail evidence does not match the approved book hash.")
    if not thumbnail.is_file() or sha256_file(thumbnail) != payload.get("thumbnail_sha256"):
        raise PipelineError("Generated Kindle thumbnail failed hash verification.")
    return payload


def install_kindle_thumbnail(
    thumbnail: dict[str, Any],
    mount: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Install a thumbnail into both old-Kindle caches with recoverable backups."""
    source = Path(thumbnail["thumbnail"])
    expected_hash = thumbnail["thumbnail_sha256"]
    cache_dirs = [mount / "system" / "thumbnails", mount / "amazon-cover-bug"]
    if not all(path.is_dir() for path in cache_dirs):
        raise PipelineError("Mounted Kindle does not expose the expected thumbnail cache directories.")
    stamp = utc_now().replace(":", "").replace("+", "_")
    backup_root = manifest_path.parent / "kindle-thumbnail-backups" / stamp
    targets = []
    for cache_dir in cache_dirs:
        destination = cache_dir / thumbnail["thumbnail_name"]
        previous_hash = sha256_file(destination) if destination.is_file() else None
        backup_path = None
        if previous_hash == expected_hash:
            action = "already-verified"
        else:
            if destination.is_file():
                backup_path = backup_root / cache_dir.name / destination.name
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if backup_path.exists():
                    raise PipelineError(f"Refusing to overwrite thumbnail backup: {backup_path}")
                shutil.copyfile(destination, backup_path)
                if sha256_file(backup_path) != previous_hash:
                    raise PipelineError("Thumbnail backup hash verification failed.")
            atomic_replace_file(source, destination)
            macos_metadata = clear_transfer_macos_metadata(destination, sidecar_preexisting=False)
            if sha256_file(destination) != expected_hash:
                raise PipelineError("Kindle thumbnail post-copy hash verification failed.")
            action = "written-and-verified"
        targets.append({
            "path": str(destination),
            "action": action,
            "previous_sha256": previous_hash,
            "sha256": sha256_file(destination),
            "backup": str(backup_path) if backup_path else None,
        })
    return {
        "status": "INSTALLED_AND_VERIFIED",
        "thumbnail_name": thumbnail["thumbnail_name"],
        "thumbnail_sha256": expected_hash,
        "width": thumbnail["thumbnail_width"],
        "height": thumbnail["thumbnail_height"],
        "targets": targets,
    }


def transfer_book(
    book: Path,
    manifest_path: Path,
    mount: Path,
    *,
    execute: bool = False,
    require_volumes: bool = True,
) -> dict[str, Any]:
    book = book.expanduser().resolve()
    if not book.is_file():
        raise PipelineError(f"Book does not exist: {book}")
    if book.suffix.lower() not in DIRECT_USB_FORMATS:
        raise PipelineError("Direct USB transfer accepts AZW3/MOBI/PDF/TXT, not EPUB. Use the approved AZW3 output.")
    manifest_path = manifest_path.expanduser().resolve()
    manifest = load_manifest(manifest_path)
    output = find_manifest_output(manifest, book)
    actual_hash = sha256_file(book)
    if actual_hash != output["sha256"]:
        raise PipelineError("Book hash does not match the preflight manifest.")
    approval = manifest.get("approval")
    if not approval or approval.get("book_sha256") != actual_hash:
        raise PipelineError("This exact book has not been approved after visual review.")
    mount, documents = validate_kindle_mount(mount, require_volumes=require_volumes)
    destination = documents / book.name
    if destination.exists():
        if destination.is_file() and sha256_file(destination) == actual_hash:
            return {
                "status": "ALREADY_PRESENT",
                "source": str(book),
                "destination": str(destination),
                "sha256": actual_hash,
                "executed": False,
            }
        raise PipelineError(f"Refusing to overwrite a different destination file: {destination}")
    free_bytes = shutil.disk_usage(mount).free
    if free_bytes < book.stat().st_size + 32 * 1024 * 1024:
        raise PipelineError("Kindle does not have enough free space with a 32 MiB safety margin.")
    plan = {
        "status": "DRY_RUN" if not execute else "PENDING",
        "source": str(book),
        "destination": str(destination),
        "bytes": book.stat().st_size,
        "sha256": actual_hash,
        "executed": execute,
    }
    if not execute:
        return plan
    with tempfile.TemporaryDirectory(prefix="kindle-thumbnail-") as temp_name:
        thumbnail = generate_kindle_thumbnail(book, Path(temp_name))
        sidecar = destination.with_name(f"._{destination.name}")
        sidecar_preexisting = sidecar.exists()
        atomic_copy_no_overwrite(book, destination)
        plan["macos_metadata"] = clear_transfer_macos_metadata(
            destination,
            sidecar_preexisting=sidecar_preexisting,
        )
        try:
            if thumbnail is not None:
                plan["library_cover"] = install_kindle_thumbnail(thumbnail, mount, manifest_path)
            else:
                plan["library_cover"] = {"status": "NOT_APPLICABLE", "reason": "format has no Kindle thumbnail key"}
        except Exception:
            # This destination did not exist before the transfer. Roll back only
            # the file created by this invocation so a cover failure cannot
            # leave an unrecorded partial delivery in the Kindle library.
            if destination.is_file() and sha256_file(destination) == actual_hash:
                destination.unlink()
            created_sidecar = destination.with_name(f"._{destination.name}")
            if not sidecar_preexisting and created_sidecar.is_file():
                created_sidecar.unlink()
            raise
    copied_hash = sha256_file(destination)
    if copied_hash != actual_hash:
        raise PipelineError("Post-copy hash verification failed; do not eject the Kindle yet.")
    plan["status"] = "COPIED_AND_VERIFIED"
    plan["verified_at"] = utc_now()
    manifest.setdefault("transfers", []).append(plan)
    markdown_path = Path(manifest.get("report_markdown") or manifest_path.with_suffix(".md"))
    save_manifest(manifest, manifest_path, markdown_path)
    return plan


def doctor() -> dict[str, Any]:
    tools = {name: tool_version(name) for name in ("epubcheck", "ebook-convert", "ebook-meta", "ebook-viewer")}
    return {
        "created_at": utc_now(),
        "tools": tools,
        "kindle_mounts": detect_kindle_mounts(),
        "ready_for_inspection": tools["epubcheck"]["available"] and tools["ebook-convert"]["available"],
        "note": "No mounted Kindle found can also mean a Scribe/2024+ model that requires Amazon USB File Manager on macOS.",
    }


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect, prepare, approve, and safely transfer local ebooks to Kindle.")
    parser.add_argument(
        "--version",
        action="version",
        version=(
            f"{TOOL_IDENTITY['name']} {TOOL_IDENTITY['version']} · "
            f"{TOOL_IDENTITY['author']} · {TOOL_IDENTITY['homepage']}"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local dependencies and mounted Kindle candidates.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect an EPUB/MOBI/AZW/AZW3 without modifying it.")
    inspect_parser.add_argument("book", type=Path)
    inspect_parser.add_argument("--report-dir", type=Path)

    prepare_parser = subparsers.add_parser("prepare", help="Normalize to EPUB and create a Kindle AZW3 copy.")
    prepare_parser.add_argument("book", type=Path)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument(
        "--profile",
        choices=["kindle", "kindle_pw3", "kindle_oasis", "kindle_scribe", "generic_eink_hd"],
        default="kindle_oasis",
    )
    prepare_parser.add_argument("--title")
    prepare_parser.add_argument("--authors")
    prepare_parser.add_argument("--language", help="Correct a known language metadata error, for example zh-CN.")
    prepare_parser.add_argument("--cover", type=Path, help="Inject a locally supplied cover image during conversion.")
    prepare_parser.add_argument("--output-stem", help="Safe user-facing base name for generated files.")
    prepare_parser.add_argument(
        "--typography-profile",
        choices=["preserve", "reader"],
        default="reader",
        help="Default 'reader' removes forced fonts/spacing and left-aligns justified text; use 'preserve' for layout-sensitive books.",
    )

    legacy_parser = subparsers.add_parser(
        "prepare-legacy",
        help="Create and round-trip-check an old-style MOBI6 file from a normalized EPUB.",
    )
    legacy_parser.add_argument("book", type=Path)
    legacy_parser.add_argument("--output-dir", type=Path, required=True)
    legacy_parser.add_argument(
        "--profile",
        choices=["kindle", "kindle_pw3", "kindle_oasis", "kindle_scribe", "generic_eink_hd"],
        default="kindle_oasis",
    )

    approve_parser = subparsers.add_parser("approve", help="Record that this exact output passed visual review.")
    approve_parser.add_argument("book", type=Path)
    approve_parser.add_argument("--manifest", type=Path, required=True)
    approve_parser.add_argument("--note", required=True)
    approve_parser.add_argument("--confirm-reviewed", action="store_true")

    subparsers.add_parser("detect-kindle", help="List legacy mass-storage Kindle mounts.")

    transfer_parser = subparsers.add_parser("transfer", help="Dry-run or copy an approved output to a mounted Kindle.")
    transfer_parser.add_argument("book", type=Path)
    transfer_parser.add_argument("--manifest", type=Path, required=True)
    transfer_parser.add_argument("--mount", type=Path, required=True)
    transfer_parser.add_argument("--execute", action="store_true")

    device_parser = subparsers.add_parser(
        "device-check",
        help="Record the user's actual Kindle open/render result for an approved file.",
    )
    device_parser.add_argument("book", type=Path)
    device_parser.add_argument("--manifest", type=Path, required=True)
    device_parser.add_argument(
        "--result",
        choices=["opened-ok", "failed-to-open", "partial"],
        required=True,
    )
    device_parser.add_argument("--note", required=True)
    device_parser.add_argument("--model")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "doctor":
            print_json(doctor())
        elif args.command == "inspect":
            report = inspect_book(args.book)
            if args.report_dir:
                report_dir = args.report_dir.expanduser().resolve()
                report_dir.mkdir(parents=True, exist_ok=True)
                stem = safe_output_stem(args.book.stem)
                report_json = report_dir / f"{stem}.inspection.json"
                report_markdown = report_dir / f"{stem}.inspection.md"
                for candidate in (report_json, report_markdown):
                    if candidate.exists():
                        raise PipelineError(f"Refusing to overwrite existing inspection report: {candidate}")
                atomic_write_text(report_json, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                atomic_write_text(report_markdown, render_report_markdown(report))
            print_json(report)
            return 0 if report["status"] in {"PASS", "REVIEW"} else 2
        elif args.command == "prepare":
            print_json(
                prepare_book(
                    args.book,
                    args.output_dir,
                    profile=args.profile,
                    title=args.title,
                    authors=args.authors,
                    language=args.language,
                    cover=args.cover,
                    typography_profile=args.typography_profile,
                    output_stem=args.output_stem,
                )
            )
        elif args.command == "prepare-legacy":
            print_json(
                prepare_legacy_mobi(
                    args.book,
                    args.output_dir,
                    profile=args.profile,
                )
            )
        elif args.command == "approve":
            print_json(approve_book(args.manifest, args.book, args.note, args.confirm_reviewed))
        elif args.command == "detect-kindle":
            print_json({"kindle_mounts": detect_kindle_mounts()})
        elif args.command == "transfer":
            print_json(transfer_book(args.book, args.manifest, args.mount, execute=args.execute))
        elif args.command == "device-check":
            print_json(
                record_device_check(
                    args.manifest,
                    args.book,
                    args.result,
                    args.note,
                    args.model,
                )
            )
        return 0
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted; no overwrite or deletion was requested.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
