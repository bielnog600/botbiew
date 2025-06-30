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

# --- Centralized Logging Functions ---
def log(cor, mensagem):
    """Prints a message to the console with a specific color."""
    print(f"{cor}[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {w}{mensagem}")

def _log_and_broadcast(level, message, pair="Sistema"):
    """Internal function to handle console logging and WebSocket broadcasting."""
    color_map = {'info': c, 'success': g, 'warning': y, 'error': r}
    console_color = color_map.get(level, w)
    
    clean_message = ''.join(filter(lambda char: char not in [g, y, r, w, c, b], message))
    
    log(console_color, f"{pair}: {clean_message}" if pair != "Sistema" else clean_message)

    log_payload = { "type": "log", "data": { "level": level, "message": clean_message, "pair": pair } }
    signal_queue.put(log_payload)

def log_info(msg, pair="Sistema"): _log_and_broadcast('info', msg, pair)
def log_success(msg, pair="Sistema"): _log_and_broadcast('success', msg, pair)
def log_warning(msg, pair="Sistema"): _log_and_broadcast('warning', msg, pair)
def log_error(msg, pair="Sistema"): _log_and_broadcast('error', msg, pair)


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
              azkzero@gmail.com - v63 (Filtro de Tendência Principal)
    ''')
    print(y + "*"*88)
    print(c + "="*88)

class WebSocketServer:
    def __init__(self, bot_state):
        self.bot_state = bot_state

    async def handler(self, websocket, *args):
        with clients_lock:
            connected_clients.add(websocket)
        log_success(f"Novo cliente WebSocket conectado: {websocket.remote_address}")
        try:
            initial_state = {
                "type": "init",
                "data": { "signals": list(self.bot_state.signal_history.values()), "placar": { "wins": self.bot_state.win_count, "losses": self.bot_state.loss_count, "gale_wins": sum(self.bot_state.gale_wins.values()) } }
            }
            await websocket.send(json.dumps(initial_state))
            await websocket.wait_closed()
        except websockets.exceptions.ConnectionClosed:
            pass # Silently handle closed connections
        finally:
            with clients_lock:
                connected_clients.discard(websocket)
            log_warning(f"Cliente WebSocket desconectado: {websocket.remote_address}")

async def broadcast_signals():
    while True:
        try:
            signal_data = signal_queue.get_nowait()
            message_to_send = json.dumps(signal_data)
            
            with clients_lock:
                if not connected_clients:
                    await asyncio.sleep(0.1)
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
            log_warning("reuse_port não suportado. Iniciando sem ele.")
            del server_options["reuse_port"]
            start_server = websockets.serve(server_instance.handler, "0.0.0.0", 8765, **server_options)
        server = await start_server
        log_success(f"Servidor WebSocket iniciado em {server.sockets[0].getsockname()}")
        await asyncio.gather(broadcast_signals(), server.wait_closed())
    try:
        loop.run_until_complete(main_async_logic())
    except Exception as e:
        log_error(f"ERRO CRÍTICO no thread do WebSocket: {e}"); traceback.print_exc()
    finally:
        log_warning("Loop do servidor WebSocket está sendo encerrado."); loop.close()

# --- Logic and Strategy Functions ---
def validar_e_limpar_velas(velas_raw):
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {'open': v_raw.get('open'), 'close': v_raw.get('close'), 'high': v_raw.get('high') or v_raw.get('max'), 'low': v_raw.get('low') or v_raw.get('min')}
        if all(v is not None for v in vela_padronizada.values()): velas_limpas.append(vela_padronizada)
    return velas_limpas

def catalogar_e_selecionar(api, params, state):
    log_info("MODO DE CATALOGAÇÃO E SELEÇÃO INICIADO...")
    
    ativos_abertos = []
    try:
        all_assets = api.get_all_open_time()
        for tipo_mercado in ['binary', 'turbo']:
            if tipo_mercado in all_assets:
                for ativo, info in all_assets[tipo_mercado].items():
                    if info.get('open', False) and ativo not in ativos_abertos: ativos_abertos.append(ativo)
    except Exception as e:
        log_error(f"Não foi possível obter os ativos abertos: {e}")
        return {}

    if not ativos_abertos: log_error("Nenhum par aberto encontrado para catalogar."); return {}

    log_info(f"Encontrados {len(ativos_abertos)} pares abertos para análise.")
    champion_strategies = {}
    assertividade_minima = params.get('Assertividade_Minima', 60)

    for ativo_original in ativos_abertos:
        try:
            log_info(f"Analisando o par...", pair=ativo_original)
            velas_historicas_raw = api.get_candles(ativo_original, 60, 300, time.time())
            todas_as_velas = validar_e_limpar_velas(velas_historicas_raw)
            if not todas_as_velas or len(todas_as_velas) < 150: 
                log_warning(f"Dados históricos insuficientes.", pair=ativo_original)
                continue
            
            best_strategy, highest_assertiveness = None, 0

            for cod, nome in ALL_STRATEGIES.items():
                wins, losses, total = 0, 0, 0
                for i in range(120, len(todas_as_velas) - 1):
                    velas_atuais, vela_resultado = todas_as_velas[:i], todas_as_velas[i]
                    score, direcao = globals().get(f'strategy_{cod}')(velas_atuais, params, None, ativo_original)
                    if score >= params.get('Minimum_Confidence_Score', 3):
                        sinal = direcao
                        total += 1
                        if (sinal == 'BUY' and vela_resultado['close'] > velas_atuais[-1]['close']) or \
                           (sinal == 'SELL' and vela_resultado['close'] < velas_atuais[-1]['close']):
                            wins += 1
                        else:
                            losses += 1
                
                if total > 5:
                    assertividade = (wins / total) * 100
                    log_info(f"Estratégia '{nome}': {assertividade:.2f}% ({wins}W/{losses}L)", pair=ativo_original)
                    if assertividade > highest_assertiveness:
                        highest_assertiveness, best_strategy = assertividade, nome
            
            if best_strategy and highest_assertiveness >= assertividade_minima:
                champion_strategies[ativo_original] = best_strategy
                log_success(f"Estratégia campeã: {best_strategy} com {highest_assertiveness:.2f}% de acerto.", pair=ativo_original)
            else:
                log_warning("Nenhuma estratégia atingiu os critérios mínimos.", pair=ativo_original)

        except Exception as e: log_error(f"Erro ao analisar: {e}", pair=ativo_original); traceback.print_exc()
        
    log_info("CATALOGAÇÃO FINALIZADA!")
    return champion_strategies

def get_candle_props(vela):
    if not vela or not all(k in vela and vela[k] is not None for k in ['high', 'low', 'open', 'close']):
        return None
        
    props = { 'open': vela['open'], 'close': vela['close'], 'high': vela['high'], 'low': vela['low'] }
    props['range'] = props['high'] - props['low']
    
    if props['range'] > 0:
        props['corpo'] = abs(props['open'] - props['close'])
        props['body_ratio'] = props['corpo'] / props['range']
    else:
        props['corpo'] = 0; props['body_ratio'] = 0

    props['is_alta'] = props['close'] > props['open']
    props['is_baixa'] = props['close'] < props['open']
    props['pavio_superior'] = props['high'] - max(props['open'], props['close'])
    props['pavio_inferior'] = min(props['open'], props['close']) - props['low']
    return props

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
    avg_gain = sum(gains[:period]) / period; avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# --- MASTER TREND FILTERS ---
def calculate_ma_slope(closes, period, lookback=3):
    if len(closes) < period + lookback: return 0
    ma_values = [sum(closes[-(period+i):-i if i > 0 else len(closes)]) / period for i in range(lookback, -1, -1)]
    if ma_values[-1] > ma_values[0]: return 1
    if ma_values[-1] < ma_values[0]: return -1
    return 0

def get_master_trend(velas, p):
    period = p.get('Trend_MA_Period', 100)
    if len(velas) < period: return 'SIDEWAYS'
    
    closes = [v['close'] for v in velas]
    last_close = closes[-1]
    
    ma_value = calculate_ema(closes, period)
    if ma_value is None: return 'SIDEWAYS'

    ma_slope = calculate_ma_slope(closes, period)

    if last_close > ma_value and ma_slope > 0: return 'UPTREND'
    if last_close < ma_value and ma_slope < 0: return 'DOWNTREND'
    return 'SIDEWAYS'

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
    
    doji_like_threshold = p.get('Exhaustion_DojiLike_Ratio', 0.2)
    if c1['body_ratio'] < doji_like_threshold and c2['body_ratio'] < doji_like_threshold:
        return True
    return False

# --- STRATEGIES (Unchanged, they respect the master filter now) ---
def strategy_sr_breakout(velas, p, state, ativo=None):
    score, direcao = 0, None
    lookback = p.get('SR_Lookback', 15)
    min_candles = max(p.get('EMA_Short_Period', 9), p.get('EMA_Long_Period', 21), p.get('SR_RSIPeriod', 14)) + lookback
    if len(velas) < min_candles: return score, direcao

    zona_analise = velas[-(lookback + 1):-1]
    highest_high, lowest_low = max(v['high'] for v in zona_analise), min(v['low'] for v in zona_analise)
    props_breakout = get_candle_props(velas[-1])
    if not props_breakout or props_breakout['body_ratio'] < p.get('SR_BodyRatio', 0.70): return score, direcao

    avg_body_size = sum(p.get('corpo', 0) for p in (get_candle_props(v) for v in zona_analise) if p) / len(zona_analise)
    if props_breakout['corpo'] <= avg_body_size: return score, direcao

    max_wick = p.get('SR_MaxOppositeWickRatio', 0.30)
    
    if velas[-1]['close'] > highest_high and (props_breakout['pavio_superior'] / props_breakout['corpo'] if props_breakout['corpo'] > 0 else 1) < max_wick: direcao = 'BUY'
    elif velas[-1]['close'] < lowest_low and (props_breakout['pavio_inferior'] / props_breakout['corpo'] if props_breakout['corpo'] > 0 else 1) < max_wick: direcao = 'SELL'
    
    if not direcao: return score, direcao
    score += 1

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

    props = [get_candle_props(velas[i]) for i in [-1, -2, -3, -4]]
    if not all(props): return score, direcao
    p_eng, p_ed, p_t1, p_t2 = props

    strong_body, max_wick = p.get('Engulfing_BodyRatio', 0.70), p.get('Engulfing_MaxOppositeWickRatio', 0.3)
    
    is_bullish = p_t1['is_baixa'] and p_t2['is_baixa'] and p_ed['is_baixa'] and p_eng['is_alta'] and \
                 velas[-1]['close'] > velas[-2]['open'] and velas[-1]['open'] < velas[-2]['close'] and \
                 p_eng['body_ratio'] >= strong_body and (p_eng['pavio_superior'] / p_eng['corpo'] if p_eng['corpo'] > 0 else 1) < max_wick
    
    is_bearish = p_t1['is_alta'] and p_t2['is_alta'] and p_ed['is_alta'] and p_eng['is_baixa'] and \
                 velas[-1]['close'] < velas[-2]['open'] and velas[-1]['open'] > velas[-2]['close'] and \
                 p_eng['body_ratio'] >= strong_body and (p_eng['pavio_inferior'] / p_eng['corpo'] if p_eng['corpo'] > 0 else 1) < max_wick
    
    if is_bullish: direcao = 'BUY'
    elif is_bearish: direcao = 'SELL'
    else: return score, direcao
    score += 1

    closes = [v['close'] for v in velas]
    trend_ema = check_trend_with_emas(closes, p)
    rsi_value = calculate_rsi(closes, p.get('Engulfing_RSIPeriod', 14))

    if (direcao == 'BUY' and trend_ema == 'SELL') or (direcao == 'SELL' and trend_ema == 'BUY'): score += 1
    if (direcao == 'BUY' and rsi_value < 40) or (direcao == 'SELL' and rsi_value > 60): score += 1
    if state and ativo and state.consecutive_losses.get(ativo, 0) == 0: score += 1
        
    return score, direcao

def strategy_candle_flow(velas, p, state, ativo=None):
    score, direcao = 0, None
    min_candles = max(p.get('EMA_Short_Period', 9), p.get('EMA_Long_Period', 21), p.get('Flow_RSIPeriod', 14)) + 3
    if len(velas) < min_candles: return score, direcao

    p1, p2 = get_candle_props(velas[-2]), get_candle_props(velas[-1])
    if not all([p1, p2]): return score, direcao

    strong_body, max_wick = p.get('Flow_BodyRatio', 0.70), p.get('Flow_MaxWickRatio', 0.40)
    
    is_bullish = p1['is_alta'] and p2['is_alta'] and p1['body_ratio'] >= strong_body and p2['body_ratio'] >= strong_body and \
                 (p1['pavio_superior'] / p1['corpo'] if p1['corpo'] > 0 else 1) < max_wick and (p2['pavio_superior'] / p2['corpo'] if p2['corpo'] > 0 else 1) < max_wick
    
    is_bearish = p1['is_baixa'] and p2['is_baixa'] and p1['body_ratio'] >= strong_body and p2['body_ratio'] >= strong_body and \
                 (p1['pavio_inferior'] / p1['corpo'] if p1['corpo'] > 0 else 1) < max_wick and (p2['pavio_inferior'] / p2['corpo'] if p2['corpo'] > 0 else 1) < max_wick

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
    if (direcao == 'BUY' and rsi_curr > 50 and rsi_curr > rsi_prev) or (direcao == 'SELL' and rsi_curr < 50 and rsi_curr < rsi_prev): score += 1
    if state and ativo and state.consecutive_losses.get(ativo, 0) == 0: score += 1

    return score, direcao

class BotState:
    def __init__(self, p):
        self.stop, self.win_count, self.loss_count = False, 0, 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.active_trades, self.signal_history = 0, {}
        self.champion_strategies, self.consecutive_losses, self.suspended_pairs = {}, {}, {}
        self.global_losses_since_catalog = 0
        self.lock = Lock()
        self.standby_mode, self.standby_until = False, 0
        self.global_loss_timestamps = deque(maxlen=p.get('Standby_Loss_Count', 3))

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(), 'pay_minimo': float(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)), 'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM', 'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)), 'modo_operacao': os.getenv('EXNOVA_MODO_OPERACAO', '1')
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    try:
        wait_time = target_entry_timestamp - time.time() - 5.0
        if wait_time > 0: time.sleep(wait_time)

        if time.time() > target_entry_timestamp + 10:
            log_error("Oportunidade perdida (atraso >10s).", pair=ativo)
            with state.lock: state.active_trades -= 1
            return

        entrada_atual, niveis_mg = valor, config['mg_niveis'] if config['usar_mg'] else 0
        for i in range(niveis_mg + 1):
            if state.stop: break
            if i > 0:
                signal_queue.put({"type": "gale", "signal_id": signal_id, "gale_level": i})
                if signal_id in state.signal_history: state.signal_history[signal_id]["gale_level"] = i
            
            gale_info = f"(Gale {i})" if i > 0 else "(Entrada Principal)"
            log_info(f"ORDEM {gale_info}: {cifrao}{entrada_atual:.2f} | {direcao.upper()} | {expiracao}M", pair=ativo)
            
            check, id_ordem = api.buy(entrada_atual, ativo, direcao, expiracao)
            if not check: log_error(f"Falha ao abrir ordem {gale_info}.", pair=ativo); break
            
            resultado, status_encontrado = 0.0, False; tempo_limite = time.time() + expiracao * 60 + 15
            while time.time() < tempo_limite:
                status, lucro = api.check_win_v4(id_ordem)
                if status: resultado, status_encontrado = lucro, True; break
                time.sleep(0.5)
            
            if not status_encontrado: log_error(f"Timeout na ordem {id_ordem}.", pair=ativo); break
            
            if resultado > 0:
                log_success(f"RESULTADO: WIN {gale_info} | Lucro: {cifrao}{resultado:.2f}", pair=ativo)
                with state.lock: state.win_count += 1; state.consecutive_losses[ativo] = 0;
                if i > 0: state.gale_wins[f'g{i}'] += 1
                break
            elif resultado < 0:
                log_error(f"RESULTADO: LOSS {gale_info} | Perda: {cifrao}{abs(resultado):.2f}", pair=ativo)
                with state.lock:
                    state.loss_count += 1; state.global_losses_since_catalog += 1; state.global_loss_timestamps.append(time.time())
                    state.consecutive_losses[ativo] = state.consecutive_losses.get(ativo, 0) + 1
                    if state.consecutive_losses[ativo] >= 2:
                        state.suspended_pairs[ativo] = time.time() + 1800
                        log_error("Par suspenso por 30 min (2 derrotas seguidas).", pair=ativo)
                if i < niveis_mg: entrada_atual *= config['mg_fator']
            else:
                log_warning(f"RESULTADO: EMPATE {gale_info}.", pair=ativo)
                if i >= niveis_mg: break
        
        placar = { "wins": state.win_count, "losses": state.loss_count, "gale_wins": sum(state.gale_wins.values()) }
        signal_queue.put({ "type": "result", "signal_id": signal_id, "result": "WIN" if resultado > 0 else ("LOSS" if resultado < 0 else "DRAW"), "placar": placar })
    except Exception as e: log_error(f"ERRO CRÍTICO NA THREAD: {e}", pair=ativo); traceback.print_exc()
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
    
    cifrao = "$"
    try:
        profile_data = API.get_profile_ansyc()
        if profile_data:
            cifrao = profile_data.get('currency_char', '$')
            log_success(f"Logado como {profile_data.get('name', 'Usuário')} | Moeda: {cifrao}")
        else:
            log_warning("Não foi possível obter dados do perfil, usando valores padrão.")
    except Exception as e:
        log_error(f"Erro ao obter perfil: {e}. Usando valores padrão.")

    if config['modo_operacao'] == '1':
        state.champion_strategies = catalogar_e_selecionar(API, PARAMS, state)
        with state.lock:
            state.consecutive_losses = {par: 0 for par in state.champion_strategies.keys()}

    minuto_anterior, analise_feita = -1, False
    ultimo_ciclo_catalogacao = time.time()
    log_info("Bot iniciado. Entrando no loop de análise inteligente...")

    while not state.stop:
        try:
            with state.lock:
                if state.standby_mode and time.time() < state.standby_until:
                    if int(time.time()) % 10 == 0: log_warning(f"Bot em modo Stand-by. Retomando em {int(state.standby_until - time.time())}s...")
                    time.sleep(5); continue
                elif state.standby_mode:
                    log_success("Modo Stand-by finalizado. Retomando análises."); state.standby_mode = False

                if len(state.global_loss_timestamps) >= PARAMS.get('Standby_Loss_Count', 3):
                    time_diff = state.global_loss_timestamps[-1] - state.global_loss_timestamps[0]
                    if time_diff <= PARAMS.get('Standby_Timeframe_Minutes', 5) * 60:
                        log_error(f"{PARAMS.get('Standby_Loss_Count', 3)} perdas em menos de {PARAMS.get('Standby_Timeframe_Minutes', 5)} min. Entrando em modo Stand-by.")
                        state.standby_mode, state.standby_until = True, time.time() + 180
                        state.global_loss_timestamps.clear(); continue
            
            if config['modo_operacao'] == '1' and (time.time() - ultimo_ciclo_catalogacao > PARAMS.get('Recatalog_Cycle_Hours', 2) * 3600 or state.global_losses_since_catalog >= PARAMS.get('Recatalog_Loss_Trigger', 5)):
                log_warning("Gatilho de segurança ativado. Recatalogando todo o mercado...")
                state.champion_strategies = catalogar_e_selecionar(API, PARAMS, state)
                with state.lock:
                    state.consecutive_losses = {par: 0 for par in state.champion_strategies.keys()}
                    state.suspended_pairs.clear(); state.global_losses_since_catalog = 0
                ultimo_ciclo_catalogacao = time.time()

            timestamp = time.time(); dt_objeto = datetime.fromtimestamp(timestamp)
            if dt_objeto.minute != minuto_anterior: minuto_anterior, analise_feita = dt_objeto.minute, False

            MAX_TRADES = PARAMS.get('MAX_SIMULTANEOUS_TRADES', 1)
            with state.lock: active_trades_count = state.active_trades
            
            if dt_objeto.second >= 30 and not analise_feita and active_trades_count < MAX_TRADES:
                analise_feita = True
                
                with state.lock:
                    for p in [p for p, t in state.suspended_pairs.items() if time.time() > t]:
                        del state.suspended_pairs[p]; log_info("Par reativado após suspensão.", pair=p)

                all_profits = API.get_all_profit()

                for ativo, estrategia in state.champion_strategies.items():
                    with state.lock:
                        if state.active_trades >= MAX_TRADES: break
                    if ativo in state.suspended_pairs: continue
                    
                    payout = all_profits.get(ativo, {}).get('turbo', 0) * 100 or all_profits.get(ativo, {}).get('binary', 0) * 100
                    if payout < config['pay_minimo']: continue

                    velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 200, time.time()))
                    if not velas or len(velas) < PARAMS.get('Trend_MA_Period', 100): continue

                    master_trend = get_master_trend(velas, PARAMS)
                    if master_trend == 'SIDEWAYS': log_info("Mercado lateral (filtro MA 100).", pair=ativo); continue
                    
                    if is_market_consolidating(velas, PARAMS): log_info("Mercado consolidado.", pair=ativo); continue
                    if is_exhaustion_pattern(velas, PARAMS): log_warning("Padrão de exaustão.", pair=ativo); continue

                    cod_est = next((cod for cod, nome in ALL_STRATEGIES.items() if nome == estrategia), None)
                    if not cod_est: continue
                    
                    score, direcao_sinal = globals().get(f'strategy_{cod_est}')(velas, PARAMS, state, ativo)

                    if score >= PARAMS.get('Minimum_Confidence_Score', 3):
                        if (master_trend == 'UPTREND' and direcao_sinal != 'BUY') or \
                           (master_trend == 'DOWNTREND' and direcao_sinal != 'SELL'):
                            log_warning(f"Sinal de {direcao_sinal} bloqueado pela tendência principal ({master_trend}).", pair=ativo)
                            continue
                        
                        horario_entrada_str = (dt_objeto.replace(second=0, microsecond=0) + timedelta(minutes=1)).strftime('%H:%M')
                        log_success(f"SINAL CONFIRMADO (Score: {score}) -> {direcao_sinal} para as {horario_entrada_str}", pair=ativo)
                        
                        with state.lock: state.active_trades += 1
                        signal_id = str(uuid.uuid4())
                        
                        signal_payload = { 
                            "type": "signal", "signal_id": signal_id, "pair": ativo, "strategy": estrategia, 
                            "direction": direcao_sinal, "entry_time": horario_entrada_str, 
                            "candle": velas[-1], "previous_candle": velas[-2],
                            "result": None, "gale_level": 0 
                        }
                        state.signal_history[signal_id] = signal_payload
                        signal_queue.put(signal_payload)

                        target_entry_timestamp = (timestamp // 60 + 1) * 60
                        tipo_op = 'turbo' if 'turbo' in all_profits.get(ativo, {}) else 'binary'
                        Thread(target=compra_thread, args=(API, ativo, config['valor_entrada'], {'BUY':'call', 'SELL':'put'}[direcao_sinal], config['expiracao'], tipo_op, state, config, cifrao, signal_id, target_entry_timestamp), daemon=True).start()

            time.sleep(0.2)
        
        except Exception as e:
            log_error(f"ERRO NO LOOP PRINCIPAL: {e}"); traceback.print_exc(); time.sleep(10)

def main():
    PARAMS = { 
        'Assertividade_Minima': 60, 'Recatalog_Cycle_Hours': 2, 'Recatalog_Loss_Trigger': 5,
        'MAX_SIMULTANEOUS_TRADES': 1,
        'Consolidation_Lookback': 10, 'Consolidation_Threshold': 0.0005, 'Exhaustion_DojiLike_Ratio': 0.2,
        'Standby_Loss_Count': 3, 'Standby_Timeframe_Minutes': 5, 'Minimum_Confidence_Score': 3,
        # Trend Filters
        'EMA_Short_Period': 9, 'EMA_Long_Period': 21, 'Trend_MA_Period': 100,
        # Strategies
        'SR_Lookback': 15, 'SR_BodyRatio': 0.70, 'SR_MaxOppositeWickRatio': 0.30, 'SR_RSIPeriod': 14,
        'Engulfing_BodyRatio': 0.70, 'Engulfing_MaxOppositeWickRatio': 0.3, 'Engulfing_RSIPeriod': 14,
        'Flow_BodyRatio': 0.70, 'Flow_MaxWickRatio': 0.40, 'Flow_RSIPeriod': 14,
    }
    bot_state = BotState(PARAMS)
    
    websocket_thread = Thread(target=start_websocket_server_sync, args=(bot_state,), daemon=True)
    websocket_thread.start()
    
    try:
        main_bot_logic(bot_state, PARAMS)
    except KeyboardInterrupt:
        log_warning("\nBot interrompido pelo usuário.")
    except Exception as e:
        log_error(f"Erro fatal: {e}")
        traceback.print_exc()
    finally:
        bot_state.stop = True; log_info("Desligando..."); time.sleep(2); sys.exit()

if __name__ == "__main__":
    main()
