# Security Policy

## Supported versions

The latest tagged release and `main` receive security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security reports. Instead, use GitHub's
[private vulnerability reporting](../../security/advisories/new) on this repository, or
email `prateeksmulye@gmail.com` with:

- A description of the issue and its impact
- Steps to reproduce (proof-of-concept welcome)
- Any suggested remediation

You can expect an acknowledgment within 72 hours and a status update within 7 days.

## Scope notes

- The public demo enforces per-IP and global daily limits on live analysis runs; the
  research library, replays, and market data are intentionally public and read-only.
- All secrets (LLM and web-research API keys, admin token, database credentials) live in
  environment variables — none are committed to this repository. If you believe a secret
  has leaked into the history, report it via the channel above.
