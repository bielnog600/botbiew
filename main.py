import sys
import os
import asyncio
import logging
import traceback # <-- IMPORTAÇÃO ADICIONADA
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.bot import TradingBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s:%(name)s:%(message)s'
)

def main():
    load_dotenv()
    bot = TradingBot()
    
    try:
        logging.info("A iniciar o bot...")
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logging.info("Bot interrompido pelo utilizador. A encerrar...")
    except Exception as e:
        logging.critical(f"Ocorreu um erro fatal no arranque do bot: {e}")
        traceback.print_exc() # Agora funciona
    finally:
        bot.is_running = False
        if bot.exnova and hasattr(bot.exnova, 'quit'):
            bot.exnova.quit()
        logging.info("Bot encerrado.")

if __name__ == "__main__":
    main()
