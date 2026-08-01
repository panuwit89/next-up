from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from finance.services.symbols import resolve_stock_symbol


load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LINE_CHANNEL_SECRET: str = ""
    LINE_CHANNEL_ACCESS_TOKEN: str = ""
    LINE_USER_ID: str = ""

    # LLM — Gemini (Google Generative Language REST API)
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GOOGLE_API_KEY: str = ""

    NEWSAPI_KEY: str = ""

    # Price fallback. Yahoo's chart endpoint blocks Render's shared egress IPs
    # with HTTP 429, so a keyed provider is required in production.
    TWELVEDATA_API_KEY: str = ""

    SCHEDULE_DAY_OF_WEEK: str = "mon"
    SCHEDULE_HOUR: int = Field(default=10, ge=0, le=23)
    SCHEDULE_MINUTE: int = Field(default=0, ge=0, le=59)
    TIMEZONE: str = "Asia/Bangkok"

    STOCK_SYMBOLS: str = "tsmc,nvidia"
    NEWS_QUERY: str = "technology OR finance OR stocks OR AI"

    @field_validator("STOCK_SYMBOLS")
    @classmethod
    def validate_csv(cls, value: str) -> str:
        values = [item.strip() for item in value.split(",") if item.strip()]
        if not values:
            raise ValueError("must contain at least one value")
        return ",".join(values)

    @property
    def stock_symbols(self) -> list[str]:
        symbols = []
        for item in self.STOCK_SYMBOLS.split(","):
            if not item.strip():
                continue
            symbol = resolve_stock_symbol(item)
            if symbol not in symbols:
                symbols.append(symbol)
        return symbols

    @property
    def normalized_llm_provider(self) -> str:
        return self.LLM_PROVIDER.strip().lower()

    @property
    def gemini_api_key(self) -> str:
        return self.GEMINI_API_KEY or self.GOOGLE_API_KEY

    @property
    def has_llm_key(self) -> bool:
        if self.normalized_llm_provider == "gemini":
            return bool(self.gemini_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
