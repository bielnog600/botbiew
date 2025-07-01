# services/supabase_service.py
from supabase import create_client, Client
from typing import List, Dict, Any, Optional # FIX: Adicionado 'Optional' à importação
from core.data_models import TradeSignal

class SupabaseService:
    """
    Wrapper para todas as interações com o Supabase.
    """
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)
        print("Serviço Supabase inicializado.")

    async def update_asset_performance(self, asset: str, strategy: str, timeframe: int, win_rate: float, total_trades: int):
        try:
            # Upsert para inserir ou atualizar o registro de performance
            await self.client.table('asset_performance').upsert({
                'asset_name': asset,
                'strategy_name': strategy,
                'timeframe_minutes': timeframe,
                'win_rate': win_rate,
                'total_trades': total_trades,
                'last_cataloged_at': 'now()'
            }).execute()
        except Exception as e:
            print(f"Erro ao atualizar performance do ativo {asset}: {e}")

    async def save_learning_stats(self, stats: Dict[str, Any]):
        try:
            await self.client.table('learning_stats').insert(stats).execute()
        except Exception as e:
            print(f"Erro ao salvar estatísticas de aprendizado: {e}")

    async def insert_trade_signal(self, signal: TradeSignal) -> Optional[int]:
        try:
            response = await self.client.table('trade_signals').insert(signal.model_dump()).execute()
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            print(f"Erro ao inserir sinal de trade: {e}")
            return None

    async def update_trade_result(self, signal_id: int, result: str):
        try:
            await self.client.table('trade_signals').update({'result': result}).eq('id', signal_id).execute()
        except Exception as e:
            print(f"Erro ao atualizar resultado do trade {signal_id}: {e}")

    async def get_bot_status(self) -> str:
        try:
            response = await self.client.table('bot_config').select('status').eq('id', 1).single().execute()
            return response.data.get('status', 'PAUSED')
        except Exception:
            return 'PAUSED' # Assume pausado em caso de erro
