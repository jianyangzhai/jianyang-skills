# Ebook quality gates

## Status meanings

| Status | Meaning | Action |
|---|---|---|
| PASS | No automated finding | Continue to visual review |
| REVIEW | Non-fatal uncertainty or rigid styling | Inspect affected content before approval |
| NEEDS_REPAIR | EPUB conformance, broken-reference, encoding, or structural errors | Normalize/repair and rerun all checks |
| BLOCKED | DRM/encryption, unsafe archive paths, active content, suspicious archive, or unsupported container | Stop; do not convert or transfer |

EPUBCheck verifies specification conformance. It does not prove good typography, correct OCR, or Kindle rendering. Calibre preview is also not a substitute for the actual device.

## Automated gates

Require all of the following before visual approval:

- Original SHA-256 recorded and source left unchanged.
- DRM/encrypted publication content absent. Standard EPUB font obfuscation may remain.
- ZIP member paths safe; no duplicate/path-traversal/bomb indicators.
- OPF package, manifest, spine, and navigation present and internally linked.
- EPUBCheck has zero fatal/error messages after normalization.
- All manifest resources and embedded links resolve locally.
- No scripts, iframes, forms, objects, `javascript:` links, or remote embedded resources.
- No Unicode replacement/null characters.
- Metadata includes a useful title, author, and language.
- Cover and non-empty TOC present.
- Generated AZW3 is readable by Calibre and reports no MOBI encryption.
- Conversion settings record the target output profile, typography profile, and any metadata overrides.

Treat warnings about rigid CSS, repeated blocks, excessive breaks, suspiciously short chapters, spaced Chinese characters, or missing cover as visual-review targets—not automatic permission to ignore them.

## Safe automatic changes

Allow Calibre normalization to:

- repair ordinary malformed markup in a derivative;
- rebuild package internals and reading order;
- normalize CSS for a reflowable ebook;
- generate a generic Kindle-profile AZW3;
- preserve cover aspect ratio;
- correct title/author metadata when the user provides the exact values.

Never automatically:

- delete paragraphs, chapters, notes, images, tables, or front/back matter;
- rewrite prose or punctuation;
- guess OCR corrections;
- remove watermarks or rights information;
- flatten a fixed-layout/art book into reflowable text without a user-approved sample;
- remove encryption or DRM;
- accept an EPUBCheck error because the preview happens to open.

## Visual review checklist

Review at least these locations in the normalized EPUB:

1. Cover: correct image, aspect ratio, no duplicate cover page.
2. Metadata: title and author display correctly.
3. TOC: entries are ordered, readable, and open the intended chapter.
4. First chapter: title, paragraph indentation, line spacing, emphasis, and chapter break.
5. Two representative middle chapters: one text-heavy and one containing images, tables, lists, quotations, or code if present.
6. Footnote/endnote sample: forward link and return link both work.
7. Final chapter/back matter: not truncated and ordered correctly.
8. Font controls: small/large sizes reflow without clipping or horizontal scrolling.
9. Themes: text remains visible in light and dark modes; colors do not hide content.
10. Images/tables: fit the viewport, preserve aspect ratio, and have no unreadably tiny essential text.
11. Reader control: body font, font size, margins, and alignment remain adjustable for ordinary reflowable prose.

For Chinese ebooks, additionally inspect:

- paragraphs broken at every source line;
- spaces inserted between Chinese characters;
- replacement glyphs, mojibake, or mixed simplified/traditional encoding damage;
- repeated page headers, footers, page numbers, and scan artifacts;
- lost full-width punctuation or quotation marks;
- first-line indentation applied to headings, lists, dialogue, or poetry incorrectly;
- blank pages caused by excessive `<br>` or forced page breaks;
- vertical text or fixed layout unintentionally flattened.
- excessive inter-character gaps caused by full justification on an old MOBI renderer;
- forced body fonts, line heights, word spacing, or letter spacing that disable or undermine reader controls;
- actual-device paragraph indentation, heading hierarchy, margins, and selected font when the target uses MOBI6.

For ordinary Chinese prose, prefer a reader-controlled derivative when the source forces full justification or body fonts. A MOBI6 preview in a modern desktop viewer does not reproduce all old Kindle typography behavior, so obtain an actual-device photo before calling the typography polished.

On the target Kindle Oasis, change between at least two installed fonts and compare the same paragraph. A selectable menu entry alone is not proof that the book applies the chosen font.

## Approval note

Write an approval note that names the items actually reviewed. If tables, images, notes, or special layouts do not exist, say so rather than implying they were checked.
