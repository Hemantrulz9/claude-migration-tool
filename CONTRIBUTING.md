# Contributing

Thanks for your interest! This is a small, focused Windows tool — contributions that keep it
**simple and dependency-light** are very welcome.

## Dev setup

```powershell
git clone https://github.com/hemantrulz/claude-migrate
cd claude-migrate
python -m pip install -r requirements-dev.txt
pytest -q
```

## Ground rules

- **Python 3.10+, pathlib, stdlib-first.** The only runtime dependency is `rich` (and it's optional).
- **Never copy or log secrets.** Anything touching MCP `env`, tokens, or credentials must go
  through `security.py`. Add a test if you touch this area.
- **Per-module error handling.** A failure in one reader must not crash the whole run.
- **Add a test** for new behaviour (`tests/`), and keep `pytest -q` green.
- Keep the build sequence intact: `config → security → path_rewriter → analyser → preflight →
  scaffold_generator → report_generator → main`.

## Reporting bugs / ideas

Open an issue with your Windows version, what you ran, and the relevant lines from
`migration.log` (redact anything sensitive first).
