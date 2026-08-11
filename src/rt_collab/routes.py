"""Plain HTTP routes (not WebSocket, not health/ready probes).

There's no user/password store in this project — auth is scoped to proving the
WebSocket layer rejects unauthenticated handshakes, not building an identity
provider. This endpoint stands in for "the client already authenticated with
whatever real IdP the product has, and is now exchanging that for a short-lived
gateway session token."
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from rt_collab.ws.auth import issue_token

router = APIRouter()


class TokenRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    token: str


@router.post("/auth/token", response_model=TokenResponse)
async def create_token(request: TokenRequest) -> TokenResponse:
    return TokenResponse(token=issue_token(request.client_id))
