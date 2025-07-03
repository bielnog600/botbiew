# main.py
import asyncio
import traceback
from dotenv import load_dotenv
from core.bot import TradingBot

async def main():
    """
    Função principal que inicializa e executa o bot.
    """
    bot = TradingBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\nDesligando o bot...")
        bot.is_running = False
    except Exception as e:
        print(f"Erro fatal no bot: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # Carrega as variáveis de ambiente de um arquivo .env se ele existir
    load_dotenv()
    # Inicia a execução assíncrona do bot
    asyncio.run(main())
