import asyncio
import logging
from core.bot import TradingBot

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s:%(name)s:%(message)s')

def main():
    """
    Função principal para inicializar e executar o bot.
    """
    bot = TradingBot()
    try:
        logging.info("A iniciar o bot...")
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logging.info("Bot interrompido pelo utilizador.")
    except Exception as e:
        logging.critical(f"Ocorreu um erro fatal no arranque do bot: {e}", exc_info=True)
    finally:
        # A lógica de encerramento agora está dentro do próprio bot (bot.run)
        logging.info("Aplicação principal a terminar.")

if __name__ == "__main__":
    main()
