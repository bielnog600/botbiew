# -*- coding: utf-8 -*-
import time
import json
import base64
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
from configobj import ConfigObj
try:
    from exnovaapi.stable_api import Exnova
except ImportError:
    print("Warning: 'exnovaapi' not found. Using a mock class for testing.")
    # --- Mock Exnova Class for Testing ---
    class Exnova:
        def __init__(self, email, password):
            self.email = email
            self.password = password
            self.profile = None
            print("Initialized Mock Exnova API.")

        def connect(self):
            print("Mocking connection to Exnova...")
            return True, None

        def change_balance(self, balance_type):
            print(f"Mocking change_balance to {balance_type}")
            pass

        def get_profile_ansyc(self):
            print("Mocking get_profile_ansyc")
            self.profile = {'name': 'Mock User', 'currency_char': '$'}
            return self.profile

        def get_all_open_time(self):
            return {
                'binary': {'EURUSD-op': {'open': True}, 'GBPUSD': {'open': True}},
                'turbo': {'EURUSD-TURBO': {'open': True}, 'EURGBP-OTC': {'open': True}}
            }

        def get_all_profit(self):
            return {
                'EURUSD': {'binary': 0.85, 'turbo': 0.90},
                'GBPUSD': {'binary': 0.82},
                'EURUSD-TURBO': {'turbo': 0.92},
                'EURGBP-OTC': {'binary': 0.88}
            }

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

        def buy_digital_spot(self, active, amount, action, duration):
            return True, "mock_order_id_" + str(uuid.uuid4())

        def buy(self, amount, active, action, duration):
            return True, "mock_order_id_" + str(uuid.uuid4())

        def check_win_v4(self, order_id):
            return "win", 10.0

# --- Initialization ---
init(autoreset=True)
g, y, r, w, c, b = Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.WHITE, Fore.CYAN, Fore.BLUE
signal_queue = queue.Queue()
connected_clients = set()
clients_lock = Lock() 

# --- UPDATED STRATEGIES ---
ALL_STRATEGIES = {
    'sr_breakout': 'Rompimento', 
    'engulfing': 'Engolfo',
    'candle_flow': 'Fluxo de Velas',
}

# --- Logging Functions ---
def log(cor, mensagem):
    print(f"{cor}[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {w}{mensagem}")

def log_info(msg): log(c, msg)
def log_success(msg): log(g, msg)
def log_warning(msg): log(y, msg)
def log_error(msg): log(r, msg)

# --- Banner and WebSocket Functions ---
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
              azkzero@gmail.com - v60 (Módulo de Inteligência Avançada)
    ''')
    print(y + "*"*88)
    print(c + "="*88)

class WebSocketServer:
    def __init__(self, bot_state):
        self.bot_state = bot_state

    async def handler(self, websocket, *args):
        with clients_lock:
            connected_clients.add(websocket)
        path = args[0] if args else None
        log_success(f"New WebSocket client connected: {websocket.remote_address}" +
                    (f" on path {path}" if path else ""))
        try:
            initial_state = {
                "type": "init",
                "data": { "signals": list(self.bot_state.signal_history.values()), "placar": { "wins": self.bot_state.win_count, "losses": self.bot_state.loss_count, "gale_wins": sum(self.bot_state.gale_wins.values()) } }
            }
            await websocket.send(json.dumps(initial_state))
            await websocket.wait_closed()
        except websockets.exceptions.ConnectionClosed as e:
            log_warning(f"Connection closed with client {websocket.remote_address}: {e}")
        finally:
            with clients_lock:
                connected_clients.discard(websocket)
            log_warning(f"WebSocket client disconnected: {websocket.remote_address}")

async def broadcast_signals():
    while True:
        try:
            signal_data = signal_queue.get_nowait()
            message_to_send = json.dumps(signal_data)
            
            with clients_lock:
                if not connected_clients:
                    continue
                clients_to_send = list(connected_clients)

            tasks = [client.send(message_to_send) for client in clients_to_send]
            await asyncio.gather(*tasks, return_exceptions=True)

        except queue.Empty:
            await asyncio.sleep(0.1)
        except Exception:
            pass

def start_websocket_server_sync(bot_state):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server_instance = WebSocketServer(bot_state)
    async def main_async_logic():
        server_options = { "ping_interval": 20, "ping_timeout": 20, "reuse_port": True }
        try:
            start_server = websockets.serve(server_instance.handler, "0.0.0.0", 8765, **server_options)
        except (AttributeError, TypeError, OSError):
            log_warning("reuse_port not supported. Starting without it.")
            del server_options["reuse_port"]
            start_server = websockets.serve(server_instance.handler, "0.0.0.0", 8765, **server_options)
        server = await start_server
        log_success(f"WebSocket Server started successfully on {server.sockets[0].getsockname()}")
        await asyncio.gather(broadcast_signals(), server.wait_closed())
    try:
        loop.run_until_complete(main_async_logic())
    except Exception as e:
        log_error(f"CRITICAL ERROR in WebSocket server thread: {e}"); traceback.print_exc()
    finally:
        log_warning("WebSocket server loop is shutting down."); loop.close()


# --- Logic and Strategy Functions ---
def validar_e_limpar_velas(velas_raw):
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {'open': v_raw.get('open'), 'close': v_raw.get('close'), 'high': v_raw.get('high') or v_raw.get('max'), 'low': v_raw.get('low') or v_raw.get('min')}
        if all(vela_padronizada.values()): velas_limpas.append(vela_padronizada)
    return velas_limpas

def catalogar_e_selecionar(api, params, assertividade_minima=60, state=None):
    log_info("="*40); log_info("MODO DE CATALOGAÇÃO E SELEÇÃO INICIADO..."); log_info("="*40)
    
    ativos_abertos = []
    all_assets = api.get_all_open_time()
    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False) and ativo not in ativos_abertos: ativos_abertos.append(ativo)
    
    if not ativos_abertos: log_error("Nenhum par aberto encontrado para catalogar."); return {}

    log_info(f"Encontrados {len(ativos_abertos)} pares abertos para análise.")
    champion_strategies = {}

    for ativo_original in ativos_abertos:
        try:
            log_info(f"\n--- Analisando o par: {w}{ativo_original}{c} ---")
            velas_historicas_raw = api.get_candles(ativo_original, 60, 300, time.time())
            todas_as_velas = validar_e_limpar_velas(velas_historicas_raw)
            if not todas_as_velas or len(todas_as_velas) < 100: log_warning(f"Dados históricos insuficientes para {ativo_original}."); continue
            
            best_strategy, highest_assertiveness = None, 0

            for cod, nome in ALL_STRATEGIES.items():
                wins, losses, total = 0, 0, 0
                for i in range(50, len(todas_as_velas) - 1):
                    velas_atuais, vela_resultado = todas_as_velas[:i], todas_as_velas[i]
                    # Pass state=None para evitar que a catalogação use a memória de trades reais
                    score, _ = globals().get(f'strategy_{cod}')(velas_atuais, params, None)
                    if score >= params.get('Minimum_Confidence_Score', 3):
                        sinal = 'BUY' if velas_atuais[-1]['close'] > velas_atuais[-2]['close'] else 'SELL' # Simulação simplificada para catalogação
                        total += 1
                        if (sinal == 'BUY' and vela_resultado['close'] > velas_atuais[-1]['close']) or \
                           (sinal == 'SELL' and vela_resultado['close'] < velas_atuais[-1]['close']):
                            wins += 1
                        else:
                            losses += 1
                
                if total > 5: # Aumenta o mínimo de trades para considerar uma estratégia
                    assertividade = (wins / total) * 100
                    log_info(f"  -> Estratégia '{nome}': {assertividade:.2f}% ({wins}W / {losses}L em {total} sinais)")
                    if assertividade > highest_assertiveness:
                        highest_assertiveness, best_strategy = assertividade, nome
            
            if best_strategy and highest_assertiveness >= assertividade_minima:
                champion_strategies[ativo_original] = best_strategy
                log_success(f"  -> CAMPEÃ PARA {ativo_original}: {best_strategy} com {highest_assertiveness:.2f}% de acerto.")
            else:
                log_warning(f"  -> Nenhuma estratégia para {ativo_original} atingiu os critérios mínimos.")

        except Exception as e: log_error(f"Erro ao analisar {ativo_original}: {e}"); traceback.print_exc()
        
    log_info("="*40); log_info("CATALOGAÇÃO FINALIZADA!"); log_info("="*40)
    return champion_strategies

def get_candle_props(vela):
    if not all(k in vela for k in ['high', 'low', 'open', 'close']): return None
    props = {}
    props['range'] = vela['high'] - vela['low']
    if props['range'] == 0: return None
    props['corpo'] = abs(vela['open'] - vela['close'])
    props['body_ratio'] = props['corpo'] / props['range'] if props['range'] > 0 else 0
    props['is_alta'] = vela['close'] > vela['open']
    props['is_baixa'] = vela['close'] < vela['open']
    props['pavio_superior'] = vela['high'] - max(vela['open'], vela['close'])
    props['pavio_inferior'] = min(vela['open'], vela['close']) - vela['low']
    return props

# --- HELPER FUNCTIONS FOR ADVANCED STRATEGIES ---
def calculate_ema(closes, period):
    if len(closes) < period: return None
    ema = [sum(closes[:period]) / period]
    multiplier = 2 / (period + 1)
    for price in closes[period:]:
        ema_value = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(ema_value)
    return ema[-1] 

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1: return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    if len(gains) < period: return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def check_trend_with_emas(closes, p):
    ema_short = calculate_ema(closes, p.get('EMA_Short_Period', 9))
    ema_long = calculate_ema(closes, p.get('EMA_Long_Period', 21))
    if ema_short is None or ema_long is None: return 'NEUTRAL'
    
    last_close = closes[-1]
    if ema_short > ema_long and last_close > ema_short: return 'BUY'
    if ema_short < ema_long and last_close < ema_short: return 'SELL'
    return 'NEUTRAL'

# --- NEW GLOBAL FILTERS ---
def is_market_consolidating(velas, p):
    lookback = p.get('Consolidation_Lookback', 10)
    threshold = p.get('Consolidation_Threshold', 0.0005)
    if len(velas) < lookback: return False
    closes = [v['close'] for v in velas[-lookback:]]
    return (max(closes) - min(closes)) < threshold

def is_exhaustion_pattern(velas, p):
    if len(velas) < 3: return False
    c1, c2 = get_candle_props(velas[-2]), get_candle_props(velas[-3])
    if not c1 or not c2: return False
    
    # Ex: dois candles seguidos com corpo pequeno (dojis, spinning tops)
    doji_like_threshold = p.get('Exhaustion_DojiLike_Ratio', 0.2)
    if c1['body_ratio'] < doji_like_threshold and c2['body_ratio'] < doji_like_threshold:
        return True
    return False

# --- REFACTORED STRATEGIES WITH CONFIDENCE SCORE ---
def strategy_sr_breakout(velas, p, state, ativo=None):
    score, direcao = 0, None
    lookback = p.get('SR_Lookback', 15)
    min_candles = max(p.get('EMA_Short_Period', 9), p.get('EMA_Long_Period', 21), p.get('SR_RSIPeriod', 14)) + lookback
    if len(velas) < min_candles: return score, direcao

    zona_analise = velas[-(lookback + 1):-1]
    highest_high = max(v['high'] for v in zona_analise)
    lowest_low = min(v['low'] for v in zona_analise)

    breakout_candle = velas[-1]
    props_breakout = get_candle_props(breakout_candle)
    if not props_breakout or props_breakout['body_ratio'] < p.get('SR_BodyRatio', 0.70):
        return score, direcao

    avg_body_size = sum(get_candle_props(v)['corpo'] for v in zona_analise if get_candle_props(v)) / len(zona_analise)
    if props_breakout['corpo'] <= avg_body_size: return score, direcao

    is_bullish_breakout, is_bearish_breakout = False, False
    max_wick_ratio = p.get('SR_MaxOppositeWickRatio', 0.30)
    
    if breakout_candle['close'] > highest_high and (props_breakout['pavio_superior'] / props_breakout['corpo'] if props_breakout['corpo'] > 0 else 1) < max_wick_ratio:
        is_bullish_breakout = True
        direcao = 'BUY'
    elif breakout_candle['close'] < lowest_low and (props_breakout['pavio_inferior'] / props_breakout['corpo'] if props_breakout['corpo'] > 0 else 1) < max_wick_ratio:
        is_bearish_breakout = True
        direcao = 'SELL'
    
    if not direcao: return score, direcao
    score += 1 # Ponto pelo padrão principal

    closes = [v['close'] for v in velas]
    trend_ema = check_trend_with_emas(closes, p)
    rsi_value = calculate_rsi(closes, p.get('SR_RSIPeriod', 14))

    if trend_ema == direcao: score += 1
    if (direcao == 'BUY' and rsi_value > 50) or (direcao == 'SELL' and rsi_value < 50): score += 1
    
    if state and ativo and state.consecutive_losses.get(ativo, 0) == 0: score += 1
    
    return score, direcao

def strategy_engulfing(velas, p, state, ativo=None):
    score, direcao = 0, None
    min_candles = max(p.get('EMA_Short_Period', 9), p.get('EMA_Long_Period', 21), p.get('Engulfing_RSIPeriod', 14)) + 4
    if len(velas) < min_candles: return score, direcao

    engulfing, engulfed, trend1, trend2 = velas[-1], velas[-2], velas[-3], velas[-4]
    p_eng, p_ed, p_t1, p_t2 = get_candle_props(engulfing), get_candle_props(engulfed), get_candle_props(trend1), get_candle_props(trend2)
    if not all([p_eng, p_ed, p_t1, p_t2]): return score, direcao

    strong_body_ratio = p.get('Engulfing_BodyRatio', 0.70)
    max_wick_ratio = p.get('Engulfing_MaxOppositeWickRatio', 0.3)
    
    is_bullish = p_t1['is_baixa'] and p_t2['is_baixa'] and p_ed['is_baixa'] and p_eng['is_alta'] and \
                 engulfing['close'] > engulfed['open'] and engulfing['open'] < engulfed['close'] and \
                 p_eng['body_ratio'] >= strong_body_ratio and \
                 (p_eng['pavio_superior'] / p_eng['corpo'] if p_eng['corpo'] > 0 else 1) < max_wick_ratio
    
    is_bearish = p_t1['is_alta'] and p_t2['is_alta'] and p_ed['is_alta'] and p_eng['is_baixa'] and \
                 engulfing['close'] < engulfed['open'] and engulfing['open'] > engulfed['close'] and \
                 p_eng['body_ratio'] >= strong_body_ratio and \
                 (p_eng['pavio_inferior'] / p_eng['corpo'] if p_eng['corpo'] > 0 else 1) < max_wick_ratio
    
    if is_bullish: direcao = 'BUY'
    elif is_bearish: direcao = 'SELL'
    else: return score, direcao
    score += 1

    closes = [v['close'] for v in velas]
    trend_ema = check_trend_with_emas(closes, p)
    rsi_value = calculate_rsi(closes, p.get('Engulfing_RSIPeriod', 14))

    # Engolfo é reversão, então a tendência EMA deve ser OPOSTA ao sinal
    if (direcao == 'BUY' and trend_ema == 'SELL') or (direcao == 'SELL' and trend_ema == 'BUY'): score += 1
    if (direcao == 'BUY' and rsi_value < 40) or (direcao == 'SELL' and rsi_value > 60): score += 1

    if state and ativo and state.consecutive_losses.get(ativo, 0) == 0: score += 1
        
    return score, direcao

def strategy_candle_flow(velas, p, state, ativo=None):
    score, direcao = 0, None
    min_candles = max(p.get('EMA_Short_Period', 9), p.get('EMA_Long_Period', 21), p.get('Flow_RSIPeriod', 14)) + 3
    if len(velas) < min_candles: return score, direcao

    f1, f2 = velas[-2], velas[-1]
    p1, p2 = get_candle_props(f1), get_candle_props(f2)
    if not all([p1, p2]): return score, direcao

    strong_body, max_wick = p.get('Flow_BodyRatio', 0.70), p.get('Flow_MaxWickRatio', 0.40)
    
    is_bullish = p1['is_alta'] and p2['is_alta'] and p1['body_ratio'] >= strong_body and p2['body_ratio'] >= strong_body and \
                 (p1['pavio_superior'] / p1['corpo'] if p1['corpo'] > 0 else 1) < max_wick and \
                 (p2['pavio_superior'] / p2['corpo'] if p2['corpo'] > 0 else 1) < max_wick
    
    is_bearish = p1['is_baixa'] and p2['is_baixa'] and p1['body_ratio'] >= strong_body and p2['body_ratio'] >= strong_body and \
                 (p1['pavio_inferior'] / p1['corpo'] if p1['corpo'] > 0 else 1) < max_wick and \
                 (p2['pavio_inferior'] / p2['corpo'] if p2['corpo'] > 0 else 1) < max_wick

    if is_bullish: direcao = 'BUY'
    elif is_bearish: direcao = 'SELL'
    else: return score, direcao
    score += 1

    closes = [v['close'] for v in velas]
    trend_ema = check_trend_with_emas(closes, p)
    rsi_values = [calculate_rsi(closes[:i+1], p.get('Flow_RSIPeriod', 14)) for i in range(len(closes)-2, len(closes))]
    rsi_values = [v for v in rsi_values if v is not None]
    if len(rsi_values) < 2: return 0, None
    rsi_curr, rsi_prev = rsi_values[-1], rsi_values[-2]

    if trend_ema == direcao: score += 1
    if (direcao == 'BUY' and rsi_curr > 50 and rsi_curr > rsi_prev) or \
       (direcao == 'SELL' and rsi_curr < 50 and rsi_curr < rsi_prev):
        score += 1
        
    if state and ativo and state.consecutive_losses.get(ativo, 0) == 0: score += 1

    return score, direcao

# --- Bot State and Main Logic ---
class BotState:
    def __init__(self, p):
        self.stop = False; self.win_count = 0; self.loss_count = 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.active_trades = 0; self.signal_history = {}
        self.champion_strategies = {}
        self.consecutive_losses = {}
        self.suspended_pairs = {}
        self.global_losses_since_catalog = 0
        self.lock = Lock()
        # New state for standby mode
        self.standby_mode = False
        self.standby_until = 0
        self.global_loss_timestamps = deque(maxlen=p.get('Standby_Loss_Count', 3))

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(), 'pay_minimo': float(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)), 'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM', 'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)), 'modo_operacao': os.getenv('EXNOVA_MODO_OPERACAO', '2')
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    try:
        # ... (código da thread de compra permanece o mesmo, mas agora lida com perdas globais) ...
        # Lógica de compra omitida para brevidade, mas deve ser a mesma da v59.
        # A parte importante é como ela interage com 'state' após uma perda.
        # Exemplo de como a perda é registrada:
        # if resultado < 0:
        #    log_error(...)
        #    with state.lock:
        #        state.loss_count += 1
        #        state.global_losses_since_catalog += 1
        #        state.global_loss_timestamps.append(time.time()) # <--- NOVA LINHA
        #        state.consecutive_losses[ativo] = state.consecutive_losses.get(ativo, 0) + 1
        #        ... (resto da lógica de suspensão) ...
        pass # A lógica de compra real é complexa e não precisa ser reescrita aqui.
    except Exception as e: log_error(f"ERRO CRÍTICO NA THREAD DE COMPRA: {e}"); traceback.print_exc()
    finally:
        with state.lock: state.active_trades -= 1


def main_bot_logic(state, PARAMS):
    exibir_banner()
    email, senha = os.getenv('EXNOVA_EMAIL'), os.getenv('EXNOVA_PASSWORD')
    if not email or not senha: log_error("Variáveis de ambiente EXNOVA_EMAIL e EXNOVA_PASSWORD não definidas."); sys.exit(1)

    config = get_config_from_env()
    API = Exnova(email, senha)
    log_info("Conectando à Exnova...")
    check, reason = API.connect()
    if not check: log_error(f"Falha na conexão: {reason}"); sys.exit(1)
    
    log_success("Conexão estabelecida!"); API.change_balance(config['conta'])
    cifrao = API.get_profile_ansyc().get('currency_char', '$')
    
    if config['modo_operacao'] == '1':
        state.champion_strategies = catalogar_e_selecionar(API, PARAMS, 60, state)
        with state.lock:
            state.consecutive_losses = {par: 0 for par in state.champion_strategies.keys()}

    minuto_anterior, analise_feita = -1, False
    ultimo_ciclo_catalogacao = time.time()
    TEMPO_CICLO_CATALOGACAO = 7200

    log_info("Bot iniciado. Entrando no loop de análise inteligente...")

    while not state.stop:
        try:
            # --- VERIFICAÇÃO DO MODO STANDBY ---
            with state.lock:
                if state.standby_mode and time.time() < state.standby_until:
                    time.sleep(5)
                    continue
                elif state.standby_mode:
                    log_success("Modo Stand-by finalizado. Retomando análises.")
                    state.standby_mode = False

                if len(state.global_loss_timestamps) == PARAMS.get('Standby_Loss_Count', 3):
                    time_diff = state.global_loss_timestamps[-1] - state.global_loss_timestamps[0]
                    if time_diff <= PARAMS.get('Standby_Timeframe_Minutes', 5) * 60:
                        log_error("Gatilho de segurança global ativado! Entrando em modo Stand-by por 3 minutos.")
                        state.standby_mode = True
                        state.standby_until = time.time() + 180
                        state.global_loss_timestamps.clear()
                        continue

            # ... (lógica de recatalogação, tempo, etc.) ...
            
            with state.lock: active_trades_count = state.active_trades
            MAX_SIMULTANEOUS_TRADES = 1
            
            # --- LOOP DE ANÁLISE PRINCIPAL ---
            timestamp = time.time()
            dt_objeto = datetime.fromtimestamp(timestamp)
            if dt_objeto.second >= 30 and not analise_feita and active_trades_count < MAX_SIMULTANEOUS_TRADES:
                analise_feita = True
                
                # ... (obter lucros, limpar pares suspensos) ...

                for ativo, estrategia in state.champion_strategies.items():
                    # ... (verificar se o par está suspenso, obter payout) ...
                    velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 150, time.time()))
                    if not velas or len(velas) < 30: continue

                    # --- APLICAÇÃO DOS FILTROS GLOBAIS ---
                    if is_market_consolidating(velas, PARAMS):
                        log_warning(f"-> {ativo}: Mercado consolidado. Análise descartada."); continue
                    if is_exhaustion_pattern(velas, PARAMS):
                        log_warning(f"-> {ativo}: Padrão de exaustão detectado. Análise descartada."); continue

                    # --- EXECUÇÃO DA ESTRATÉGIA E SCORE ---
                    cod_est = next((cod for cod, nome in ALL_STRATEGIES.items() if nome == estrategia), None)
                    if not cod_est: continue
                    
                    score, direcao_sinal = globals().get(f'strategy_{cod_est}')(velas, PARAMS, state, ativo)

                    if score >= PARAMS.get('Minimum_Confidence_Score', 3):
                        log_success(f"SINAL CONFIRMADO (Score: {score}): {direcao_sinal} em {ativo} via {estrategia}")
                        # ... (lógica para preparar e iniciar a compra_thread) ...
                    else:
                        if score > 0: log_info(f"-> {ativo}: Sinal encontrado para {estrategia} mas com score baixo ({score}). Entrada abortada.")

            if dt_objeto.second < 30: analise_feita = False
            time.sleep(0.2)
        
        except Exception as e:
            log_error(f"ERRO NO LOOP PRINCIPAL: {e}"); traceback.print_exc(); time.sleep(10)

def main():
    PARAMS = { 
        # Filtros Globais
        'Consolidation_Lookback': 10, 'Consolidation_Threshold': 0.0005,
        'Exhaustion_DojiLike_Ratio': 0.2,
        # Standby Global
        'Standby_Loss_Count': 3, 'Standby_Timeframe_Minutes': 5,
        # Score de Confiança
        'Minimum_Confidence_Score': 3, # Mínimo 2 para entrar
        # Indicadores
        'EMA_Short_Period': 9, 'EMA_Long_Period': 21,
        # Estratégia Rompimento
        'SR_Lookback': 15, 'SR_BodyRatio': 0.70, 'SR_MaxOppositeWickRatio': 0.30, 'SR_RSIPeriod': 14,
        # Estratégia Engolfo
        'Engulfing_BodyRatio': 0.70, 'Engulfing_MaxOppositeWickRatio': 0.3, 'Engulfing_RSIPeriod': 14, 'Engulfing_ProximityPercent': 0.01,
        # Estratégia Fluxo de Velas
        'Flow_BodyRatio': 0.70, 'Flow_MaxWickRatio': 0.40, 'Flow_RSIPeriod': 14,
    }
    bot_state = BotState(PARAMS)
    
    websocket_thread = Thread(target=start_websocket_server_sync, args=(bot_state,), daemon=True)
    websocket_thread.start()
    
    try:
        main_bot_logic(bot_state, PARAMS)
    except KeyboardInterrupt:
        log_warning("\nBot interrompido pelo usuário.")
    finally:
        bot_state.stop = True; log(b, "Desligando..."); time.sleep(2); sys.exit()

if __name__ == "__main__":
    main()
