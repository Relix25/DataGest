from __future__ import annotations

import core.credential_manager as credential_module
from core.credential_manager import CredentialManager


def test_set_and_get_token_with_keyring(monkeypatch) -> None:
    store: dict[tuple[str, str], str] = {}

    def fake_set_password(service: str, username: str, token: str) -> None:
        store[(service, username)] = token

    def fake_get_password(service: str, username: str) -> str | None:
        return store.get((service, username))

    monkeypatch.setattr(credential_module, "_set_password", fake_set_password)
    monkeypatch.setattr(credential_module, "_get_password", fake_get_password)

    manager = CredentialManager()
    manager.set_token("datagest", "user1", "secret-token")

    assert manager.get_token("datagest", "user1") == "secret-token"
