"""
report_generator.py — Module 4. Produce MIGRATION-REPORT.md: a plain-English,
do-this-in-order action report based on analysis_result.json and what was done.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import config
from config import TOOL_VERSION, log, safe_write


def _pillar_count_complete(scores: dict) -> int:
    return sum(1 for k, v in scores.items() if k != "memory" and v == "present")


def _new_machine_status(created_names: set[str], analysis: dict) -> dict:
    mcp_count = len(analysis.get("mcp_servers", []))
    proj_scaffolded = sum(1 for n in created_names if n.endswith("CLAUDE.md") and "projects" in n.replace("\\", "/"))
    return {
        "profile": "created" if "CLAUDE.md" in created_names or any(n.endswith("\\CLAUDE.md") or n.endswith("/CLAUDE.md") for n in created_names) else "skipped",
        "memory": "Check manually",
        "writing_style": "created" if any(n.endswith("style-guide.md") for n in created_names) else "skipped",
        "projects": f"{proj_scaffolded} scaffolded",
        "connectors": f"{mcp_count} servers restored",
    }


def generate_report(analysis: dict, created_files: list[Path] | None = None,
                    preflight_results: list[dict] | None = None,
                    path_rewrites: list[dict] | None = None,
                    target_root: Path | None = None) -> Path | None:
    target_root = Path(target_root) if target_root else config.USERPROFILE
    created_files = created_files or []
    created_names = {str(p) for p in created_files}
    scores = analysis.get("pillar_scores", {})
    complete = _pillar_count_complete(scores)
    new_status = _new_machine_status({str(Path(p).as_posix()) for p in created_files} | created_names, analysis)

    active = analysis.get("projects", {}).get("active", [])
    abandoned = analysis.get("projects", {}).get("abandoned", [])
    servers = analysis.get("mcp_servers", [])
    agents = analysis.get("agents", [])
    plugins = analysis.get("plugins", [])
    domains = analysis.get("inferred_domains", [])
    vhdx = analysis.get("cowork_vhdx_path", "")

    def pill(name):  # old-machine status text
        return scores.get(name, "unknown")

    active_block = "\n".join(f"- {p['name']} (modified {p['last_modified'][:10]})" for p in active) or "- None"
    inactive_block = "\n".join(f"- {p['name']} (modified {p['last_modified'][:10]})" for p in abandoned) or "- None"
    server_rows = "\n".join(
        f"| {s['name']} | {'Yes' if s.get('has_hardcoded_paths') else 'No'} | {'Yes' if s.get('requires_token') else 'No'} | {'Path fixed' if s.get('has_hardcoded_paths') else 'OK'} |"
        for s in servers) or "| (none) | - | - | - |"
    agents_block = ", ".join(agents) if agents else "None found"
    plugins_block = ", ".join(plugins) if plugins else "None found"
    files_block = "\n".join(f"- `{p}`" for p in created_files) or "- (no files created)"

    rewrite_rows = "\n".join(
        f"| {r.get('server_name','?')} | {r.get('old','')} | {r.get('new','')} |" for r in (path_rewrites or [])
    ) or "| No path rewrites needed | | |"

    style_reason = {
        "missing": "You had no writing-style preferences recorded — set one up to keep Claude consistent.",
        "partial": "You had a few style hints — expand them for better consistency.",
        "present": "You had style preferences — re-upload them to keep Claude consistent.",
    }.get(scores.get("writing_style", "missing"), "")

    content = f"""# Claude Migration Report
Generated: {datetime.now().isoformat(timespec='seconds')}
Source Machine: {analysis.get('source_username','')}
Target Machine: {target_root.name}
Tool Version: {TOOL_VERSION}

---

## Setup Maturity Score: {complete}/5 pillars complete

| Pillar | Status on Old Machine | Status on New Machine |
|--------|----------------------|-----------------------|
| Profile (CLAUDE.md) | {pill('profile')} | {new_status['profile']} |
| Memory | Unknown — check manually | {new_status['memory']} |
| Writing Style | {pill('writing_style')} | {new_status['writing_style']} |
| Projects | {pill('projects')} | {new_status['projects']} |
| Connectors (MCP) | {pill('connectors')} | {new_status['connectors']} |

---

## What Was Found on Your Old Machine

### Active Projects ({len(active)} — modified in last 90 days)
{active_block}

### Inactive Projects ({len(abandoned)} — older than 90 days)
{inactive_block}

### MCP Servers ({len(servers)} total)
| Server | Hardcoded Paths | Token Required | Status After Migration |
|--------|----------------|----------------|----------------------|
{server_rows}

### Agents Found
{agents_block}

### Plugins Found
{plugins_block}

---

## Files Created on This Machine

{files_block}

---

## Your Action List — Do These in Order

### 1. Review Your Profile (10 minutes)
File: `~\\.claude\\CLAUDE.md`
Open this file and edit the placeholder sections.
This is the single most impactful thing you can do.
The more accurate this file, the better every Claude response.

### 2. Turn On Memory
Go to: Claude Desktop → Settings → Capabilities → Memory → Enable
Why: Without this, every chat starts from zero.
Cannot be done by this tool — requires manual action in Claude Desktop.

### 3. Upload Your Writing Style
File: `~\\.claude\\style-guide.md`
Go to: Claude Desktop → Settings → Profile → Writing Style → Upload sample
Why: {style_reason}

### 4. Reconnect MCP Servers
File: `~\\.claude\\connectors-todo.md`
{len(servers)} servers need attention. Work through the checklist.
Priority: re-enter API tokens first — servers won't start without them.

### 5. Set Up Projects in Claude Desktop
Go to: Claude Desktop → Projects → New Project
For each active project, create a Project and upload its CLAUDE.md as context.
Your project CLAUDE.md files are in: `~\\.claude\\projects\\`

### 6. Review Inactive Projects
{inactive_block}
Decide: keep, archive, or delete.

---

## What This Tool Cannot Do (be honest)

- **Memory status**: Cannot be read from files. Check Settings → Capabilities manually.
- **Conversation history**: Stored on Anthropic's servers. Not local. Not migrated.
- **API tokens / keys**: Never copied. Must be re-entered manually.
- **Cowork virtual disk (VHDX)**: Too large to copy automatically.
  Location on old machine: {vhdx or "Not found / Cowork not used"}
  To migrate: copy this folder manually via USB or network.
- **Claude.ai account settings**: Managed in your browser account. Already synced.

---

## Paths Fixed During Migration

| Server | Original Path | Rewritten To |
|--------|--------------|-------------|
{rewrite_rows}

---
*Claude Migration Tool v{TOOL_VERSION}*
*Review this report, then delete or archive it once your setup is confirmed working.*
"""

    path = Path(target_root) / ".claude" / "MIGRATION-REPORT.md"
    if safe_write(path, content):
        log("INFO", f"Migration report written: {path}")
        return path
    return None
