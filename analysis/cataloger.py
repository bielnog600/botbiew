import time
import traceback
import logging

class Cataloger:
    def __init__(self, exnova_service, supabase_service, strategy_map):
        self.exnova = exnova_service
        self.supabase = supabase_service
        self.strategy_map = strategy_map
        self.logger = self._get_logger()

    def _get_logger(self):
        # Função auxiliar para loggar com o prefixo [CATALOGER]
        def logger(level, message):
            log_message = f"[CATALOGER] {message}"
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level.upper()}] {log_message}", flush=True)
            if self.supabase:
                self.supabase.insert_log(level, log_message)
        return logger

    def run_cataloging_cycle(self):
        self.logger('INFO', "A iniciar novo ciclo de catalogação...")
        try:
            open_assets = self.exnova.get_all_open_assets()
            if not open_assets:
                self.logger('WARNING', "Não foi possível obter a lista de pares abertos.")
                return

            self.logger('INFO', f"{len(open_assets)} pares abertos encontrados para análise.")

            for pair_name in open_assets:
                self.logger('INFO', f"A catalogar o par: {pair_name}...")
                
                candles = self.exnova.get_historical_candles(pair_name, 60, 200)
                if not candles or len(candles) < 50:
                    self.logger('WARNING', f"Velas insuficientes para catalogar {pair_name}.")
                    continue

                best_strategy_for_pair = {'name': 'N/A', 'win_rate': 0, 'wins': 0, 'losses': 0}
                
                for strategy_name, strategy_func in self.strategy_map.items():
                    wins, losses, draws = 0, 0, 0
                    
                    for i in range(len(candles) - 51, len(candles) - 1):
                        historical_slice = candles[:i+1]
                        
                        direction = strategy_func(historical_slice)
                        if direction:
                            actual_result_candle = candles[i+1]
                            if direction.lower() == 'call' and actual_result_candle['close'] > actual_result_candle['open']:
                                wins += 1
                            elif direction.lower() == 'put' and actual_result_candle['close'] < actual_result_candle['open']:
                                wins += 1
                            elif actual_result_candle['close'] == actual_result_candle['open']:
                                draws += 1
                            else:
                                losses += 1
                    
                    total_trades = wins + losses
                    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                    
                    self.logger('INFO', f" -> {pair_name}: {strategy_name} -> {win_rate:.1f}% ({wins}W/{losses}L)")

                    if win_rate > best_strategy_for_pair['win_rate']:
                        best_strategy_for_pair = {
                            'name': strategy_name,
                            'win_rate': win_rate,
                            'wins': wins,
                            'losses': losses
                        }

                if best_strategy_for_pair['name'] != 'N/A':
                    self.logger('SUCCESS', f"Melhor estratégia para {pair_name}: {best_strategy_for_pair['name']} com {best_strategy_for_pair['win_rate']:.1f}%")
                    asset_data = {
                        "pair": pair_name,
                        "best_strategy": best_strategy_for_pair['name'],
                        "win_rate": best_strategy_for_pair['win_rate'],
                        "wins": best_strategy_for_pair['wins'],
                        "losses": best_strategy_for_pair['losses']
                    }
                    # --- CORREÇÃO FINAL: Nome da função corrigido (singular) ---
                    self.supabase.upsert_cataloged_asset(asset_data)

        except Exception as e:
            self.logger('ERROR', f"Erro no loop de catalogação: {e}")
            traceback.print_exc()
        finally:
            self.logger('SUCCESS', "Ciclo de catalogação concluído.")
