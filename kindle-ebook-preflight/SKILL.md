---
name: kindle-ebook-preflight
description: Inspect, normalize, improve typography, visually review, approve, and transfer a locally supplied EPUB, MOBI, AZW, or AZW3 ebook for clear Kindle reading with reader-selectable fonts. Use when the user asks to check an ebook for formatting/layout errors, make a book Kindle-ready, create an old-Kindle-compatible fallback, inspect its cover/TOC/chapters/images/footnotes, or transfer an approved book to Kindle. Do not use to find or download books, extract books for analysis, bypass DRM, or transfer content the user has not supplied and authorized.
license: GPL-3.0-only
metadata:
  author: Jianyang Zhai
  homepage: https://github.com/jianyangzhai/jianyang-skills
  source: https://github.com/jianyangzhai/jianyang-skills/tree/main/kindle-ebook-preflight
  version: "1.0.0"
  compatibility: Python 3.10+, W3C EPUBCheck, and Calibre; direct transfer requires a mounted Kindle
---

# Kindle ebook preflight

Treat this as a gated local publishing workflow:

`source (read-only) -> structural inspection -> normalized EPUB -> typography profile -> AZW3/MOBI6 -> visual review -> hash-bound approval -> Kindle transfer + library cover -> actual-device check`

For high-quality imports to a Kindle Oasis or another reflowable Kindle target, read [references/high-quality-import.md](references/high-quality-import.md). It defines the reader-first quality target, source priority, and actual-device acceptance test established from a successful local workflow and mature Kindle tooling.

Run all commands from this Skill directory with `python3 scripts/ebook_pipeline.py ...`.

## Boundaries

- Process only a local ebook the user supplied and has the right to use.
- Never search for or download books.
- Never remove or work around DRM. Stop with `BLOCKED` when encryption is detected.
- Preserve the source byte-for-byte. Write derivatives to a separate output directory.
- Never silently overwrite an output or a file already on Kindle.
- Never mark a book transfer-ready from automated checks alone. Complete visual review first.
- Keep wireless Send to Kindle separate: it uploads the file to Amazon and requires explicit authorization.
- Treat a LAN download server as temporary local-network exposure. Require explicit authorization, serve one approved hash only, and stop it after the device result is known.

## 1. Check the workstation

Run:

```bash
python3 scripts/ebook_pipeline.py doctor
```

Require W3C EPUBCheck and Calibre (`ebook-convert`, `ebook-meta`, `ebook-viewer`). If missing, explain the free dependencies and ask before installing them. Do not install packages as a side effect of this Skill.

## 2. Inspect the source

Run inspection without changing the source:

```bash
python3 scripts/ebook_pipeline.py inspect "/absolute/path/book.epub" --report-dir "/absolute/path/review"
```

Accept `.epub`, `.mobi`, `.azw`, and `.azw3`. MOBI/AZW files are converted only inside a temporary directory for inspection.

Interpret status strictly:

- `PASS`: no automated finding; visual review is still required.
- `REVIEW`: warnings require judgment before conversion or approval.
- `NEEDS_REPAIR`: allow Calibre normalization to attempt repair, then require a clean postflight.
- `BLOCKED`: stop; do not convert or transfer.

Read [references/quality-gates.md](references/quality-gates.md) when evaluating findings or deciding whether a warning is acceptable.

## 3. Prepare Kindle derivatives

Classify the book before conversion. Ordinary reflowable prose uses the default `reader` profile. Poetry, code-heavy books, textbooks, art books, and layout-sensitive publications must explicitly use `preserve`.

Create a new output directory outside the Skill and source directories. The current personal-device defaults are `kindle_oasis` and `reader`:

```bash
python3 scripts/ebook_pipeline.py prepare "/absolute/path/book.mobi" \
  --output-dir "/absolute/path/Kindle-ready"
```

For confirmed Chinese prose whose source language metadata is missing or wrong, the equivalent explicit command is:

```bash
python3 scripts/ebook_pipeline.py prepare "/absolute/path/book.mobi" \
  --output-dir "/absolute/path/Kindle-ready" \
  --profile kindle_oasis \
  --typography-profile reader \
  --language zh-CN \
  --output-stem "书名-排版优化版"
```

`reader` changes justified text to left alignment and removes forced font family/line height/word spacing while preserving the source's paragraph and heading structure. Never embed a user's font without checking its embedding license; prefer leaving body text selectable by the Kindle. Use `--language` only to correct a known metadata error.

Use `--title` or `--authors` only to correct known metadata. Select `--profile kindle_scribe`, `kindle_pw3`, or another listed profile only when targeting a different confirmed device.

Preserve an acceptable embedded cover and reuse it for the Kindle library thumbnail. If the source lacks a usable cover, search for the matching published edition's official cover before considering a generated substitute. Generate a substitute only when a suitable published cover cannot be found and the user approves that fallback. When the user supplies or approves a local cover image, add `--cover "/absolute/path/cover.png"`; the pipeline records its path, size, and SHA-256 and injects it during EPUB normalization and AZW3 generation. Never silently replace an acceptable cover, and visually review every cover change.

Expected outputs:

- `*.kindle.epub`: normalized master for preview or separately authorized Send to Kindle.
- `*.kindle.azw3`: direct USB derivative for a legacy mass-storage Kindle.
- `*.preflight.json`: hashes, tool evidence, findings, outputs, approval, and transfer history.
- `*.preflight.md`: human-readable report.

If the normalized EPUB still has EPUBCheck errors or blocking findings, stop. Do not label or transfer a defective derivative.

## 4. Perform visual review

Open the normalized EPUB in Calibre's viewer and, when available, Kindle Previewer. Inspect the cover, TOC navigation, first chapter, representative middle chapters, final chapter, images/tables, footnotes, chapter breaks, font resizing, and dark/light appearance.

For a `reader` derivative, specifically confirm that Chinese body text is not stretched by full justification, headings remain distinct, paragraph indents are consistent, and no body-level font rule prevents reader selection. A desktop preview is insufficient when the target is an old MOBI renderer; request an actual-device photo when typography is in doubt.

The final Oasis acceptance test must switch between at least two device-installed fonts in the `Aa` menu. If the menu changes but the page does not, or the font is unavailable for only this book, keep the result `partial` and inspect format/CSS before blaming the font files.

Use the detailed checklist in [references/quality-gates.md](references/quality-gates.md). Record concrete observations; do not write “looks good” without checking representative pages.

Automated conformance and Calibre preview do not prove actual-device rendering. Keep that uncertainty until the user opens the transferred book on Kindle.

## 5. Approve the exact reviewed file

Approve only after the visual checklist passes:

```bash
python3 scripts/ebook_pipeline.py approve "/absolute/path/book.kindle.azw3" \
  --manifest "/absolute/path/book.preflight.json" \
  --note "Cover, TOC, first/middle/last chapters, images, footnotes and font resizing reviewed" \
  --confirm-reviewed
```

Approval is bound to the file's SHA-256. Any later file change invalidates transfer.

## 6. Identify the connected Kindle

Run:

```bash
python3 scripts/ebook_pipeline.py detect-kindle
```

Then read [references/kindle-transfer.md](references/kindle-transfer.md).

- If a verified `/Volumes/<Kindle>/documents` mount is present, use the legacy direct-copy workflow below.
- If no mount appears, do not guess. Kindle Scribe and 2024-or-newer devices on macOS may require Amazon's USB File Manager. Use that separate workflow after identifying the model.

## 7. Choose modern typography or old-device fallback

Prefer AZW3/KF8 for a compatible Kindle because it retains richer CSS and reader-selected/custom fonts. If USB is unavailable but the Kindle browser can download local files, test the approved `.azw3` under its real extension and MIME type; do not disguise KF8 as `.mobi`.

If the Kindle rejects AZW3/KF8, create a true old-style MOBI6 from the reviewed normalized EPUB:

```bash
python3 scripts/ebook_pipeline.py prepare-legacy "/absolute/path/book.kindle.epub" \
  --output-dir "/absolute/path/legacy-ready" \
  --profile kindle_oasis
```

The command converts with Calibre's old MOBI mode, then round-trips the result back to EPUB and reruns all structural checks. Do not transfer when that round trip returns `NEEDS_REPAIR` or `BLOCKED`. MOBI6 is the compatibility fallback; do not promise custom-font selection or enhanced typesetting.

After visual review, approve the exact `.legacy.mobi`. With explicit permission to expose the file on the local network, start the single-file server:

```bash
python3 scripts/serve_lan.py "/absolute/path/book.legacy.mobi" \
  --manifest "/absolute/path/book.legacy.preflight.json" \
  --host <current-lan-ip> --port 8080
```

Use the Mac's current LAN address, never guess a stale one. The server refuses an unapproved or hash-changed file and exposes no directory listing. Use a new filename after a failed Kindle download to avoid cache/library collisions. Stop the server with Ctrl-C immediately after the device result is recorded.

## 8. Dry-run, confirm, and transfer by USB

When the user supplies specific local ebook file(s) and says the Kindle is connected or asks to use this workflow, that request authorizes same-task USB transfer of the exact reviewed derivatives. Complete every quality and hash gate before executing. This does not authorize overwriting a different existing book, bypassing DRM, choosing a generated cover, deleting unrelated content, or uploading through Amazon/LAN; stop for those cases.

For requests without that explicit connected-Kindle context, first show the exact source, destination, byte size, and hash:

```bash
python3 scripts/ebook_pipeline.py transfer "/absolute/path/book.kindle.azw3" \
  --manifest "/absolute/path/book.preflight.json" \
  --mount "/Volumes/Kindle"
```

After the user confirms that exact plan, execute:

```bash
python3 scripts/ebook_pipeline.py transfer "/absolute/path/book.kindle.azw3" \
  --manifest "/absolute/path/book.preflight.json" \
  --mount "/Volumes/Kindle" \
  --execute
```

Require `COPIED_AND_VERIFIED`. The script copies through a partial file, atomically renames it, and verifies the destination hash. Do not eject automatically.

For AZW/AZW3/MOBI, transfer also derives a 500-pixel Kindle thumbnail from the approved embedded cover using Calibre's Kindle driver rules, writes and verifies it in both `system/thumbnails` and `amazon-cover-bug`, and records any replaced cache file in a recoverable local backup. Treat the cover cache as part of delivery, not an optional cosmetic step.

## 9. Verify on the actual Kindle

Ask the user to eject safely, open the book, change font size, follow several TOC entries, inspect a picture/table/footnote, and reach the final chapter. Report local transfer as complete but device rendering as pending until this check succeeds.

Record the user's explicit result against the approved file hash:

```bash
python3 scripts/ebook_pipeline.py device-check "/absolute/path/book.legacy.mobi" \
  --manifest "/absolute/path/book.legacy.preflight.json" \
  --result opened-ok \
  --model "Kindle Oasis" \
  --note "User opened the book and supplied an actual-device typography check."
```

Use `failed-to-open` or `partial` when appropriate. Do not turn silence into success.

## Report back

Always state:

- source format, path, size, and hash;
- automated status and unresolved warnings;
- derivative paths and hashes;
- visual-review coverage;
- device transfer method and destination;
- copy-verification result;
- actual-device verification status.
