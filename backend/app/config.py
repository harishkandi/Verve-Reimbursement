from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-secret-change-me-in-production-0000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite:///./reimbursement.db"
    jwt_secret: str = DEV_SECRET
    jwt_expiry_minutes: int = 12 * 60
    upload_dir: str = "./uploads"
    max_upload_mb: int = 10
    cors_origins: list[str] = ["http://localhost:5173"]
    app_url: str = "http://localhost:5173"

    # Email is only sent when SMTP_HOST is set; otherwise messages are logged.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "reimbursements@verve.example"

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


settings = Settings()

# A production deploy with the dev JWT secret would let anyone mint tokens.
if not settings.is_dev and settings.jwt_secret == DEV_SECRET:
    raise RuntimeError("JWT_SECRET must be set outside dev")
