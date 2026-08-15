from ingest.cli import supabase_backend_key


def test_backend_key_prefers_current_secret_key(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_current")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy")

    assert supabase_backend_key() == "sb_secret_current"


def test_backend_key_falls_back_to_legacy_service_role(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "legacy")

    assert supabase_backend_key() == "legacy"
