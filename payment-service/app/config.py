from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения"""
    
    # База данных
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/payments"
    
    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    
    # API
    api_key: str = "change-me-in-production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Outbox Publisher
    outbox_publish_interval: int = 5  # секунды
    outbox_batch_size: int = 100
    
    # Логирование
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


settings = Settings()
