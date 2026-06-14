import path_rewriter as pr


def _cfg():
    return {
        "mcpServers": {
            "filesystem": {"command": "npx", "args": ["-y", "server-fs", "C:\\Users\\OldName\\data"],
                           "env": {"ROOT": "C:\\Users\\OldName\\proj"}},
            "other": {"command": "node", "args": ["/Users/OldName/app.js"]},
        },
        "unrelated": "no path here",
    }


def test_scan_finds_hardcoded_paths_and_server_names():
    hits = pr.scan_for_hardcoded_paths(_cfg(), "OldName")
    assert len(hits) == 3
    assert any(h["server_name"] == "filesystem" for h in hits)


def test_rewrite_paths_windows_and_posix():
    cfg = _cfg()
    new = pr.rewrite_paths(cfg, "OldName", "NewName")
    assert new["mcpServers"]["filesystem"]["args"][2] == "C:\\Users\\NewName\\data"
    assert new["mcpServers"]["filesystem"]["env"]["ROOT"] == "C:\\Users\\NewName\\proj"
    assert new["mcpServers"]["other"]["args"][0] == "/Users/NewName/app.js"
    # input not mutated
    assert "OldName" in str(cfg)


def test_rewrite_noop_when_same_user():
    cfg = _cfg()
    out = pr.rewrite_paths(cfg, "Same", "Same")
    assert out == cfg
