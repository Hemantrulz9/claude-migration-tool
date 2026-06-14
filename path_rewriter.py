"""
path_rewriter.py — fix hardcoded user paths so configs work on the new machine.

Hardcoded C:\\Users\\<oldname> paths in MCP args/env are the #1 cause of silent
migration failures. These helpers detect and rewrite them.
"""

from __future__ import annotations

import re

from config import log

# Matches Windows (C:\Users\name) and POSIX (/Users/name) user-home prefixes.
_HARDCODED_RE = re.compile(r"(?i)[A-Za-z]:\\Users\\[^\\/\"']+|/Users/[^/\"']+")


def _walk(node, location: str, server_name: str | None, visit):
    """Recursively walk dict/list/str, calling visit(location, value, server_name) on strings.
    Returns the (possibly rebuilt) node so callers can use this for transforms too."""
    if isinstance(node, dict):
        new = {}
        for key, value in node.items():
            child_loc = f"{location}.{key}" if location else str(key)
            # track the MCP server name when we descend into mcpServers.<name>
            child_server = server_name
            if location.endswith("mcpServers") or location == "mcpServers":
                child_server = str(key)
            new[key] = _walk(value, child_loc, child_server, visit)
        return new
    if isinstance(node, list):
        return [_walk(v, f"{location}[{i}]", server_name, visit) for i, v in enumerate(node)]
    if isinstance(node, str):
        return visit(location, node, server_name)
    return node


def scan_for_hardcoded_paths(config: dict, current_username: str) -> list[dict]:
    """
    Walk the config recursively. Return a list of:
      { "location": "dotted.path", "value": "<string with hardcoded path>", "server_name": "<mcp server or None>" }
    """
    found: list[dict] = []

    def visit(location, value, server_name):
        if _HARDCODED_RE.search(value):
            found.append({"location": location, "value": value, "server_name": server_name})
        return value

    _walk(config, "", None, visit)
    return found


def rewrite_paths(config: dict, old_username: str, new_username: str) -> dict:
    """
    Recursively replace C:\\Users\\{old_username} and /Users/{old_username} with the
    new username's equivalent. Returns a rewritten copy. Logs every replacement.
    """
    if not old_username or old_username == new_username:
        log("INFO", "Path rewrite skipped (no username change).")
        return config

    replacements = [
        (f"C:\\Users\\{old_username}", f"C:\\Users\\{new_username}"),
        (f"/Users/{old_username}", f"/Users/{new_username}"),
    ]
    count = {"n": 0}

    def visit(location, value, server_name):
        new_value = value
        for old, new in replacements:
            # case-insensitive replace for the Windows form, exact for POSIX
            if "\\Users\\" in old:
                pattern = re.compile(re.escape(old), re.IGNORECASE)
                if pattern.search(new_value):
                    # function replacement avoids backslash interpretation in the replacement string
                    new_value = pattern.sub(lambda _m: new, new_value)
            else:
                if old in new_value:
                    new_value = new_value.replace(old, new)
        if new_value != value:
            count["n"] += 1
            where = f"{location}" + (f" (server '{server_name}')" if server_name else "")
            log("INFO", f"Path rewritten at {where}: {old_username} -> {new_username}")
        return new_value

    result = _walk(config, "", None, visit)
    log("INFO", f"Path rewrite complete: {count['n']} string(s) changed.")
    return result
