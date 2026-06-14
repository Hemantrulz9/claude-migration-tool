"""
analyser.py — Module 1. Reads everything from the SOURCE machine and produces
analysis_result.json. Read-only: never writes to the target during analysis.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import config
from config import (
    ACTIVE_PROJECT_DAYS,
    SECRET_ENV_KEY_PATTERNS,
    SOURCE_PATHS,
    STYLE_KEYWORDS,
    TOOL_VERSION,
    log,
)

_HARDCODED = re.compile(r"(?i)[A-Za-z]:\\Users\\|/Users/")
_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")

_STOPWORDS = {
    "the", "and", "for", "you", "your", "this", "that", "with", "are", "was", "but", "not",
    "all", "any", "can", "have", "has", "had", "will", "would", "should", "could", "from",
    "they", "them", "their", "what", "when", "which", "who", "how", "use", "used", "using",
    "about", "into", "more", "most", "some", "such", "than", "then", "these", "those", "also",
    "here", "there", "very", "just", "like", "make", "made", "want", "need", "always", "never",
    "claude", "file", "files", "project", "projects", "add", "edit", "review",
}

_ROLE_CLUSTERS = [
    (["waterproof", "flooring", "concrete", "construction", "buildcon", "civil"], "Construction Business Owner"),
    (["shopify", "product", "inventory", "ecommerce", "store", "order"], "Ecommerce Operator"),
    (["invoice", "gst", "accounts", "tally", "ledger", "tax"], "Business Finance Manager"),
    (["code", "api", "backend", "deploy", "function", "module", "script"], "Software Developer"),
]


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def read_mcp_config(config_path: Path) -> list[dict]:
    """Read mcpServers from a config file (desktop config or global .claude.json)."""
    config_path = Path(config_path)
    if not config_path.exists():
        log("WARN", f"MCP config not found at {config_path}")
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log("ERROR", f"Could not parse MCP config {config_path}: {e}")
        return []

    servers_out: list[dict] = []

    def parse_block(block: dict):
        if not isinstance(block, dict):
            return
        for name, server in block.items():
            if not isinstance(server, dict):
                continue
            args = server.get("args", []) or []
            env = server.get("env", {}) or {}
            env_keys = list(env.keys()) if isinstance(env, dict) else []
            values_to_check = [str(a) for a in args] + [str(v) for v in (env.values() if isinstance(env, dict) else [])]
            hardcoded = [v for v in values_to_check if _HARDCODED.search(v)]
            requires_token = any(
                any(pat in key.upper() for pat in SECRET_ENV_KEY_PATTERNS) for key in env_keys
            )
            servers_out.append({
                "name": name,
                "command": server.get("command", server.get("type", "")),
                "args": list(args),
                "env_keys": env_keys,
                "has_hardcoded_paths": bool(hardcoded),
                "hardcoded_paths_found": hardcoded,
                "requires_token": requires_token,
            })

    # global + per-project mcpServers (Claude Code) and top-level (desktop config)
    if isinstance(data, dict):
        parse_block(data.get("mcpServers", {}))
        projects = data.get("projects")
        if isinstance(projects, dict):
            for proj in projects.values():
                if isinstance(proj, dict):
                    parse_block(proj.get("mcpServers", {}))
    return servers_out


def read_projects(projects_folder: Path) -> list[dict]:
    """Scan ~/.claude/projects/* subfolders; return project dicts sorted by last_modified desc."""
    projects_folder = Path(projects_folder)
    out: list[dict] = []
    if not projects_folder.exists():
        log("WARN", f"Projects folder not found: {projects_folder}")
        return out
    for sub in projects_folder.iterdir():
        if not sub.is_dir():
            continue
        claude_md = sub / "CLAUDE.md"
        has_md = claude_md.exists()
        content = ""
        if has_md:
            try:
                content = claude_md.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                log("WARN", f"Could not read {claude_md}: {e}")
        try:
            mtime = datetime.fromtimestamp(sub.stat().st_mtime)
        except OSError:
            mtime = datetime.now()
        out.append({
            "name": sub.name,
            "has_claude_md": has_md,
            "claude_md_word_count": _word_count(content),
            "claude_md_content": content,
            "last_modified": mtime.isoformat(),
        })
    out.sort(key=lambda p: p["last_modified"], reverse=True)
    return out


def _list_names(folder: Path) -> list[str]:
    folder = Path(folder)
    if not folder.exists():
        return []
    names: list[str] = []
    for item in folder.iterdir():
        if item.is_dir():
            names.append(item.name)
        elif item.suffix.lower() == ".md":
            names.append(item.stem)
    return sorted(set(names))


def read_agents(agents_folder: Path) -> list[str]:
    """Return list of agent names (folder names or .md filenames)."""
    try:
        return _list_names(agents_folder)
    except OSError as e:
        log("ERROR", f"Could not read agents: {e}")
        return []


def read_plugins(plugins_folder: Path) -> list[str]:
    """Return list of plugin names."""
    try:
        return _list_names(plugins_folder)
    except OSError as e:
        log("ERROR", f"Could not read plugins: {e}")
        return []


def read_commands(commands_folder: Path) -> list[str]:
    """Return list of custom slash-command names."""
    try:
        return _list_names(commands_folder)
    except OSError as e:
        log("ERROR", f"Could not read commands: {e}")
        return []


def read_cowork_sessions(localappdata: Path) -> list[str]:
    """Glob Claude_* package folders under LocalAppData/Packages; return names only."""
    try:
        return [p.name for p in config.resolve_cowork_packages()]
    except OSError as e:
        log("ERROR", f"Could not read cowork sessions: {e}")
        return []


def read_root_claude_md(root_md_path: Path) -> dict:
    """Return {exists, word_count, content} for the root CLAUDE.md."""
    root_md_path = Path(root_md_path)
    if not root_md_path.exists():
        return {"exists": False, "word_count": 0, "content": ""}
    try:
        content = root_md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log("WARN", f"Could not read root CLAUDE.md: {e}")
        return {"exists": True, "word_count": 0, "content": ""}
    return {"exists": True, "word_count": _word_count(content), "content": content}


def _all_claude_md_text(root_md: dict, projects: list[dict]) -> str:
    parts = [root_md.get("content", "")]
    parts += [p.get("claude_md_content", "") for p in projects]
    return "\n".join(parts)


def score_pillars(analysis_data: dict) -> dict:
    """Score the 5 setup pillars per the rules in the build instructions."""
    root_md = analysis_data.get("root_claude_md", {})
    projects = analysis_data.get("projects", {})
    all_projects = list(projects.get("active", [])) + list(projects.get("abandoned", []))
    mcp = analysis_data.get("mcp_servers", [])
    all_text = analysis_data.get("_all_claude_md_text", "").lower()

    # profile
    if root_md.get("exists"):
        profile = "present" if root_md.get("word_count", 0) > 200 else "partial"
    else:
        profile = "missing"

    # writing_style
    matches = sum(1 for kw in STYLE_KEYWORDS if kw in all_text)
    if matches >= 3:
        writing_style = "present"
    elif matches >= 1:
        writing_style = "partial"
    else:
        writing_style = "missing"

    # projects
    if not all_projects:
        projects_score = "missing"
    elif any(p.get("has_claude_md") for p in all_projects):
        projects_score = "present"
    else:
        projects_score = "partial"

    # connectors
    n = len(mcp)
    connectors = "present" if n >= 3 else ("partial" if n >= 1 else "missing")

    return {
        "profile": profile,
        "memory": "unknown",  # cannot be read from files
        "writing_style": writing_style,
        "projects": projects_score,
        "connectors": connectors,
    }


def infer_domain_and_role(all_claude_md_text: str) -> dict:
    """Local text analysis: top domain terms + a mapped role. No external calls."""
    text = (all_claude_md_text or "").lower()
    words = [w for w in _WORD.findall(text) if w not in _STOPWORDS]
    freq = Counter(words)
    inferred_domains = [w for w, _ in freq.most_common(5)]

    best_role = "Professional (role not determined)"
    best_hits = 0
    for keywords, role in _ROLE_CLUSTERS:
        hits = sum(freq.get(k, 0) for k in keywords)
        if hits > best_hits:
            best_hits, best_role = hits, role

    return {"inferred_domains": inferred_domains, "inferred_role": best_role}


def _paths_for(source_root: Path) -> dict:
    """
    Build the source path map. If source_root is the live USERPROFILE, use SOURCE_PATHS
    (which resolves the real global-config + APPDATA locations). Otherwise derive paths
    relative to the given source_root (a copied old-profile folder).
    """
    sr = Path(source_root)
    if sr == config.USERPROFILE:
        return dict(SOURCE_PATHS)
    global_cfg = sr / ".claude.json"
    if not global_cfg.exists():
        alt = sr / ".claude" / "claude.json"
        global_cfg = alt if alt.exists() else global_cfg
    return {
        "claude_desktop_config": sr / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        "claude_appdata_folder": sr / "AppData" / "Roaming" / "Claude",
        "claude_code_global": global_cfg,
        "claude_root": sr / ".claude",
        "agents_folder": sr / ".claude" / "agents",
        "plugins_folder": sr / ".claude" / "plugins",
        "commands_folder": sr / ".claude" / "commands",
        "projects_folder": sr / ".claude" / "projects",
        "root_claude_md": sr / ".claude" / "CLAUDE.md",
        "style_guide": sr / ".claude" / "style-guide.md",
    }


def analyse(source_root: Path) -> dict:
    """Master analysis function. Reads the source machine, writes analysis_result.json."""
    source_root = Path(source_root)
    log("INFO", f"Analyse started. Source: {source_root}")
    paths = _paths_for(source_root)

    def safe(fn, *a, default=None):
        try:
            return fn(*a)
        except Exception as e:  # per spec: catch per module, never crash the run
            log("ERROR", f"{getattr(fn, '__name__', 'step')} failed: {e}")
            return default

    # MCP from desktop config AND global .claude.json (real Claude Code location), de-duped.
    mcp = safe(read_mcp_config, paths["claude_desktop_config"], default=[]) or []
    mcp += safe(read_mcp_config, paths["claude_code_global"], default=[]) or []
    seen, mcp_unique = set(), []
    for s in mcp:
        key = (s["name"], s.get("command", ""))
        if key not in seen:
            seen.add(key)
            mcp_unique.append(s)
    log("INFO", f"Found {len(mcp_unique)} MCP server(s)")

    projects = safe(read_projects, paths["projects_folder"], default=[]) or []
    cutoff = datetime.now() - timedelta(days=ACTIVE_PROJECT_DAYS)
    active, abandoned = [], []
    for p in projects:
        try:
            mod = datetime.fromisoformat(p["last_modified"])
        except (ValueError, KeyError):
            mod = datetime.now()
        (active if mod >= cutoff else abandoned).append(p)

    agents = safe(read_agents, paths["agents_folder"], default=[]) or []
    plugins = safe(read_plugins, paths["plugins_folder"], default=[]) or []
    commands = safe(read_commands, paths["commands_folder"], default=[]) or []
    cowork = safe(read_cowork_sessions, config.LOCALAPPDATA, default=[]) or []
    root_md = safe(read_root_claude_md, paths["root_claude_md"], default={"exists": False, "word_count": 0, "content": ""})

    all_text = _all_claude_md_text(root_md, projects)
    inferred = safe(infer_domain_and_role, all_text, default={"inferred_domains": [], "inferred_role": ""})

    vhdx_list = safe(config.resolve_cowork_vhdx, default=[]) or []
    vhdx_path = str(vhdx_list[0].parent) if vhdx_list else ""

    result = {
        "tool_version": TOOL_VERSION,
        "generated_at": datetime.now().isoformat(),
        "source_username": source_root.name or config.USERPROFILE.name,
        "source_root": str(source_root),
        "mcp_servers": mcp_unique,
        "projects": {"active": active, "abandoned": abandoned},
        "agents": agents,
        "plugins": plugins,
        "commands": commands,
        "cowork_sessions": cowork,
        "root_claude_md": root_md,
        "pillar_scores": {},
        "inferred_domains": inferred["inferred_domains"],
        "inferred_role": inferred["inferred_role"],
        "cowork_vhdx_path": vhdx_path,
    }
    # pillar scoring needs combined text + the structured pieces
    result["_all_claude_md_text"] = all_text
    result["pillar_scores"] = safe(score_pillars, result, default={})
    del result["_all_claude_md_text"]  # internal helper, not part of the output schema

    out_path = Path.cwd() / "analysis_result.json"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        log("INFO", f"Wrote {out_path}")
    except OSError as e:
        log("ERROR", f"Could not write analysis_result.json: {e}")

    return result
