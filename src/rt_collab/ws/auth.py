"""WebSocket handshake auth: signed, timed tokens (no user/password store here —
see rt_collab.routes.issue_token for what "logging in" means in this project)."""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from rt_collab.config import settings

_SALT = "rt-collab-ws-token"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.auth_secret, salt=_SALT)


def issue_token(client_id: str) -> str:
    return _serializer().dumps({"client_id": client_id})


def verify_token(token: str) -> str | None:
    """Returns the client_id if `token` is validly signed and unexpired, else None."""
    try:
        data = _serializer().loads(token, max_age=settings.auth_token_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    client_id = data.get("client_id")
    return client_id if isinstance(client_id, str) and client_id else None
