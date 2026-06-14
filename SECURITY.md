# Security

This tool handles a user's Claude configuration, which can contain secrets. Its design rules:

- **Secrets are never copied.** MCP `env` values are redacted to a placeholder; files matching
  credential patterns (`*.key`, `*.pem`, `.env*`, `credentials.json`, `token.json`, etc.) or
  containing token-like strings are skipped (`security.py`).
- **Secrets are never logged.** `migration.log` records actions, not values.
- **Nothing is overwritten without a timestamped backup.**

## What you should NOT commit

If you fork/build this repo, never commit:
- `signing/*.pfx` / any private key (already in `.gitignore`)
- `analysis_result.json`, `migration.log`, or `MIGRATION-REPORT.md` from a real machine — they
  describe your setup.

## Reporting a vulnerability

Please open a private security advisory on GitHub (or email the maintainer) rather than a public
issue. Include reproduction steps and the affected version.
