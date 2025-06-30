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
except ImportError:
    print("ERRO: A biblioteca 'supabase' não está instalada. Por favor, instale-a com: pip install supabase")
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
signal_queue = queue.Queue()
connected_clients = set()
clients_lock = Lock()

# --- Centralized Logging ---
def log(cor, mensagem): print(f"{cor}[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {w}{mensagem}")
def log_info(msg, pair="Sistema"): log(c, f"{pair}: {msg}" if pair != "Sistema" else msg)
def log_success(msg, pair="Sistema"): log(g, f"{pair}: {msg}" if pair != "Sistema" else msg)
def log_warning(msg, pair="Sistema"): log(y, f"{pair}: {msg}" if pair != "Sistema" else msg)
def log_error(msg, pair="Sistema"): log(r, f"{pair}: {msg}" if pair != "Sistema" else msg)

def broadcast_message(message_data):
    signal_queue.put(message_data)

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
              azkzero@gmail.com - v67 (Sistema Unificado)
    ''')
    print(y + "*"*88)
    print(c + "="*88)

# --- WebSocket Server ---
class WebSocketServer:
    def __init__(self, bot_state): self.bot_state = bot_state
    async def handler(self, websocket, *args):
        with clients_lock: connected_clients.add(websocket)
        log_info(f"Novo cliente WebSocket conectado: {websocket.remote_address}")
        try:
            initial_state = { "type": "init", "data": { "signals": list(self.bot_state.signal_history.values()), "placar": { "wins": self.bot_state.win_count, "losses": self.bot_state.loss_count, "gale_wins": sum(self.bot_state.gale_wins.values()) } } }
            await websocket.send(json.dumps(initial_state))
            await websocket.wait_closed()
        except websockets.exceptions.ConnectionClosed: pass
        finally:
            with clients_lock: connected_clients.discard(websocket)
            log_warning(f"Cliente WebSocket desconectado: {websocket.remote_address}")

async def broadcast_signals():
    while True:
        try:
            message_data = signal_queue.get_nowait()
            message_to_send = json.dumps(message_data)
            with clients_lock:
                if not connected_clients: await asyncio.sleep(0.1); continue
                clients_to_send = list(connected_clients)
            tasks = [client.send(message_to_send) for client in clients_to_send]
            await asyncio.gather(*tasks, return_exceptions=True)
        except queue.Empty: await asyncio.sleep(0.1)
        except Exception: pass

def start_websocket_server_sync(bot_state):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server_instance = WebSocketServer(bot_state)
    async def main_async_logic():
        server_options = { "ping_interval": 20, "ping_timeout": 20, "reuse_port": True }
        try:
            start_server = websockets.serve(server_instance.handler, "0.0.0.0", 8765, **server_options)
        except (AttributeError, TypeError, OSError):
            log_warning("reuse_port não suportado."); del server_options["reuse_port"]
            start_server = websockets.serve(server_instance.handler, "0.0.0.0", 8765, **server_options)
        server = await start_server
        log_success(f"Servidor WebSocket iniciado em {server.sockets[0].getsockname()}")
        await asyncio.gather(broadcast_signals(), server.wait_closed())
    try: loop.run_until_complete(main_async_logic())
    except Exception as e: log_error(f"ERRO CRÍTICO no thread do WebSocket: {e}"); traceback.print_exc()
    finally: log_warning("Loop do servidor WebSocket está sendo encerrado."); loop.close()

# --- Logic and Strategy Functions ---
def validar_e_limpar_velas(velas_raw):
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {'open': v_raw.get('open'), 'close': v_raw.get('close'), 'high': v_raw.get('high') or v_raw.get('max'), 'low': v_raw.get('low') or v_raw.get('min')}
        if all(v is not None for v in vela_padronizada.values()): velas_limpas.append(vela_padronizada)
    return velas_limpas

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
        self.stop, self.win_count, self.loss_count = False, 0, 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.active_trades, self.signal_history = 0, {}
        self.champion_strategies, self.consecutive_losses, self.suspended_pairs = {}, {}, {}
        self.global_losses_since_catalog = 0
        self.lock = Lock()
        self.standby_mode, self.standby_until = False, 0
        self.global_loss_timestamps = deque(maxlen=2)

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)),
        'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'pay_minimo': int(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM',
        'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)),
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    resultado_final = "ERROR"
    try:
        wait_time = target_entry_timestamp - time.time() - 5.0
        if wait_time > 0: time.sleep(wait_time)
        if time.time() > target_entry_timestamp + 10:
            log_error("Oportunidade perdida (atraso >10s).", pair=ativo)
            return
        entrada_atual, niveis_mg = valor, config['mg_niveis'] if config['usar_mg'] else 0
        for i in range(niveis_mg + 1):
            if state.stop: break
            if i > 0:
                broadcast_message({"type": "gale", "signal_id": signal_id, "gale_level": i})
                if signal_id in state.signal_history: state.signal_history[signal_id]["gale_level"] = i
            gale_info = f"(Gale {i})" if i > 0 else "(Entrada Principal)"
            log_info(f"ORDEM {gale_info}: {cifrao}{entrada_atual:.2f} | {direcao.upper()} | {expiracao}M", pair=ativo)
            check, id_ordem = api.buy(entrada_atual, ativo, direcao, expiracao)
            if not check: log_error(f"Falha ao abrir ordem {gale_info}.", pair=ativo); resultado_final = "ERROR"; break
            resultado, status_encontrado = 0.0, False
            tempo_limite = time.time() + expiracao * 60 + 15
            while time.time() < tempo_limite:
                status, lucro = api.check_win_v4(id_ordem)
                if status: resultado, status_encontrado = lucro, True; break
                time.sleep(0.5)
            if not status_encontrado: log_error(f"Timeout na ordem {id_ordem}.", pair=ativo); resultado_final = "ERROR"; break
            if resultado > 0:
                log_success(f"RESULTADO: WIN {gale_info} | Lucro: {cifrao}{resultado:.2f}", pair=ativo)
                with state.lock: state.win_count += 1; state.consecutive_losses[ativo] = 0;
                if i > 0: state.gale_wins[f'g{i}'] += 1
                resultado_final = 'WIN'; break
            elif resultado < 0:
                log_error(f"RESULTADO: LOSS {gale_info} | Perda: {cifrao}{abs(resultado):.2f}", pair=ativo)
                with state.lock:
                    state.loss_count += 1; state.global_losses_since_catalog += 1; state.global_loss_timestamps.append(time.time())
                    state.consecutive_losses[ativo] = state.consecutive_losses.get(ativo, 0) + 1
                    if state.consecutive_losses[ativo] >= 2:
                        state.suspended_pairs[ativo] = time.time() + 1800
                        log_error("Par suspenso por 30 min (2 derrotas seguidas).", pair=ativo)
                if i < niveis_mg: entrada_atual *= config['mg_fator']
                else: resultado_final = 'LOSS'
            else:
                log_warning(f"RESULTADO: EMPATE {gale_info}.", pair=ativo)
                if i >= niveis_mg: resultado_final = 'DRAW'; break
        placar = { "wins": state.win_count, "losses": state.loss_count, "gale_wins": sum(state.gale_wins.values()) }
        broadcast_message({ "type": "result", "signal_id": signal_id, "result": resultado_final, "placar": placar })
    except Exception as e: log_error(f"ERRO CRÍTICO NA THREAD: {e}", pair=ativo); traceback.print_exc()
    finally:
        with state.lock: state.active_trades -= 1

def run_trading_cycle(API, state, params, config, cifrao):
    try:
        if not state.champion_strategies or params.get('force_re-catalog', False):
            # A lógica de catalogação pode ser adicionada aqui
            log_info("Definindo estratégias padrão para todos os pares...")
            all_assets = API.get_all_open_time()
            open_pairs = [asset for market in ['binary', 'turbo'] if market in all_assets for asset, info in all_assets[market].items() if info.get('open')]
            default_strategy = list(ALL_STRATEGIES.values())[0]
            state.champion_strategies = {pair: default_strategy for pair in open_pairs}
            log_info(f"Estratégia '{default_strategy}' definida como padrão.")

        minuto_anterior = -1
        while True: # Loop interno para o ciclo de trading
            timestamp = time.time(); dt_objeto = datetime.fromtimestamp(timestamp)
            if dt_objeto.minute != minuto_anterior: minuto_anterior, analise_feita = dt_objeto.minute, False
            
            with state.lock: active_trades_count = state.active_trades
            MAX_TRADES = params.get('MAX_SIMULTANEOUS_TRADES', 1)

            if dt_objeto.second >= 30 and not analise_feita and active_trades_count < MAX_TRADES:
                analise_feita = True
                all_profits = API.get_all_profit()
                for ativo, estrategia in state.champion_strategies.items():
                    with state.lock:
                        if state.active_trades >= MAX_TRADES: break
                    
                    payout = all_profits.get(ativo, {}).get('turbo', 0) * 100 or all_profits.get(ativo, {}).get('binary', 0) * 100
                    if payout < config.get('pay_minimo', 80): continue

                    velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 100, time.time()))
                    if not velas or len(velas) < 30: continue
                    
                    broadcast_message({"type": "live_analysis", "data": {"pair": ativo, "strategy": estrategia, "candle": velas[-1]}})

                    cod_est = next((cod for cod, nome in ALL_STRATEGIES.items() if nome == estrategia), None)
                    if not cod_est: continue
                    
                    strategy_function = STRATEGY_FUNCTIONS[cod_est]
                    score, direcao_sinal = strategy_function(velas, params)

                    if score > 0 and direcao_sinal:
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
                        broadcast_message(signal_payload)

                        target_entry_timestamp = (timestamp // 60 + 1) * 60
                        tipo_op = 'turbo' if 'turbo' in all_profits.get(ativo, {}) else 'binary'
                        Thread(target=compra_thread, args=(API, ativo, config['valor_entrada'], {'BUY':'call', 'SELL':'put'}[direcao_sinal], config['expiracao'], tipo_op, state, config, cifrao, signal_id, target_entry_timestamp), daemon=True).start()
            time.sleep(1)
    except Exception as e:
        log_error(f"Erro no ciclo de trading: {e}"); traceback.print_exc()

def main_bot_logic(state):
    exibir_banner()
    email, senha = os.getenv('EXNOVA_EMAIL'), os.getenv('EXNOVA_PASSWORD')
    if not email or not senha: log_error("Variáveis de ambiente EXNOVA_EMAIL e EXNOVA_PASSWORD não definidas."); sys.exit(1)

    supabase_url = os.getenv('SUPABASE_URL', 'SEU_URL_DO_SUPABASE')
    supabase_key = os.getenv('SUPABASE_KEY', 'SUA_CHAVE_ANON_DO_SUPABASE')
    if 'SEU_URL' in supabase_url or 'SUA_CHAVE' in supabase_key:
        log_error("As credenciais do Supabase não foram definidas nas variáveis de ambiente."); sys.exit(1)
    
    supabase_client = create_client(supabase_url, supabase_key)
    log_success("Conectado ao Supabase com sucesso.")

    config = get_config_from_env()
    API = Exnova(email, senha)
    log_info("Conectando à Exnova...")
    check, reason = API.connect()
    if not check: log_error(f"Falha na conexão: {reason}"); sys.exit(1)
    
    log_success("Conexão com a Exnova estabelecida!"); API.change_balance(config['conta'])
    
    cifrao = "$"
    try:
        profile_data = API.get_profile_ansyc()
        if profile_data: cifrao = profile_data.get('currency_char', '$')
        log_success(f"Logado como {profile_data.get('name', 'Usuário')} | Moeda: {cifrao}")
    except Exception as e:
        log_error(f"Erro ao obter perfil: {e}. Usando valores padrão.")

    log_info("Bot iniciado. A aguardar comandos do painel de administração...")

    while not state.stop:
        try:
            response = supabase_client.table('bot_config').select('*').eq('id', 1).single().execute()
            config_data = response.data
            
            bot_status = config_data.get('status', 'PAUSED')
            remote_params = config_data.get('params', {})

            if bot_status == 'PAUSED':
                if int(time.time()) % 20 == 0:
                    log_info("Bot em modo PAUSADO. A aguardar comando 'RUNNING' do painel.")
                time.sleep(5)
                continue

            log_info("Bot em modo RUNNING. Iniciando ciclo de análise...")
            run_trading_cycle(API, state, remote_params, config, cifrao)
            
            time.sleep(10)

        except Exception as e:
            log_error(f"ERRO NO LOOP PRINCIPAL: {e}"); traceback.print_exc(); time.sleep(10)

def main():
    bot_state = BotState()
    
    websocket_thread = Thread(target=start_websocket_server_sync, args=(bot_state,), daemon=True)
    websocket_thread.start()

    main_bot_logic(bot_state)

if __name__ == "__main__":
    main()
