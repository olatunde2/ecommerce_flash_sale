from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://flashsale:flashsale@localhost:5432/flashsale"
    )
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "amqp://flashsale:flashsale@localhost:5672//"
    rate_limit_requests: int = Field(default=100, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    invoice_output_dir: str = "./invoices"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
