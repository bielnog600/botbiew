import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

class Settings:
    # Credenciais
    EXNOVA_EMAIL = os.getenv("EXNOVA_EMAIL")
    EXNOVA_PASSWORD = os.getenv("EXNOVA_PASSWORD")
    
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    
    # --- CONFIGURAÇÕES DE TRADING ---
    
    # Tipo de Conta: "REAL" ou "PRACTICE"
    # Se não estiver definido no .env, usa PRACTICE por segurança
    MODE = os.getenv("MODE", "PRACTICE").upper()
    
    # Valor da Entrada Inicial
    try:
        AMOUNT = float(os.getenv("AMOUNT", 400.0))
    except:
        AMOUNT = 1.0

    # Configurações de Martingale
    try:
        MARTINGALE_LEVELS = int(os.getenv("MARTINGALE_LEVELS", 1))
        MARTINGALE_FACTOR = float(os.getenv("MARTINGALE_FACTOR", 2.3))
    except:
        MARTINGALE_LEVELS = 2
        MARTINGALE_FACTOR = 2.2

    # Proxy (Opcional)
    EXNOVA_PROXY = os.getenv("EXNOVA_PROXY")

settings = Settings()
