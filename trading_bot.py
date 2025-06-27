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
                'binary': {'EURUSD': {'open': True}, 'GBPUSD': {'open': True}},
                'turbo': {'EURUSD-TURBO': {'open': True}}
            }

        def get_all_profit(self):
            return {
                'EURUSD': {'binary': 0.85, 'turbo': 0.90},
                'GBPUSD': {'binary': 0.82},
                'EURUSD-TURBO': {'turbo': 0.92}
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
            with clients_lock:
                clients_to_send = list(connected_clients)
            if clients_to_send:
                message = json.dumps(signal_data)
                log_info(f"Broadcasting message to {len(clients_to_send)} client(s): {message[:150]}...")
                tasks = [client.send(message) for client in clients_to_send]
                await asyncio.gather(*tasks, return_exceptions=True)
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
def validar_e_limpar_velas(velas_raw):
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {'open': v_raw.get('open'), 'close': v_raw.get('close'), 'high': v_raw.get('high') or v_raw.get('max'), 'low': v_raw.get('low') or v_raw.get('min')}
        if all(vela_padronizada.values()): velas_limpas.append(vela_padronizada)
    return velas_limpas

def catalogar_estrategias(api, state, params):
    log_info("="*40); log_info("STARTING STRATEGY CATALOGING MODE..."); log_info("="*40)
    TODAS_AS_ESTRATEGIAS = {'mql_pullback': 'Pullback MQL', 'flow': 'Fluxo', 'patterns': 'Padrões', 'rejection_candle': 'Rejeição'}
    ativos_abertos = []
    all_assets = api.get_all_open_time()
    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False) and ativo not in ativos_abertos: ativos_abertos.append(ativo)
    if not ativos_abertos: log_error("No open currency pairs found to catalog."); return
    log_info(f"Found {len(ativos_abertos)} open pairs for analysis.")
    for ativo in ativos_abertos:
        try:
            log_info(f"\n--- Analyzing pair: {w}{ativo}{c} ---")
            velas_historicas_raw = api.get_candles(ativo, 60, 240, time.time())
            todas_as_velas = validar_e_limpar_velas(velas_historicas_raw)
            if not todas_as_velas or len(todas_as_velas) < 100: log_warning(f"Could not get enough historical data for {ativo}."); continue
            resultados = {nome: {'win': 0, 'loss': 0} for nome in TODAS_AS_ESTRATEGIAS.values()}
            for i in range(50, len(todas_as_velas) - 1):
                velas_atuais = todas_as_velas[:i]; vela_sinal = velas_atuais[-1]; vela_resultado = todas_as_velas[i]
                for cod, nome in TODAS_AS_ESTRATEGIAS.items():
                    sinal = globals().get(f'strategy_{cod}')(velas_atuais, params)
                    if sinal:
                        if (sinal == 'BUY' and vela_resultado['close'] > vela_sinal['close']) or \
                           (sinal == 'SELL' and vela_resultado['close'] < vela_sinal['close']):
                            resultados[nome]['win'] += 1
                        else:
                            resultados[nome]['loss'] += 1
            performance_do_par = {}
            for nome, res in resultados.items():
                total = res['win'] + res['loss']
                if total > 5:
                    assertividade = (res['win'] / total) * 100
                    performance_do_par[nome] = assertividade
                    log_info(f"  -> Strategy '{nome}' for {ativo}: {assertividade:.2f}% accuracy ({res['win']}W / {res['loss']}L)")
            if performance_do_par:
                state.strategy_performance[ativo] = performance_do_par
        except Exception as e: log_error(f"An error occurred while analyzing the pair {ativo}: {e}"); traceback.print_exc()
    log_info("="*40); log_info("CATALOGING FINISHED!"); log_info("="*40); time.sleep(5)


def sma_slope(closes, period):
    if len(closes) < period + 1: return None
    sma1 = sum(closes[-(period+1):-1]); sma2 = sum(closes[-period:])
    if sma1 == sma2: return None
    return sma2 > sma1

def detect_fractals(velas, max_levels):
    highs, lows = [v['high'] for v in velas], [v['low'] for v in velas]
    res, sup = deque(maxlen=max_levels), deque(maxlen=max_levels)
    for i in range(len(velas) - 3, 2, -1):
        if highs[i-1] > max(highs[i-3:i-1] + highs[i:i+2]): res.append(highs[i-1])
        if lows[i-1] < min(lows[i-3:i-1] + lows[i:i+2]): sup.append(lows[i-1])
    return list(res), list(sup)

def strategy_rejection_candle(velas, p):
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    o, h, l, c = velas[-2]['open'], velas[-2]['high'], velas[-2]['low'], velas[-2]['close']
    range_total = h - l
    if range_total == 0: return None
    corpo = abs(o - c); pavio_superior = h - max(o, c); pavio_inferior = min(o, c) - l
    if nano_up and ((pavio_inferior / range_total) >= p.get('RejectionWickMinRatio', 0.6)) and ((corpo / range_total) <= p.get('RejectionBodyMaxRatio', 0.3)) and ((pavio_superior / range_total) <= p.get('RejectionOppositeWickMaxRatio', 0.15)): return 'BUY'
    if not nano_up and ((pavio_superior / range_total) >= p.get('RejectionWickMinRatio', 0.6)) and ((corpo / range_total) <= p.get('RejectionBodyMaxRatio', 0.3)) and ((pavio_inferior / range_total) <= p.get('RejectionOppositeWickMaxRatio', 0.15)): return 'SELL'
    return None

def strategy_mql_pullback(velas, p):
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    res_levels, sup_levels = detect_fractals(velas, p['MaxLevels'])
    last = velas[-1]
    if nano_up and sup_levels and last['close'] > last['open']:
        if last['low'] <= sup_levels[0] + p['Proximity'] * p['Point'] and last['close'] >= sup_levels[0]: return 'BUY'
    if not nano_up and res_levels and last['close'] < last['open']:
        if last['high'] >= res_levels[0] - p['Proximity'] * p['Point'] and last['close'] <= res_levels[0]: return 'SELL'
    return None

def strategy_flow(velas, p):
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    flow_candles = velas[-2:]; min_body_ratio = p.get('FlowBodyMinRatio', 0.5)
    def is_strong_candle(vela):
        range_total = vela['high'] - vela['low']
        if range_total == 0: return False
        corpo = abs(vela['open'] - vela['close'])
        return (corpo / range_total) >= min_body_ratio
    if not all(is_strong_candle(v) for v in flow_candles): return None
    last_flow_candle = flow_candles[-1]; range_total_last = last_flow_candle['high'] - last_flow_candle['low']
    if range_total_last > 0:
        pavio_superior = last_flow_candle['high'] - max(last_flow_candle['open'], last_flow_candle['close'])
        pavio_inferior = min(last_flow_candle['open'], last_flow_candle['close']) - last_flow_candle['low']
        max_opposite_wick_ratio = p.get('FlowOppositeWickMaxRatio', 0.4)
    else: return None
    res_levels, sup_levels = detect_fractals(velas, p['MaxLevels']); proximity_zone = p['Proximity'] * p['Point']
    if nano_up and all(v['close'] > v['open'] for v in flow_candles):
        if (pavio_superior / range_total_last) > max_opposite_wick_ratio: return None
        if res_levels and abs(last_flow_candle['high'] - res_levels[0]) < proximity_zone: return None
        return 'BUY'
    if not nano_up and all(v['close'] < v['open'] for v in flow_candles):
        if (pavio_inferior / range_total_last) > max_opposite_wick_ratio: return None
        if sup_levels and abs(last_flow_candle['low'] - sup_levels[0]) < proximity_zone: return None
        return 'SELL'
    return None

def strategy_patterns(velas, p):
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    penultimate, last = velas[-2], velas[-1]
    if nano_up and (penultimate['close'] < penultimate['open'] and last['close'] > last['open'] and last['open'] < penultimate['close'] and last['close'] > penultimate['open']): return 'BUY'
    if not nano_up and (penultimate['close'] > penultimate['open'] and last['close'] < last['open'] and last['open'] > penultimate['close'] and last['close'] < penultimate['open']): return 'SELL'
    return None

def is_market_indecisive(velas, p):
    if len(velas) < p.get('IndecisionCandles', 3): return False
    last_candles = velas[-p.get('IndecisionCandles', 3):]
    indecisive_candles = 0
    for vela in last_candles:
        range_total = vela['high'] - vela['low']
        if range_total == 0: indecisive_candles += 1; continue
        corpo = abs(vela['open'] - vela['close'])
        if (corpo / range_total) <= p.get('IndecisionBodyMaxRatio', 0.4): indecisive_candles += 1
    return indecisive_candles >= p.get('IndecisionMinCount', 2)

class BotState:
    def __init__(self):
        self.stop = False; self.win_count = 0; self.loss_count = 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.is_trading = False; self.signal_history = {}; self.strategy_performance = {}; self.lock = Lock()

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(), 'pay_minimo': float(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)), 'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM', 'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)), 'modo_operacao': os.getenv('EXNOVA_MODO_OPERACAO', '2')
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    try:
        wait_time = target_entry_timestamp - time.time()
        if wait_time > 0: time.sleep(max(0, wait_time - 0.2))
        while time.time() < target_entry_timestamp: pass
        entrada_atual = valor; direcao_atual, niveis_mg = direcao, config['mg_niveis'] if config['usar_mg'] else 0
        resultado_final = None
        for i in range(niveis_mg + 1):
            if state.stop: break
            if i > 0:
                gale_payload = {"type": "gale", "signal_id": signal_id, "gale_level": i}
                signal_queue.put(gale_payload)
                if signal_id in state.signal_history: state.signal_history[signal_id]["gale_level"] = i
            gale_info = f"(Gale {i})" if i > 0 else "(Main Entry)"; log_info(f"ORDER {gale_info}: {ativo} | {cifrao}{entrada_atual:.2f} | {direcao_atual.upper()} | {expiracao}M")
            if tipo_op == 'digital': check, id_ordem = api.buy_digital_spot(ativo, entrada_atual, direcao_atual, expiracao)
            else: check, id_ordem = api.buy(entrada_atual, ativo, direcao_atual, expiracao)
            if not check: log_error(f"Failed to open order in Gale {i}."); resultado_final = "ERROR"; break
            resultado, status_encontrado = 0.0, False; tempo_limite = time.time() + expiracao * 60 + 15
            while time.time() < tempo_limite:
                status, lucro = api.check_win_v4(id_ordem)
                if status: resultado, status_encontrado = lucro, True; break
                time.sleep(0.5)
            if not status_encontrado: log_error(f"Timeout on order {id_ordem}."); resultado_final = "ERROR"; break
            if resultado > 0:
                log_success(f"RESULT: WIN {gale_info} | Profit: {cifrao}{resultado:.2f}")
                with state.lock:
                    state.win_count += 1
                    if i > 0: state.gale_wins[f'g{i}'] += 1
                resultado_final = 'WIN'; break
            elif resultado < 0:
                log_error(f"RESULT: LOSS {gale_info} | Loss: {cifrao}{abs(resultado):.2f}")
                if i < niveis_mg: entrada_atual *= config['mg_fator']
                else:
                    with state.lock: state.loss_count += 1
                    resultado_final = 'LOSS'
            else:
                log_warning(f"RESULT: DRAW {gale_info}.")
                if i < niveis_mg: log_info("Re-entering after a draw...")
                else: resultado_final = 'DRAW'
        if resultado_final and resultado_final != "ERROR" and signal_id in state.signal_history:
            state.signal_history[signal_id]["result"] = resultado_final
            placar_payload = { "type": "result", "signal_id": signal_id, "result": resultado_final, "placar": { "wins": state.win_count, "losses": state.loss_count, "gale_wins": sum(state.gale_wins.values()) } }
            signal_queue.put(placar_payload)
    except Exception as e: log_error(f"CRITICAL ERROR IN PURCHASE THREAD: {e}"); traceback.print_exc()
    finally:
        with state.lock: state.is_trading = False

def obter_melhor_par(api, payout_minimo):
    all_profits = api.get_all_profit(); all_assets = api.get_all_open_time(); ativos = {}
    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False):
                    try:
                        payout = all_profits.get(ativo, {}).get(tipo_mercado, 0) * 100
                        if payout >= payout_minimo:
                            if ativo not in ativos or payout > ativos[ativo]['payout']: ativos[ativo] = {'payout': payout, 'tipo': 'digital' if tipo_mercado == 'digital' else 'turbo'}
                    except Exception: continue
    if not ativos: return None, None, None
    best_asset = max(ativos, key=lambda k: ativos[k]['payout'])
    return best_asset, ativos[best_asset]['tipo'], ativos[best_asset]['payout']

def main_bot_logic(state):
    exibir_banner()
    email = os.getenv('EXNOVA_EMAIL', 'test@example.com')
    senha = os.getenv('EXNOVA_PASSWORD', 'password')
    if not email or not senha:
        log_error("Environment variables EXNOVA_EMAIL and EXNOVA_PASSWORD not set.")
        sys.exit(1)

    config = get_config_from_env()
    API = Exnova(email, senha)
    log_info("Attempting to connect to Exnova...")
    check, reason = API.connect()
    if not check:
        log_error(f"Connection failed: {reason}")
        sys.exit(1)

    log_success("Connection established successfully!")
    API.change_balance(config['conta'])
    cifrao = "$"
    try:
        perfil = API.get_profile_ansyc()
        cifrao = perfil.get('currency_char', '$')
        log_info(f"Hello, {perfil.get('name', 'User')}! Bot starting in server mode.")
    except Exception as e:
        log_warning(f"Could not get user profile. Error: {e}")
        log_info(f"Hello! Bot starting in server mode.")
    
    PARAMS = { 
        'MAPeriod': 5, 'MaxLevels': 10, 'Proximity': 7.0, 'Point': 1e-6, 
        'FlowBodyMinRatio': 0.5, 'FlowOppositeWickMaxRatio': 0.4, 
        'RejectionWickMinRatio': 0.6, 'RejectionBodyMaxRatio': 0.3, 'RejectionOppositeWickMaxRatio': 0.15, 
        'IndecisionCandles': 3, 'IndecisionBodyMaxRatio': 0.4, 'IndecisionMinCount': 2 
    }

    # ### LÓGICA DE CATALOGAÇÃO PERIÓDICA ###
    last_catalog_time = 0
    if config['modo_operacao'] == '1':
        catalogar_estrategias(API, state, PARAMS)
        last_catalog_time = time.time()

    minuto_anterior, analise_feita = -1, False
    log_info("Bot started. Entering analysis loop...")

    while not state.stop:
        try:
            # ### VERIFICAÇÃO PARA RECATALOGAÇÃO A CADA 4 HORAS ###
            if config['modo_operacao'] == '1' and (time.time() - last_catalog_time) > (4 * 3600):
                with state.lock:
                    is_trading_check = state.is_trading
                if not is_trading_check:
                    log_info("="*50); log_info("PERIODIC RE-CATALOGING (4H) INITIATED"); log_info("="*50)
                    signal_queue.put({"type": "analysis_status", "status": "Recatalogando estratégias (4h)..."})
                    catalogar_estrategias(API, state, PARAMS)
                    last_catalog_time = time.time() # Reinicia o temporizador
                    log_info("="*50); log_info("PERIODIC RE-CATALOGING FINISHED"); log_info("="*50)
                else:
                    log_warning("Re-cataloging postponed: trade in progress.")

            timestamp = time.time()
            dt_objeto = datetime.fromtimestamp(timestamp)
            minuto_atual, segundo_atual = dt_objeto.minute, dt_objeto.second

            if minuto_atual != minuto_anterior:
                minuto_anterior, analise_feita = minuto_atual, False
                with state.lock:
                    is_trading = state.is_trading
                if not is_trading:
                    horario_proxima_vela = (dt_objeto.replace(second=0, microsecond=0) + timedelta(minutes=1)).strftime('%H:%M')
                    signal_queue.put({"type": "analysis_status", "status": f"Aguardando vela das {horario_proxima_vela}...", "next_entry_time": horario_proxima_vela})
            
            with state.lock:
                is_trading = state.is_trading

            if segundo_atual >= 50 and not analise_feita and not is_trading:
                analise_feita = True
                sinal_encontrado_neste_ciclo = False

                if config['modo_operacao'] == '1': # MODO CONSERVADOR (CATALOGADO)
                    open_assets = API.get_all_open_time()
                    for tipo_mercado in ['binary', 'turbo']:
                        if tipo_mercado in open_assets:
                            for ativo, info in open_assets[tipo_mercado].items():
                                if info.get('open', False) and ativo in state.strategy_performance:
                                    status_log = [f"Analisando par catalogado: {ativo}"]
                                    signal_queue.put({"type": "analysis_update", "asset": ativo, "status_list": status_log})
                                    velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 150, time.time()))
                                    if not velas or len(velas) < 20 or is_market_indecisive(velas, PARAMS): continue

                                    for nome_estrategia, assertividade in state.strategy_performance[ativo].items():
                                        if assertividade >= 70:
                                            cod_map = {'Pullback MQL': 'mql_pullback', 'Fluxo': 'flow', 'Padrões': 'patterns', 'Rejeição': 'rejection_candle'}
                                            cod_estrategia = next((cod for cod, nome in cod_map.items() if nome == nome_estrategia), None)
                                            if not cod_estrategia: continue
                                            status_log.append(f"Testando {nome_estrategia} ({assertividade:.1f}%)...")
                                            signal_queue.put({"type": "analysis_update", "asset": ativo, "status_list": status_log})
                                            sinal = globals().get(f'strategy_{cod_estrategia}')(velas, PARAMS)
                                            if sinal:
                                                direcao_final = {'BUY': 'call', 'SELL': 'put'}.get(sinal)
                                                nome_estrategia_usada = nome_estrategia
                                                tipo_op = tipo_mercado
                                                sinal_encontrado_neste_ciclo = True
                                                status_log.append(f"SINAL ENCONTRADO com {nome_estrategia}!"); signal_queue.put({"type": "analysis_update", "asset": ativo, "status_list": status_log}); break
                                            else: status_log[-1] = f"{nome_estrategia}: Sem sinal."
                                    if sinal_encontrado_neste_ciclo: break
                            if sinal_encontrado_neste_ciclo: break
                
                else: # MODO AGRESSIVO (PADRÃO)
                    ativo, tipo_op, payout = obter_melhor_par(API, config['pay_minimo'])
                    if ativo:
                        signal_queue.put({"type": "analysis_update", "asset": ativo, "status_list": ["Analisando par..."]})
                        velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 150, time.time()))
                        if velas and len(velas) >= 20 and not is_market_indecisive(velas, PARAMS):
                            strategies_to_try = [('Pullback MQL', 'mql_pullback'), ('Fluxo', 'flow'), ('Padrões', 'patterns'), ('Rejeição', 'rejection_candle')]
                            status_log = ["Analisando par..."]
                            for nome, cod in strategies_to_try:
                                status_log.append(f"Testando: {nome}..."); signal_queue.put({"type": "analysis_update", "asset": ativo, "status_list": status_log})
                                sinal = globals().get(f'strategy_{cod}')(velas, PARAMS)
                                if sinal:
                                    direcao_final = {'BUY': 'call', 'SELL': 'put'}.get(sinal); nome_estrategia_usada = nome
                                    sinal_encontrado_neste_ciclo = True
                                    status_log.append(f"SINAL ENCONTRADO com {nome}!"); signal_queue.put({"type": "analysis_update", "asset": ativo, "status_list": status_log}); break
                                else: status_log[-1] = f"{nome}: Sem sinal."
                            if not sinal_encontrado_neste_ciclo:
                                status_log.append("Nenhuma estratégia encontrou sinal."); signal_queue.put({"type": "analysis_update", "asset": ativo, "status_list": status_log})

                if sinal_encontrado_neste_ciclo:
                    with state.lock: state.is_trading = True
                    horario_analise_dt = dt_objeto.replace(second=0, microsecond=0); horario_analise_str = horario_analise_dt.strftime('%H:%M')
                    horario_entrada_dt = horario_analise_dt + timedelta(minutes=1); horario_entrada_str = horario_entrada_dt.strftime('%H:%M')
                    log_success(f"SIGNAL FOUND: {direcao_final.upper()} on {ativo} for the {horario_entrada_str} candle")
                    target_entry_timestamp = (timestamp // 60 + 1) * 60; signal_id = str(uuid.uuid4()); vela_sinal = velas[-1]
                    signal_payload = {
                        "type": "signal", "signal_id": signal_id, "pair": ativo, "strategy": nome_estrategia_usada, "direction": direcao_final.upper(),
                        "entry_time": horario_entrada_str, "analysis_time": horario_analise_str, 
                        "candle": { "open": vela_sinal['open'], "close": vela_sinal['close'], "high": vela_sinal['high'], "low": vela_sinal['low'], "color": 'text-green-400' if vela_sinal['close'] > vela_sinal['open'] else 'text-red-400' },
                        "result": None, "gale_level": 0
                    }
                    state.signal_history[signal_id] = signal_payload; signal_queue.put(signal_payload)
                    Thread(target=compra_thread, args=(API, ativo, config['valor_entrada'], direcao_final, config['expiracao'], tipo_op, state, config, cifrao, signal_id, target_entry_timestamp), daemon=True).start()
            
            time.sleep(0.2)
        
        except Exception as e:
            log_error(f"UNHANDLED ERROR IN MAIN LOOP: {e}"); traceback.print_exc()
            log_warning("Waiting 10 seconds before continuing..."); time.sleep(10)

def main():
    bot_state = BotState()
    websocket_thread = Thread(target=start_websocket_server_sync, args=(bot_state,), daemon=True); websocket_thread.start()
    try: main_bot_logic(bot_state)
    except KeyboardInterrupt: log_warning("\nBot interrupted by user.")
    except Exception as e: log_error(f"Fatal error starting the bot: {e}"); traceback.print_exc()
    finally: bot_state.stop = True; log(b, "Shutting down the bot..."); time.sleep(2); sys.exit()

if __name__ == "__main__":
    main()
