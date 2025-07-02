# core/bot.py
import asyncio
import time
import traceback
from datetime import datetime
from typing import List, Dict, Optional

from config import settings
from services.exnova_service import AsyncExnovaService
from services.supabase_service import SupabaseService
from analysis.strategy import STRATEGIES
from core.data_models import TradeSignal, ActiveTrade, Candle

class TradingBot:
    def __init__(self):
        self.supabase = SupabaseService(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.exnova = AsyncExnovaService(settings.EXNOVA_EMAIL, settings.EXNOVA_PASSWORD)
        self.is_running = True

    async def logger(self, level: str, message: str):
        print(f"[{level.upper()}] {message}", flush=True)
        # Não precisamos de sobrecarregar o Supabase com logs de diagnóstico
        # await self.supabase.insert_log(level, message)

    async def run(self):
        """
        MODO DE DIAGNÓSTICO: Esta função irá conectar-se à API e listar
        todos os métodos disponíveis para descobrirmos a função correta
        para verificar os resultados das operações.
        """
        await self.logger('INFO', 'Bot a iniciar em MODO DE DIAGNÓSTICO DE API...')
        
        # Tenta conectar-se à Exnova
        connection_success = await self.exnova.connect()
        if not connection_success:
            await self.logger('ERROR', "Não foi possível conectar à Exnova. Verifique as credenciais.")
            return

        await self.logger('SUCCESS', f"Conexão com a Exnova estabelecida.")
        
        try:
            # Lista todos os atributos e métodos disponíveis no objeto da API
            api_methods = dir(self.exnova.api)
            
            await self.logger('DIAGNOSTIC', "-------------------------------------------------")
            await self.logger('DIAGNOSTIC', "FUNÇÕES DISPONÍVEIS NA API EXNOVA:")
            await self.logger('DIAGNOSTIC', "-------------------------------------------------")
            
            # Imprime apenas os métodos que não começam com '__' (métodos públicos)
            public_methods = [method for method in api_methods if not method.startswith('_')]
            
            # Procura por palavras-chave comuns relacionadas a resultados
            keywords = ['profit', 'win', 'result', 'check', 'get_trade']
            
            for method_name in sorted(public_methods):
                # Destaca os métodos que provavelmente são os que procuramos
                if any(keyword in method_name.lower() for keyword in keywords):
                    await self.logger('DIAGNOSTIC', f" ---> {method_name} <--- POSSÍVEL CANDIDATO!")
                else:
                    await self.logger('DIAGNOSTIC', f"      {method_name}")

            await self.logger('DIAGNOSTIC', "-------------------------------------------------")
            await self.logger('DIAGNOSTIC', "Diagnóstico concluído. Por favor, envie esta lista de funções.")
            
        except Exception as e:
            await self.logger('ERROR', f"Erro durante o diagnóstico da API: {e}")

        # Mantém o bot a correr para que possamos ver os logs
        await self.logger('INFO', "O bot irá agora aguardar. Pode pará-lo e enviar os logs.")
        while True:
            await asyncio.sleep(300)

    # O resto do código é desativado para o modo de diagnóstico
    async def trading_cycle(self): pass
