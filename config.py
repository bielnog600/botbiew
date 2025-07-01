# config.py
import os
from pydantic_settings import BaseSettings
from pydantic import Extra

class Settings(BaseSettings):
    """
    Carrega e valida as configurações a partir de variáveis de ambiente.
    """
    # === Variáveis Obrigatórias ===
    # O bot não iniciará se estas não estiverem definidas no ambiente.
    EXNOVA_EMAIL: str
    EXNOVA_PASSWORD: str
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # === Configurações Opcionais com Valores Padrão ===
    LOG_LEVEL: str = "INFO"
    MAX_CONCURRENT_ASSETS: int = 10
    LEARNING_MODE_DURATION_SECONDS: int = 300 # 5 minutos
    CATALOG_HISTORY_HOURS: int = 24

    class Config:
        # Define o arquivo .env como uma fonte de variáveis
        env_file = ".env"
        env_file_encoding = "utf-8"
        
        # FIX: Ignora quaisquer variáveis de ambiente extras que não estão definidas
        # nesta classe. Isto resolve o erro de validação no Coolify.
        extra = 'ignore'

# Instância única para ser importada em outros módulos
settings = Settings()
