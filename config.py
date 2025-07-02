# config.py
import os
from pydantic_settings import BaseSettings
from pydantic import Extra

class Settings(BaseSettings):
    """
    Carrega e valida as configurações a partir de variáveis de ambiente.
    """
    EXNOVA_EMAIL: str
    EXNOVA_PASSWORD: str
    SUPABASE_URL: str
    SUPABASE_KEY: str

    LOG_LEVEL: str = "INFO"
    
    # FIX: Adicionado o parâmetro que estava em falta.
    # Define o número máximo de pares que o bot irá analisar em cada ciclo.
    MAX_ASSETS_TO_MONITOR: int = 15
    
    # Define o número máximo de operações abertas em simultâneo.
    MAX_CONCURRENT_TRADES: int = 2

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = 'ignore'

settings = Settings()
