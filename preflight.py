"""
preflight.py — Module 2. Validate the TARGET machine before any restore/scaffold.

Prints clear pass/warn/fail per check. A failed CRITICAL check blocks the operation.
Uses `rich` for colour if available; degrades gracefully to plain text otherwise.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import config
from config import CLAUDE_PROCESS_NAME, log

# Optional colour output.
try:
    from rich.console import Console
    _console = Console()

    def _say(msg, style=None):
        _console.print(msg, style=style)
except Exception:  # rich not installed yet
    def _say(msg, style=None):
        print(msg)


PREFLIGHT_CHECKS = [
    {"name": "Node.js", "command": ["node", "--version"], "min_version": "18", "critical": False,
     "fail_message": "Some MCP servers need Node.js 18+.", "fix_command": "winget install OpenJS.NodeJS.LTS"},
    {"name": "Python", "command": ["python", "--version"], "min_version": "3.10", "critical": False,
     "fail_message": "Some MCP servers need Python 3.10+.", "fix_command": "winget install Python.Python.3.12"},
    {"name": "uv", "command": ["uv", "--version"], "min_version": None, "critical": False,
     "fail_message": "uv not found. Some MCP servers require it.", "fix_command": "winget install astral-sh.uv"},
    {"name": "Claude Desktop installed", "type": "path_exists", "path": "CLAUDE_DESKTOP_INSTALL", "critical": True,
     "fail_message": "Claude Desktop not found. Install it before restoring config.",
     "fix_command": "Download from https://claude.ai/download"},
    {"name": "Claude Desktop not running", "type": "process_not_running", "process": "claude.exe", "critical": True,
     "fail_message": "Claude Desktop is running. Close it completely before restore.",
     "fix_command": "Right-click system tray icon -> Quit"},
    {"name": "Disk space", "type": "disk_space", "min_mb": 500, "critical": False,
     "fail_message": "Less than 500MB free. Ensure sufficient disk space.",
     "fix_command": "Free up disk space on target drive"},
]


def _version_tuple(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text or "")
    if not m:
        return ()
    return tuple(int(g) for g in m.groups() if g is not None)


def _meets_min(found: str, minimum: str | None) -> bool:
    if not minimum:
        return True
    fv, mv = _version_tuple(found), _version_tuple(minimum)
    return fv >= mv if fv and mv else True


def _check_command(chk: dict) -> tuple[str, str]:
    try:
        proc = subprocess.run(chk["command"], capture_output=True, text=True, timeout=15)
        out = (proc.stdout or "") + (proc.stderr or "")
        ver = out.strip().splitlines()[0] if out.strip() else ""
        if not ver:
            return "fail", "not found / no version"
        if _meets_min(ver, chk.get("min_version")):
            return "pass", ver
        return "fail", f"{ver} (need >= {chk['min_version']})"
    except (FileNotFoundError, OSError):
        return "fail", "not installed"
    except subprocess.TimeoutExpired:
        return "fail", "version check timed out"


def _check_path_exists(chk: dict) -> tuple[str, str]:
    # Use the robust resolver (covers installer + Store builds).
    found = config.resolve_desktop_install()
    if found:
        return "pass", str(found)
    return "fail", f"not found (checked {len(config.CLAUDE_DESKTOP_INSTALL_CANDIDATES)} locations)"


def _check_process_not_running(chk: dict) -> tuple[str, str]:
    proc_name = chk.get("process", CLAUDE_PROCESS_NAME)
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {proc_name}"],
                             capture_output=True, text=True, timeout=15)
        if proc_name.lower() in (out.stdout or "").lower():
            return "fail", f"{proc_name} is running"
        return "pass", "not running"
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return "warn", "could not determine (tasklist unavailable)"


def _check_disk_space(chk: dict, target: Path) -> tuple[str, str]:
    try:
        usage = shutil.disk_usage(str(target))
        free_mb = usage.free // (1024 * 1024)
        if free_mb >= chk.get("min_mb", 0):
            return "pass", f"{free_mb} MB free"
        return "fail", f"only {free_mb} MB free (need >= {chk['min_mb']} MB)"
    except OSError as e:
        return "warn", f"could not check: {e}"


def run_preflight(target: Path | None = None) -> dict:
    """
    Run all preflight checks. Returns {"ok": bool, "results": [...]}.
    ok is False if any CRITICAL check failed (caller should halt).
    """
    target = Path(target) if target else config.USERPROFILE
    _say("\n== Checking whether this PC is ready for Claude ==", style="bold cyan")
    results = []
    critical_failed = False

    for chk in PREFLIGHT_CHECKS:
        ctype = chk.get("type", "command")
        if ctype == "command":
            status, detail = _check_command(chk)
        elif ctype == "path_exists":
            status, detail = _check_path_exists(chk)
        elif ctype == "process_not_running":
            status, detail = _check_process_not_running(chk)
        elif ctype == "disk_space":
            status, detail = _check_disk_space(chk, target)
        else:
            status, detail = "warn", "unknown check type"

        is_critical = chk.get("critical", False)
        if status == "fail" and not is_critical:
            status = "warn"  # non-critical failures are warnings

        if status == "pass":
            _say(f"  [PASS] {chk['name']}: {detail}", style="green")
            log("INFO", f"Preflight PASS {chk['name']}: {detail}")
        elif status == "warn":
            _say(f"  [WARN] {chk['name']}: {detail}", style="yellow")
            _say(f"         {chk.get('fail_message','')}  Fix: {chk.get('fix_command','')}", style="yellow")
            log("WARN", f"Preflight WARN {chk['name']}: {detail} | {chk.get('fail_message','')}")
        else:  # fail + critical
            critical_failed = True
            _say(f"  [FAIL] {chk['name']}: {detail}", style="bold red")
            _say(f"         {chk.get('fail_message','')}  Fix: {chk.get('fix_command','')}", style="red")
            log("ERROR", f"Preflight FAIL (critical) {chk['name']}: {detail} | {chk.get('fail_message','')}")

        results.append({
            "name": chk["name"], "status": status, "detail": detail,
            "critical": is_critical, "fix_command": chk.get("fix_command", ""),
        })

    ok = not critical_failed
    if ok:
        _say("\nThis PC is ready. You can go ahead.", style="bold green")
    else:
        _say("\nNot ready yet - fix the item(s) marked [FAIL] above, then run this again.", style="bold red")
    log("INFO", f"Preflight complete. ok={ok}")
    return {"ok": ok, "results": results}
