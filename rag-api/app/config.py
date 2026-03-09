from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    anthropic_api_key: str
    anthropic_model: str = "claude-haiku-4-5-20251001"
    embed_model: str = "all-mpnet-base-v2"
    upload_dir: str = "./data/uploads"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    redis_url: str = "redis://localhost:6379/0"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings: Settings = get_settings()
