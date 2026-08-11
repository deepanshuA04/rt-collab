"""Runtime configuration for the gateway, sourced from environment variables / .env."""

from __future__ import annotations

import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RT_", extra="ignore")

    # Identity of this gateway process. Every Pub/Sub message is tagged with this id
    # so an instance can recognize and skip its own re-published messages (loop prevention).
    instance_id: str = str(uuid.uuid4())

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

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )


settings = Settings()
