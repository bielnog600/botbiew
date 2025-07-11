from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict

class Settings(BaseSettings):
    # Ignora variáveis de ambiente extras não definidas aqui
    model_config = ConfigDict(
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8"
    )

    # Exnova API credentials
    EXNOVA_EMAIL: str    = Field(..., env="EXNOVA_EMAIL")
    EXNOVA_PASSWORD: str = Field(..., env="EXNOVA_PASSWORD")

    # Supabase credentials
    SUPABASE_URL: str = Field(..., env="SUPABASE_URL")
    SUPABASE_KEY: str = Field(..., env="SUPABASE_KEY")

    # Bot behavior settings
    MAX_ASSETS_TO_MONITOR: int = 180
    MAX_CONCURRENT_TRADES: int = 1

    ENTRY_VALUE: float        = Field(1.0, env="ENTRY_VALUE")
    USE_MARTINGALE: bool      = Field(False, env="USE_MARTINGALE")
    MARTINGALE_FACTOR: float  = Field(2.3, env="MARTINGALE_FACTOR")
    MARTINGALE_LEVELS: int    = Field(2, env="MARTINGALE_LEVELS")

    # Operation mode: CONSERVADOR or AGRESSIVO
    OPERATION_MODE: str = Field("CONSERVADOR", env="OPERATION_MODE")

    # Intervalos
    BOT_CONFIG_POLL_INTERVAL: int = Field(15, env="BOT_CONFIG_POLL_INTERVAL")

# Instancia as configurações:
settings = Settings()
