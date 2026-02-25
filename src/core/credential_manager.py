from __future__ import annotations

try:
    import keyring as _keyring
except ModuleNotFoundError:
    _keyring = None


def _set_password(service: str, username: str, token: str) -> None:
    if _keyring is None:
        raise RuntimeError("keyring package is not installed. Install dependencies to use credential storage.")
    _keyring.set_password(service, username, token)


def _get_password(service: str, username: str) -> str | None:
    if _keyring is None:
        raise RuntimeError("keyring package is not installed. Install dependencies to use credential storage.")
    return _keyring.get_password(service, username)


class CredentialManager:
    def set_token(self, service: str, username: str, token: str) -> None:
        _set_password(service, username, token)

    def get_token(self, service: str, username: str) -> str | None:
        return _get_password(service, username)
