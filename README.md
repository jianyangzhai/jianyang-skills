<div align="center">

[English](README.md) · [中文](README.zh-CN.md)

# Jianyang Skills

**Small Agent Skills proven in real workflows, packaged with tests, boundaries, and installable source.**

</div>

Need a reliable way to turn a messy ebook into a Kindle-ready file without losing font control, metadata, or the original source? The first featured Skill here is for readers with a locally supplied, DRM-free ebook and a Kindle—especially older USB-mounted models. It produces inspected and reviewed derivatives, hashes, reports, and a gated transfer path. Install it with one command, inspect the reproducible evidence below, and keep the final visual decision on the actual device.

```bash
npx skills add https://github.com/jianyangzhai/jianyang-skills --skill kindle-ebook-preflight
```

<!-- attribution:start -->
Built and maintained by [Jianyang Zhai](https://github.com/jianyangzhai) · [@jianyangzhai](https://github.com/jianyangzhai) · [jianyang-skills](https://github.com/jianyangzhai/jianyang-skills)
<!-- attribution:end -->

## Featured Skill

### [Kindle Ebook Preflight](kindle-ebook-preflight/README.md)

Inspect, normalize, visually review, approve, and safely transfer a locally supplied EPUB, MOBI, AZW, or AZW3 without forcing reader typography.

What it gives you:

- structural EPUB/MOBI inspection and explicit DRM blocking;
- normalized EPUB plus AZW3/KF8 and optional MOBI6 fallback;
- reader-controlled or layout-preserving typography profiles;
- cover, TOC, chapters, images, notes, and final-page review gates;
- SHA-256-bound approval, atomic USB copy, and verified library thumbnails;
- a machine-readable manifest and human-readable report.

## Evidence

Current local evidence on macOS:

- 14 deterministic checks pass using synthetic, redistributable fixtures;
- W3C EPUBCheck 5.3.0 and Calibre 9.13.0 are detected;
- EPUB→AZW3 and MOBI6 round-trip paths pass;
- generated EPUB/AZW3 contain zero maintainer-brand strings.

The evidence does not replace opening the exact derivative on the target Kindle and testing font switching, TOC, images/notes, and the final chapter.

## Install

The command above uses the open Agent Skills format and selects only `kindle-ebook-preflight`. The `skills` CLI reports anonymous install telemetry by default. To opt out:

```bash
DISABLE_TELEMETRY=1 npx skills add https://github.com/jianyangzhai/jianyang-skills --skill kindle-ebook-preflight
```

You can also inspect [SKILL.md](kindle-ebook-preflight/SKILL.md) before installation. Requirements are Python 3.10+, W3C EPUBCheck, and Calibre; direct transfer needs a Kindle mounted as mass storage.

To download the public repository first and then install from the reviewed local checkout:

```bash
git clone https://github.com/jianyangzhai/jianyang-skills.git
npx skills add ./jianyang-skills --skill kindle-ebook-preflight
```

ClawHub/OpenClaw distribution is intentionally unavailable while its MIT-0 publishing rule conflicts with this Skill's GPL-3.0-only license. If that conflict is resolved and an approved release is actually published, the intended install command will be:

```bash
openclaw skills install @jianyangzhai/kindle-ebook-preflight
```

Do not treat that ClawHub command as available until the public listing is verified.

## Other public work

These projects keep their own repositories and history:

- [Idea Darwin](https://github.com/jianyangzhai/idea-darwin) — evolve raw ideas through structured variation and selection.
- [De-AI Writing](https://github.com/jianyangzhai/de-ai-writing) — remove generic AI-writing patterns from Chinese prose.
- [Resume De-AI](https://github.com/jianyangzhai/resume-de-ai) — review résumé language for AI-like phrasing without flattening professional tone.

## Trust boundaries

- No book search or downloading.
- No DRM removal or bypass.
- No overwrite of source files or different existing Kindle books.
- No generated cover without a failed official-cover search and explicit approval.
- No hidden telemetry, tracking pixels, or third-party upload. The optional LAN transfer serves one hash-approved file only after explicit authorization and binds to an explicitly supplied local address.
- Maintainer attribution appears in documentation and reports, never in an ebook's body, cover, title, author, TOC, metadata, or Kindle thumbnail.

See [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), and [ATTRIBUTIONS.md](ATTRIBUTIONS.md).

## About

This repository is the generated public release surface for Agent Skills built and maintained by [Jianyang Zhai](https://github.com/jianyangzhai). Each release is packaged from a separate canonical source, verified before publication, and linked back here through [@jianyangzhai](https://github.com/jianyangzhai).

## Licenses

Root documentation is MIT licensed. Each Skill can carry its own license; `kindle-ebook-preflight` is currently `GPL-3.0-only` because its thumbnail helper runs inside and imports Calibre modules. See the nearest `LICENSE` file.
