# High-quality Kindle Oasis import

Use this reference for books intended for a Kindle Oasis or another reflowable Kindle target. The goal is not maximum decorative styling. It is a clean, reflowable book with strong hierarchy, natural Chinese spacing, sharp source images, reliable navigation, and working reader-selected fonts.

## Source priority

Choose the best local source the user supplies:

1. A structurally valid EPUB with complete cover, TOC, metadata, and high-resolution images.
2. A DRM-free AZW3/KF8 when no EPUB exists.
3. A DRM-free MOBI only as a recovery source; do not keep MOBI6 as the preferred final format.

Do not assume a larger file is better. Inspect structure, image dimensions, metadata, TOC, encoding, CSS, and representative pages. Stop on DRM rather than attempting removal.

When the user supplies multiple editions, inspect each source independently and rank them before conversion. Prefer complete structure and clean representative pages over filename claims or file size; keep the rejected candidates unchanged and state why the selected source won.

## Default prose contract

For ordinary Chinese fiction and nonfiction:

- normalize to EPUB 3 and require zero EPUBCheck errors;
- output an AZW3/KF8 with the `kindle_oasis` profile;
- preserve and reuse an acceptable embedded cover; when none exists, prefer the matching published edition's official cover, and use a generated substitute only after search fails and the user approves the fallback;
- record the SHA-256 of any replacement cover injected during conversion;
- use `reader` typography so justified body text becomes left-aligned on the old renderer;
- remove forced body font family, line height, letter spacing, and word spacing;
- preserve paragraph indent, headings, emphasis, quotations, section breaks, images, and TOC;
- correct known title, author, and language metadata without inventing values;
- leave the body font to the device instead of embedding a font by default.

Use `preserve` for poetry, code, textbooks, fixed layout, art books, or meaningful spatial composition. A global CSS filter is too coarse for those works.

## Mature toolchain

- W3C EPUBCheck is the production conformance gate for EPUB 2/3: <https://github.com/w3c/epubcheck>
- Calibre documents `kindle_oasis`, `--change-justification`, and `--filter-css` for deterministic conversion: <https://manual.calibre-ebook.com/generated/en/ebook-convert.html>
- Amazon's QA checklist covers cover, TOC, font size/typeface changes, images, tables, backgrounds, and whole-book review: <https://kdp.amazon.com/en_US/help/topic/GGRXLC5USU4H67YM>
- Amazon's reflowable-text guidance favors reader defaults and warns against forced body styling: <https://kdp.amazon.com/en_US/help/topic/GH4DRT75GWWAGBTU>
- Long-running MobileRead reports consistently distinguish AZW3/KF8 font support from MOBI limitations: <https://www.mobileread.com/forums/showthread.php?t=365873>

Community reports are supporting experience, not a substitute for the official format checks or the actual target device.

## Visual review

Review the exact normalized EPUB and generated AZW3:

- cover and duplicate-cover behavior;
- metadata and library title length;
- all TOC levels and representative links;
- first, middle, image/table/note, and final sections;
- natural Chinese punctuation, spacing, and first-line indentation;
- heading hierarchy and scene breaks;
- small and large font sizes without clipping or horizontal scrolling;
- light/dark readability when the device supports the theme;
- image sharpness at the Oasis viewport and preserved aspect ratio.

Do not approve from automated checks alone. Approval binds the reviewed AZW3 hash.

## Actual-device acceptance

After verified USB copy and safe ejection, require the user to confirm:

1. The book appears with the intended title, author, and cover.
2. It opens without a conversion error.
3. The same paragraph visibly changes when switching between at least two installed fonts in `Aa`.
4. Font size, boldness, margins, spacing, and alignment controls work.
5. Chinese text has no stretched inter-character gaps.
6. TOC navigation, a representative image/note, and the final chapter work.

Record `opened-ok` only when these checks pass. Use `partial` when the book opens but typography, font selection, navigation, or content remains wrong. Keep MOBI6 solely as a fallback when the Oasis rejects the approved AZW3.

## Observed legacy-Kindle workflow

This workflow has been exercised on a Kindle Oasis after hash-verified metadata cleanup and dual-cache library thumbnails. Preserve these tested defaults for future user-supplied books:

- clean library display means canonical title, correct author, and a verified thumbnail derived from the embedded or user-approved cover;
- write the thumbnail to both `system/thumbnails` and `amazon-cover-bug` using Calibre's Kindle thumbnail naming and a 500-pixel height limit;
- preserve the supplied source and verify the final device copy by SHA-256;
- when the user supplies the files and states that the Kindle is connected, complete the reviewed USB transfer in the same task without a redundant second confirmation;
- actual opening, font switching, navigation, and final-page checks remain a separate device acceptance result.
