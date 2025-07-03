# main.py
import asyncio
import traceback # FIX: Importa o módulo traceback.
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
        # Esta chamada agora funcionará corretamente.
        traceback.print_exc()

if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
