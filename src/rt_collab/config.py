"""Runtime configuration for the gateway, sourced from environment variables / .env."""

from __future__ import annotations

import uuid

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RT_", extra="ignore")

    # Identity of this gateway process. Every Pub/Sub message is tagged with this id
    # so an instance can recognize and skip its own re-published messages (loop prevention).
    # default_factory (not a bare default) so each Settings() instantiation gets its
    # own id instead of all instances sharing one value computed at class-definition time.
    instance_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    environment: str = "development"
    log_level: str = "INFO"

    redis_url: str = "redis://localhost:6379/0"

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "rt_collab"
    mysql_password: str = "rt_collab"
    mysql_database: str = "rt_collab"

    # Shared secret used to sign/verify connection tokens presented at the WebSocket
    # handshake. In production this should come from a real secrets manager.
    auth_secret: str = "dev-secret-change-me"
    auth_token_max_age_seconds: int = 24 * 60 * 60

    # Bounded outbound backlog per WebSocket connection. When a client can't keep up
    # and this fills, the connection is dropped rather than the message silently
    # discarded — see rt_collab.ws.registry.Connection.enqueue for why.
    ws_send_queue_maxsize: int = 32

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )


settings = Settings()
