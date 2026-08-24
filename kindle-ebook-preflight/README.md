# Kindle Ebook Preflight

Turn a locally supplied EPUB, MOBI, AZW, or AZW3 into a reviewed Kindle candidate without surrendering reader font controls or silently changing the source.

This Skill is for readers using a legacy or USB-mounted Kindle who care about clean Chinese typography, correct title/author/cover metadata, working navigation, and a reproducible transfer record. It does not find books, remove DRM, generate unapproved covers, or claim that a desktop preview proves device rendering.

## What you get

- read-only source inspection and EPUBCheck evidence;
- a normalized EPUB master and AZW3/KF8 derivative;
- an explicit `reader` or `preserve` typography profile;
- cover, TOC, chapter, image, note, and font-control review gates;
- SHA-256-bound approval and atomic USB transfer;
- verified Kindle library thumbnails where the device exposes the expected caches;
- a machine-readable manifest and human-readable report.

## Install

After the public repository is approved and published:

```bash
npx skills add https://github.com/jianyangzhai/jianyang-skills --skill kindle-ebook-preflight
```

You can opt out of the `skills` CLI's anonymous install telemetry:

```bash
DISABLE_TELEMETRY=1 npx skills add https://github.com/jianyangzhai/jianyang-skills --skill kindle-ebook-preflight
```

To inspect a local checkout before installing it:

```bash
git clone https://github.com/jianyangzhai/jianyang-skills.git
npx skills add ./jianyang-skills --skill kindle-ebook-preflight
```

ClawHub/OpenClaw is currently `BLOCKED_LICENSE`: ClawHub publishes Skills as MIT-0, while this Skill is GPL-3.0-only. The intended command below is documentation for a possible future approved listing, not a currently working install path:

```bash
openclaw skills install @jianyangzhai/kindle-ebook-preflight
```

The Skill requires Python 3.10+, W3C EPUBCheck, and Calibre. Direct USB transfer requires a Kindle mounted as mass storage; newer devices may require Amazon's USB File Manager.

## Use

Give the agent a local ebook you have the right to use and ask it to inspect or prepare the file for Kindle. The pipeline stops at visual review and hash-bound approval before any transfer. See [SKILL.md](SKILL.md) for the complete workflow and [quality gates](references/quality-gates.md) for acceptance criteria.

## Evidence and limits

The bundled deterministic self-test currently covers structural inspection, unsafe archives, encryption blocking, EPUB normalization, AZW3 and MOBI6 conversion, overwrite refusal, hash-bound approval, transfer dry-run, atomic verified copy, and dual-cache thumbnail installation. Automated checks still cannot replace opening the exact derivative on the target Kindle and testing font switching, TOC, images/notes, and the final chapter.

The source book remains byte-for-byte unchanged. Generated reports identify this tool, but author branding is never injected into an ebook's body, cover, title, author, TOC, metadata, or Kindle thumbnail.

## License

`GPL-3.0-only`. See [LICENSE](LICENSE).

<!-- attribution:start -->
Built and maintained by [Jianyang Zhai](https://github.com/jianyangzhai) · [@jianyangzhai](https://github.com/jianyangzhai) · [jianyang-skills](https://github.com/jianyangzhai/jianyang-skills)
<!-- attribution:end -->
