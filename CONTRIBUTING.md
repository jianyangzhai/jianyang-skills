# Contributing

Issues and focused pull requests are welcome.

Before proposing a change:

1. Explain the concrete failure mode and target Kindle or ebook format.
2. Use a synthetic, public-domain, or otherwise redistributable fixture.
3. Preserve the source-file, DRM, visual-review, approval, and transfer boundaries.
4. Run `python3 kindle-ebook-preflight/scripts/self_test.py` on a workstation with EPUBCheck and Calibre.
5. Run `python3 tests/test_release_boundaries.py` with Python 3.10+.
6. State what was checked on a real device and what remains unverified.

Do not submit books, credentials, private paths, device identifiers, generated covers presented as official editions, or personal network addresses.
