import json

import analyser
import report_generator
import scaffold_generator

SECRET = "sk-ant-SECRETTOKEN1234567890ABCDEF"


def _build_source(root):
    (root / ".claude" / "projects" / "projA").mkdir(parents=True)
    (root / "AppData" / "Roaming" / "Claude").mkdir(parents=True)
    profile = ("# About Me\n" + "I run a waterproofing and flooring construction business. " * 30 +
               "\nI prefer concise bullet points. Always avoid jargon. My tone is formal.\n")
    (root / ".claude" / "CLAUDE.md").write_text(profile, encoding="utf-8")
    (root / ".claude" / "projects" / "projA" / "CLAUDE.md").write_text(
        "# Project A\nPrefer tables.\n", encoding="utf-8")
    cfg = {"mcpServers": {
        "filesystem": {"command": "npx", "args": ["-y", "server-fs", "C:\\Users\\OldName\\data"], "env": {}},
        "github": {"command": "node", "args": ["gh.js"], "env": {"GITHUB_TOKEN": SECRET}},
        "memory": {"command": "uvx", "args": ["mcp-memory"], "env": {}},
    }}
    (root / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json").write_text(
        json.dumps(cfg, indent=2), encoding="utf-8")


def test_analyse_scores_and_redacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "OldName"
    _build_source(src)

    res = analyser.analyse(src)
    assert len(res["mcp_servers"]) == 3
    assert res["pillar_scores"]["profile"] == "present"     # >200 words
    assert res["pillar_scores"]["connectors"] == "present"  # 3 servers
    assert res["pillar_scores"]["projects"] == "present"    # projA has CLAUDE.md
    assert res["pillar_scores"]["writing_style"] == "present"
    assert res["inferred_role"] == "Construction Business Owner"
    assert any(s["name"] == "github" and s["requires_token"] for s in res["mcp_servers"])
    # secret VALUE never written to the analysis output
    assert SECRET not in (tmp_path / "analysis_result.json").read_text(encoding="utf-8")


def test_scaffold_and_report_no_leak(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "OldName"
    _build_source(src)
    analysis = analyser.analyse(src)

    tgt = tmp_path / "NewName"
    tgt.mkdir()
    created = scaffold_generator.scaffold(analysis, target_root=tgt)
    names = {p.name for p in created}
    assert "style-guide.md" in names
    assert "connectors-todo.md" in names

    rep = report_generator.generate_report(analysis, created_files=created, target_root=tgt)
    text = rep.read_text(encoding="utf-8")
    assert "MCP Servers (3" in text
    assert SECRET not in text  # no secret leak anywhere in the report
