from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://diamondscope:changeme_in_prod@db:5432/diamondscope"
    cors_origins: str = "http://localhost:5173"

    jwt_secret: str = "dev_secret_change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    admin_email: str = "bkasman95@gmail.com"
    admin_password: str = "changeme"

    cache_dir: str = "/app/cache"
    default_season_window: int = 6

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
