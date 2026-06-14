# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-15

First public release.

### Added
- **Analyse** the source machine: MCP servers, projects (active/inactive), agents, plugins,
  commands, Cowork sessions, and a 5-pillar maturity score (Profile / Memory / Writing Style /
  Projects / Connectors).
- **Pre-flight** checks for the target machine: Node / Python / uv / Claude Desktop installed +
  not running + disk space, each with a fix command.
- **Transfer**: safe copy with secret **redaction**, hardcoded-path **rewriting**
  (`C:\Users\old → new`), and timestamped backups.
- **Scaffold**: generates `CLAUDE.md`, `style-guide.md`, `connectors-todo.md`, and per-project
  `CLAUDE.md` files, filling pillar gaps.
- **Report**: a plain-English `MIGRATION-REPORT.md` action list.
- **Single-file Windows app** (`Claude-Migrate.exe`) with an interactive menu on double-click,
  best-effort admin elevation, and a self-elevating `.bat` launcher.
- Robust path resolution for both installer and Microsoft Store builds of Claude Desktop.
- Test suite (`pytest`) and Windows CI.

### Security
- Secrets are never copied or logged; credential-pattern files are skipped.
