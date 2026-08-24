# Kindle transfer modes on macOS

Verify current Amazon guidance when the device model or behavior is uncertain. Product behavior can change.

## Format and typography decision

Use a reflowable format. Prefer AZW3/KF8 when the target opens it: it retains substantially more CSS and font behavior than old MOBI6. Use MOBI6 only as a compatibility fallback.

For Chinese prose, conspicuously stretched spaces between characters usually mean an old renderer is applying full justification without modern spacing compensation. Rebuild with `--typography-profile reader`, which uses Calibre conversion controls to:

- change justified text to left alignment while preserving centered headings;
- remove forced `font-family`, `line-height`, `letter-spacing`, and `word-spacing` rules;
- preserve the source's paragraph indents, section spacing, and heading hierarchy.

This profile intentionally leaves the body font to the reader/device. Keep `preserve` for poetry, code, textbooks, fixed layout, or any book whose spacing is meaningful.

Amazon documents that reflowable books support adjustable font settings, that body text should normally retain reader defaults, and that publisher fonts are a KF8-era feature. It also documents that enhanced typesetting reduces distracting justification gaps. From those facts and the observed behavior of old MOBI files, infer that MOBI6 cannot be relied on for user-installed fonts or enhanced typography; confirm the exact device rather than promising support.

Official references (checked 2026-08-16):

- <https://digprjsurvey.amazon.com/csad/help/node/T5Y94BzSCGwm0vd75W>
- <https://kdp.amazon.com/en_US/help/topic/GH4DRT75GWWAGBTU>
- <https://kdp.amazon.com/en_US/help/topic/GNY87A6WM6EK6YEE>

## Legacy mass-storage Kindle

Models released before 2024 generally appear under `/Volumes` on macOS, except Kindle Scribe. Confirm all of these before direct copy:

- an explicit volume under `/Volumes`;
- a `documents/` directory;
- a Kindle-like volume name or `system/` directory;
- enough free space;
- an approved AZW3 whose hash matches the preflight manifest.

Use the Skill's transfer command. It defaults to dry-run, refuses overwrite, writes through a partial file, atomically renames, attempts to remove macOS-only metadata created for that new destination, reports known attributes that remain, and verifies SHA-256 after copying. It does not scan or delete unrelated AppleDouble files.

For AZW/AZW3/MOBI, the same command also extracts the approved embedded cover and generates the device thumbnail with Calibre's Kindle driver logic. It verifies identical copies in both `system/thumbnails` and `amazon-cover-bug`; a differing existing cache file is backed up locally before replacement. A successful book copy without the intended library cover is incomplete for this user's established workflow.

Prefer the generated `.azw3` for this mode. Do not directly copy `.epub` merely because Amazon accepts EPUB through Send to Kindle; wireless ingestion converts it server-side.

## Kindle Scribe and 2024-or-newer Kindle

Amazon states that Kindle Scribe and devices released in 2024 or later require a separate macOS application for USB browsing/transfers, such as Send to Kindle's USB File Manager. These devices may not expose `/Volumes/<Kindle>/documents`, so the direct-copy command must stop.

Identify the model and follow the current official USB File Manager flow. Treat GUI automation as a separate action: show the exact file and ask before placing it through the app.

Official reference (checked 2026-08-16):
<https://digprjsurvey.amazon.com/csad/help/node/TCUBEdEkbIhK07ysFu>

## Wireless Send to Kindle

Amazon currently accepts EPUB and other listed formats through Send to Kindle, up to 200 MB per file. This is an external upload to Amazon, not a local USB copy. Do not use it from a request that only authorized local Kindle transfer.

Official service:
<https://www.amazon.com/sendtokindle>

## Temporary local-network browser download

Use this only after the user explicitly authorizes temporary LAN exposure. It does not upload to Amazon.

1. Approve the exact MOBI/AZW3 hash after visual review.
2. Resolve the Mac's current LAN address and confirm the Kindle is on the same trusted network.
3. Run `scripts/serve_lan.py` with the exact book, manifest, host, and port.
4. Verify `/healthz` locally.
5. Have the user download the uniquely named file in the Kindle browser.
6. Watch for a successful GET, but treat that only as download evidence.
7. Record whether the user could open and render the book.
8. Stop the server immediately.

The server exposes one file only, checks its current SHA-256 against the approval, disables caching, and has no directory listing. Do not bind broadly by default or leave it running after the transfer.

If the Kindle says it cannot open the selected content, remove that failed library item before retrying. Do not merely rename a KF8-only payload to `.mobi`. Try a real `.azw3` first when the browser accepts it; otherwise generate a true MOBI6 with `prepare-legacy` and use a new filename.

Validated recovery pattern from an old Kindle Oasis on 2026-08-16: a KF8-only file carrying a `.mobi` extension downloaded successfully but failed to open; a true MOBI6 derivative with a new filename opened successfully. This is evidence for the fallback, not a claim that every Oasis/browser firmware behaves identically.

## Final device check

After safe ejection, ask the user to verify:

- the book appears with the correct title/author/cover;
- it opens without a conversion error;
- font resizing and theme changes work;
- TOC links work;
- a representative image/table/footnote renders;
- the final chapter is present.

Local copy verification is complete only when hashes match. Actual Kindle rendering remains unverified until the user performs this check.

When the user supplies an actual-device photo, compare character spacing, paragraph indentation, line spacing, heading hierarchy, margins, and active font controls—not only whether the text is legible. Record the result with `device-check`; do not infer success from an HTTP 200 or copy hash alone.
