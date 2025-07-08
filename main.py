import asyncio
import logging
from core.bot import TradingBot

# NOVO: Configuração para silenciar os logs desnecessários da biblioteca httpx (usada pelo Supabase)
# Isto irá limpar a sua consola, mostrando apenas os logs importantes do seu bot.
logging.basicConfig(level=logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)

def main():
    """
    Ponto de entrada principal para a aplicação.
    Cria uma instância do TradingBot e inicia o seu ciclo de execução.
    """
    bot = TradingBot()
    try:
        print("A iniciar o bot...")
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nBot a desligar...")
    except Exception as e:
        print(f"Ocorreu um erro fatal: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
