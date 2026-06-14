import security


def test_redact_env_values_blanks_values_keeps_keys():
    cfg = {"mcpServers": {"fs": {"command": "npx",
           "env": {"API_KEY": "sk-ant-abcdefghij1234567890", "FOO": "bar"}}}}
    red = security.redact_env_values(cfg)
    assert red["mcpServers"]["fs"]["env"]["API_KEY"] == security.REDACTED
    assert "API_KEY" in red["mcpServers"]["fs"]["env"]            # key preserved
    assert cfg["mcpServers"]["fs"]["env"]["API_KEY"].startswith("sk-ant")  # input not mutated


def test_detect_secrets_in_file(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("normal\napi_key=sk-ant-abcdefghij1234567890ZZZZ\nplain\nBearer abcdefghijklmnop1234567890\n",
                 encoding="utf-8")
    hits = security.detect_secrets_in_file(f)
    assert 2 in hits and 4 in hits


def test_is_safe_to_copy_blocks_credentials_and_secrets(tmp_path):
    creds = tmp_path / ".credentials.json"
    creds.write_text("{}", encoding="utf-8")
    ok, reason = security.is_safe_to_copy(creds)
    assert ok is False and "never-copy" in reason

    secret = tmp_path / "notes.md"
    secret.write_text("token=sk-ant-abcdefghij1234567890ZZZZ\n", encoding="utf-8")
    ok2, _ = security.is_safe_to_copy(secret)
    assert ok2 is False

    clean = tmp_path / "CLAUDE.md"
    clean.write_text("# notes about tone and voice\n", encoding="utf-8")
    ok3, _ = security.is_safe_to_copy(clean)
    assert ok3 is True
