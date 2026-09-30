from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.infisical import load_infisical_secrets

load_infisical_secrets()


class Settings(BaseSettings):
    """Application settings loaded after the optional Infisical bootstrap."""

    PROJECT_NAME: str = "Ouros Knowledge MCP"
    DESCRIPTION: str = "FastAPI and MCP server for Qdrant knowledge retrieval."
    VERSION: str = "0.1.0"
    APP_PORT: int = 8000
    APP_NAME: str = "ouros_knowledge_mcp"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: SecretStr | None = None
    QDRANT_COLLECTION_NAME: str = "ouros_knowledge"
    NVIDIA_API_KEY: SecretStr | None = None
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_EMBEDDING_MODEL: str = "nvidia/nemotron-3-embed-1b"
    NVIDIA_NIM_URL: str | None = None
    NVIDIA_NIM_MODEL: str = "meta/llama-3.1-70b-instruct"
    NVIDIA_NIM_TIMEOUT: int = 60
    IMPORT_MARKDOWN_MAX_CHARS: int = 120_000
    SEARCH_TOP_K: int = Field(default=5, ge=1)
    SEARCH_MAX_K: int = Field(default=20, ge=1)
    MIDAS_DATABASE_URL: SecretStr | None = None
    MIDAS_IMPORT_DATABASE_URL: SecretStr | None = None
    MIDAS_DB_CONNECT_TIMEOUT: int = 10
    MCP_RESOURCE_URL: str = "http://localhost:8000/mcp"
    MCP_JWT_ISSUER: str = "https://ouros-keycloak.discloud.app/realms/ouros"
    MCP_JWT_AUDIENCE: str = "ms-mcp-server-ouros-knowledge"
    MCP_JWT_AUTHORIZED_PARTY: str = "ms-ai-server-mcp-exchange"
    MCP_METRICS_KEYCLOAK_AUTHORIZED_PARTY: str = "ouros-prometheus"
    MCP_JWKS_URL: str | None = None
    TELEMETRY_JWT_AUDIENCE: str = "ms-telemetry-dashboard-service"
    TELEMETRY_DASHBOARD_API_URL: str | None = None
    TELEMETRY_DASHBOARD_API_TIMEOUT_SECONDS: float = Field(default=20, gt=0, le=60)

    @field_validator(
        "QDRANT_API_KEY",
        "NVIDIA_API_KEY",
        "MIDAS_DATABASE_URL",
        "MIDAS_IMPORT_DATABASE_URL",
        mode="before",
    )
    @classmethod
    def empty_secret_to_none(cls, value):
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("TELEMETRY_DASHBOARD_API_URL")
    @classmethod
    def validate_telemetry_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("TELEMETRY_DASHBOARD_API_URL inválida")
        if parsed.scheme != "https" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("TELEMETRY_DASHBOARD_API_URL deve usar HTTPS")
        return value

    @model_validator(mode="after")
    def validate_keycloak_jwt_config(self) -> "Settings":
        if self.SEARCH_MAX_K < self.SEARCH_TOP_K:
            raise ValueError(
                "SEARCH_MAX_K deve ser maior ou igual a SEARCH_TOP_K"
            )

        self.MCP_JWT_ISSUER = self.MCP_JWT_ISSUER.strip()
        self.MCP_JWT_AUDIENCE = self.MCP_JWT_AUDIENCE.strip()
        self.MCP_JWT_AUTHORIZED_PARTY = self.MCP_JWT_AUTHORIZED_PARTY.strip()
        self.MCP_METRICS_KEYCLOAK_AUTHORIZED_PARTY = self.MCP_METRICS_KEYCLOAK_AUTHORIZED_PARTY.strip()
        self.TELEMETRY_JWT_AUDIENCE = self.TELEMETRY_JWT_AUDIENCE.strip()

        if (
            not self.MCP_JWT_ISSUER
            or not self.MCP_JWT_AUDIENCE
            or not self.MCP_JWT_AUTHORIZED_PARTY
            or not self.MCP_METRICS_KEYCLOAK_AUTHORIZED_PARTY
            or not self.TELEMETRY_JWT_AUDIENCE.strip()
        ):
            raise ValueError(
                "issuer, audiences e authorized party do Keycloak são obrigatórios"
            )
        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
