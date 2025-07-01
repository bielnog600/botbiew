# main.py
import asyncio
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
        # Adicionar lógica para aguardar tarefas pendentes finalizarem se necessário
    except Exception as e:
        print(f"Erro fatal no bot: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # Carrega as variáveis de ambiente de um arquivo .env se ele existir
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(main())
