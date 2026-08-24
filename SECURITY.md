# Security

Review every Skill before installation and run it with the least authority needed for the task.

For `kindle-ebook-preflight`:

- input must be a local file the user is allowed to use;
- DRM or encrypted content is blocked;
- archive traversal and oversized expansion are blocked;
- output is written outside the source directory without silent overwrite;
- transfer requires a reviewed, hash-approved derivative;
- network sharing and Amazon uploads require separate authorization;
- no telemetry or hidden network call is implemented by the Skill.

Report a suspected vulnerability through a GitHub Security Advisory when the repository makes that channel available. Otherwise open an issue containing reproduction steps but no private book, credential, personal path, device identifier, or unpublished exploit payload.
