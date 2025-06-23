# -*- coding: utf-8 -*-
import time
import json
import base64
import getpass
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
# ### ATUALIZAÇÃO ### Import necessário para o servidor de health check
from http.server import HTTPServer, BaseHTTPRequestHandler

from colorama import init, Fore
from configobj import ConfigObj
from exnovaapi.stable_api import Exnova

init(autoreset=True)
g, y, r, w, c, b = Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.WHITE, Fore.CYAN, Fore.BLUE

signal_queue = queue.Queue()
connected_clients = set()

def log(cor, mensagem):
    print(f"{cor}[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {w}{mensagem}")

def log_info(msg): log(c, msg)
def log_success(msg): log(g, msg)
def log_warning(msg): log(y, msg)
def log_error(msg): log(r, msg)

def exibir_banner():
    # ... (código do banner mantido)
    print(c + "\n" + "="*88)
    print(y + "*"*88)
    print(g + '''
            ██╗      ██████╗  ██████╗  █████╗ ███╗   ██╗    ███████╗███╗   ███╗██╗████████ ██╗  ██╗
            ██║     ██╔═══██╗██╔════╝ ██╔══██╗████╗  ██║    ██╔════╝████╗ ████║██║╚══██╔══╝██║  ██║
            ██║     ██║   ██║██║  ███╗███████║██╔██╗ ██║    ███████╗██╔████╔██║██║   ██║   ███████║
            ██║     ██║   ██║██║   ██║██╔══██║██║╚██╗██║    ╚════██║██║╚██╔╝██║██║   ██║   ██╔══██║
            ███████╗╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║    ███████║██║ ╚═╝ ██║██║   ██║   ██║  ██║
            ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝    ╚══════╝╚═╝     ╚═╝╚═╝   ╚═╝   ╚═╝  ╚═╝ '''+c+'''    
    ████████╗██████╗ ██╗ █████╗ ██╗         ██╗   ██║██╗  ████████╗██████╗  █████╗ ██████╗  ██████╗ ████████╗
    ╚══██╔══╝██╔══██╗██║██╔══██╗██║         ██║   ██║██║  ╚══██╔══╝██╔══██╗██╔═══██╗╚══██╔══╝
       ██║   ██████╔╝██║███████║██║         ██║   ██║██║     ██║   ██████╔╝███████║██████╔╝██║   ██║   ██║   
       ██║   ██╔══██╗██║██╔══██║██║         ██║   ██║██║     ██║   ██╔══██╗██╔══██║██╔══██╗██║   ██║   ██║   
       ██║   ██║  ██║██║██║  ██║███████╗    ╚██████╔╝███████╗██║   ██║  ██║██║  ██║██████╔╝╚██████╔╝   ██║   
       ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝     ╚═════╝ ╚══════╝╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝    ╚═╝ '''+y+'''
                                                azkzero@gmail.com
    ''')
    print(y + "*"*88)
    print(c + "="*88)

# ### ATUALIZAÇÃO ### Servidor HTTP para responder aos Health Checks
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
        else:
            self.send_response(404)
            self.end_headers()

def run_health_check_server():
    server_address = ('', 8080) # Usa uma porta diferente da do WebSocket
    httpd = HTTPServer(server_address, HealthCheckHandler)
    log_info("Servidor de Health Check a correr na porta 8080...")
    httpd.serve_forever()

async def ws_handler(websocket, bot_state):
    # ... (código mantido)
    connected_clients.add(websocket)
    log_success(f"Novo cliente WebSocket conectado: {websocket.remote_address}")
    try:
        initial_state = {"type": "init", "data": {"signals": list(bot_state.signal_history.values()), "placar": {"wins": bot_state.win_count, "losses": bot_state.loss_count, "gale_wins": sum(bot_state.gale_wins.values())}}}
        await websocket.send(json.dumps(initial_state))
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)
        log_warning(f"Cliente WebSocket desconectado: {websocket.remote_address}")

async def broadcast_signals():
    # ... (código mantido)
    while True:
        try:
            signal_data = signal_queue.get_nowait()
            if connected_clients:
                message = json.dumps(signal_data)
                await asyncio.gather(*[client.send(message) for client in connected_clients])
        except queue.Empty:
            await asyncio.sleep(0.1)
        except Exception as e:
            log_error(f"Erro no broadcast do WebSocket: {e}")

def start_websocket_server_sync(bot_state):
    # ... (código mantido)
    asyncio.set_event_loop(asyncio.new_event_loop())
    handler_with_state = lambda ws: ws_handler(ws, bot_state)
    asyncio.get_event_loop().run_until_complete(start_websocket_server_async(handler_with_state))

async def start_websocket_server_async(handler):
    # ... (código mantido)
    async with websockets.serve(handler, "0.0.0.0", 8765):
        log_info("Servidor WebSocket iniciado em ws://0.0.0.0:8765")
        await broadcast_signals()

def validar_e_limpar_velas(velas_raw):
    # ... (código mantido)
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {}
        if 'open' in v_raw: vela_padronizada['open'] = v_raw['open']
        if 'close' in v_raw: vela_padronizada['close'] = v_raw['close']
        if 'high' in v_raw: vela_padronizada['high'] = v_raw['high']
        elif 'max' in v_raw: vela_padronizada['high'] = v_raw['max']
        if 'low' in v_raw: vela_padronizada['low'] = v_raw['low']
        elif 'min' in v_raw: vela_padronizada['low'] = v_raw['min']
        chaves_obrigatorias = ['open', 'high', 'low', 'close']
        if all(key in vela_padronizada for key in chaves_obrigatorias): velas_limpas.append(vela_padronizada)
    return velas_limpas

def catalogar_estrategias(api, state, params):
    # ... (código mantido)
    log_info("="*40); log_info("INICIANDO MODO DE CATALOGAÇÃO DE ESTRATÉGIAS..."); log_info("="*40)
    TODAS_AS_ESTRATEGIAS = {'mql_pullback': strategy_mql_pullback, 'flow': strategy_flow, 'patterns': strategy_patterns, 'rejection_candle': strategy_rejection_candle}
    ativos_abertos = []
    all_assets = api.get_all_open_time()
    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False) and ativo not in ativos_abertos: ativos_abertos.append(ativo)
    if not ativos_abertos: log_error("Nenhum par de moeda aberto encontrado para catalogar."); return
    log_info(f"Encontrados {len(ativos_abertos)} pares abertos para análise.")
    for ativo in ativos_abertos:
        try:
            log_info(f"\n--- Analisando o par: {w}{ativo}{c} ---")
            velas_historicas_raw = api.get_candles(ativo, 60, 500, time.time())
            todas_as_velas = validar_e_limpar_velas(velas_historicas_raw)
            if not todas_as_velas or len(todas_as_velas) < 100: log_warning(f"Não foi possível obter dados históricos suficientes para {ativo}."); continue
            resultados = {nome: {'win': 0, 'loss': 0} for nome in TODAS_AS_ESTRATEGIAS}
            total_sinais = 0
            for i in range(50, len(todas_as_velas) - 1):
                velas_atuais = todas_as_velas[:i]; vela_sinal = velas_atuais[-1]; vela_resultado = todas_as_velas[i]
                for nome, funcao_estrategia in TODAS_AS_ESTRATEGIAS.items():
                    sinal = funcao_estrategia(velas_atuais, params) 
                    if sinal:
                        total_sinais += 1
                        if sinal == 'BUY' and vela_resultado['close'] > vela_sinal['close']: resultados[nome]['win'] += 1
                        elif sinal == 'SELL' and vela_resultado['close'] < vela_sinal['close']: resultados[nome]['win'] += 1
                        else: resultados[nome]['loss'] += 1
            melhor_estrategia = None; maior_assertividade = 0
            print(f" {y}Resultados para {ativo} (baseado em {total_sinais} sinais totais):")
            for nome, res in resultados.items():
                total_operacoes = res['win'] + res['loss']
                if total_operacoes > 0:
                    assertividade = (res['win'] / total_operacoes) * 100
                    print(f"    - {c}{nome:<20}{w}: {g}{res['win']} wins, {r}{res['loss']} loss {y}({assertividade:.2f}%)")
                    if assertividade > maior_assertividade: maior_assertividade = assertividade; melhor_estrategia = nome
                else: print(f"    - {c}{nome:<20}{w}: Nenhum sinal gerado.")
            if melhor_estrategia and maior_assertividade > 50:
                log_success(f" >> Melhor estratégia para {ativo}: '{melhor_estrategia}' com {maior_assertividade:.2f}% de acerto.")
                state.strategy_performance[ativo] = {'best_strategy': melhor_estrategia, 'win_rate': maior_assertividade}
            else: log_error(f" >> Nenhuma estratégia teve desempenho satisfatório para {ativo}.")
        except Exception as e: log_error(f"Ocorreu um erro ao analisar o par {ativo}: {e}"); traceback.print_exc(); continue
    log_info("="*40); log_info("CATALOGAÇÃO FINALIZADA!"); log_info("="*40); time.sleep(5)
    
def sma_slope(closes, period):
    # ... (código mantido)
    if len(closes) < period + 1: return None
    sma = deque(maxlen=period)
    for close in closes[- (period + 1):]: sma.append(sum(closes[-(period):])/period)
    if len(sma) < 2 or sma[-2] == 0: return None
    return sma[-1] > sma[-2]

def detect_fractals(velas, max_levels):
    # ... (código mantido)
    highs, lows = [v['high'] for v in velas], [v['low'] for v in velas]
    res, sup = deque(maxlen=max_levels), deque(maxlen=max_levels)
    for i in range(len(velas) - 3, 2, -1):
        if highs[i-1] > max(highs[i-3:i-1] + highs[i:i+2]): res.append(highs[i-1])
        if lows[i-1] < min(lows[i-3:i-1] + lows[i:i+2]): sup.append(lows[i-1])
    return list(res), list(sup)

def strategy_rejection_candle(velas, p):
    # ... (código mantido)
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    vela_anterior = velas[-2]; o, h, l, c = vela_anterior['open'], vela_anterior['high'], vela_anterior['low'], vela_anterior['close']
    range_total = h - l
    if range_total == 0: return None
    corpo = abs(o - c); pavio_superior = h - max(o, c); pavio_inferior = min(o, c) - l
    if nano_up and ((pavio_inferior / range_total) >= 0.6) and ((corpo / range_total) <= 0.3) and ((pavio_superior / range_total) <= 0.15): return 'BUY'
    if not nano_up and ((pavio_superior / range_total) >= 0.6) and ((corpo / range_total) <= 0.3) and ((pavio_inferior / range_total) <= 0.15): return 'SELL'
    return None

def strategy_mql_pullback(velas, p):
    # ... (código mantido)
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    res_levels, sup_levels = detect_fractals(velas, p['MaxLevels'])
    last = velas[-1]
    if nano_up and sup_levels and last['close'] > last['open']:
        sup_level = sup_levels[0]; target_price = sup_level + p['Proximity'] * p['Point']
        if last['low'] <= target_price and last['close'] >= sup_level: return 'BUY'
    if not nano_up and res_levels and last['close'] < last['open']:
        res_level = res_levels[0]; target_price = res_level - p['Proximity'] * p['Point']
        if last['high'] >= target_price and last['close'] <= res_level: return 'SELL'
    return None

def strategy_flow(velas, p):
    # ... (código mantido)
    flow_candles_count = p.get('FlowCandles', 3)
    if len(velas) < p['MAPeriod'] + flow_candles_count: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    last_candles = velas[-flow_candles_count:]
    if nano_up and all(v['close'] > v['open'] for v in last_candles): return 'BUY'
    if not nano_up and all(v['close'] < v['open'] for v in last_candles): return 'SELL'
    return None

def strategy_patterns(velas, p):
    # ... (código mantido)
    if len(velas) < p['MAPeriod'] + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    penultimate, last = velas[-2], velas[-1]
    if nano_up:
        if (penultimate['close'] < penultimate['open'] and last['close'] > last['open'] and last['open'] < penultimate['close'] and last['close'] > penultimate['open']): return 'BUY'
        if (penultimate['close'] < penultimate['open'] and last['close'] > last['open'] and last['open'] > penultimate['close'] and last['close'] < penultimate['open']): return 'BUY'
    if not nano_up:
        if (penultimate['close'] > penultimate['open'] and last['close'] < last['open'] and last['open'] > penultimate['close'] and last['close'] < penultimate['open']): return 'SELL'
        if (penultimate['close'] > penultimate['open'] and last['close'] < last['open'] and last['open'] < penultimate['close'] and last['close'] > penultimate['open']): return 'SELL'
    return None
    
def is_market_indecisive(velas, p):
    # ... (código mantido)
    candles_to_check, body_max_ratio, min_indecisive_count = p.get('IndecisionCandles', 3), p.get('IndecisionBodyMaxRatio', 0.4), p.get('IndecisionMinCount', 2)
    if len(velas) < candles_to_check: return False
    last_candles, indecisive_candles_found = velas[-candles_to_check:], 0
    for vela in last_candles:
        range_total = vela['high'] - vela['low']
        if range_total == 0:
            indecisive_candles_found += 1
            continue
        corpo = abs(vela['open'] - vela['close'])
        if (corpo / range_total) <= body_max_ratio:
            indecisive_candles_found += 1
    return indecisive_candles_found >= min_indecisive_count
    
class BotState:
    def __init__(self):
        self.stop = True
        self.lucro_total = 0.0
        self.win_count = 0
        self.loss_count = 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.is_trading = False
        self.signal_history = {}
        self.strategy_performance = {}

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(),
        'pay_minimo': float(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)),
        'stop_win': float(os.getenv('EXNOVA_STOP_WIN', 10)),
        'stop_loss': float(os.getenv('EXNOVA_STOP_LOSS', 10)),
        'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'NAO').upper() == 'SIM',
        'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)),
        'modo_operacao': os.getenv('EXNOVA_MODO_OPERACAO', '2')
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    # ... (código da thread de compra mantido)
    try:
        wait_time = target_entry_timestamp - time.time()
        if wait_time > 0: time.sleep(max(0, wait_time - 0.2));
        while time.time() < target_entry_timestamp: pass
        
        entrada_atual = valor
        direcao_atual, niveis_mg = direcao, config['mg_niveis'] if config['usar_mg'] else 0
        resultado_final = None
        for i in range(niveis_mg + 1):
            if not state.stop: break
            if i > 0:
                gale_payload = {"type": "gale", "signal_id": signal_id, "gale_level": i}
                signal_queue.put(gale_payload)
                state.signal_history[signal_id]["gale_level"] = i
            gale_info = f"(Gale {i})" if i > 0 else "(Entrada Principal)"
            log_info(f"ORDEM {gale_info}: {ativo} | {cifrao}{entrada_atual:.2f} | {direcao_atual.upper()} | {expiracao}M")
            if tipo_op == 'digital': check, id_ordem = api.buy_digital_spot(ativo, entrada_atual, direcao_atual, expiracao)
            else: check, id_ordem = api.buy(entrada_atual, ativo, direcao_atual, expiracao)
            if not check: log_error(f"Falha ao abrir ordem no Gale {i}."); resultado_final = "ERRO"; break
            resultado, status_encontrado = 0.0, False
            tempo_limite = time.time() + expiracao * 60 + 15
            while time.time() < tempo_limite:
                status, lucro = api.check_win_v4(id_ordem)
                if status: resultado, status_encontrado = lucro, True; break
                time.sleep(0.5)
            if not status_encontrado: log_error(f"Timeout na ordem {id_ordem}."); resultado_final = "ERRO"; break
            state.lucro_total += resultado
            if resultado > 0:
                log_success(f"RESULTADO: WIN {gale_info} | Lucro: {cifrao}{resultado:.2f}")
                state.win_count += 1
                if i > 0: state.gale_wins[f'g{i}'] += 1
                resultado_final = 'WIN'
                break
            elif resultado < 0:
                log_error(f"RESULTADO: LOSS {gale_info} | Prejuízo: {cifrao}{resultado:.2f}")
                if i < niveis_mg: entrada_atual *= config['mg_fator']
                else: state.loss_count += 1; resultado_final = 'LOSS'
            else: log_warning(f"RESULTADO: EMPATE {gale_info}.")
            checar_stop(state, config)
        if resultado_final and resultado_final != "ERRO":
            state.signal_history[signal_id]["result"] = resultado_final
            placar_payload = {"type": "result", "signal_id": signal_id, "result": resultado_final, "placar": {"wins": state.win_count, "losses": state.loss_count, "gale_wins": sum(state.gale_wins.values())}}
            signal_queue.put(placar_payload)
        exibir_placar(state, config)
    except Exception as e: log_error(f"ERRO CRÍTICO NA THREAD DE COMPRA: {e}"); traceback.print_exc()
    finally: state.is_trading = False

def obter_melhor_par(api, payout_minimo):
    all_assets, ativos = api.get_all_open_time(), {}
    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False):
                    try:
                        payout = api.get_all_profit()[ativo][tipo_mercado] * 100
                        if payout >= payout_minimo and (ativo not in ativos or payout > ativos[ativo]['payout']):
                            ativos[ativo] = {'payout': payout, 'tipo': 'binary' if tipo_mercado == 'turbo' else tipo_mercado}
                    except Exception: continue
    if not ativos: return None, None, None
    return max(ativos, key=lambda k: ativos[k]['payout']), ativos[max(ativos, key=lambda k: ativos[k]['payout'])]['tipo'], ativos[max(ativos, key=lambda k: ativos[k]['payout'])]['payout']
    
def main_bot_logic(state):
    # ... (código de setup mantido, sem alterações)
    exibir_banner()
    email = os.getenv('EXNOVA_EMAIL')
    senha = os.getenv('EXNOVA_PASSWORD')
    if not email or not senha:
        log_error("Variáveis de ambiente EXNOVA_EMAIL e EXNOVA_PASSWORD não definidas.")
        sys.exit(1)
    
    config = get_config_from_env()
    API = Exnova(email, senha)
    check, reason = API.connect()
    if not check: log_error(f"Falha na conexão: {reason}"); sys.exit()
    log_success("Conexão estabelecida com sucesso!")
    API.change_balance(config['conta'])
    perfil = API.get_profile_ansyc()
    cifrao, nome_usuario = perfil['currency_char'], perfil['name']
    log_info(f"Olá, {w}{nome_usuario}{c}! Bot a iniciar em modo de servidor.")
    
    if config['modo_operacao'] == '1': catalogar_estrategias(API, state, {})
    
    minuto_anterior, analise_feita = -1, False
    log_info("Bot iniciado. Aguardando janela de análise...")
    
    while state.stop:
        try:
            timestamp = API.get_server_timestamp()
            dt_objeto = datetime.fromtimestamp(timestamp)
            minuto_atual, segundo_atual = dt_objeto.minute, dt_objeto.second

            if minuto_atual != minuto_anterior:
                minuto_anterior, analise_feita = minuto_atual, False
                if not state.is_trading:
                    msg = f"Observando a vela das {dt_objeto.strftime('%H:%M')}..."
                    signal_queue.put({"type": "analysis_status", "asset": "AGUARDANDO", "message": msg})

            if segundo_atual >= 55 and not analise_feita and not state.is_trading:
                analise_feita = True
                signal_queue.put({"type": "analysis_status", "asset": "BOT", "message": "Procurando melhor par..."})
                ativo, tipo_op, payout = obter_melhor_par(API, config['pay_minimo'])
                if not ativo:
                    signal_queue.put({"type": "analysis_status", "asset": "AVISO", "message": "Nenhum par com payout mínimo."})
                    continue

                signal_queue.put({"type": "analysis_status", "asset": ativo, "message": "A obter velas..."})
                velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 150, time.time()))

                if not velas or len(velas) < 20:
                    signal_queue.put({"type": "analysis_status", "asset": ativo, "message": "Dados insuficientes."})
                    continue
                
                signal_queue.put({"type": "analysis_status", "asset": ativo, "message": "A aplicar estratégias..."})
                direcao_final, nome_estrategia_usada = None, None
                
                if state.strategy_performance.get(ativo):
                    cod_est = state.strategy_performance[ativo]['best_strategy']
                    sinal = globals().get(f'strategy_{cod_est}')(velas, {})
                    if sinal:
                        direcao_final, nome_estrategia_usada = {'BUY': 'call', 'SELL': 'put'}.get(sinal), cod_est.replace('_', ' ').title()
                else: 
                    for nome, cod in [('Pullback MQL', 'mql_pullback'), ('Fluxo', 'flow'), ('Padrões', 'patterns'), ('Rejeição', 'rejection_candle')]:
                        sinal = globals().get(f'strategy_{cod}')(velas, {})
                        if sinal:
                            direcao_final, nome_estrategia_usada = {'BUY': 'call', 'SELL': 'put'}.get(sinal), nome
                            break
                
                if direcao_final:
                    state.is_trading = True
                    horario_entrada_dt = dt_objeto.replace(second=0, microsecond=0) + timedelta(minutes=1)
                    horario_entrada_str = horario_entrada_dt.strftime('%H:%M')
                    log_success(f"SINAL ENCONTRADO: {direcao_final.upper()} em {ativo} para a vela das {horario_entrada_str}")
                    
                    target_entry_timestamp = (timestamp // 60 + 1) * 60
                    signal_id = str(uuid.uuid4())
                    vela_sinal = velas[-1]
                    signal_payload = {"type": "signal", "signal_id": signal_id, "pair": ativo, "strategy": nome_estrategia_usada, "direction": direcao_final.upper(), "entry_time": horario_entrada_str, "candle": {"open": vela_sinal['open'], "close": vela_sinal['close'], "high": vela_sinal['high'], "low": vela_sinal['low'], "color": 'text-green-400' if vela_sinal['close'] > vela_sinal['open'] else 'text-red-400'}, "result": None, "gale_level": 0}
                    state.signal_history[signal_id] = signal_payload
                    signal_queue.put(signal_payload)

                    Thread(target=compra_thread, args=(API, ativo, config['valor_entrada'], direcao_final, config['expiracao'], tipo_op, state, config, cifrao, signal_id, target_entry_timestamp), daemon=True).start()
                else:
                    signal_queue.put({"type": "analysis_status", "asset": ativo, "message": "Nenhuma estratégia encontrou sinal."})
            
            time.sleep(0.2)
        
        except Exception as e:
            log_error(f"ERRO NÃO TRATADO NO LOOP PRINCIPAL: {e}")
            traceback.print_exc()
            log_warning("Aguardando 10 segundos antes de continuar...")
            time.sleep(10)

def main():
    bot_state = BotState()
    
    # Inicia o servidor de health check numa thread separada
    health_check_thread = Thread(target=run_health_check_server, daemon=True)
    health_check_thread.start()
    
    websocket_thread = Thread(target=start_websocket_server_sync, args=(bot_state,), daemon=True)
    websocket_thread.start()
    main_bot_logic(bot_state)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_warning("\nBot interrompido pelo usuário.")
    finally:
        log(b, "Encerrando o bot."); sys.exit()
