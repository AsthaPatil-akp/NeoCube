from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    database_url: str = "sqlite:///./app.db"
    secret_key: str = "dev-only-change-me"
    cookie_secure: bool = False
    frontend_origin: str = "http://localhost:5173"
    environment: str = "development"
    upload_dir: str = "uploads"
    max_upload_bytes: int = 5_000_000
    admin_email: str | None = None
    admin_password: str | None = None
    model_dir: str = "models"
    n8n_webhook_url: str | None = None
    ai_product_finder_enabled: bool = True
    vision_model_dir: str = "models/vision"
    vision_dataset_dir: str = "vision_dataset"
    max_product_image_bytes: int = 5_000_000

    @property
    def session_https_only(self) -> bool:
        if self.environment.lower() == "production":
            return True
        return self.cookie_secure


settings = Settings()
