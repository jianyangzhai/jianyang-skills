#!/usr/bin/env python3
"""Dependency-free release and branding boundary tests."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTION_START = "<!-- attribution:start -->"
ATTRIBUTION_END = "<!-- attribution:end -->"
FORBIDDEN_EBOOK_SUFFIXES = {".epub", ".mobi", ".azw", ".azw3", ".kfx"}
TEXT_SUFFIXES = {"", ".css", ".html", ".json", ".md", ".py", ".sh", ".svg", ".txt", ".yaml", ".yml"}


def load_manifest(root: Path) -> dict:
    return json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if any(part in {".git", "__pycache__"} for part in path.relative_to(root).parts):
            continue
        if path.is_file() or path.is_symlink():
            yield path


def text(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE"}:
        return None
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        return None
    return data.decode("utf-8")


def sensitive_patterns() -> dict[str, re.Pattern[str]]:
    home = r"/" + r"Users/" + r"[A-Za-z0-9._-]+"
    private_ip = (
        r"(?<!\d)(?:10(?:\.\d{1,3}){3}|"
        + r"192"
        + r"\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?!\d)"
    )
    email = r"\b[A-Z0-9._%+-]+" + "@" + r"[A-Z0-9.-]+\.[A-Z]{2,}\b"
    return {
        "personal-home-path": re.compile(home),
        "private-ip": re.compile(private_ip),
        "email": re.compile(email, re.IGNORECASE),
    }


def local_link_issues(path: Path, root: Path, value: str) -> list[str]:
    issues: list[str] = []
    for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", value):
        target = match.group(1).strip().split(" ", 1)[0].strip("<>")
        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        local = target.split("#", 1)[0]
        if local and not (path.parent / local).resolve().exists():
            issues.append(f"broken-local-link:{path.relative_to(root)}:{target}")
    return issues


def check_repo(root: Path) -> list[str]:
    manifest = load_manifest(root)
    identity = manifest["identity"]
    slug = manifest["featured_skill"]["slug"]
    required = [
        "README.md",
        "README.zh-CN.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "ATTRIBUTIONS.md",
        "release-manifest.json",
        f"{slug}/README.md",
        f"{slug}/SKILL.md",
        f"{slug}/LICENSE",
    ]
    issues = [f"required-file-missing:{item}" for item in required if not (root / item).is_file()]
    attribution_files = [root / "README.md", root / "README.zh-CN.md", root / slug / "README.md"]
    for path in attribution_files:
        if not path.is_file():
            continue
        value = path.read_text(encoding="utf-8")
        if value.count(ATTRIBUTION_START) != 1 or value.count(ATTRIBUTION_END) != 1:
            issues.append(f"attribution-count:{path.relative_to(root)}")
            continue
        block = value[value.index(ATTRIBUTION_START):value.index(ATTRIBUTION_END)]
        for expected in [identity["name"], f"@{identity['handle']}", identity["repository"]]:
            if expected not in block:
                issues.append(f"brand-missing:{path.relative_to(root)}:{expected}")
    for relative, contract in manifest["readme_contracts"].items():
        path = root / relative
        if not path.is_file():
            issues.append(f"readme-contract-file-missing:{relative}")
            continue
        value = path.read_text(encoding="utf-8")
        headings = [line[3:].strip() for line in value.splitlines() if line.startswith("## ")]
        for heading in contract.get("required_headings", []):
            if headings.count(heading) != 1:
                issues.append(f"readme-heading-count:{relative}:{heading}")
        for phrase in contract.get("required_phrases", []):
            if phrase not in value:
                issues.append(f"readme-required-phrase:{relative}:{phrase}")
        limit = contract.get("first_screen_attribution_max_chars")
        if limit is not None:
            end = value.find(ATTRIBUTION_END)
            if end < 0 or end + len(ATTRIBUTION_END) > limit:
                issues.append(f"readme-attribution-below-first-screen:{relative}:{limit}")
    skill = (root / slug / "SKILL.md").read_text(encoding="utf-8") if (root / slug / "SKILL.md").is_file() else ""
    expected_lines = [
        f"name: {slug}",
        f"license: {manifest['featured_skill']['license']}",
        f"  author: {identity['name']}",
        f"  homepage: {identity['repository']}",
        f"  source: {manifest['featured_skill']['source']}",
        f"  version: \"{manifest['featured_skill']['version']}\"",
    ]
    for expected in expected_lines:
        if skill.count(expected) != 1:
            issues.append(f"skill-metadata:{expected}")
    patterns = sensitive_patterns()
    for path in iter_files(root):
        relative = path.relative_to(root)
        if path.is_symlink():
            issues.append(f"symlink:{relative}")
            continue
        if path.suffix.lower() in FORBIDDEN_EBOOK_SUFFIXES:
            issues.append(f"ebook-in-repository:{relative}")
        value = text(path)
        if value is None:
            continue
        for name, pattern in patterns.items():
            if pattern.search(value):
                issues.append(f"{name}:{relative}")
        if path.suffix.lower() == ".md":
            issues.extend(local_link_issues(path, root, value))
    return sorted(set(issues))


def scan_ebook(path: Path, manifest: dict) -> list[str]:
    identity = manifest["identity"]
    terms = [identity["name"], identity["handle"], identity["github_profile"], identity["repository"]]
    payloads: list[tuple[str, bytes]] = [(path.name, path.read_bytes())]
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                member = PurePosixPath(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    return [f"unsafe-archive-member:{info.filename}"]
                if info.file_size < 8 * 1024 * 1024:
                    payloads.append((info.filename, archive.read(info)))
    issues = []
    for location, payload in payloads:
        for term in terms:
            encodings = [term.encode("utf-8"), term.encode("utf-16le"), term.encode("utf-16be")]
            if any(encoded in payload for encoded in encodings):
                issues.append(f"ebook-brand-injection:{location}:{term}")
    return sorted(set(issues))


def main() -> int:
    checks: list[str] = []
    assert check_repo(ROOT) == [], check_repo(ROOT)
    checks.append("valid repository candidate passes")

    with tempfile.TemporaryDirectory(prefix="jianyang-skills-release-test-") as temp_name:
        temp = Path(temp_name)
        candidate = temp / "repo"
        shutil.copytree(ROOT, candidate, ignore=shutil.ignore_patterns("__pycache__"))
        readme = candidate / "README.md"
        clean = readme.read_text(encoding="utf-8")
        identity = load_manifest(candidate)["identity"]
        for required_brand in [identity["name"], f"@{identity['handle']}", identity["repository"]]:
            start = clean.index(ATTRIBUTION_START)
            end = clean.index(ATTRIBUTION_END, start)
            block = clean[start:end]
            assert required_brand in block
            damaged = clean[:start] + block.replace(required_brand, "removed-brand", 1) + clean[end:]
            readme.write_text(damaged, encoding="utf-8")
            assert any(item.startswith("brand-missing:") for item in check_repo(candidate))
            readme.write_text(clean, encoding="utf-8")
            assert check_repo(candidate) == []
        checks.append("each required attribution value is red when removed and green when restored")

        readme.write_text(clean.replace("## Install", "## Setup", 1), encoding="utf-8")
        assert any(item.startswith("readme-heading-count:") for item in check_repo(candidate))
        readme.write_text(clean, encoding="utf-8")
        assert check_repo(candidate) == []
        checks.append("README information contract is red and green")

        security = candidate / "SECURITY.md"
        original = security.read_text(encoding="utf-8")
        injected_ip = "192" + ".168.1.4"
        security.write_text(original + "\nHost: " + injected_ip + "\n", encoding="utf-8")
        assert any(item.startswith("private-ip:") for item in check_repo(candidate))
        security.write_text(original, encoding="utf-8")
        assert check_repo(candidate) == []
        checks.append("private network injection is red and removal is green")

        injected_path = "/" + "Users/example/private-book.epub"
        security.write_text(original + "\nPath: " + injected_path + "\n", encoding="utf-8")
        assert any(item.startswith("personal-home-path:") for item in check_repo(candidate))
        security.write_text(original, encoding="utf-8")
        assert check_repo(candidate) == []
        checks.append("personal path injection is red and removal is green")

        manifest = load_manifest(candidate)
        branded = temp / "branded.epub"
        with zipfile.ZipFile(branded, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("content.opf", f"<dc:creator>{manifest['identity']['name']}</dc:creator>")
        assert scan_ebook(branded, manifest)
        clean_epub = temp / "clean.epub"
        with zipfile.ZipFile(clean_epub, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("content.opf", "<dc:creator>Original Author</dc:creator>")
        assert scan_ebook(clean_epub, manifest) == []
        checks.append("ebook brand injection is red and clean ebook is green")

    print(json.dumps({"status": "PASS", "count": len(checks), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
