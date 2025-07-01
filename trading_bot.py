# -*- coding: utf-8 -*-
import time
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timedelta
from collections import deque
from threading import Thread, Lock

try:
    from supabase import create_client, Client
    from postgrest.exceptions import APIError
except ImportError:
    print("ERRO: A biblioteca 'supabase' ou 'postgrest' não está instalada. Por favor, instale-a com: pip install supabase")
    sys.exit(1)

try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("Warning: 'exnovaapi' not found. Using a mock class for testing.")
    # --- Mock Exnova Class for Testing ---
    class Exnova:
        _trades = {}
        def __init__(self, email, password): self.email, self.password, self.profile = email, password, None
        def connect(self): return True, None
        def change_balance(self, balance_type): pass
        def get_profile_ansyc(self): self.profile = {'name': 'Mock User', 'currency_char': '$'}; return self.profile
        def get_all_open_time(self): return {'binary': {'EURUSD-op': {'open': True}},'turbo': {'EURUSD-TURBO': {'open': True}}}
        def get_all_profit(self): return {'EURUSD-op': {'binary': 0.85, 'turbo': 0.90}}
        def get_candles(self, active, interval, count, endtime):
            candles = []
            start_price = 1.1000
            for i in range(count):
                open_price = start_price + (i * 0.0001) * (-1 if i % 2 == 0 else 1)
                close_price = open_price + 0.0005 * (-1 if i % 3 == 0 else 1)
                high_price = max(open_price, close_price) + 0.0003
                low_price = min(open_price, close_price) - 0.0003
                candles.append({'open': open_price, 'close': close_price, 'max': high_price, 'min': low_price})
            return candles
        def buy(self, amount, active, action, duration):
            order_id = "mock_order_id_" + str(uuid.uuid4())
            self._trades[order_id] = {'time': time.time(), 'duration': duration, 'result': 'win' if time.time() % 2 == 0 else 'loss'}
            return True, order_id
        def check_win_v4(self, order_id):
            trade = self._trades.get(order_id)
            if not trade: return None, None
            if time.time() > trade['time'] + (trade['duration'] * 60):
                result = trade['result']
                del self._trades[order_id]
                return result, 10.0
            return None, 0

# --- Initialization ---
from colorama import init, Fore
init(autoreset=True)
g, y, r, w, c, b = Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.WHITE, Fore.CYAN, Fore.BLUE

# --- Centralized Logging ---
def log(cor, mensagem): print(f"{cor}[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {w}{mensagem}")
def log_info(msg, pair="Sistema"): log(c, f"{pair}: {msg}" if pair != "Sistema" else msg)
def log_success(msg, pair="Sistema"): log(g, f"{pair}: {msg}" if pair != "Sistema" else msg)
def log_warning(msg, pair="Sistema"): log(y, f"{pair}: {msg}" if pair != "Sistema" else msg)
def log_error(msg, pair="Sistema"): log(r, f"{pair}: {msg}" if pair != "Sistema" else msg)

# --- Banner ---
def exibir_banner():
    print(c + "\n" + "="*88)
    print(y + "MAROMBIEW BOT - v70 (Sintaxe Corrigida)")
    print(c + "="*88 + "\n")


# --- Logic and Strategy Functions ---
def sma_slope(closes, period):
    if len(closes) < period + 1: return None
    sma1 = sum(closes[-(period+1):-1]) / period; sma2 = sum(closes[-period:]) / period
    if sma1 == sma2: return None
    return sma2 > sma1

def detect_fractals(velas, n_levels):
    try:
        highs = [v['max'] for v in velas]
        lows = [v['min'] for v in velas]
    except KeyError as e:
        log_error(f"Chave de vela ausente: {e}. Verifique o formato dos dados da API. Vela problemática: {velas[-1] if velas else 'N/A'}")
        return [], []
        
    res_levels, sup_levels = [], []
    for i in range(2, len(velas) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]: res_levels.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]: sup_levels.append(lows[i])
    return sorted(res_levels, reverse=True)[:n_levels], sorted(sup_levels, reverse=True)[:n_levels]

def strategy_mql_pullback(velas, p):
    if len(velas) < p.get('MAPeriod', 14) + 2: return 0, None
    nano_up = sma_slope([v['close'] for v in velas], p.get('MAPeriod', 14))
    if nano_up is None: return 0, None
    res_levels, sup_levels = detect_fractals(velas, p.get('MaxLevels', 5))
    last = velas[-1]
    direcao = None
    
    try:
        if nano_up and sup_levels and last['close'] > last['open']:
            sup_level = sup_levels[0]; target_price = sup_level + p.get('Proximity', 2) * p.get('Point', 0.00001)
            if last['min'] <= target_price and last['close'] >= sup_level: direcao = 'BUY'
        if not nano_up and res_levels and last['close'] < last['open']:
            res_level = res_levels[0]; target_price = res_level - p.get('Proximity', 2) * p.get('Point', 0.00001)
            if last['max'] >= target_price and last['close'] <= res_level: direcao = 'SELL'
    except KeyError as e:
        log_error(f"Chave ausente na estratégia MQL Pullback: {e}. Vela: {last}")
        return 0, None

    return (1, direcao) if direcao else (0, None)

ALL_STRATEGIES = { 'mql_pullback': 'Pullback MQL' }

class BotState:
    def __init__(self):
        self.stop = False
        self.active_trades = [] 
        self.lock = Lock()

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)),
        'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
    }

def check_and_update_results(state, API, supabase_client):
    while not state.stop:
        with state.lock:
            for trade in list(state.active_trades):
                result, _ = API.check_win_v4(trade['order_id'])
                
                if result:
                    log_info(f"Resultado da operação {trade['order_id']}: {result.upper()}", trade['pair'])
                    
                    try:
                        supabase_client.table('trade_signals').update({
                            'result': result.upper()
                        }).eq('id', trade['signal_id']).execute()
                        log_success(f"Resultado do sinal {trade['signal_id']} atualizado para {result.upper()}", trade['pair'])
                    except Exception as e:
                        log_error(f"Falha ao atualizar resultado do sinal {trade['signal_id']}: {e}", trade['pair'])

                    state.active_trades.remove(trade)
        
        time.sleep(5)

def run_trading_cycle(API, supabase_client, state, params, config):
    max_trades = params.get('MAX_SIMULTANEOUS_TRADES', 1)

    if len(state.active_trades) >= max_trades:
        if int(time.time()) % 20 == 0:
            log_warning(f"Limite de {max_trades} operações simultâneas atingido. Aguardando...")
        return

    try:
        open_assets = API.get_all_open_time()
        available_assets = {**open_assets.get('binary', {}), **open_assets.get('turbo', {})}

        for asset, details in available_assets.items():
            if not details.get('open'):
                continue

            clean_asset = asset.split('-')[0]
            
            velas = API.get_candles(clean_asset, 60, 100, time.time())
            if not velas or len(velas) < 20:
                continue

            for name, func in STRATEGY_FUNCTIONS.items():
                signal, direction = func(velas, params)
                
                if signal and direction:
                    log_success(f"Sinal encontrado! Ativo: {clean_asset}, Direção: {direction}, Estratégia: {name}")

                    try:
                        # FIX: Remove .select('id'). The insert response already contains the data.
                        response = supabase_client.table('trade_signals').insert({
                            'pair': clean_asset,
                            'direction': direction,
                            'strategy': name
                        }).execute()
                        
                        # The data from the new row is in response.data
                        if response.data:
                            signal_id = response.data[0]['id']
                            log_info(f"Sinal registrado no painel com ID: {signal_id}", clean_asset)
                        else:
                            log_error(f"Não foi possível registrar o sinal no painel: {response.error}", clean_asset)
                            continue
                    except Exception as e:
                        log_error(f"Exceção ao registrar sinal: {e}", clean_asset)
                        traceback.print_exc()
                        continue

                    status, order_id = API.buy(config['valor_entrada'], clean_asset, direction, config['expiracao'])

                    if status:
                        log_success(f"Operação realizada com sucesso! ID da Ordem: {order_id}", clean_asset)
                        
                        with state.lock:
                            state.active_trades.append({
                                'order_id': order_id,
                                'signal_id': signal_id,
                                'pair': clean_asset
                            })
                    else:
                        log_error(f"Falha ao realizar a operação: {order_id}", clean_asset)
                    
                    time.sleep(2)
                    return

    except Exception as e:
        log_error(f"Erro no ciclo de negociação: {e}")
        traceback.print_exc()


def main_bot_logic(state):
    exibir_banner()
    email, senha = os.getenv('EXNOVA_EMAIL'), os.getenv('EXNOVA_PASSWORD')
    if not email or not senha:
        log_error("Variáveis de ambiente EXNOVA_EMAIL e EXNOVA_PASSWORD não definidas.")
        sys.exit(1)

    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    if not supabase_url or not supabase_key:
        log_error("As credenciais do Supabase não foram definidas nas variáveis de ambiente.")
        sys.exit(1)
    
    supabase_client = create_client(supabase_url, supabase_key)
    log_success("Conectado ao Supabase com sucesso.")

    config = get_config_from_env()
    API = Exnova(email, senha)
    log_info("Conectando à Exnova...")
    check, reason = API.connect()
    if not check:
        log_error(f"Falha na conexão: {reason}")
        sys.exit(1)
    
    log_success("Conexão com a Exnova estabelecida!")
    API.change_balance(config['conta'])
    
    result_checker_thread = Thread(target=check_and_update_results, args=(state, API, supabase_client))
    result_checker_thread.daemon = True
    result_checker_thread.start()
    log_info("Monitor de resultados iniciado em segundo plano.")


    log_info("Bot iniciado. A aguardar comandos do painel de administração...")

    while not state.stop:
        try:
            response = supabase_client.table('bot_config').select('*').eq('id', 1).single().execute()
            config_data = response.data
            
            bot_status = config_data.get('status', 'PAUSED')
            remote_params = config_data.get('params', {})

            if bot_status == 'RUNNING':
                # No need to log this every time, it clutters the console
                # log_info("Bot em modo RUNNING. Iniciando ciclo de análise...")
                run_trading_cycle(API, supabase_client, state, remote_params, config)
            else:
                if int(time.time()) % 20 == 0:
                    log_info("Bot em modo PAUSADO. A aguardar comando 'RUNNING' do painel.")
            
            time.sleep(2) # Sleep for a shorter time to be more responsive

        except APIError as e:
            if hasattr(e, 'code') and e.code == 'PGRST116':
                log_warning("Configuração do bot não encontrada. Crie a configuração no painel.")
                time.sleep(15)
            else:
                log_error(f"ERRO DE API NO LOOP PRINCIPAL: {e}"); time.sleep(10)
        except Exception as e:
            log_error(f"ERRO INESPERADO NO LOOP PRINCIPAL: {e}"); traceback.print_exc(); time.sleep(10)

def main():
    bot_state = BotState()
    try:
        main_bot_logic(bot_state)
    except KeyboardInterrupt:
        log_warning("\nDesligando o bot...")
        bot_state.stop = True

if __name__ == "__main__":
    main()
