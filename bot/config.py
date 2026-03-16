from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Telegram
    bot_token: str

    # Security
    encryption_key: str

    # Database
    db_path: str = "data/bot.db"

    # Logging
    log_level: str = "INFO"

    # Admin — Telegram user ID allowed to use the bot (0 = no restriction)
    admin_user_id: int = 0

    # Trading defaults per pair
    @staticmethod
    def default_params(pair: str) -> dict:
        if pair == "BTCUSDC":
            return {"profit_pct": 0.7, "drop_pct": 0.6}
        # KAS, XRP, SOL
        return {"profit_pct": 0.6, "drop_pct": 0.9}


settings = Settings()  # type: ignore[call-arg]
