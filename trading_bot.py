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
              azkzero@gmail.com - v16 (Análise Antecipada)
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
    for ativo_original in ativos_abertos:
        try:
            log_info(f"\n--- Analyzing pair: {w}{ativo_original}{c} ---")
            velas_historicas_raw = api.get_candles(ativo_original, 60, 240, time.time())
            todas_as_velas = validar_e_limpar_velas(velas_historicas_raw)
            if not todas_as_velas or len(todas_as_velas) < 100: log_warning(f"Could not get enough historical data for {ativo_original}."); continue
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
                if total > 1: 
                    assertividade = (res['win'] / total) * 100
                    performance_do_par[nome] = assertividade
                    log_info(f"  -> Strategy '{nome}' for {ativo_original}: {assertividade:.2f}% accuracy ({res['win']}W / {res['loss']}L)")
                else:
                    msg = f"Amostra muito pequena para '{nome}' ({total} sinais). Ignorando."
                    log_warning(f"  -> {msg}")
                    log_payload = {"type": "log", "data": {"level": "warning", "message": msg, "pair": ativo_original}}
                    signal_queue.put(log_payload)
            if performance_do_par:
                normalized_name = normalize_asset(ativo_original)
                state.strategy_performance[normalized_name] = performance_do_par
        except Exception as e: log_error(f"An error occurred while analyzing the pair {ativo_original}: {e}"); traceback.print_exc()
    log_info("="*40); log_info("CATALOGING FINISHED!"); log_info("="*40); time.sleep(5)

def sma_slope(closes, period):
    if len(closes) < period + 1: return None
    sma1 = sum(closes[-(period+1):-1]) / period; sma2 = sum(closes[-period:]) / period
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
    if nano_up and ((pavio_inferior / range_total) >= p.get('RejectionWickMinRatio')) and ((corpo / range_total) <= p.get('RejectionBodyMaxRatio')) and ((pavio_superior / range_total) <= p.get('RejectionOppositeWickMaxRatio')): return 'BUY'
    if not nano_up and ((pavio_superior / range_total) >= p.get('RejectionWickMinRatio')) and ((corpo / range_total) <= p.get('RejectionBodyMaxRatio')) and ((pavio_inferior / range_total) <= p.get('RejectionOppositeWickMaxRatio')): return 'SELL'
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
    flow_candles = velas[-2:]; min_body_ratio = p.get('FlowBodyMinRatio', 0.4)
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
        max_opposite_wick_ratio = p.get('FlowOppositeWickMaxRatio', 0.45)
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
    if len(velas) < p['MAPeriod'] + 5:
        return None

    v1, v2, v3 = velas[-3], velas[-2], velas[-1]

    def get_props(vela):
        props = {}
        props['range'] = vela['high'] - vela['low']
        if props['range'] == 0: return None
        props['corpo'] = abs(vela['open'] - vela['close'])
        props['body_ratio'] = props['corpo'] / props['range']
        props['is_alta'] = vela['close'] > vela['open']
        props['is_baixa'] = vela['close'] < vela['open']
        return props

    p1, p2, p3 = get_props(v1), get_props(v2), get_props(v3)
    if not all([p1, p2, p3]): return None

    if p2['is_baixa'] and p3['is_alta'] and p3['corpo'] > p2['corpo'] and v3['close'] > v2['open'] and v3['open'] < v2['close']:
        return 'BUY'
    if p2['is_alta'] and p3['is_baixa'] and p3['corpo'] > p2['corpo'] and v3['close'] < v2['open'] and v3['open'] > v2['close']:
        return 'SELL'

    if p1['is_baixa'] and p1['body_ratio'] > 0.6 and \
       p2['body_ratio'] < 0.3 and \
       p3['is_alta'] and p3['body_ratio'] > 0.6 and v3['close'] > (v1['open'] + v1['close']) / 2:
        return 'BUY'
    if p1['is_alta'] and p1['body_ratio'] > 0.6 and \
       p2['body_ratio'] < 0.3 and \
       p3['is_baixa'] and p3['body_ratio'] > 0.6 and v3['close'] < (v1['open'] + v1['close']) / 2:
        return 'SELL'

    tendencia_alta = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if tendencia_alta is not None:
        if tendencia_alta and p3['is_alta'] and p3['body_ratio'] > 0.7:
            return 'BUY'
        if not tendencia_alta and p3['is_baixa'] and p3['body_ratio'] > 0.7:
            return 'SELL'

    if tendencia_alta is not None:
        if tendencia_alta and p2['body_ratio'] < 0.3 and p3['is_alta'] and p3['body_ratio'] > 0.5:
            return 'BUY'
        if not tendencia_alta and p2['body_ratio'] < 0.3 and p3['is_baixa'] and p3['body_ratio'] > 0.5:
            return 'SELL'
            
    return None

def is_market_indecisive(velas, p):
    if len(velas) < p.get('IndecisionCandles', 3): return False
    last_candles = velas[-p.get('IndecisionCandles', 3):]
    indecisive_candles = 0
    for vela in last_candles:
        range_total = vela['high'] - vela['low']
        if range_total == 0: indecisive_candles += 1; continue
        corpo = abs(vela['open'] - vela['close'])
        if (corpo / range_total) <= p.get('IndecisionBodyMaxRatio', 0.15):
             indecisive_candles += 1
    return indecisive_candles >= p.get('IndecisionMinCount', 2)

class BotState:
    def __init__(self):
        self.stop = False; self.win_count = 0; self.loss_count = 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.active_trades = 0; self.signal_history = {}; self.strategy_performance = {}; self.lock = Lock()

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(), 'pay_minimo': float(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)), 'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM', 'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)), 'modo_operacao': os.getenv('EXNOVA_MODO_OPERACAO', '2')
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    try:
        wait_time = target_entry_timestamp - time.time() - 0.8
        
        if wait_time > 0:
            log_info(f"Aguardando {wait_time:.2f}s para entrada precisa em {ativo}...")
            time.sleep(wait_time)

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
                resultado_final = 'WIN'; break
            elif resultado < 0:
                log_error(f"RESULTADO: LOSS {gale_info} | Perda: {cifrao}{abs(resultado):.2f}")
                if i < niveis_mg: entrada_atual *= config['mg_fator']
                else:
                    with state.lock: state.loss_count += 1
                    resultado_final = 'LOSS'
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
    if not ativos: 
        msg = f"Nenhum ativo encontrado com payout >= {payout_minimo}%. Verifique a corretora ou o valor mínimo."
        log_error(msg)
        log_payload = {"type": "log", "data": {"level": "error", "message": msg, "pair": "Sistema"}}
        signal_queue.put(log_payload)
        return None
    
    sorted_assets = sorted(ativos.items(), key=lambda item: item[1]['payout'], reverse=True)
    payout_list_str = ", ".join([f"{ativo}({details['payout']:.0f}%)" for ativo, details in sorted_assets])
    log_info(f"Ativos com bom payout encontrados: {payout_list_str}")
    return sorted_assets

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
    
    PARAMS = { 
        'MAPeriod': 5, 'MaxLevels': 10, 'Proximity': 10.0, 'Point': 1e-6, 
        'FlowBodyMinRatio': 0.4, 'FlowOppositeWickMaxRatio': 0.45, 
        'RejectionWickMinRatio': 0.58, 'RejectionBodyMaxRatio': 0.3, 'RejectionOppositeWickMaxRatio': 0.2, 
        'IndecisionCandles': 3,
        'IndecisionBodyMaxRatio': 0.05,
        'IndecisionMinCount': 3
    }
    
    last_catalog_time = 0
    if config['modo_operacao'] == '1':
        catalogar_estrategias(API, state, PARAMS)
        last_catalog_time = time.time()

    minuto_anterior, analise_feita = -1, False
    log_info("Bot iniciado. Entrando no loop de análise...")

    while not state.stop:
        try:
            MAX_SIMULTANEOUS_TRADES = 4

            if config['modo_operacao'] == '1' and (time.time() - last_catalog_time) > (4 * 3600):
                with state.lock:
                    is_trading_check = state.active_trades > 0
                if not is_trading_check:
                    log_info("="*50); log_info("RECATALOGAÇÃO PERIÓDICA (4H) INICIADA"); log_info("="*50)
                    signal_queue.put({"type": "analysis_status", "status": "Recatalogando estratégias (4h)..."})
                    catalogar_estrategias(API, state, PARAMS)
                    last_catalog_time = time.time()
                    log_info("="*50); log_info("RECATALOGAÇÃO PERIÓDICA FINALIZADA"); log_info("="*50)
                else:
                    log_warning("Recatalogação adiada: operação em andamento.")

            timestamp = time.time()
            dt_objeto = datetime.fromtimestamp(timestamp)
            minuto_atual, segundo_atual = dt_objeto.minute, dt_objeto.second

            if minuto_anterior != minuto_atual:
                minuto_anterior, analise_feita = minuto_atual, False
                with state.lock:
                    active_trades_count = state.active_trades
                if active_trades_count == 0:
                    horario_proxima_vela = (dt_objeto.replace(second=0, microsecond=0) + timedelta(minutes=1)).strftime('%H:%M')
                    status_payload = {
                        "type": "analysis_status", 
                        "status": "Aguardando vela das %s...",
                        "next_entry_time": horario_proxima_vela
                    }
                    signal_queue.put(status_payload)
            
            with state.lock:
                active_trades_count = state.active_trades
            
            # ALTERAÇÃO CRÍTICA AQUI: Análise antecipada
            if segundo_atual >= 55 and not analise_feita and active_trades_count < MAX_SIMULTANEOUS_TRADES:
                analise_feita = True
                sinais_para_executar = []

                if config['modo_operacao'] == '1': # MODO CONSERVADOR
                    potential_trades = []
                    open_assets = API.get_all_open_time()
                    all_profits = API.get_all_profit()
                    for tipo_mercado in ['binary', 'turbo']:
                        if tipo_mercado in open_assets:
                            for ativo_original, info in open_assets[tipo_mercado].items():
                                normalized_name = normalize_asset(ativo_original)
                                if info.get('open', False) and normalized_name in state.strategy_performance:
                                    log_info(f"--- Analisando {ativo_original} ---")
                                    velas = validar_e_limpar_velas(API.get_candles(ativo_original, 60, 150, time.time()))
                                    
                                    if not velas or len(velas) < 20: continue
                                    
                                    if is_market_indecisive(velas, PARAMS):
                                        msg = "MERCADO CONSIDERADO INDECISO. Análise descartada."
                                        log_warning(f"-> {ativo_original}: {msg}")
                                        log_payload = {"type": "log", "data": {"level": "warning", "message": msg, "pair": ativo_original}}
                                        signal_queue.put(log_payload)
                                        continue

                                    all_strategies_to_check = {'Pullback MQL': 'mql_pullback', 'Fluxo': 'flow', 'Padrões': 'patterns', 'Rejeição': 'rejection_candle'}
                                    for nome_estrategia, cod_est in all_strategies_to_check.items():
                                        is_approved = False
                                        assertividade = 0
                                        if normalized_name in state.strategy_performance and nome_estrategia in state.strategy_performance[normalized_name]:
                                            assertividade = state.strategy_performance[normalized_name][nome_estrategia]
                                            if assertividade >= 75:
                                                is_approved = True

                                        sinal = globals().get(f'strategy_{cod_est}')(velas, PARAMS)
                                        
                                        if sinal and is_approved:
                                            msg = f"SINAL VÁLIDO ENCONTRADO com '{nome_estrategia}' ({assertividade:.2f}%)"
                                            log_success(f"-> {ativo_original}: {msg}")
                                            log_payload = {"type": "log", "data": {"level": "success", "message": msg, "pair": ativo_original}}
                                            signal_queue.put(log_payload)
                                            
                                            payout = all_profits.get(ativo_original, {}).get(tipo_mercado, 0) * 100
                                            potential_trades.append({'ativo': ativo_original, 'tipo_op': tipo_mercado, 'velas': velas, 'payout': payout, 'direcao': {'BUY': 'call', 'SELL': 'put'}.get(sinal), 'nome_estrategia': nome_estrategia, 'assertividade': assertividade})
                                        
                                        elif sinal and not is_approved:
                                            msg = f"Sinal encontrado com '{nome_estrategia}', mas a estratégia não foi aprovada (Assertividade: {assertividade:.2f}%)."
                                            log_warning(f"-> {ativo_original}: {msg}")
                                            log_payload = {"type": "log", "data": {"level": "warning", "message": msg, "pair": ativo_original}}
                                            signal_queue.put(log_payload)
                                            
                                        elif not sinal:
                                            msg = f"Estratégia '{nome_estrategia}' checada, mas sem sinal no momento."
                                            log_info(f"-> {ativo_original}: {msg}")
                                            log_payload = {"type": "log", "data": {"level": "info", "message": msg, "pair": ativo_original}}
                                            signal_queue.put(log_payload)
                    
                    if potential_trades:
                        log_success(f"ENCONTRADOS {len(potential_trades)} SINAIS VÁLIDOS. Priorizando os melhores...")
                        sorted_trades = sorted(potential_trades, key=lambda x: (x['assertividade'], x['payout']), reverse=True)
                        sinais_para_executar = sorted_trades
                
                else: # MODO AGRESSIVO
                    sorted_assets = obter_melhor_par(API, config['pay_minimo'])
                    if sorted_assets:
                        for ativo, details in sorted_assets:
                            if len(sinais_para_executar) + active_trades_count >= MAX_SIMULTANEOUS_TRADES:
                                break
                            velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 150, time.time()))
                            if velas and len(velas) >= 20 and not is_market_indecisive(velas, PARAMS):
                                strategies_to_try = [('Pullback MQL', 'mql_pullback'), ('Fluxo', 'flow'), ('Padrões', 'patterns'), ('Rejeição', 'rejection_candle')]
                                for nome, cod in strategies_to_try:
                                    sinal = globals().get(f'strategy_{cod}')(velas, PARAMS)
                                    if sinal:
                                        sinais_para_executar.append({
                                            'ativo': ativo, 'tipo_op': details['tipo'], 'velas': velas,
                                            'direcao': {'BUY': 'call', 'SELL': 'put'}.get(sinal),
                                            'nome_estrategia': nome
                                        })
                                        break
                
                vagas_disponiveis = MAX_SIMULTANEOUS_TRADES - active_trades_count
                for sinal_info in sinais_para_executar[:vagas_disponiveis]:
                    with state.lock:
                        state.active_trades += 1
                    
                    horario_analise_dt = dt_objeto.replace(second=0, microsecond=0)
                    horario_analise_str = horario_analise_dt.strftime('%H:%M')
                    horario_entrada_dt = horario_analise_dt + timedelta(minutes=1)
                    horario_entrada_str = horario_entrada_dt.strftime('%H:%M')
                    log_success(f"SINAL ENCONTRADO: {sinal_info['direcao'].upper()} em {sinal_info['ativo']} para a vela das {horario_entrada_str}")
                    
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
