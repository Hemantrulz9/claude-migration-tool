"""
security.py — ensure no secrets are ever written to export files or logs.

Three responsibilities:
  - redact_env_values: blank MCP env VALUES (keep keys) before any config is written.
  - detect_secrets_in_file: flag lines that look like they contain secrets.
  - is_safe_to_copy: gate every file copy on filename patterns + secret detection.
"""

from __future__ import annotations

import copy
import re
from fnmatch import fnmatch
from pathlib import Path

from config import NEVER_COPY_PATTERNS, log

REDACTED = "[REDACTED - re-enter on new machine]"

# Patterns that strongly indicate a secret value.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),          # OpenAI / Anthropic style
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),       # Anthropic
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),       # GitHub tokens
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),    # Slack
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),          # Google API key
    re.compile(r"AKIA[0-9A-Z]{16}"),                 # AWS access key id
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),  # JWT
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.=]{16,}"),
    re.compile(r"(?i)(token|api[_-]?key|secret|password)\s*[=:]\s*['\"]?[^\s'\"]{12,}"),
]

# A bare long alphanumeric token (no spaces), used as a weaker heuristic.
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")


def redact_env_values(config: dict) -> dict:
    """
    Walk mcpServers[*].env in the config dict and replace every VALUE with REDACTED.
    Keys are preserved. Returns a deep copy; the input is not mutated.
    Never logs the original values.
    """
    if not isinstance(config, dict):
        return config
    result = copy.deepcopy(config)
    servers = result.get("mcpServers")
    if isinstance(servers, dict):
        for name, server in servers.items():
            if isinstance(server, dict) and isinstance(server.get("env"), dict):
                redacted_keys = list(server["env"].keys())
                server["env"] = {k: REDACTED for k in redacted_keys}
                if redacted_keys:
                    log("INFO", f"Redacted {len(redacted_keys)} env value(s) for MCP server '{name}'")
    return result


def detect_secrets_in_file(file_path: Path) -> list[int]:
    """
    Scan a text file for lines that look like they contain secrets.
    Returns a sorted list of 1-based line numbers where secrets are suspected.
    Returns [] for binary/unreadable files (logged as WARN).
    """
    file_path = Path(file_path)
    hits: set[int] = set()
    try:
        with open(file_path, "r", encoding="utf-8", errors="strict") as fh:
            lines = fh.readlines()
    except (UnicodeDecodeError, OSError):
        # Binary or unreadable: cannot scan; treat as not-a-text-secret here.
        log("WARN", f"Could not text-scan for secrets: {file_path}")
        return []

    for i, line in enumerate(lines, start=1):
        if any(p.search(line) for p in _SECRET_PATTERNS):
            hits.add(i)
            continue
        # weaker heuristic: a long bare token alongside a secret-ish key word
        if _LONG_TOKEN.search(line) and re.search(r"(?i)token|key|secret|auth|pass|cred", line):
            hits.add(i)
    return sorted(hits)


def is_safe_to_copy(file_path: Path) -> tuple[bool, str]:
    """
    Returns (True, "") if the file is safe to copy.
    Returns (False, reason) if it must NOT be copied.

    Blocks when:
      - filename matches a NEVER_COPY_PATTERNS entry, or
      - detect_secrets_in_file finds suspected secrets.
    """
    file_path = Path(file_path)
    name = file_path.name
    for pattern in NEVER_COPY_PATTERNS:
        if fnmatch(name.lower(), pattern.lower()):
            return False, f"filename matches never-copy pattern '{pattern}'"

    secret_lines = detect_secrets_in_file(file_path)
    if secret_lines:
        preview = ", ".join(str(n) for n in secret_lines[:5])
        return False, f"suspected secret(s) on line(s): {preview}"

    return True, ""
