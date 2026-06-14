"""
main.py — CLI entry point. Wires analyser, preflight, scaffold, report, and the
safe transfer phase into commands:

    claude-migrate analyse   [--source PATH]
    claude-migrate preflight [--target PATH]
    claude-migrate transfer  --source PATH --target PATH [--yes]
    claude-migrate scaffold  [--from analysis_result.json] [--target PATH] [--yes]
    claude-migrate report    [--from analysis_result.json] [--target PATH]
    claude-migrate full      --source PATH --target PATH [--yes]

Destructive actions always confirm first (unless --yes).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
from pathlib import Path

import config
from config import log, safe_write
import analyser
import preflight as preflight_mod
import report_generator
import scaffold_generator
import security
from path_rewriter import rewrite_paths, scan_for_hardcoded_paths

try:
    from rich.console import Console
    _c = Console()
    def say(msg, style=None): _c.print(msg, style=style)
except Exception:
    def say(msg, style=None): print(msg)


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def try_elevate() -> bool:
    """
    Best-effort: try to relaunch elevated (UAC). Returns True if an elevated instance
    was launched (the caller should exit this one). Returns False if elevation was
    declined or unavailable — the caller then continues as a standard user, which is
    fine because the core migration only writes to the user's own profile.
    """
    if getattr(sys, "frozen", False):  # PyInstaller exe
        exe, params = sys.executable, ""
    else:  # running as a script
        exe, params = sys.executable, f'"{os.path.abspath(__file__)}"'
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return int(rc) > 32  # >32 == success; <=32 == declined/failed
    except Exception:
        return False


def _pause():
    try:
        input("\nPress Enter to continue...")
    except (EOFError, KeyboardInterrupt):
        pass


def _ask_path(prompt: str, default: Path) -> Path:
    try:
        raw = input(f"{prompt} [{default}]: ").strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        return default
    return Path(raw) if raw else default


def interactive_menu() -> None:
    """Menu shown on double-click (no CLI args)."""
    here = config.USERPROFILE
    say("\n" + "=" * 60, style="magenta")
    say("   CLAUDE MIGRATION TOOL  v" + config.TOOL_VERSION, style="bold magenta")
    say("=" * 60, style="magenta")
    say(f"   Administrator: {'YES' if is_admin() else 'no (some steps may be limited)'}",
        style=("green" if is_admin() else "yellow"))
    while True:
        say("\n  1. Full migration   (analyse -> preflight -> transfer -> scaffold -> report)")
        say("  2. Analyse this machine")
        say("  3. Pre-flight check (is this machine ready?)")
        say("  4. Scaffold smart setup (from analysis_result.json)")
        say("  5. Generate migration report")
        say("  6. Quit")
        try:
            choice = input("\n  Choose 1-6: ").strip().lstrip("﻿")
        except (EOFError, KeyboardInterrupt):
            return
        try:
            if choice == "1":
                src = _ask_path("Source profile path", here)
                tgt = _ask_path("Target profile path", here)
                cmd_full(argparse.Namespace(source=str(src), target=str(tgt), yes=False))
            elif choice == "2":
                src = _ask_path("Source profile path", here)
                cmd_analyse(argparse.Namespace(source=str(src)))
            elif choice == "3":
                cmd_preflight_nonexit(Path(here))
            elif choice == "4":
                tgt = _ask_path("Target profile path", here)
                cmd_scaffold(argparse.Namespace(from_file=None, target=str(tgt), yes=False))
            elif choice == "5":
                tgt = _ask_path("Target profile path", here)
                cmd_report(argparse.Namespace(from_file=None, target=str(tgt)))
            elif choice in ("6", "q", "quit", "exit"):
                say("Goodbye.", style="cyan")
                return
            else:
                say("Enter a number 1-6.", style="yellow")
                continue
        except SystemExit:
            pass  # don't let a sub-command exit the menu
        except Exception as e:
            say(f"Error: {e}", style="red")
        _pause()


def cmd_preflight_nonexit(target: Path) -> None:
    """Preflight for the menu (does not sys.exit)."""
    preflight_mod.run_preflight(target)


def confirm(question: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        say(f"{question} [non-interactive: defaulting to NO]", style="yellow")
        return False
    try:
        return input(f"{question} (y/n): ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _interactive_overwrite_prompt(question: str) -> str:
    if not sys.stdin or not sys.stdin.isatty():
        return "skip"
    try:
        return input(f"{question} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "skip"


def _load_analysis(from_path: str | None) -> dict:
    p = Path(from_path) if from_path else (Path.cwd() / "analysis_result.json")
    if not p.exists():
        say(f"analysis_result.json not found at {p}. Run 'analyse' first.", style="red")
        sys.exit(2)
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- transfer
def do_transfer(source: Path, target: Path, assume_yes: bool = False) -> list[dict]:
    """
    Safe copy from source to target:
      - claude_desktop_config.json: redact env values, rewrite paths, safe_write.
      - ~/.claude text artifacts (root CLAUDE.md, style-guide, project CLAUDE.md,
        agents, commands): copy when is_safe_to_copy, with backup.
    Returns the list of path-rewrites performed (for the report).
    """
    source, target = Path(source), Path(target)
    old_user, new_user = source.name, target.name
    say(f"\n== Transfer: {source} -> {target} ==", style="bold cyan")
    log("INFO", f"Transfer started. {source} -> {target} (user {old_user} -> {new_user})")
    rewrites: list[dict] = []

    # 1) desktop config: redact + rewrite + write
    src_cfg = source / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    dst_cfg = target / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    if src_cfg.exists():
        try:
            data = json.loads(src_cfg.read_text(encoding="utf-8"))
            for hit in scan_for_hardcoded_paths(data, old_user):
                rewrites.append({"server_name": hit.get("server_name") or "?", "old": hit["value"],
                                 "new": hit["value"].replace(old_user, new_user)})
            data = security.redact_env_values(data)
            data = rewrite_paths(data, old_user, new_user)
            if safe_write(dst_cfg, json.dumps(data, indent=2, ensure_ascii=False)):
                say(f"  config: redacted + path-fixed -> {dst_cfg}", style="green")
        except (json.JSONDecodeError, OSError) as e:
            log("ERROR", f"Transfer of desktop config failed: {e}")
            say(f"  config transfer failed: {e}", style="red")
    else:
        say("  desktop config not found on source — skipping.", style="yellow")

    # 2) ~/.claude text artifacts
    pairs = [
        (source / ".claude" / "CLAUDE.md", target / ".claude" / "CLAUDE.md"),
        (source / ".claude" / "style-guide.md", target / ".claude" / "style-guide.md"),
    ]
    # project CLAUDE.md files
    src_projects = source / ".claude" / "projects"
    if src_projects.exists():
        for sub in src_projects.iterdir():
            md = sub / "CLAUDE.md"
            if md.exists():
                pairs.append((md, target / ".claude" / "projects" / sub.name / "CLAUDE.md"))
    # agents + commands
    for folder in ("agents", "commands"):
        src_folder = source / ".claude" / folder
        if src_folder.exists():
            for item in src_folder.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(source)
                    pairs.append((item, target / rel))

    copied = skipped = 0
    for src, dst in pairs:
        if not src.exists():
            continue
        ok, reason = security.is_safe_to_copy(src)
        if not ok:
            skipped += 1
            log("WARN", f"Skipped (security) {src}: {reason}")
            say(f"  skip {src.name}: {reason}", style="yellow")
            continue
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
            if old_user and old_user != new_user:
                text = text.replace(f"C:\\Users\\{old_user}", f"C:\\Users\\{new_user}").replace(
                    f"/Users/{old_user}", f"/Users/{new_user}")
            if safe_write(dst, text):
                copied += 1
        except OSError as e:
            log("ERROR", f"Copy failed {src}: {e}")

    say(f"  transferred {copied} file(s), skipped {skipped}.", style="green")
    log("INFO", f"Transfer complete. copied={copied} skipped={skipped} rewrites={len(rewrites)}")
    return rewrites


# --------------------------------------------------------------------------- commands
def cmd_analyse(args):
    source = Path(args.source) if args.source else config.USERPROFILE
    res = analyser.analyse(source)
    say(f"Analysis written to analysis_result.json", style="green")
    say(f"  MCP servers: {len(res['mcp_servers'])} | "
        f"projects: {len(res['projects']['active'])} active / {len(res['projects']['abandoned'])} inactive | "
        f"pillars: {res['pillar_scores']}", style="cyan")


def cmd_preflight(args):
    result = preflight_mod.run_preflight(Path(args.target) if args.target else None)
    sys.exit(0 if result["ok"] else 1)


def cmd_transfer(args):
    if not confirm("Begin transfer (writes config + files to target, backing up existing)?", args.yes):
        say("Transfer cancelled.", style="yellow"); return
    do_transfer(Path(args.source), Path(args.target), args.yes)


def cmd_scaffold(args):
    analysis = _load_analysis(args.from_file)
    target = Path(args.target) if args.target else config.USERPROFILE
    created = scaffold_generator.scaffold(analysis, target_root=target,
                                          prompt_fn=_interactive_overwrite_prompt)
    say(f"Scaffold complete: {len(created)} file(s) created.", style="green")
    for c in created:
        say(f"  {c}")


def cmd_report(args):
    analysis = _load_analysis(args.from_file)
    target = Path(args.target) if args.target else config.USERPROFILE
    p = report_generator.generate_report(analysis, target_root=target)
    say(f"Report written: {p}", style="green")


def cmd_full(args):
    source, target = Path(args.source), Path(args.target)
    say("=== FULL MIGRATION PIPELINE ===", style="bold magenta")

    say("\n[1/5] Analyse source", style="bold")
    analysis = analyser.analyse(source)

    say("\n[2/5] Preflight target", style="bold")
    pf = preflight_mod.run_preflight(target)
    if not pf["ok"]:
        say("Critical preflight failure — stopping. Fix the items above and re-run.", style="bold red")
        sys.exit(1)
    if not confirm("Continue to transfer?", args.yes):
        say("Stopped before transfer.", style="yellow"); return

    say("\n[3/5] Transfer", style="bold")
    rewrites = do_transfer(source, target, args.yes)
    if not confirm("Continue to scaffold?", args.yes):
        say("Stopped before scaffold.", style="yellow"); return

    say("\n[4/5] Scaffold", style="bold")
    created = scaffold_generator.scaffold(analysis, target_root=target,
                                          prompt_fn=_interactive_overwrite_prompt,
                                          preflight_results=pf["results"])

    say("\n[5/5] Report", style="bold")
    report_generator.generate_report(analysis, created_files=created, preflight_results=pf["results"],
                                     path_rewrites=rewrites, target_root=target)
    say("\nMigration pipeline complete. Read MIGRATION-REPORT.md in ~/.claude.", style="bold green")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude-migrate", description="Claude Setup Intelligence & Migration Tool")
    p.add_argument("--version", action="version", version=f"claude-migrate {config.TOOL_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyse", help="Read the source machine, write analysis_result.json")
    a.add_argument("--source", help="Source user-profile path (default: current USERPROFILE)")
    a.set_defaults(func=cmd_analyse)

    pf = sub.add_parser("preflight", help="Validate the target machine")
    pf.add_argument("--target", help="Target user-profile path (default: current USERPROFILE)")
    pf.set_defaults(func=cmd_preflight)

    t = sub.add_parser("transfer", help="Copy config + files from source to target (safe)")
    t.add_argument("--source", required=True)
    t.add_argument("--target", required=True)
    t.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    t.set_defaults(func=cmd_transfer)

    s = sub.add_parser("scaffold", help="Generate scaffold files on the target")
    s.add_argument("--from", dest="from_file", help="analysis_result.json path")
    s.add_argument("--target")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_scaffold)

    r = sub.add_parser("report", help="Generate MIGRATION-REPORT.md")
    r.add_argument("--from", dest="from_file", help="analysis_result.json path")
    r.add_argument("--target")
    r.set_defaults(func=cmd_report)

    f = sub.add_parser("full", help="analyse -> preflight -> transfer -> scaffold -> report")
    f.add_argument("--source", required=True)
    f.add_argument("--target", required=True)
    f.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    f.set_defaults(func=cmd_full)
    return p


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # Bare launch (double-click): elevate to admin, then show the interactive menu.
    if not argv:
        if not is_admin():
            if try_elevate():
                return  # elevated instance launched; this un-elevated one exits
            # Elevation declined/unavailable -> continue as standard user (core migration
            # writes only to the user's own profile and does not require admin).
            say("Running without administrator rights. Core migration still works; only "
                "machine-wide steps (system env vars) may be limited.", style="yellow")
        interactive_menu()
        return
    # CLI usage stays un-elevated and scriptable.
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
