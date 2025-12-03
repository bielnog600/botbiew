import asyncio
import logging
import sys
import os

# Adiciona o diretório atual ao path do sistema para garantir importações corretas
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.bot import TradingBot

def configure_logging():
    """
    Configura o sistema de logs e silencia bibliotecas barulhentas.
    """
    # Configuração básica do logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # --- CORREÇÃO DO SPAM DE LOGS ---
    # Define o nível de log das bibliotecas de rede para WARNING.
    # Isso esconde os logs de "HTTP Request: GET ..." (INFO), mas mostra erros se algo falhar.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.INFO) # Mantém info de websockets se necessário

def main():
    # Aplica a configuração de logs antes de iniciar
    configure_logging()
    
    try:
        bot = TradingBot()
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n[SISTEMA] Bot parado pelo utilizador (Ctrl+C).")
    except Exception as e:
        print(f"\n[ERRO FATAL] Ocorreu um erro não tratado: {e}")

if __name__ == "__main__":
    main()
