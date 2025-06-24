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
# The configobj library is not used in the script, so it can be removed.
# from configobj import ConfigObj
from exnovaapi.stable_api import Exnova

# --- Mock Exnova Class for Testing ---
# This class simulates the Exnova API for local testing without real credentials.
class MockExnova:
    """A mock class to simulate the Exnova API for testing purposes."""
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.profile = None

    def connect(self):
        log_info("Mocking connection to Exnova...")
        return True, None

    def change_balance(self, balance_type):
        log_info(f"Mocking change_balance to {balance_type}")
        pass

    def get_profile_ansyc(self):
        log_info("Mocking get_profile_ansyc")
        self.profile = {'name': 'Test User', 'currency_char': '$'}
        return self.profile

    def get_all_open_time(self):
        # Returns a sample of open assets for testing.
        return {
            'binary': {'EURUSD': {'open': True}, 'GBPUSD': {'open': True}},
            'turbo': {'EURUSD-TURBO': {'open': True}}
        }

    def get_all_profit(self):
        # Returns sample profits for open assets.
        return {
            'EURUSD': {'binary': 0.85, 'turbo': 0.90},
            'GBPUSD': {'binary': 0.82}
        }

    def get_candles(self, active, interval, count, endtime):
        # Generates mock candle data for analysis.
        log_info(f"Mocking get_candles for {active}")
        candles = []
        start_price = 1.1000
        for i in range(count):
            candles.append({
                'open': start_price + (i * 0.0001),
                'close': start_price + 0.0005 + (i * 0.0001),
                'high': start_price + 0.0010 + (i * 0.0001),
                'low': start_price - 0.0005 + (i * 0.0001)
            })
        return candles

    def buy_digital_spot(self, active, amount, action, duration):
        log_info(f"Mocking buy_digital_spot: {active}, {amount}, {action}, {duration}")
        return True, "mock_order_" + str(uuid.uuid4())

    def buy(self, amount, active, action, duration):
        log_info(f"Mocking buy: {amount}, {active}, {action}, {duration}")
        return True, "mock_order_" + str(uuid.uuid4())

    def check_win_v4(self, order_id):
        # Simulates checking the result of a trade.
        log_info(f"Mocking check_win_v4 for order {order_id}")
        # Simulate a winning trade for testing purposes.
        return "win", 1.85 * float(os.getenv('EXNOVA_VALOR_ENTRADA', 1))


# --- Initialization ---
init(autoreset=True)
g, y, r, w, c, b = Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.WHITE, Fore.CYAN, Fore.BLUE
signal_queue = queue.Queue()
connected_clients = set()

# --- Logging Functions ---
def log(cor, mensagem):
    """Prints a colored log message to the console."""
    print(f"{cor}[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {w}{mensagem}")

def log_info(msg): log(c, msg)
def log_success(msg): log(g, msg)
def log_warning(msg): log(y, msg)
def log_error(msg): log(r, msg)

# --- Banner and WebSocket Functions ---
def exibir_banner():
    """Displays the application's startup banner."""
    print(c + "\n" + "="*88)
    print(y + "*"*88)
    print(g + '''
          ██╗     ██████╗  ██████╗  █████╗ ███╗   ██╗     ███████╗███╗   ███╗██╗████████╗██╗  ██╗
          ██║     ██╔═══██╗██╔════╝ ██╔══██╗████╗  ██║     ██╔════╝████╗ ████║██║╚══██╔══╝██║  ██║
          ██║     ██║   ██║██║  ███╗███████║██╔██╗ ██║     ███████╗██╔████╔██║██║   ██║   ███████║
          ██║     ██║   ██║██║   ██║██╔══██║██║╚██╗██║     ╚════██║██║╚██╔╝██║██║   ██║   ██╔══██║
          ███████╗╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║     ███████║██║ ╚═╝ ██║██║   ██║   ██║  ██║
          ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝     ╚══════╝╚═╝     ╚═╝╚═╝   ╚═╝   ╚═╝  ╚═╝ '''+c+'''    
    ████████╗██████╗ ██╗ █████╗ ██╗         ██╗   ██║██╗  ████████╗██████╗  █████╗ ██████╗  ██████╗ ████████╗
    ╚══██╔══╝██╔══██╗██║██╔══██╗██║         ██║   ██║██║  ╚══██╔══╝██╔══██╗██╔═══██╗╚══██╔══╝
      ██║   ██████╔╝██║███████║██║         ██║   ██║██║     ██║   ██████╔╝███████║██████╔╝██║   ██║   ██║   
      ██║   ██╔══██╗██║██╔══██║██║         ██║   ██║██║     ██║   ██╔══██╗██╔══██║██╔══██╗██║   ██║   ██║   
      ██║   ██║  ██║██║██║  ██║███████╗     ╚██████╔╝███████╗██║   ██║  ██║██║  ██║██████╔╝╚██████╔╝   ██║   
      ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝      ╚═════╝ ╚══════╝╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝    ╚═╝ '''+y+'''
                  azkzero@gmail.com
    ''')
    print(y + "*"*88)
    print(c + "="*88)

async def ws_handler(websocket, path, bot_state):
    """Handles new WebSocket connections, sends initial state, and manages client lifecycle."""
    connected_clients.add(websocket)
    log_success(f"New WebSocket client connected: {websocket.remote_address}")
    try:
        initial_state = {
            "type": "init",
            "data": {
                "signals": list(bot_state.signal_history.values()),
                "placar": {
                    "wins": bot_state.win_count,
                    "losses": bot_state.loss_count,
                    "gale_wins": sum(bot_state.gale_wins.values())
                }
            }
        }
        await websocket.send(json.dumps(initial_state))
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)
        log_warning(f"WebSocket client disconnected: {websocket.remote_address}")

async def broadcast_signals():
    """Continuously broadcasts signals from the queue to all connected WebSocket clients."""
    while True:
        try:
            signal_data = signal_queue.get_nowait()
            if connected_clients:
                message = json.dumps(signal_data)
                await asyncio.gather(*[client.send(message) for client in connected_clients])
        except queue.Empty:
            await asyncio.sleep(0.1)
        except Exception as e:
            log_error(f"Error in WebSocket broadcast: {e}")

def start_websocket_server_sync(bot_state):
    """Initializes and runs the WebSocket server in a synchronous context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    handler_with_state = lambda ws, path: ws_handler(ws, path, bot_state)
    loop.run_until_complete(start_websocket_server_async(handler_with_state))


async def start_websocket_server_async(handler):
    """Starts the WebSocket server, with a fallback for environments that don't support reuse_port."""
    try:
        server = await websockets.serve(handler, "0.0.0.0", 8765, reuse_port=True)
        log_info("WebSocket server started on ws://0.0.0.0:8765 with reuse_port.")
    except (NotImplementedError, OSError):
        log_warning("reuse_port is not available. Starting server without it.")
        server = await websockets.serve(handler, "0.0.0.0", 8765)
        log_info("WebSocket server started on ws://0.0.0.0:8765.")

    await broadcast_signals()


# --- Logic and Strategy Functions ---
def validar_e_limpar_velas(velas_raw):
    """Validates and cleans raw candle data from the API."""
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {
            'open': v_raw.get('open'),
            'close': v_raw.get('close'),
            'high': v_raw.get('high') or v_raw.get('max'),
            'low': v_raw.get('low') or v_raw.get('min')
        }
        if all(vela_padronizada.values()):
            velas_limpas.append(vela_padronizada)
    return velas_limpas

def catalogar_estrategias(api, state, params):
    """Analyzes historical data to determine the best trading strategy for each asset."""
    log_info("="*40); log_info("STARTING STRATEGY CATALOGING MODE..."); log_info("="*40)
    TODAS_AS_ESTRATEGIAS = {
        'mql_pullback': strategy_mql_pullback,
        'flow': strategy_flow,
        'patterns': strategy_patterns,
        'rejection_candle': strategy_rejection_candle
    }
    ativos_abertos = []
    all_assets = api.get_all_open_time()
    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False) and ativo not in ativos_abertos:
                    ativos_abertos.append(ativo)

    if not ativos_abertos:
        log_error("No open currency pairs found to catalog.")
        return

    log_info(f"Found {len(ativos_abertos)} open pairs for analysis.")
    for ativo in ativos_abertos:
        try:
            log_info(f"\n--- Analyzing pair: {w}{ativo}{c} ---")
            velas_historicas_raw = api.get_candles(ativo, 60, 500, time.time())
            todas_as_velas = validar_e_limpar_velas(velas_historicas_raw)
            if not todas_as_velas or len(todas_as_velas) < 100:
                log_warning(f"Could not get enough historical data for {ativo}.")
                continue

            resultados = {nome: {'win': 0, 'loss': 0} for nome in TODAS_AS_ESTRATEGIAS}
            for i in range(50, len(todas_as_velas) - 1):
                velas_atuais = todas_as_velas[:i]
                vela_sinal = velas_atuais[-1]
                vela_resultado = todas_as_velas[i]
                for nome, funcao_estrategia in TODAS_AS_ESTRATEGIAS.items():
                    sinal = funcao_estrategia(velas_atuais, params)
                    if sinal:
                        if (sinal == 'BUY' and vela_resultado['close'] > vela_sinal['close']) or \
                           (sinal == 'SELL' and vela_resultado['close'] < vela_sinal['close']):
                            resultados[nome]['win'] += 1
                        else:
                            resultados[nome]['loss'] += 1

            melhor_estrategia, maior_assertividade = None, 0
            for nome, res in resultados.items():
                total = res['win'] + res['loss']
                if total > 0:
                    assertividade = (res['win'] / total) * 100
                    if assertividade > maior_assertividade:
                        maior_assertividade, melhor_estrategia = assertividade, nome
            if melhor_estrategia and maior_assertividade > 50:
                log_success(f" >> Best strategy for {ativo}: '{melhor_estrategia}' with {maior_assertividade:.2f}% accuracy.")
                state.strategy_performance[ativo] = {'best_strategy': melhor_estrategia}
        except Exception as e:
            log_error(f"An error occurred while analyzing pair {ativo}: {e}")
            traceback.print_exc()
    log_info("="*40); log_info("CATALOGING FINISHED!"); log_info("="*40); time.sleep(5)

def sma_slope(closes, period):
    """Calculates the slope of a Simple Moving Average."""
    if len(closes) < period + 1: return None
    sma1 = sum(closes[-(period+1):-1]) / period
    sma2 = sum(closes[-period:]) / period
    if sma1 == sma2: return None
    return sma2 > sma1

def detect_fractals(velas, max_levels):
    """Detects fractal support and resistance levels."""
    highs, lows = [v['high'] for v in velas], [v['low'] for v in velas]
    res, sup = deque(maxlen=max_levels), deque(maxlen=max_levels)
    for i in range(len(velas) - 3, 2, -1):
        if highs[i-1] > max(highs[i-3:i-1] + highs[i:i+2]): res.append(highs[i-1])
        if lows[i-1] < min(lows[i-3:i-1] + lows[i:i+2]): sup.append(lows[i-1])
    return list(res), list(sup)

def strategy_rejection_candle(velas, p):
    """Strategy based on identifying rejection candles."""
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    o, h, l, c = velas[-2]['open'], velas[-2]['high'], velas[-2]['low'], velas[-2]['close']
    range_total = h - l
    if range_total == 0: return None
    corpo = abs(o - c); pavio_superior = h - max(o, c); pavio_inferior = min(o, c) - l
    if nano_up and ((pavio_inferior / range_total) >= p.get('RejectionWickMinRatio', 0.6)) and \
       ((corpo / range_total) <= p.get('RejectionBodyMaxRatio', 0.3)) and \
       ((pavio_superior / range_total) <= p.get('RejectionOppositeWickMaxRatio', 0.15)):
        return 'BUY'
    if not nano_up and ((pavio_superior / range_total) >= p.get('RejectionWickMinRatio', 0.6)) and \
       ((corpo / range_total) <= p.get('RejectionBodyMaxRatio', 0.3)) and \
       ((pavio_inferior / range_total) <= p.get('RejectionOppositeWickMaxRatio', 0.15)):
        return 'SELL'
    return None

def strategy_mql_pullback(velas, p):
    """Strategy based on pullbacks to fractal levels."""
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    res_levels, sup_levels = detect_fractals(velas, p['MaxLevels'])
    last = velas[-1]
    if nano_up and sup_levels and last['close'] > last['open']:
        if last['low'] <= sup_levels[0] + p['Proximity'] * p['Point'] and last['close'] >= sup_levels[0]:
            return 'BUY'
    if not nano_up and res_levels and last['close'] < last['open']:
        if last['high'] >= res_levels[0] - p['Proximity'] * p['Point'] and last['close'] <= res_levels[0]:
            return 'SELL'
    return None

def strategy_flow(velas, p):
    """Strategy based on market flow (consecutive candles of the same color)."""
    if len(velas) < p['MAPeriod'] + 3: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    last_candles = velas[-3:]
    if nano_up and all(v['close'] > v['open'] for v in last_candles): return 'BUY'
    if not nano_up and all(v['close'] < v['open'] for v in last_candles): return 'SELL'
    return None

def strategy_patterns(velas, p):
    """Strategy based on common candlestick patterns (e.g., engulfing)."""
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    penultimate, last = velas[-2], velas[-1]
    if nano_up:
        # Bullish Engulfing variations
        if (penultimate['close'] < penultimate['open'] and last['close'] > last['open'] and last['open'] < penultimate['close'] and last['close'] > penultimate['open']): return 'BUY'
        if (penultimate['close'] < penultimate['open'] and last['close'] > last['open'] and last['open'] > penultimate['close'] and last['close'] < penultimate['open']): return 'BUY'
    if not nano_up:
        # Bearish Engulfing variations
        if (penultimate['close'] > penultimate['open'] and last['close'] < last['open'] and last['open'] > penultimate['close'] and last['close'] < penultimate['open']): return 'SELL'
        if (penultimate['close'] > penultimate['open'] and last['close'] < last['open'] and last['open'] < penultimate['close'] and last['close'] > penultimate['open']): return 'SELL'
    return None

def is_market_indecisive(velas, p):
    """Determines if the market is currently indecisive based on recent candle bodies."""
    if len(velas) < 3: return False
    last_candles, indecisive_candles = velas[-3:], 0
    for vela in last_candles:
        range_total = vela['high'] - vela['low']
        if range_total == 0:
            indecisive_candles += 1
            continue
        corpo = abs(vela['open'] - vela['close'])
        if (corpo / range_total) <= 0.4:
            indecisive_candles += 1
    return indecisive_candles >= 2

class BotState:
    """A class to hold the state of the bot."""
    def __init__(self):
        self.stop = False
        self.win_count = 0
        self.loss_count = 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.is_trading = False
        self.signal_history = {}
        self.strategy_performance = {}

def get_config_from_env():
    """Loads configuration from environment variables with sensible defaults."""
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(),
        'pay_minimo': float(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)),
        'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM',
        'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)),
        'modo_operacao': os.getenv('EXNOVA_MODO_OPERACAO', '2')
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    """Handles the logic for placing a trade and subsequent Martingale entries in a separate thread."""
    try:
        wait_time = target_entry_timestamp - time.time()
        if wait_time > 0:
            time.sleep(max(0, wait_time - 0.2))
        while time.time() < target_entry_timestamp:
            pass

        entrada_atual = valor
        niveis_mg = config['mg_niveis'] if config['usar_mg'] else 0
        resultado_final = "ERRO" # Default result

        for i in range(niveis_mg + 1):
            if state.stop: break
            if i > 0:
                gale_payload = {"type": "gale", "signal_id": signal_id, "gale_level": i}
                signal_queue.put(gale_payload)
                if signal_id in state.signal_history:
                    state.signal_history[signal_id]["gale_level"] = i

            gale_info = f"(Gale {i})" if i > 0 else "(Main Entry)"
            log_info(f"ORDER {gale_info}: {ativo} | {cifrao}{entrada_atual:.2f} | {direcao.upper()} | {expiracao}M")

            if tipo_op == 'digital':
                check, id_ordem = api.buy_digital_spot(ativo, entrada_atual, direcao, expiracao)
            else:
                check, id_ordem = api.buy(entrada_atual, ativo, direcao, expiracao)

            if not check:
                log_error(f"Failed to open order in Gale {i}.")
                break # Breaks the loop, result is "ERRO"

            resultado, status_encontrado = 0.0, False
            tempo_limite = time.time() + expiracao * 60 + 15
            while time.time() < tempo_limite:
                status, lucro = api.check_win_v4(id_ordem)
                if status:
                    resultado, status_encontrado = lucro, True
                    break
                time.sleep(0.5)

            if not status_encontrado:
                log_error(f"Timeout on order {id_ordem}.")
                break # Breaks the loop, result is "ERRO"

            if resultado > 0:
                log_success(f"RESULT: WIN {gale_info} | Profit: {cifrao}{resultado:.2f}")
                state.win_count += 1
                if i > 0: state.gale_wins[f'g{i}'] += 1
                resultado_final = 'WIN'
                break # Exit on win
            elif resultado < 0:
                log_error(f"RESULT: LOSS {gale_info} | Loss: {cifrao}{abs(resultado):.2f}")
                if i < niveis_mg:
                    entrada_atual *= config['mg_fator']
                else:
                    state.loss_count += 1
                    resultado_final = 'LOSS'
            else: # Empate
                log_warning(f"RESULT: DRAW {gale_info}.")
                # Decide if a draw should be treated as a loss for Martingale
                # Here, it's treated as a neutral event, and we don't proceed to the next gale
                resultado_final = 'DRAW'
                break

        if signal_id in state.signal_history and resultado_final != "ERRO":
            state.signal_history[signal_id]["result"] = resultado_final
            placar_payload = {
                "type": "result",
                "signal_id": signal_id,
                "result": resultado_final,
                "placar": {
                    "wins": state.win_count,
                    "losses": state.loss_count,
                    "gale_wins": sum(state.gale_wins.values())
                }
            }
            signal_queue.put(placar_payload)
    except Exception as e:
        log_error(f"CRITICAL ERROR IN PURCHASE THREAD: {e}")
        traceback.print_exc()
    finally:
        state.is_trading = False

def obter_melhor_par(api, payout_minimo):
    """Finds the best asset to trade based on the highest payout."""
    all_assets = api.get_all_open_time()
    melhor_ativo = None
    melhor_payout = 0
    melhor_tipo = None

    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False):
                    try:
                        payout = api.get_all_profit()[ativo][tipo_mercado] * 100
                        if payout >= payout_minimo and payout > melhor_payout:
                            melhor_payout = payout
                            melhor_ativo = ativo
                            melhor_tipo = 'binary' if tipo_mercado == 'turbo' else tipo_mercado
                    except (KeyError, TypeError):
                        continue

    if melhor_ativo:
        return melhor_ativo, melhor_tipo, melhor_payout
    return None, None, None


def main_bot_logic(state):
    """The main logic loop for the trading bot."""
    exibir_banner()
    # Use environment variables with defaults for easier testing
    email = os.getenv('EXNOVA_EMAIL', 'test@example.com')
    senha = os.getenv('EXNOVA_PASSWORD', 'password')
    use_mock_api = os.getenv('USE_MOCK_API', 'true').lower() == 'true'

    config = get_config_from_env()
    API = MockExnova(email, senha) if use_mock_api else Exnova(email, senha)

    log_info("Attempting to connect to Exnova...")
    check, reason = API.connect()
    if not check:
        log_error(f"Connection failed: {reason}")
        sys.exit(1)

    log_success("Successfully connected!")
    API.change_balance(config['conta'])

    cifrao = "$"
    try:
        perfil = API.get_profile_ansyc()
        cifrao = perfil.get('currency_char', '$')
        log_info(f"Hello, {perfil.get('name', 'User')}! Bot starting in server mode.")
    except Exception as e:
        log_warning(f"Could not get user profile. Error: {e}")
        log_info(f"Hello! Bot starting in server mode.")

    PARAMS = { 'MAPeriod': 5, 'MaxLevels': 10, 'Proximity': 7.0, 'Point': 1e-6, 'FlowCandles': 3, 'RejectionWickMinRatio': 0.6, 'RejectionBodyMaxRatio': 0.3, 'RejectionOppositeWickMaxRatio': 0.15, 'IndecisionCandles': 3, 'IndecisionBodyMaxRatio': 0.4, 'IndecisionMinCount': 2 }
    if config['modo_operacao'] == '1':
        catalogar_estrategias(API, state, PARAMS)

    minuto_anterior, analise_feita = -1, False
    log_info("Bot started. Entering analysis loop...")

    while not state.stop:
        try:
            timestamp = time.time()
            dt_objeto = datetime.fromtimestamp(timestamp)
            minuto_atual, segundo_atual = dt_objeto.minute, dt_objeto.second

            if minuto_atual != minuto_anterior:
                minuto_anterior, analise_feita = minuto_atual, False
                if not state.is_trading:
                    msg = f"Observing the candle at {dt_objeto.strftime('%H:%M')}..."
                    signal_queue.put({"type": "analysis_status", "asset": "WAITING", "message": msg})

            if segundo_atual >= 55 and not analise_feita and not state.is_trading:
                analise_feita = True
                ativo, tipo_op, payout = obter_melhor_par(API, config['pay_minimo'])
                if not ativo:
                    continue

                velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 150, time.time()))
                if not velas or len(velas) < 20:
                    continue

                if is_market_indecisive(velas, PARAMS):
                    continue

                direcao_final, nome_estrategia_usada = None, None
                strategies_to_check = {
                    'mql_pullback': 'MQL Pullback',
                    'flow': 'Flow',
                    'patterns': 'Patterns',
                    'rejection_candle': 'Rejection'
                }
                
                best_strat_code = state.strategy_performance.get(ativo, {}).get('best_strategy')

                if best_strat_code:
                    sinal = globals().get(f'strategy_{best_strat_code}')(velas, PARAMS)
                    if sinal:
                        direcao_final = {'BUY': 'call', 'SELL': 'put'}.get(sinal)
                        nome_estrategia_usada = strategies_to_check.get(best_strat_code, "Unknown Strategy")
                else:
                    for cod, nome in strategies_to_check.items():
                        sinal = globals().get(f'strategy_{cod}')(velas, PARAMS)
                        if sinal:
                            direcao_final = {'BUY': 'call', 'SELL': 'put'}.get(sinal)
                            nome_estrategia_usada = nome
                            break

                if direcao_final:
                    state.is_trading = True
                    horario_entrada_dt = dt_objeto.replace(second=0, microsecond=0) + timedelta(minutes=1)
                    horario_entrada_str = horario_entrada_dt.strftime('%H:%M')
                    log_success(f"SIGNAL FOUND: {direcao_final.upper()} on {ativo} for the {horario_entrada_str} candle")

                    target_entry_timestamp = (timestamp // 60 + 1) * 60
                    signal_id = str(uuid.uuid4())
                    vela_sinal = velas[-1]
                    signal_payload = {
                        "type": "signal", "signal_id": signal_id, "pair": ativo,
                        "strategy": nome_estrategia_usada, "direction": direcao_final.upper(),
                        "entry_time": horario_entrada_str,
                        "candle": {
                            "open": vela_sinal['open'], "close": vela_sinal['close'],
                            "high": vela_sinal['high'], "low": vela_sinal['low'],
                            "color": 'text-green-400' if vela_sinal['close'] > vela_sinal['open'] else 'text-red-400'
                        },
                        "result": None, "gale_level": 0
                    }
                    state.signal_history[signal_id] = signal_payload
                    signal_queue.put(signal_payload)

                    Thread(
                        target=compra_thread,
                        args=(API, ativo, config['valor_entrada'], direcao_final, config['expiracao'], tipo_op, state, config, cifrao, signal_id, target_entry_timestamp),
                        daemon=True
                    ).start()

            time.sleep(0.2)
        except Exception as e:
            log_error(f"UNHANDLED ERROR IN MAIN LOOP: {e}")
            traceback.print_exc()
            log_warning("Waiting 10 seconds before continuing...");
            time.sleep(10)

def main():
    """Main function to start the bot and its threads."""
    bot_state = BotState()

    websocket_thread = Thread(target=start_websocket_server_sync, args=(bot_state,), daemon=True)
    websocket_thread.start()

    main_logic_thread = Thread(target=main_bot_logic, args=(bot_state,), daemon=True)
    main_logic_thread.start()

    try:
        # Keep the main thread alive to allow daemon threads to run
        while main_logic_thread.is_alive():
            main_logic_thread.join(timeout=1.0)
    except KeyboardInterrupt:
        log_warning("\nBot interrupted by user.")
        bot_state.stop = True
    except Exception as e:
        log_error(f"Fatal error starting the bot: {e}")
        traceback.print_exc()
    finally:
        log(b, "Shutting down the bot.")
        # Allow some time for threads to finish up
        time.sleep(2)
        sys.exit()

if __name__ == "__main__":
    main()
