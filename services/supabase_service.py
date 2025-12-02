from supabase import create_client, Client
from typing import Dict, Any, Optional
import traceback

class SupabaseService:
    def __init__(self, url: str, key: str):
        self.client: Optional[Client] = None
        if not url or not key:
            print("[SUPABASE] URL ou Key não configurados. Modo offline.")
            return
            
        try:
            self.client = create_client(url, key)
            print("[SUPABASE] Cliente inicializado.")
        except Exception as e:
            print(f"[SUPABASE] Erro ao inicializar cliente: {e}")

    def insert_log(self, level: str, message: str):
        if not self.client: return
        try:
            # Tabela 'logs' deve existir no Supabase
            self.client.table('logs').insert({"level": level, "message": message}).execute()
        except Exception as e:
            # Imprime erro no console mas não quebra a execução
            print(f"[SUPABASE ERROR] Falha ao inserir log: {e}")

    def get_bot_config(self) -> Dict[str, Any]:
        default_config = {
            "status": "RUNNING", "account_type": "PRACTICE", 
            "entry_value": 1.0, "stop_win": 10, "stop_loss": 5,
            "use_martingale": False, "martingale_levels": 0, "martingale_factor": 2.0,
            "max_simultaneous_trades": 2, "confirmation_threshold": 2
        }
        if not self.client: return default_config

        try:
            response = self.client.table('bot_config').select("*").limit(1).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return default_config
        except Exception as e:
            print(f"[SUPABASE ERROR] Falha ao ler config: {e}")
            return default_config

    def update_config(self, updates: Dict[str, Any]):
        if not self.client: return
        try:
            # Assume que existe um ID=1 ou similar para config única
            self.client.table('bot_config').update(updates).eq('id', 1).execute()
        except Exception as e:
            print(f"[SUPABASE ERROR] Falha ao atualizar config: {e}")

    def insert_trade_signal(self, signal) -> Optional[str]:
        if not self.client: return None
        try:
            data = {
                "pair": signal.pair,
                "direction": signal.direction,
                "strategy": signal.strategy,
                "status": "PENDING",
                "created_at": "now()"
            }
            res = self.client.table('trade_history').insert(data).execute()
            if res.data:
                return res.data[0]['id']
        except Exception as e:
            print(f"[SUPABASE ERROR] Falha ao inserir trade: {e}")
        return None

    def update_trade_result(self, trade_id: str, result: str, martingale_level: int):
        if not self.client: return
        try:
            self.client.table('trade_history').update({
                "result": result,
                "martingale_level": martingale_level
            }).eq('id', trade_id).execute()
        except Exception as e:
            print(f"[SUPABASE ERROR] Falha ao atualizar trade: {e}")

    def update_current_balance(self, balance: float):
        if not self.client: return
        try:
            self.update_config({"current_balance": balance})
        except Exception:
            pass
