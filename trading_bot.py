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

import asyncio
import websockets
import queue

from colorama import init, Fore

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
                candles.append({'open': open_price, 'close': close_price, 'high': high_price, 'low': low_price, 'max': high_price, 'min': low_price})
            return candles
        def buy(self, amount, active, action, duration): return True, "mock_order_id_" + str(uuid.uuid4())
        def check_win_v4(self, order_id): return "win", 10.0

# --- Initialization ---
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
    print(y + "*"*88)
    print(g + '''
          ██╗     ██████╗  ██████╗  █████╗ ███╗   ██╗     ███████╗███╗   ███╗██╗████████╗██╗  ██╗
          ██║     ██╔═══██╗██╔════╝ ██╔══██╗████╗  ██║     ██╔════╝████╗ ████║██║╚══██╔══╝██║  ██║
          ██║     ██║   ██║██║  ███╗███████║██╔██╗ ██║     ███████╗██╔████╔██║██║   ██║    ███████║
          ██║     ██║   ██║██║   ██║██╔══██║██║╚██╗██║     ╚════██║██║╚██╔╝██║██║   ██║    ██╔══██║
          ███████╗╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║     ███████║██║ ╚═╝ ██║██║   ██║    ██║  ██║
          ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝     ╚══════╝╚═╝     ╚═╝╚═╝   ╚═╝    ╚═╝  ╚═╝ '''+c+'''
    ████████╗██████╗ ██╗ █████╗ ██╗       ██╗   ██║██╗  ████████╗██████╗  █████╗ ██████╗  ██████╗ ████████╗
    ╚══██╔══╝██╔══██╗██║██╔══██╗██║       ██║   ██║██║  ╚══██╔══╝██╔══██╗██╔═══██╗╚══██╔══╝
      ██║   ██████╔╝██║███████║██║       ██║   ██║██║     ██║   ████████╗███████║██████╔╝██║    ██║    ██║
      ██║   ██╔══██╗██║██╔══██║██║       ██║   ██║██║     ██║   ██╔══██╗██╔══██║██╔══██╗██║    ██║    ██║
      ██║   ██║  ██║██║██║  ██║███████╗    ╚██████╔╝███████╗██║   ██║  ██║██║  ██║██████╔╝╚██████╔╝    ██║
      ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝     ╚═════╝ ╚══════╝╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝     ╚═╝ '''+y+'''
              azkzero@gmail.com - v68 (Autocorreção de Base de Dados)
    ''')
    print(y + "*"*88)
    print(c + "="*88)

# --- Logic and Strategy Functions ---
def sma_slope(closes, period):
    if len(closes) < period + 1: return None
    sma1 = sum(closes[-(period+1):-1]) / period; sma2 = sum(closes[-period:]) / period
    if sma1 == sma2: return None
    return sma2 > sma1

def detect_fractals(velas, n_levels):
    highs = [v['high'] for v in velas]; lows = [v['low'] for v in velas]
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
    if nano_up and sup_levels and last['close'] > last['open']:
        sup_level = sup_levels[0]; target_price = sup_level + p.get('Proximity', 2) * p.get('Point', 0.00001)
        if last['low'] <= target_price and last['close'] >= sup_level: direcao = 'BUY'
    if not nano_up and res_levels and last['close'] < last['open']:
        res_level = res_levels[0]; target_price = res_level - p.get('Proximity', 2) * p.get('Point', 0.00001)
        if last['high'] >= target_price and last['close'] <= res_level: direcao = 'SELL'
    return (1, direcao) if direcao else (0, None)

def strategy_flow(velas, p):
    if len(velas) < p.get('MAPeriod', 14) + 3: return 0, None
    nano_up = sma_slope([v['close'] for v in velas], p.get('MAPeriod', 14))
    if nano_up is None: return 0, None
    last_candles = velas[-3:]
    direcao = None
    if nano_up and all(v['close'] > v['open'] for v in last_candles): direcao = 'BUY'
    if not nano_up and all(v['close'] < v['open'] for v in last_candles): direcao = 'SELL'
    return (1, direcao) if direcao else (0, None)

def strategy_patterns(velas, p):
    if len(velas) < p.get('MAPeriod', 14) + 2: return 0, None
    nano_up = sma_slope([v['close'] for v in velas], p.get('MAPeriod', 14))
    if nano_up is None: return 0, None
    penultimate, last = velas[-2], velas[-1]
    direcao = None
    if nano_up:
        if (penultimate['close'] < penultimate['open'] and last['close'] > last['open'] and last['open'] < penultimate['close'] and last['close'] > penultimate['open']): direcao = 'BUY'
        if (penultimate['close'] < penultimate['open'] and last['close'] > last['open'] and last['open'] > penultimate['close'] and last['close'] < penultimate['open']): direcao = 'BUY'
    if not nano_up:
        if (penultimate['close'] > penultimate['open'] and last['close'] < last['open'] and last['open'] > penultimate['close'] and last['close'] < penultimate['open']): direcao = 'SELL'
        if (penultimate['close'] > penultimate['open'] and last['close'] < last['open'] and last['open'] < penultimate['close'] and last['close'] > penultimate['open']): direcao = 'SELL'
    return (1, direcao) if direcao else (0, None)

ALL_STRATEGIES = { 'mql_pullback': 'Pullback MQL', 'flow': 'Fluxo', 'patterns': 'Padrões de Velas' }
STRATEGY_FUNCTIONS = { 'mql_pullback': strategy_mql_pullback, 'flow': strategy_flow, 'patterns': strategy_patterns }

class BotState:
    def __init__(self):
        self.stop = False
        self.active_trades = 0
        self.champion_strategies = {}
        self.lock = Lock()

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)),
        'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
    }

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
    
    cifrao = "$"
    try:
        profile_data = API.get_profile_ansyc()
        if profile_data:
            cifrao = profile_data.get('currency_char', '$')
            log_success(f"Logado como {profile_data.get('name', 'Usuário')} | Moeda: {cifrao}")
    except Exception as e:
        log_error(f"Erro ao obter perfil: {e}. Usando valores padrão.")

    log_info("Bot iniciado. A aguardar comandos do painel de administração...")

    while not state.stop:
        try:
            # --- LÓGICA DE AUTOCORREÇÃO E LEITURA DE CONFIGURAÇÃO ---
            try:
                response = supabase_client.table('bot_config').select('*').eq('id', 1).single().execute()
                config_data = response.data
            except APIError as e:
                # --- FIX: Check for the specific error code 'PGRST116' which means no rows were found ---
                if hasattr(e, 'code') and e.code == 'PGRST116':
                    log_warning("Configuração do bot não encontrada na base de dados. A criar configuração padrão...")
                    default_params = {
                        "Assertividade_Minima": 80, "MAX_SIMULTANEOUS_TRADES": 1, "Standby_Loss_Count": 2,
                        "Standby_Timeframe_Minutes": 5, "Recatalog_Cycle_Hours": 2, "Recatalog_Loss_Trigger": 5,
                        "Consolidation_Lookback": 10, "Consolidation_Threshold": 0.0005, "Exhaustion_DojiLike_Ratio": 0.2,
                        "MAPeriod": 14, "MaxLevels": 5, "Proximity": 2, "Point": 0.00001
                    }
                    insert_response = supabase_client.table('bot_config').insert({
                        "id": 1,
                        "status": "PAUSED",
                        "params": default_params
                    }).execute()
                    
                    # Check if the insert was successful and get the new data
                    if insert_response.data:
                        log_success("Configuração padrão criada com sucesso. O bot continuará em modo PAUSADO.")
                        config_data = insert_response.data[0]
                    else:
                        log_error("Falha ao criar configuração padrão. A tentar novamente no próximo ciclo.")
                        time.sleep(10)
                        continue # Restart the loop
                else:
                    # Re-raise any other API errors that are not the 'zero rows' error
                    log_error(f"Erro de API do Supabase não tratado: {e}")
                    raise e

            bot_status = config_data.get('status', 'PAUSED')
            remote_params = config_data.get('params', {})

            if bot_status == 'PAUSED':
                # Log 'PAUSED' status less frequently to avoid spamming the console
                if int(time.time()) % 20 == 0:
                    log_info("Bot em modo PAUSADO. A aguardar comando 'RUNNING' do painel.")
                time.sleep(5)
                continue

            log_info("Bot em modo RUNNING. Iniciando ciclo de análise...")
            # run_trading_cycle(API, state, remote_params, config, cifrao)
            
            time.sleep(10)

        except Exception as e:
            log_error(f"ERRO NO LOOP PRINCIPAL: {e}"); traceback.print_exc(); time.sleep(10)

def main():
    bot_state = BotState()
    # O WebSocket não é mais necessário neste modelo simplificado
    main_bot_logic(bot_state)

if __name__ == "__main__":
    main()
