# config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Carrega e valida as configurações a partir de variáveis de ambiente.
    """
    EXNOVA_EMAIL: str
    EXNOVA_PASSWORD: str
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # Configurações com valores padrão
    LOG_LEVEL: str = "INFO"
    MAX_CONCURRENT_ASSETS: int = 10
    LEARNING_MODE_DURATION_SECONDS: int = 300 # 5 minutos
    CATALOG_HISTORY_HOURS: int = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Instância única para ser importada em outros módulos
settings = Settings()
