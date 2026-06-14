"""
scaffold_generator.py — Module 5. Create new files on the TARGET machine from
analysis_result.json, filling gaps in the 5 pillars. Never overwrites without
confirmation. Returns the list of files created (used by the report).
"""

from __future__ import annotations

import re
from pathlib import Path

import config
from config import GENERATED_HEADER, OUTPUT_PATHS, STYLE_KEYWORDS, log, safe_write
from path_rewriter import rewrite_paths  # noqa: F401  (kept for parity; project copy uses text rewrite)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _default_prompt(_question: str) -> str:
    """Non-interactive default: skip overwriting existing files (safe)."""
    return "skip"


def extract_style_sentences(all_claude_md_content: str) -> list[str]:
    """Return unique sentences that mention a style keyword."""
    if not all_claude_md_content:
        return []
    out, seen = [], set()
    for raw in _SENTENCE_SPLIT.split(all_claude_md_content):
        s = raw.strip().lstrip("#-*> ").strip()
        if not s:
            continue
        low = s.lower()
        if any(kw in low for kw in STYLE_KEYWORDS):
            if low not in seen:
                seen.add(low)
                out.append(s)
    return out


def _active_projects(analysis: dict) -> list[dict]:
    return list(analysis.get("projects", {}).get("active", []))


def _all_projects(analysis: dict) -> list[dict]:
    p = analysis.get("projects", {})
    return list(p.get("active", [])) + list(p.get("abandoned", []))


def _all_md_text(analysis: dict) -> str:
    parts = [analysis.get("root_claude_md", {}).get("content", "")]
    parts += [p.get("claude_md_content", "") for p in _all_projects(analysis)]
    return "\n".join(parts)


# --------------------------------------------------------------------------- 5a root CLAUDE.md
def generate_root_claude_md(analysis: dict, target_root: Path, prompt_fn=_default_prompt) -> Path | None:
    pillar = analysis.get("pillar_scores", {}).get("profile", "missing")
    if pillar == "present":
        log("INFO", "Root CLAUDE.md pillar already 'present'; skipping generation.")
        return None

    path = Path(target_root) / ".claude" / "CLAUDE.md"
    style_sentences = extract_style_sentences(_all_md_text(analysis))
    active = _active_projects(analysis)
    mcp = analysis.get("mcp_servers", [])

    projects_block = "\n".join(f"- **{p['name']}**: [describe what this project is]" for p in active) or "- [Add your active projects here]"
    tools_block = "\n".join(f"- {s['name']}" for s in mcp) or "- [Add the tools/MCP servers you use]"
    style_block = "\n".join(f"- {s}" for s in style_sentences) or "- [Add your preferences here]"
    domains = ", ".join(analysis.get("inferred_domains", [])) or "[not determined]"
    role = analysis.get("inferred_role", "") or "Professional (role not determined)"

    content = (
        "# About Me\n"
        f"{GENERATED_HEADER}"
        f"{role} — inferred from your project history.\n"
        f"Active domains: {domains}.\n\n"
        "# My Active Projects\n"
        f"{projects_block}\n\n"
        "# Tools I Use\n"
        f"{tools_block}\n\n"
        "# How I Like to Work\n"
        f"{style_block}\n\n"
        "# Important Context\n"
        "- [Add key facts Claude should always know]\n"
        "- [Add constraints or things to avoid]\n\n"
        "---\n"
        "*This file was auto-generated from your previous machine's setup.*\n"
        "*Edit it before your first Claude session on this machine.*\n"
        "*The more detail you add, the better Claude will understand your context.*\n"
    )

    if path.exists():
        choice = (prompt_fn("Overwrite existing CLAUDE.md? (y/n/merge)") or "n").strip().lower()
        if choice in ("n", "no", "skip"):
            log("INFO", f"Skipped existing root CLAUDE.md (user choice).")
            return None
        if choice in ("merge", "m"):
            existing = path.read_text(encoding="utf-8", errors="replace")
            merged = existing.rstrip() + "\n\n## Migration Additions\n" + content
            return path if safe_write(path, merged) else None
    return path if safe_write(path, content) else None


# --------------------------------------------------------------------------- 5b per-project CLAUDE.md
_PROJECT_TEMPLATE = (
    "# Project: {name}\n"
    f"{GENERATED_HEADER}"
    "<!-- Fill in the sections below before using Claude on this project -->\n\n"
    "## Goal\n[What is this project trying to achieve?]\n\n"
    "## Key Context\n[Facts Claude should always know about this project]\n\n"
    "## Output Format Preferences\n[How do you want responses structured — bullets, prose, tables, code?]\n\n"
    "## Do Not\n[Things Claude should avoid on this project]\n\n"
    "## Key Files / Docs\n[List important files or documents Claude should know about]\n"
)


def generate_project_claude_mds(analysis: dict, target_root: Path) -> list[Path]:
    """Copy existing project CLAUDE.md (path-rewritten) or scaffold a template if none."""
    written: list[Path] = []
    old_user = analysis.get("source_username", "")
    new_user = config.USERPROFILE.name
    for proj in _all_projects(analysis):
        name = proj["name"]
        dest = Path(target_root) / ".claude" / "projects" / name / "CLAUDE.md"
        if proj.get("has_claude_md") and proj.get("claude_md_content"):
            text = proj["claude_md_content"]
            if old_user and old_user != new_user:
                text = text.replace(f"C:\\Users\\{old_user}", f"C:\\Users\\{new_user}").replace(
                    f"/Users/{old_user}", f"/Users/{new_user}")
            if not dest.exists() and safe_write(dest, text):
                written.append(dest)
        else:
            if not dest.exists() and safe_write(dest, _PROJECT_TEMPLATE.format(name=name)):
                written.append(dest)
    return written


# --------------------------------------------------------------------------- 5c style-guide.md
def generate_style_guide(analysis: dict, target_root: Path) -> Path | None:
    path = Path(target_root) / ".claude" / "style-guide.md"
    sentences = extract_style_sentences(_all_md_text(analysis))
    extracted = "\n".join(sentences) if sentences else "[No explicit style preferences found in your CLAUDE.md files]"
    content = (
        "# My Writing Style Guide\n"
        "<!-- Auto-extracted from your CLAUDE.md files by Claude Migration Tool v1.0 -->\n"
        "<!-- Upload this file to Claude Desktop: Settings -> Profile -> Writing Style -> Upload sample -->\n\n"
        "## Extracted Style Preferences\n"
        f"{extracted}\n\n"
        "## Notes\n"
        "- Review each line above — remove anything that doesn't reflect your actual style\n"
        "- Add examples of your own writing below for better calibration\n"
        "- The more specific, the better\n\n"
        "## My Writing Examples\n"
        "[Paste 2-3 paragraphs of your own writing here]\n"
    )
    return path if safe_write(path, content) else None


# --------------------------------------------------------------------------- 5d connectors-todo.md
_DOMAIN_CONNECTORS = [
    (("construction", "project", "civil", "buildcon", "waterproof", "flooring"),
     ["Google Drive", "Gmail", "WhatsApp Business"]),
    (("ecommerce", "shopify", "store", "product", "inventory", "order"),
     ["Shopify MCP", "Gmail", "Google Sheets"]),
    (("finance", "accounts", "invoice", "gst", "tally", "tax"),
     ["Google Sheets", "Gmail"]),
    (("software", "code", "api", "backend", "deploy", "github"),
     ["GitHub MCP", "filesystem"]),
]


def _server_status(server: dict) -> str:
    if server.get("requires_token"):
        return "Token Needed"
    if server.get("has_hardcoded_paths"):
        return "Path Fixed"
    return "Ready"


def _suggested_connectors(domains: list[str]) -> list[str]:
    doml = " ".join(domains).lower()
    suggestions: list[str] = []
    for keys, conns in _DOMAIN_CONNECTORS:
        if any(k in doml for k in keys):
            suggestions += conns
    # de-dup preserve order
    seen, out = set(), []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def generate_connectors_todo(analysis: dict, target_root: Path, preflight_results: list[dict] | None = None) -> Path | None:
    path = Path(target_root) / ".claude" / "connectors-todo.md"
    servers = analysis.get("mcp_servers", [])
    rows = "\n".join(
        f"| {s['name']} | {_server_status(s)} | {'Re-enter API token' if s.get('requires_token') else ('Verify rewritten path' if s.get('has_hardcoded_paths') else 'No action')} |"
        for s in servers
    ) or "| (none found) | - | - |"

    token_servers = [s["name"] for s in servers if s.get("requires_token")]
    tokens_block = "\n".join(f"- {n}" for n in token_servers) or "- None"

    missing_runtimes = []
    fix_cmds = []
    for r in (preflight_results or []):
        if r.get("status") in ("warn", "fail") and r.get("name") in ("Node.js", "Python", "uv"):
            missing_runtimes.append(r["name"])
            if r.get("fix_command"):
                fix_cmds.append(r["fix_command"])
    runtimes_block = "\n".join(f"- {n}" for n in missing_runtimes) or "- None detected as missing"
    fix_block = "\n".join(f"- `{c}`" for c in fix_cmds) or "- (none)"

    suggestions = _suggested_connectors(analysis.get("inferred_domains", []))
    sugg_block = "\n".join(f"- {s}" for s in suggestions) or "- (no domain-based suggestions)"

    content = (
        "# MCP Server Reconnection Checklist\n"
        "<!-- Generated by Claude Migration Tool v1.0 -->\n"
        "<!-- Work through this list after Claude Desktop is open on your new machine -->\n\n"
        "## Servers from Your Previous Machine\n\n"
        "| Server | Status | Action Required |\n|--------|--------|-----------------|\n"
        f"{rows}\n\n"
        "## Tokens to Re-enter\n"
        "These servers require you to manually enter API tokens.\n"
        "Tokens are NEVER copied by this tool for security.\n"
        f"{tokens_block}\n\n"
        "## Missing Runtimes\n"
        f"{runtimes_block}\n\n"
        "Fix commands:\n"
        f"{fix_block}\n\n"
        f"## Suggested Connectors You Don't Have Yet\n"
        f"Based on your detected domains ({', '.join(analysis.get('inferred_domains', [])) or 'none'}), consider adding:\n"
        f"{sugg_block}\n"
    )
    return path if safe_write(path, content) else None


# --------------------------------------------------------------------------- orchestration
def scaffold(analysis: dict, target_root: Path | None = None, prompt_fn=_default_prompt,
             preflight_results: list[dict] | None = None) -> list[Path]:
    """Generate all scaffold files. Returns the list of paths created/updated."""
    target_root = Path(target_root) if target_root else config.USERPROFILE
    log("INFO", f"Scaffold started. Target: {target_root}")
    created: list[Path] = []

    for fn in (
        lambda: generate_root_claude_md(analysis, target_root, prompt_fn),
        lambda: generate_style_guide(analysis, target_root),
        lambda: generate_connectors_todo(analysis, target_root, preflight_results),
    ):
        try:
            p = fn()
            if p:
                created.append(p)
        except Exception as e:
            log("ERROR", f"Scaffold step failed: {e}")

    try:
        created += generate_project_claude_mds(analysis, target_root)
    except Exception as e:
        log("ERROR", f"Project scaffold failed: {e}")

    log("INFO", f"Scaffold complete. {len(created)} file(s) created.")
    return created
