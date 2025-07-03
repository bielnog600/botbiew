# services/supabase_service.py
import asyncio
from supabase import create_client, Client
from typing import List, Dict, Any, Optional
from core.data_models import TradeSignal
from config import settings

class SupabaseService:
    """
    Wrapper para todas as interações com o Supabase,
    com gestão de cliente robusta para ambiente assíncrono.
    """
    def __init__(self, url: str, key: str):
        self._url = url
        self._key = key
        self._loop = None
        print("Serviço Supabase inicializado.")

    def _create_client(self) -> Client:
        return create_client(self._url, self._key)

    async def _get_loop(self):
        if self._loop is None: self._loop = asyncio.get_running_loop()
        return self._loop

    async def get_bot_config(self) -> Dict[str, Any]:
        try:
            loop = await self._get_loop()
            response = await loop.run_in_executor(None, lambda: self._create_client().table('bot_config').select('*').eq('id', 1).single().execute())
            return response.data if response.data else {}
        except Exception as e:
            print(f"Erro ao buscar configuração do bot: {e}", flush=True)
            return {'status': 'PAUSED'}

    async def update_current_balance(self, balance: float):
        try:
            loop = await self._get_loop()
            await loop.run_in_executor(None, lambda: self._create_client().table('bot_config').update({'current_balance': balance}).eq('id', 1).execute())
        except Exception as e:
            print(f"Erro ao atualizar saldo no Supabase: {e}", flush=True)

    async def insert_log(self, level: str, message: str):
        try:
            loop = await self._get_loop()
            await loop.run_in_executor(None, lambda: self._create_client().table('bot_logs').insert({'level': level.upper(), 'message': message}).execute())
        except Exception as e:
            print(f"Erro ao inserir log no Supabase: {e}", flush=True)

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        try:
            loop = await self._get_loop()
            response = await loop.run_in_executor(None, lambda: self._create_client().table('trade_signals').insert(signal.model_dump(exclude_none=True)).execute())
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            await self.insert_log('ERROR', f"Falha CRÍTICA ao inserir sinal de trade: {e}")
            return None

    async def update_trade_result(self, signal_id: int, result: str, martingale_level: int = 0) -> bool:
        try:
            loop = await self._get_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._create_client().table('trade_signals').update({
                    'result': result,
                    'martingale_level': martingale_level
                }).eq('id', signal_id).execute()
            )
            return bool(response.data)
        except Exception as e:
            await self.insert_log('ERROR', f"Falha ao atualizar resultado do trade {signal_id}: {e}")
            return False

    # FIX: Adicionado o parâmetro 'timeframe' à definição da função.
    async def update_asset_performance(self, asset: str, strategy: str, timeframe: int, win_rate: float, total_trades: int):
        """
        Insere ou atualiza o registro de performance de uma estratégia para um ativo.
        """
        try:
            loop = await self._get_loop()
            await loop.run_in_executor(
                None,
                lambda: self._create_client().table('asset_performance').upsert({
                    'asset_name': asset,
                    'strategy_name': strategy,
                    'timeframe_minutes': timeframe, # Incluído o timeframe no payload.
                    'win_rate': win_rate,
                    'total_trades': total_trades,
                    'last_cataloged_at': 'now()'
                }, on_conflict='asset_name,strategy_name').execute()
            )
        except Exception as e:
            print(f"Erro ao atualizar performance do ativo {asset}: {e}", flush=True)

    async def get_best_performing_assets(self) -> List[str]:
        """Busca no banco de dados os ativos com a melhor performance."""
        try:
            loop = await self._get_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._create_client().table('asset_performance')
                    .select('asset_name')
                    .gte('win_rate', 85) # O threshold está hardcoded por enquanto
                    .order('win_rate', desc=True)
                    .limit(settings.MAX_ASSETS_TO_MONITOR)
                    .execute()
            )
            return [item['asset_name'] for item in response.data] if response.data else []
        except Exception as e:
            print(f"Erro ao buscar melhores ativos: {e}", flush=True)
            return []
