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
from configobj import ConfigObj
from exnovaapi.stable_api import Exnova

init(autoreset=True)
g, y, r, w, c, b = Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.WHITE, Fore.CYAN, Fore.BLUE

# Fila para comunicação entre threads (comandos e sinais)
command_queue = queue.Queue()
signal_queue = queue.Queue()
connected_clients = set()

def log(cor, mensagem):
    print(f"{cor}[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {w}{mensagem}")

def log_info(msg): log(c, msg)
def log_success(msg): log(g, msg)
def log_warning(msg): log(y, msg)
def log_error(msg): log(r, msg)

class BotState:
    def __init__(self):
        self.stop_trading = True  # Inicia parado
        self.is_cataloging = False
        self.is_trading_loop_active = False
        self.lucro_total = 0.0
        self.win_count = 0
        self.loss_count = 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.signal_history = {}
        self.strategy_performance = {}

def get_config_from_env():
    return {
        'conta': os.getenv('EXNOVA_CONTA', 'PRACTICE').upper(),
        'pay_minimo': float(os.getenv('EXNOVA_PAY_MINIMO', 80)),
        'valor_entrada': float(os.getenv('EXNOVA_VALOR_ENTRADA', 1)),
        'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM',
        'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)),
    }

def validar_e_limpar_velas(velas_raw):
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {'open': v_raw.get('open'), 'close': v_raw.get('close'), 'high': v_raw.get('high') or v_raw.get('max'), 'low': v_raw.get('low') or v_raw.get('min')}
        if all(vela_padronizada.values()): velas_limpas.append(vela_padronizada)
    return velas_limpas
    
def strategy_rejection_candle(velas, p):
    if len(velas) < 5 + 2: return None
    nano_up = sma_slope([v['close'] for v in velas], 5)
    if nano_up is None: return None
    o, h, l, c = velas[-2]['open'], velas[-2]['high'], velas[-2]['low'], velas[-2]['close']
    range_total = h - l
    if range_total == 0: return None
    corpo = abs(o - c); pavio_superior = h - max(o, c); pavio_inferior = min(o, c) - l
    if nano_up and (pavio_inferior / range_total >= 0.6) and (corpo / range_total <= 0.3) and (pavio_superior / range_total <= 0.15): return 'BUY'
    if not nano_up and (pavio_superior / range_total >= 0.6) and (corpo / range_total <= 0.3) and (pavio_inferior / range_total <= 0.15): return 'SELL'
    return None

def sma_slope(closes, period):
    if len(closes) < period + 1: return None
    sma1 = sum(closes[-(period+1):-1]) / period
    sma2 = sum(closes[-period:]) / period
    if sma1 == sma2: return None
    return sma2 > sma1

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
    state.is_trading_loop_active = True
    try:
        wait_time = target_entry_timestamp - time.time()
        if wait_time > 0: time.sleep(max(0, wait_time - 0.2));
        while time.time() < target_entry_timestamp: pass
        
        entrada_atual = valor
        direcao_atual, niveis_mg = direcao, config['mg_niveis'] if config['usar_mg'] else 0
        resultado_final = None
        for i in range(niveis_mg + 1):
            if state.stop_trading: break # Verifica se o utilizador mandou parar
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
                if state.stop_trading: break
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
        if resultado_final and resultado_final != "ERRO":
            state.signal_history[signal_id]["result"] = resultado_final
            placar_payload = {"type": "result", "signal_id": signal_id, "result": resultado_final, "placar": {"wins": state.win_count, "losses": state.loss_count, "gale_wins": sum(state.gale_wins.values())}}
            signal_queue.put(placar_payload)
    finally:
        state.is_trading_loop_active = False

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

def trading_loop(state, config, API, cifrao):
    minuto_anterior, analise_feita = -1, False
    state.is_trading_loop_active = True
    while not state.stop_trading:
        try:
            timestamp = time.time()
            dt_objeto = datetime.fromtimestamp(timestamp)
            minuto_atual, segundo_atual = dt_objeto.minute, dt_objeto.second

            if minuto_atual != minuto_anterior:
                minuto_anterior, analise_feita = minuto_atual, False
                msg = f"Observando a vela das {dt_objeto.strftime('%H:%M')}..."
                signal_queue.put({"type": "status_update", "message": msg})

            if segundo_atual >= 55 and not analise_feita:
                analise_feita = True
                ativo, tipo_op, payout = obter_melhor_par(API, config['pay_minimo'])
                if not ativo: continue
                velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 150, time.time()))
                if not velas or len(velas) < 20: continue
                
                direcao_final, nome_estrategia = strategy_rejection_candle(velas, config), "Rejeição de Pavio"
                
                if direcao_final:
                    target_entry_timestamp = (timestamp // 60 + 1) * 60
                    signal_id = str(uuid.uuid4())
                    horario_entrada_str = (datetime.fromtimestamp(target_entry_timestamp)).strftime('%H:%M')
                    vela_sinal = velas[-1]
                    signal_payload = {"type": "signal", "signal_id": signal_id, "pair": ativo, "strategy": nome_estrategia, "direction": direcao_final.upper(), "entry_time": horario_entrada_str, "candle": {"open": vela_sinal['open'], "close": vela_sinal['close'], "high": vela_sinal['high'], "low": vela_sinal['low'], "color": 'text-green-400' if vela_sinal['close'] > vela_sinal['open'] else 'text-red-400'}, "result": None, "gale_level": 0}
                    state.signal_history[signal_id] = signal_payload
                    signal_queue.put(signal_payload)
                    Thread(target=compra_thread, args=(API, ativo, config['valor_entrada'], direcao_final, config['expiracao'], tipo_op, state, config, cifrao, signal_id, target_entry_timestamp), daemon=True).start()
            
            time.sleep(0.2)
        except Exception as e:
            log_error(f"ERRO NO LOOP DE TRADING: {e}")
            time.sleep(10)
    state.is_trading_loop_active = False
    log_info("Loop de trading parado.")
    signal_queue.put({"type": "status_update", "message": "Análise Parada."})

def bot_controller():
    exibir_banner()
    email = os.getenv('EXNOVA_EMAIL')
    senha = os.getenv('EXNOVA_PASSWORD')
    if not email or not senha:
        log_error("Variáveis de ambiente EXNOVA_EMAIL e EXNOVA_PASSWORD não definidas."); return
    
    state = BotState()
    config = get_config_from_env()
    API = Exnova(email, senha)
    log_info("A tentar conectar à Exnova...")
    check, reason = API.connect()
    if not check: log_error(f"Falha na conexão: {reason}"); return
    log_success("Conexão estabelecida!")
    API.change_balance(config['conta'])
    cifrao = API.get_profile_ansyc().get('currency_char', '$')

    while True:
        try:
            command = command_queue.get()
            if command['type'] == 'start_trading':
                if not state.is_trading_loop_active:
                    log_info("Recebido comando para LIGAR análise.")
                    state.stop_trading = False
                    Thread(target=trading_loop, args=(state, config, API, cifrao), daemon=True).start()
            elif command['type'] == 'stop_trading':
                log_info("Recebido comando para PARAR análise.")
                state.stop_trading = True
        except Exception as e:
            log_error(f"Erro no controlador do bot: {e}")

async def ws_main_handler(websocket, state):
    connected_clients.add(websocket)
    log_success(f"Novo cliente conectado: {websocket.remote_address}")
    try:
        initial_state = {"type": "init", "data": {"signals": list(state.signal_history.values()), "placar": {"wins": state.win_count, "losses": state.loss_count, "gale_wins": sum(state.gale_wins.values())}}}
        await websocket.send(json.dumps(initial_state))
        
        async for message in websocket:
            data = json.loads(message)
            log_info(f"Comando recebido do frontend: {data}")
            command_queue.put(data)
    finally:
        connected_clients.remove(websocket)
        log_warning(f"Cliente desconectado: {websocket.remote_address}")

def main():
    state = BotState()
    
    # Inicia o controlador do bot em segundo plano
    controller_thread = Thread(target=bot_controller, daemon=True)
    controller_thread.start()
    
    # Inicia o servidor WebSocket em segundo plano
    websocket_thread = Thread(target=start_websocket_server_sync, args=(state,), daemon=True)
    websocket_thread.start()

    log_info("Bot Service iniciado. Aguardando comandos do frontend.")
    
    # Mantém o programa principal vivo
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
