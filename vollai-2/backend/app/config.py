"""Application configuration from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    neo4j_uri: str = "neo4j+s://65d988d7.databases.neo4j.io"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "3ivJaobtTEg6UpPdQYM4rs6J00cEKWDvzO-E2ZQMwWs"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    domain_id: str = "discovered-database"
    session_strategy: str = "per_conversation"
    backend_port: int = 8000
    frontend_port: int = 3000









    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
