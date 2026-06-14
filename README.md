# Claude Migrate

**Move your Claude Desktop + Claude Code setup to a new Windows PC — without the silent breakage.**

[![CI](https://github.com/Hemantrulz9/claude-migration-tool/actions/workflows/ci.yml/badge.svg)](https://github.com/Hemantrulz9/claude-migration-tool/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6)
![License](https://img.shields.io/badge/license-MIT-green)

Claude Migrate safely **migrates** your setup, **analyses** it against 5 maturity pillars,
**scaffolds** a smarter setup on the new machine, and writes a plain-English **action report**.
It’s not just a file copier — it’s a Claude **setup-intelligence engine**.

It fixes the things that quietly break a Claude migration: **hardcoded `C:\Users\<name>` paths**
in MCP configs, **secrets that should never be copied**, and **missing runtimes** on the new box —
none of which a plain copy-paste handles.

> Free and open source (MIT). Built to be a no-nonsense, dependency-light Windows tool.

## Run it (single program, double-click)

**Easiest:** download **`Claude-Migrate.exe`** from the [Releases](../../releases) page, then double-click it.
- It asks for **administrator rights** (UAC), then opens an interactive menu.
- No Python install required — everything is bundled in the one file.
- Cloned the repo instead? Double-click **`Claude-Migrate.bat`** (self-elevates and runs from
  source), or build the exe yourself (see below).

The menu walks you through: **Full migration**, **Analyse**, **Pre-flight check**, **Scaffold**,
and **Generate report**.

> Power users: the same exe is a full CLI — `Claude-Migrate.exe full --source ... --target ...`.
> Passing CLI arguments does **not** force elevation, so it stays scriptable.

### Rebuild the single exe
```powershell
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --onefile --name Claude-Migrate --distpath dist --workpath build --specpath build main.py
```

## Code signing (publisher: hemantrulz)

The exe is signed with a **self-signed** `hemantrulz` certificate (SHA-256, DigiCert-timestamped).
File → Properties → Digital Signatures shows **hemantrulz** as the signer.

- Re-sign after any rebuild (signing must be the last step):
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\Sign-Build.ps1
  ```
- Cert files are written to `.\signing\` (git-ignored): `hemantrulz.cer` (public) and
  `hemantrulz.pfx` (private key backup). Keep the `.pfx` and its password private — never commit them.

**Trust it on a machine** (so Windows shows the signature as *valid* — one-time):
double-click `hemantrulz.cer` → **Install Certificate** → *Local Machine* → *Place all
certificates in the following store* → **Trusted Root Certification Authorities** → confirm the
security prompt. (Or, in an **admin** PowerShell: `Import-Certificate -FilePath signing\hemantrulz.cer
-CertStoreLocation Cert:\LocalMachine\Root` then again into `...\TrustedPublisher`.)

> Self-signed means: trusted only where you've imported the cert. On other machines it still shows
> "unknown publisher" and **SmartScreen may still warn** (it's reputation-based, not just trust).
> For trust everywhere with no per-machine setup, buy a code-signing certificate from a public CA —
> note the publisher name on a CA cert is your **validated identity**, not a free-choice handle.

## Requirements

- Windows 10 / 11
- Python 3.10+
- `pip install -r requirements.txt` (just `rich`, for coloured output — the tool still runs
  without it, just in plain text)

## Install

```powershell
cd claude-migration-tool
python -m pip install -r requirements.txt
```

## The 5 Pillars

| Pillar | What it means |
|--------|---------------|
| Profile | A root `~/.claude/CLAUDE.md` describing who you are and how you work |
| Memory | Claude Desktop memory enabled (cannot be read from files — checked manually) |
| Writing Style | Style/tone preferences Claude should follow |
| Projects | Per-project `CLAUDE.md` context files |
| Connectors | MCP servers configured |

## Commands

```powershell
# 1. Analyse the OLD machine -> writes analysis_result.json
python main.py analyse

# 2. Validate the NEW machine is ready (runtimes, Claude installed/closed, disk)
python main.py preflight

# 3. Copy config + files OLD -> NEW (redacts secrets, fixes hardcoded paths, backs up)
python main.py transfer --source "C:\Users\OldName" --target "C:\Users\NewName"

# 4. Generate the smart scaffold on the NEW machine
python main.py scaffold --from analysis_result.json

# 5. Generate the action report
python main.py report --from analysis_result.json

# OR run the whole pipeline (asks before each destructive step)
python main.py full --source "C:\Users\OldName" --target "C:\Users\NewName"
```

Add `--yes` to skip confirmation prompts (for automation).

## What it produces (in `~/.claude` on the target)

- `CLAUDE.md` — your profile, pre-filled from inferred role/domains, projects, and tools
- `style-guide.md` — style preferences extracted from your old CLAUDE.md files
- `connectors-todo.md` — MCP reconnection checklist (which need tokens, which need runtimes)
- `projects/<name>/CLAUDE.md` — per-project context (copied or scaffolded)
- `MIGRATION-REPORT.md` — a do-this-in-order action list

Plus `analysis_result.json` and `migration.log` in the working directory.

## Safety

- **Secrets are never copied.** MCP `env` values are redacted to `[REDACTED - re-enter on new
  machine]`; files matching credential patterns or containing token-like strings are skipped.
- **Nothing is overwritten without a backup.** Existing files are copied to
  `<name>.backup.<timestamp>` first.
- **Hardcoded `C:\Users\<oldname>` paths are rewritten** to the new user automatically.
- Every action is logged to `migration.log` (never secret values).

## What it cannot do (by design, this version)

- Read Memory status (check Claude Desktop → Settings → Capabilities manually)
- Migrate conversation history (stored on Anthropic's servers, not local)
- Copy API tokens/keys (re-enter manually — by design)
- Copy the Cowork VM virtual disk (`.vhdx`, too large — the report tells you where it is)
- GUI, cloud sync, MCP health test, scheduled backup (Phase 3 — not in this version)

## Notes on paths

`config.py` resolves paths robustly for both the standalone-installer and Microsoft Store
builds of Claude Desktop: the global Claude Code config is read from `~/.claude.json` (with
`~/.claude/claude.json` as a fallback), and Cowork VM disks are searched under both
`%APPDATA%\Claude\vm_bundles` and `%LOCALAPPDATA%\Packages\Claude_*`.

## Project layout

```
main.py                 CLI + interactive menu (entry point)
config.py               paths, logging, safe_write
analyser.py             reads the source machine -> analysis_result.json
preflight.py            validates the target machine
path_rewriter.py        scans + rewrites hardcoded user paths
security.py             redaction + secret detection
scaffold_generator.py   generates the 5-pillar files
report_generator.py     writes MIGRATION-REPORT.md
tests/                  pytest suite
```

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Keep it simple and
dependency-light, and never copy or log secrets (see [SECURITY.md](SECURITY.md)).

```powershell
pip install -r requirements-dev.txt
pytest -q
```

## Disclaimer

Not affiliated with or endorsed by Anthropic. "Claude" is a trademark of Anthropic. This is an
independent community tool. It never copies API keys/tokens and never uploads your data anywhere —
everything runs locally on your machine.

## Author

Built by **[hemantrulz](https://github.com/Hemantrulz9)** — part of the **ExcelProKit** project.
If this saved you time, a ⭐ on the repo helps it reach other Claude users.

## License

[MIT](LICENSE) © 2026 Hemant Chauhan (hemantrulz) · ExcelProKit
