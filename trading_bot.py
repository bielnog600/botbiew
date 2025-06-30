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
              azkzero@gmail.com - v59 (Estratégia de Rompimento Aprimorada)
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

            if signal_data.get("type") == "log":
                log_info(f"Broadcasting LOG to {len(clients_to_send)} client(s)...")
            else:
                log_info(f"Broadcasting message to {len(clients_to_send)} client(s): {message_to_send[:150]}...")

            tasks = [client.send(message_to_send) for client in clients_to_send]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    log_error(f"Failed to send to client {clients_to_send[i].remote_address}: {result}")

        except queue.Empty:
            await asyncio.sleep(0.1)
        except Exception as e:
            log_error(f"Error in WebSocket broadcast: {e}")


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
        log_success(f"WebSocket Server started successfully on {server.sockets[0].getsockname()} with keep-alive pings.")
        await asyncio.gather(broadcast_signals(), server.wait_closed())
    try:
        loop.run_until_complete(main_async_logic())
    except Exception as e:
        log_error(f"CRITICAL ERROR in WebSocket server thread: {e}"); traceback.print_exc()
    finally:
        log_warning("WebSocket server loop is shutting down."); loop.close()


# --- Logic and Strategy Functions ---
def normalize_asset(name):
    return name.replace('-OTC', '').replace('-op', '').replace('-OP', '')

def validar_e_limpar_velas(velas_raw):
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {'open': v_raw.get('open'), 'close': v_raw.get('close'), 'high': v_raw.get('high') or v_raw.get('max'), 'low': v_raw.get('low') or v_raw.get('min')}
        if all(vela_padronizada.values()): velas_limpas.append(vela_padronizada)
    return velas_limpas

def catalogar_e_selecionar(api, params, assertividade_minima=80):
    log_info("="*40); log_info("MODO DE CATALOGAÇÃO E SELEÇÃO INICIADO..."); log_info("="*40)
    
    ativos_abertos = []
    all_assets = api.get_all_open_time()
    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False) and ativo not in ativos_abertos: ativos_abertos.append(ativo)
    
    if not ativos_abertos: log_error("Nenhum par aberto encontrado para catalogar."); return {}, []

    log_info(f"Encontrados {len(ativos_abertos)} pares abertos para análise.")
    champion_strategies = {}

    for ativo_original in ativos_abertos:
        try:
            log_info(f"\n--- Analisando o par: {w}{ativo_original}{c} ---")
            velas_historicas_raw = api.get_candles(ativo_original, 60, 120, time.time())
            todas_as_velas = validar_e_limpar_velas(velas_historicas_raw)
            if not todas_as_velas or len(todas_as_velas) < 100: log_warning(f"Não foi possível obter dados históricos suficientes para {ativo_original}."); continue
            
            best_strategy = None
            highest_assertiveness = 0

            for cod, nome in ALL_STRATEGIES.items():
                wins, losses, total = 0, 0, 0
                for i in range(50, len(todas_as_velas) - 1):
                    velas_atuais, vela_resultado = todas_as_velas[:i], todas_as_velas[i]
                    sinal = globals().get(f'strategy_{cod}')(velas_atuais, params)
                    if sinal:
                        total += 1
                        if (sinal == 'BUY' and vela_resultado['close'] > velas_atuais[-1]['close']) or \
                           (sinal == 'SELL' and vela_resultado['close'] < velas_atuais[-1]['close']):
                            wins += 1
                        else:
                            losses += 1
                
                if total > 2:
                    assertividade = (wins / total) * 100
                    log_info(f"  -> Estratégia '{nome}': {assertividade:.2f}% ({wins}W / {losses}L)")
                    if assertividade > highest_assertiveness:
                        highest_assertiveness = assertividade
                        best_strategy = nome
            
            if best_strategy and highest_assertiveness >= assertividade_minima:
                champion_strategies[ativo_original] = best_strategy
                log_success(f"  -> CAMPEÃ PARA {ativo_original}: {best_strategy} com {highest_assertiveness:.2f}% de acerto.")
            else:
                log_warning(f"  -> Nenhuma estratégia para {ativo_original} atingiu a assertividade mínima de {assertividade_minima}%.")

        except Exception as e: log_error(f"Ocorreu um erro ao analisar o par {ativo_original}: {e}"); traceback.print_exc()
        
    log_info("="*40); log_info("CATALOGAÇÃO FINALIZADA!"); log_info("="*40)
    return champion_strategies


def get_candle_props(vela):
    props = {}
    if not all(k in vela for k in ['high', 'low', 'open', 'close']): return None
    props['range'] = vela['high'] - vela['low']
    if props['range'] == 0: return None
    props['corpo'] = abs(vela['open'] - vela['close'])
    props['body_ratio'] = props['corpo'] / props['range']
    props['is_alta'] = vela['close'] > vela['open']
    props['is_baixa'] = vela['close'] < vela['open']
    props['pavio_superior'] = vela['high'] - max(vela['open'], vela['close'])
    props['pavio_inferior'] = min(vela['open'], vela['close']) - vela['low']
    return props

# --- HELPER FUNCTIONS FOR ADVANCED STRATEGIES ---
def calculate_ema(closes, period):
    if len(closes) < period: return None
    ema = []
    sma = sum(closes[:period]) / period
    ema.append(sma)
    multiplier = 2 / (period + 1)
    for price in closes[period:]:
        ema_value = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(ema_value)
    return ema[-1] 

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1: return None
    
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [delta if delta > 0 else 0 for delta in deltas]
    losses = [-delta if delta < 0 else 0 for delta in deltas]

    if len(gains) < period: return None

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0: return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
    
# --- STRATEGIES ---
def strategy_sr_breakout(velas, p):
    """
    Estratégia de Rompimento de Suporte/Resistência aprimorada.
    """
    lookback = p.get('SR_Lookback', 15)
    min_candles = max(p.get('SR_EMAPeriod', 20), p.get('SR_RSIPeriod', 14)) + lookback
    if len(velas) < min_candles:
        return None

    # --- 1. Marcar zonas de S/R ---
    zona_analise = velas[-(lookback + 1):-1]
    highest_high = max(v['high'] for v in zona_analise)
    lowest_low = min(v['low'] for v in zona_analise)

    # --- 2. Verificar o candle de rompimento ---
    breakout_candle = velas[-1]
    props_breakout = get_candle_props(breakout_candle)
    if not props_breakout:
        return None

    strong_body_ratio = p.get('SR_BodyRatio', 0.70)
    max_opposite_wick_ratio = p.get('SR_MaxOppositeWickRatio', 0.30)

    # Verifica se o corpo é forte
    if props_breakout['body_ratio'] < strong_body_ratio:
        return None

    # Verifica se o candle é maior que a média dos candles da zona de análise
    avg_body_size = sum(get_candle_props(v)['corpo'] for v in zona_analise if get_candle_props(v) and get_candle_props(v)['corpo']) / len(zona_analise)
    if props_breakout['corpo'] <= avg_body_size:
        return None

    is_bullish_breakout = False
    if breakout_candle['close'] > highest_high:
        # Pavio curto contra o movimento
        if (props_breakout['pavio_superior'] / props_breakout['corpo'] if props_breakout['corpo'] > 0 else 1) < max_opposite_wick_ratio:
            is_bullish_breakout = True

    is_bearish_breakout = False
    if breakout_candle['close'] < lowest_low:
        # Pavio curto contra o movimento
        if (props_breakout['pavio_inferior'] / props_breakout['corpo'] if props_breakout['corpo'] > 0 else 1) < max_opposite_wick_ratio:
            is_bearish_breakout = True

    if not is_bullish_breakout and not is_bearish_breakout:
        return None

    # --- 3. Confirmar com Confluências ---
    closes = [v['close'] for v in velas]
    ema_value = calculate_ema(closes, p.get('SR_EMAPeriod', 20))
    rsi_value = calculate_rsi(closes, p.get('SR_RSIPeriod', 14))

    if ema_value is None or rsi_value is None:
        return None
        
    ema_confirm = False
    rsi_confirm = False

    if is_bullish_breakout:
        if breakout_candle['close'] > ema_value: ema_confirm = True
        if rsi_value > 50: rsi_confirm = True
    elif is_bearish_breakout:
        if breakout_candle['close'] < ema_value: ema_confirm = True
        if rsi_value < 50: rsi_confirm = True
    
    if not (ema_confirm or rsi_confirm):
        return None

    # --- 4. Sinal de Entrada ---
    if is_bullish_breakout: return 'BUY'
    if is_bearish_breakout: return 'SELL'
    
    return None
    
def strategy_engulfing(velas, p):
    min_candles = max(p.get('Engulfing_EMAPeriod', 20), p.get('Engulfing_RSIPeriod', 14)) + 4
    if len(velas) < min_candles: return None

    engulfing_candle, engulfed_candle = velas[-1], velas[-2]
    trend_candle_1, trend_candle_2 = velas[-3], velas[-4]

    props_engulfing = get_candle_props(engulfing_candle)
    props_engulfed = get_candle_props(engulfed_candle)
    props_trend1 = get_candle_props(trend_candle_1)
    props_trend2 = get_candle_props(trend_candle_2)

    if not all([props_engulfing, props_engulfed, props_trend1, props_trend2]): return None

    strong_body_ratio = p.get('Engulfing_BodyRatio', 0.7)
    max_wick_ratio = p.get('Engulfing_MaxOppositeWickRatio', 0.3)

    is_bullish_engulf = (
        props_trend1['is_baixa'] and props_trend2['is_baixa'] and
        props_engulfed['is_baixa'] and props_engulfing['is_alta'] and
        engulfing_candle['close'] > engulfed_candle['open'] and 
        engulfing_candle['open'] < engulfed_candle['close'] and
        props_engulfing['body_ratio'] >= strong_body_ratio and
        (props_engulfing['pavio_superior'] / props_engulfing['corpo'] < max_wick_ratio if props_engulfing['corpo'] > 0 else False)
    )

    is_bearish_engulf = (
        props_trend1['is_alta'] and props_trend2['is_alta'] and
        props_engulfed['is_alta'] and props_engulfing['is_baixa'] and
        engulfing_candle['close'] < engulfed_candle['open'] and 
        engulfing_candle['open'] > engulfed_candle['close'] and
        props_engulfing['body_ratio'] >= strong_body_ratio and
        (props_engulfing['pavio_inferior'] / props_engulfing['corpo'] < max_wick_ratio if props_engulfing['corpo'] > 0 else False)
    )

    if not is_bullish_engulf and not is_bearish_engulf: return None

    closes = [v['close'] for v in velas]
    ema_value = calculate_ema(closes, p.get('Engulfing_EMAPeriod', 20))
    rsi_value = calculate_rsi(closes, p.get('Engulfing_RSIPeriod', 14))

    if ema_value is None or rsi_value is None: return None
        
    ema_confirm, rsi_confirm = False, False

    if is_bullish_engulf:
        proximity = ema_value * (p.get('Engulfing_ProximityPercent', 0.01) / 100)
        if abs(engulfing_candle['low'] - ema_value) <= proximity: ema_confirm = True
        if rsi_value < 30: rsi_confirm = True

    elif is_bearish_engulf:
        proximity = ema_value * (p.get('Engulfing_ProximityPercent', 0.01) / 100)
        if abs(engulfing_candle['high'] - ema_value) <= proximity: ema_confirm = True
        if rsi_value > 70: rsi_confirm = True
    
    if not (ema_confirm or rsi_confirm): return None

    if is_bullish_engulf: return 'BUY'
    if is_bearish_engulf: return 'SELL'
    return None

def strategy_candle_flow(velas, p):
    min_candles = p.get('Flow_RSIPeriod', 14) + 3
    if len(velas) < min_candles:
        return None

    flow_candle_1, flow_candle_2 = velas[-2], velas[-1] 

    props_1 = get_candle_props(flow_candle_1)
    props_2 = get_candle_props(flow_candle_2)

    if not all([props_1, props_2]):
        return None

    strong_body_ratio = p.get('Flow_BodyRatio', 0.70)
    max_wick_ratio = p.get('Flow_MaxWickRatio', 0.40)
    
    is_bullish_flow = (
        props_1['is_alta'] and props_2['is_alta'] and
        props_1['body_ratio'] >= strong_body_ratio and
        props_2['body_ratio'] >= strong_body_ratio and
        (props_1['pavio_superior'] / props_1['corpo'] < max_wick_ratio if props_1['corpo'] > 0 else False) and
        (props_2['pavio_superior'] / props_2['corpo'] < max_wick_ratio if props_2['corpo'] > 0 else False)
    )
    
    is_bearish_flow = (
        props_1['is_baixa'] and props_2['is_baixa'] and
        props_1['body_ratio'] >= strong_body_ratio and
        props_2['body_ratio'] >= strong_body_ratio and
        (props_1['pavio_inferior'] / props_1['corpo'] < max_wick_ratio if props_1['corpo'] > 0 else False) and
        (props_2['pavio_inferior'] / props_2['corpo'] < max_wick_ratio if props_2['corpo'] > 0 else False)
    )

    if not is_bullish_flow and not is_bearish_flow:
        return None

    closes = [v['close'] for v in velas]
    rsi_values = [calculate_rsi(closes[:i+1], p.get('Flow_RSIPeriod', 14)) for i in range(len(closes)-2, len(closes))]
    
    rsi_values = [v for v in rsi_values if v is not None]
    if len(rsi_values) < 2:
        return None
    
    rsi_current, rsi_previous = rsi_values[-1], rsi_values[-2]

    rsi_confirm = False
    if is_bullish_flow and rsi_current > 50 and rsi_current > rsi_previous:
        rsi_confirm = True
    elif is_bearish_flow and rsi_current < 50 and rsi_current < rsi_previous:
        rsi_confirm = True

    if not rsi_confirm:
        return None

    if is_bullish_flow: return 'BUY'
    if is_bearish_flow: return 'SELL'
    
    return None

def is_market_too_volatile(velas, p):
    last_candles = velas[-p.get('VolatilityCandles', 3):]
    volatile_count = 0
    for vela in last_candles:
        range_total = vela['high'] - vela['low']
        if range_total == 0: continue
        corpo = abs(vela['open'] - vela['close'])
        pavio_total = range_total - corpo
        if (pavio_total / range_total) > p.get('MaxWickRatio', 0.65):
            volatile_count += 1
    return volatile_count >= p.get('MinVolatileCandles', 2)

def is_market_gapped(velas, p):
    if len(velas) < 2: return False
    vela_anterior, vela_atual = velas[-2], velas[-1]
    gap = abs(vela_atual['open'] - vela_anterior['close'])
    avg_range = sum(v['high'] - v['low'] for v in velas[-10:]) / 10
    if avg_range == 0: return False
    return (gap / avg_range) > p.get('GapMaxPercentage', 0.3)

def is_trade_confirmed_by_previous_candle(sinal, vela_anterior, p):
    if not vela_anterior: return False
    
    range_total = vela_anterior['high'] - vela_anterior['low']
    if range_total == 0: return True 
    
    pavio_superior = vela_anterior['high'] - max(vela_anterior['open'], vela_anterior['close'])
    pavio_inferior = min(vela_anterior['open'], vela_anterior['close']) - vela_anterior['low']
    
    if sinal == 'BUY':
        if (pavio_superior / range_total) > p.get('ConfirmationMaxOppositeWickRatio', 0.45):
            return False
    
    if sinal == 'SELL':
        if (pavio_inferior / range_total) > p.get('ConfirmationMaxOppositeWickRatio', 0.45):
            return False
        
    return True

class BotState:
    def __init__(self):
        self.stop = False; self.win_count = 0; self.loss_count = 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.active_trades = 0; self.signal_history = {}
        self.champion_strategies = {}
        self.consecutive_losses = {}
        self.suspended_pairs = {}
        self.global_losses_since_catalog = 0
        self.lock = Lock()

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(), 'pay_minimo': float(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)), 'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM', 'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)), 'modo_operacao': os.getenv('EXNOVA_MODO_OPERACAO', '2')
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    try:
        wait_time = target_entry_timestamp - time.time() - 5.0
        
        if wait_time > 0:
            log_info(f"Aguardando {wait_time:.2f}s para entrada precisa (envio 5s antes)...")
            time.sleep(wait_time)

        if time.time() > target_entry_timestamp + 10:
            msg = "ENTRADA ABORTADA: Oportunidade identificada tarde demais (após 10s)."
            log_error(f"-> {ativo}: {msg}")
            log_payload = {"type": "log", "data": {"level": "error", "message": msg, "pair": ativo}}
            signal_queue.put(log_payload)
            with state.lock: state.active_trades -= 1
            return

        entrada_atual = valor; direcao_atual, niveis_mg = direcao, config['mg_niveis'] if config['usar_mg'] else 0
        resultado_final = None
        for i in range(niveis_mg + 1):
            if state.stop: break
            if i > 0:
                gale_payload = {"type": "gale", "signal_id": signal_id, "gale_level": i}
                signal_queue.put(gale_payload)
                if signal_id in state.signal_history: state.signal_history[signal_id]["gale_level"] = i
            gale_info = f"(Gale {i})" if i > 0 else "(Entrada Principal)"; log_info(f"ORDEM {gale_info}: {ativo} | {cifrao}{entrada_atual:.2f} | {direcao_atual.upper()} | {expiracao}M")
            if tipo_op == 'digital': check, id_ordem = api.buy_digital_spot(ativo, entrada_atual, direcao_atual, expiracao)
            else: check, id_ordem = api.buy(entrada_atual, ativo, direcao_atual, expiracao)
            if not check: log_error(f"Falha ao abrir ordem no Gale {i}."); resultado_final = "ERROR"; break
            resultado, status_encontrado = 0.0, False; tempo_limite = time.time() + expiracao * 60 + 15
            while time.time() < tempo_limite:
                status, lucro = api.check_win_v4(id_ordem)
                if status: resultado, status_encontrado = lucro, True; break
                time.sleep(0.5)
            if not status_encontrado: log_error(f"Timeout na ordem {id_ordem}."); resultado_final = "ERROR"; break
            if resultado > 0:
                log_success(f"RESULTADO: WIN {gale_info} | Lucro: {cifrao}{resultado:.2f}")
                with state.lock:
                    state.win_count += 1
                    if i > 0: state.gale_wins[f'g{i}'] += 1
                    state.consecutive_losses[ativo] = 0
                resultado_final = 'WIN'; break
            elif resultado < 0:
                log_error(f"RESULTADO: LOSS {gale_info} | Perda: {cifrao}{abs(resultado):.2f}")
                with state.lock:
                    state.loss_count += 1
                    state.global_losses_since_catalog += 1
                    state.consecutive_losses[ativo] = state.consecutive_losses.get(ativo, 0) + 1
                    if state.consecutive_losses[ativo] >= 2:
                        state.suspended_pairs[ativo] = time.time() + 1800
                        msg = f"Par {ativo} suspenso por 30 min. devido a 2 derrotas seguidas."
                        log_error(msg)
                        log_payload = {"type": "log", "data": {"level": "error", "message": msg, "pair": ativo}}
                        signal_queue.put(log_payload)
                if i < niveis_mg: entrada_atual *= config['mg_fator']
                else: resultado_final = 'LOSS'
            else:
                log_warning(f"RESULTADO: EMPATE {gale_info}.")
                if i < niveis_mg: log_info("Re-entrando após empate...")
                else: resultado_final = 'DRAW'
        if resultado_final and resultado_final != "ERROR" and signal_id in state.signal_history:
            state.signal_history[signal_id]["result"] = resultado_final
            placar_payload = { "type": "result", "signal_id": signal_id, "result": resultado_final, "placar": { "wins": state.win_count, "losses": state.loss_count, "gale_wins": sum(state.gale_wins.values()) } }
            signal_queue.put(placar_payload)
    except Exception as e: log_error(f"ERRO CRÍTICO NA THREAD DE COMPRA: {e}"); traceback.print_exc()
    finally:
        with state.lock: state.active_trades -= 1

def main_bot_logic(state):
    exibir_banner()
    email = os.getenv('EXNOVA_EMAIL', 'test@example.com')
    senha = os.getenv('EXNOVA_PASSWORD', 'password')
    if not email or not senha:
        log_error("Variáveis de ambiente EXNOVA_EMAIL e EXNOVA_PASSWORD não definidas.")
        sys.exit(1)

    config = get_config_from_env()
    API = Exnova(email, senha)
    log_info("Tentando conectar à Exnova...")
    check, reason = API.connect()
    if not check:
        log_error(f"Falha na conexão: {reason}")
        sys.exit(1)

    log_success("Conexão estabelecida com sucesso!")
    API.change_balance(config['conta'])
    cifrao = "$"
    try:
        perfil = API.get_profile_ansyc()
        cifrao = perfil.get('currency_char', '$')
        log_info(f"Olá, {perfil.get('name', 'User')}! Iniciando bot em modo servidor.")
    except Exception as e:
        log_warning(f"Não foi possível obter o perfil do usuário. Erro: {e}")
        log_info(f"Olá! Iniciando bot em modo servidor.")
    
    # --- UPDATED PARAMS DICTIONARY ---
    PARAMS = { 
        'VolatilityCandles': 3, 'MinVolatileCandles': 3, 'MaxWickRatio': 0.75, 
        'ConfirmationMaxOppositeWickRatio': 0.45, 'GapMaxPercentage': 0.3,
        
        # Parâmetros Estratégia Rompimento Aprimorada
        'SR_Lookback': 15,
        'SR_BodyRatio': 0.70,
        'SR_MaxOppositeWickRatio': 0.30,
        'SR_EMAPeriod': 20,
        'SR_RSIPeriod': 14,
        
        # Parâmetros Estratégia Engolfo Aprimorada
        'Engulfing_BodyRatio': 0.70,
        'Engulfing_MaxOppositeWickRatio': 0.3,
        'Engulfing_EMAPeriod': 20,
        'Engulfing_RSIPeriod': 14,
        'Engulfing_ProximityPercent': 0.01,

        # Parâmetros Estratégia Fluxo de Velas
        'Flow_BodyRatio': 0.70,
        'Flow_MaxWickRatio': 0.40,
        'Flow_RSIPeriod': 14,
    }
    
    if config['modo_operacao'] == '1':
        state.champion_strategies = catalogar_e_selecionar(API, PARAMS, 60)
        with state.lock:
            state.consecutive_losses = {par: 0 for par in state.champion_strategies.keys()}

    minuto_anterior, analise_feita = -1, False
    ultimo_sinal_timestamp = time.time()
    ultimo_ciclo_catalogacao = time.time()
    TEMPO_LIMITE_INATIVIDADE = 300
    TEMPO_CICLO_CATALOGACAO = 7200

    log_info("Bot iniciado. Entrando no loop de análise...")

    while not state.stop:
        try:
            MAX_SIMULTANEOUS_TRADES = 1
            
            if config['modo_operacao'] == '1':
                if time.time() - ultimo_ciclo_catalogacao > TEMPO_CICLO_CATALOGACAO or state.global_losses_since_catalog >= 5:
                    msg = "Gatilho de segurança ativado. Recatalogando todo o mercado..."
                    log_warning(msg)
                    log_payload = {"type": "log", "data": {"level": "warning", "message": msg, "pair": "SISTEMA"}}
                    signal_queue.put(log_payload)

                    state.champion_strategies = catalogar_e_selecionar(API, PARAMS, 60)
                    with state.lock:
                        state.consecutive_losses = {par: 0 for par in state.champion_strategies.keys()}
                        state.suspended_pairs.clear()
                        state.global_losses_since_catalog = 0
                    ultimo_ciclo_catalogacao = time.time()
                    ultimo_sinal_timestamp = time.time()
            
            timestamp = time.time()
            dt_objeto = datetime.fromtimestamp(timestamp)
            minuto_atual, segundo_atual = dt_objeto.minute, dt_objeto.second

            if minuto_anterior != minuto_atual:
                minuto_anterior, analise_feita = minuto_atual, False
                with state.lock: active_trades_count = state.active_trades
                if active_trades_count == 0:
                    horario_proxima_vela = (dt_objeto.replace(second=0, microsecond=0) + timedelta(minutes=1)).strftime('%H:%M')
                    status_payload = { "type": "analysis_status", "status": "Aguardando vela das %s...", "next_entry_time": horario_proxima_vela }
                    signal_queue.put(status_payload)
            
            with state.lock: active_trades_count = state.active_trades
            
            if segundo_atual >= 30 and not analise_feita and active_trades_count < MAX_SIMULTANEOUS_TRADES:
                analise_feita = True
                sinais_para_executar = []

                if config['modo_operacao'] == '1':
                    potential_trades = []
                    all_profits = API.get_all_profit()
                    
                    with state.lock:
                        pares_a_remover = [p for p, t in state.suspended_pairs.items() if time.time() > t]
                        for p in pares_a_remover:
                            del state.suspended_pairs[p]

                    for ativo_original, estrategia_campea in state.champion_strategies.items():
                        if ativo_original in state.suspended_pairs: continue

                        tipo_mercado, payout = None, 0
                        for market_type in ['binary', 'turbo']:
                            if ativo_original in all_profits and market_type in all_profits.get(ativo_original, {}):
                                tipo_mercado, payout = market_type, all_profits[ativo_original][market_type] * 100
                                break
                        
                        if not tipo_mercado or payout < config['pay_minimo']: continue

                        log_info(f"--- Analisando {ativo_original} com a estratégia campeã: {estrategia_campea} ---")
                        velas = validar_e_limpar_velas(API.get_candles(ativo_original, 60, 150, time.time()))
                        if not velas or len(velas) < 20: continue
                        
                        if is_market_too_volatile(velas, PARAMS) or is_market_gapped(velas, PARAMS):
                            msg = "Mercado instável (volátil ou com gap). Análise descartada."
                            log_warning(f"-> {ativo_original}: {msg}")
                            log_payload = {"type": "log", "data": {"level": "warning", "message": msg, "pair": ativo_original}}
                            signal_queue.put(log_payload)
                            continue

                        cod_est = next((cod for cod, nome in ALL_STRATEGIES.items() if nome == estrategia_campea), None)
                        if not cod_est: continue
                        
                        sinal = globals().get(f'strategy_{cod_est}')(velas, PARAMS)
                        if sinal and is_trade_confirmed_by_previous_candle(sinal, velas[-2], PARAMS):
                            potential_trades.append({'ativo': ativo_original, 'tipo_op': tipo_mercado, 'velas': velas, 'payout': payout, 'direcao': {'BUY': 'call', 'SELL': 'put'}.get(sinal), 'nome_estrategia': estrategia_campea})
                    
                    if potential_trades:
                        sorted_trades = sorted(potential_trades, key=lambda x: x['payout'], reverse=True)
                        sinais_para_executar = sorted_trades
                
                vagas_disponiveis = MAX_SIMULTANEOUS_TRADES - active_trades_count
                for sinal_info in sinais_para_executar[:vagas_disponiveis]:
                    with state.lock: state.active_trades += 1
                    
                    ultimo_sinal_timestamp = time.time()
                    
                    horario_analise_dt = dt_objeto.replace(second=0, microsecond=0)
                    horario_analise_str = horario_analise_dt.strftime('%H:%M')
                    horario_entrada_dt = horario_analise_dt + timedelta(minutes=1)
                    horario_entrada_str = horario_entrada_dt.strftime('%H:%M')
                    log_success(f"ORDEM PREPARADA: {sinal_info['direcao'].upper()} em {sinal_info['ativo']} para a vela das {horario_entrada_str}")
                    
                    target_entry_timestamp = (timestamp // 60 + 1) * 60
                    signal_id = str(uuid.uuid4())
                    vela_sinal = sinal_info['velas'][-1]
                    signal_payload = {
                        "type": "signal", "signal_id": signal_id, "pair": sinal_info['ativo'], "strategy": sinal_info['nome_estrategia'], "direction": sinal_info['direcao'].upper(),
                        "entry_time": horario_entrada_str, "analysis_time": horario_analise_str, 
                        "candle": { "open": vela_sinal['open'], "close": vela_sinal['close'], "high": vela_sinal['high'], "low": vela_sinal['low'], "color": 'text-green-400' if vela_sinal['close'] > vela_sinal['open'] else 'text-red-400' },
                        "result": None, "gale_level": 0
                    }
                    state.signal_history[signal_id] = signal_payload
                    signal_queue.put(signal_payload)
                    Thread(target=compra_thread, args=(API, sinal_info['ativo'], config['valor_entrada'], sinal_info['direcao'], config['expiracao'], sinal_info['tipo_op'], state, config, cifrao, signal_id, target_entry_timestamp), daemon=True).start()
            
            time.sleep(0.2)
        
        except Exception as e:
            log_error(f"ERRO NÃO TRATADO NO LOOP PRINCIPAL: {e}")
            traceback.print_exc()
            log_warning("Aguardando 10 segundos antes de continuar...")
            time.sleep(10)

def main():
    bot_state = BotState()
    websocket_thread = Thread(target=start_websocket_server_sync, args=(bot_state,), daemon=True)
    websocket_thread.start()
    
    try:
        main_bot_logic(bot_state)
    except KeyboardInterrupt:
        log_warning("\nBot interrompido pelo usuário.")
    except Exception as e:
        log_error(f"Erro fatal ao iniciar o bot: {e}")
        traceback.print_exc()
    finally:
        bot_state.stop = True
        log(b, "Desligando o bot...")
        time.sleep(2)
        sys.exit()

if __name__ == "__main__":
    main()
