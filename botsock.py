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
from http.server import HTTPServer, BaseHTTPRequestHandler

import asyncio
import websockets
import queue

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

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, format, *args):
        return

def run_health_check_server():
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    log_info("Servidor de Health Check a correr na porta 8080...")
    httpd.serve_forever()

async def ws_handler(websocket, bot_state):
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
    asyncio.set_event_loop(asyncio.new_event_loop())
    handler_with_state = lambda ws: ws_handler(ws, bot_state)
    asyncio.get_event_loop().run_until_complete(start_websocket_server_async(handler_with_state))

async def start_websocket_server_async(handler):
    async with websockets.serve(handler, "0.0.0.0", 8765):
        log_info("Servidor WebSocket iniciado em ws://0.0.0.0:8765")
        await broadcast_signals()

def validar_e_limpar_velas(velas_raw):
    if not velas_raw: return []
    velas_limpas = []
    for v_raw in velas_raw:
        if not isinstance(v_raw, dict): continue
        vela_padronizada = {'open': v_raw.get('open'), 'close': v_raw.get('close'), 'high': v_raw.get('high') or v_raw.get('max'), 'low': v_raw.get('low') or v_raw.get('min')}
        if all(vela_padronizada.values()): velas_limpas.append(vela_padronizada)
    return velas_limpas

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
        'expiracao': int(os.getenv('EXNOVA_EXPIRACAO', 1)),
        'usar_mg': os.getenv('EXNOVA_USAR_MG', 'SIM').upper() == 'SIM',
        'mg_niveis': int(os.getenv('EXNOVA_MG_NIVEIS', 2)),
        'mg_fator': float(os.getenv('EXNOVA_MG_FATOR', 2.0)),
        'modo_operacao': os.getenv('EXNOVA_MODO_OPERACAO', '2')
    }

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao, signal_id, target_entry_timestamp):
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
        if resultado_final and resultado_final != "ERRO":
            state.signal_history[signal_id]["result"] = resultado_final
            placar_payload = {"type": "result", "signal_id": signal_id, "result": resultado_final, "placar": {"wins": state.win_count, "losses": state.loss_count, "gale_wins": sum(state.gale_wins.values())}}
            signal_queue.put(placar_payload)
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
    exibir_banner()
    email = os.getenv('EXNOVA_EMAIL')
    senha = os.getenv('EXNOVA_PASSWORD')
    if not email or not senha:
        log_error("Variáveis de ambiente EXNOVA_EMAIL e EXNOVA_PASSWORD não definidas.")
        sys.exit(1)
    
    config = get_config_from_env()
    API = Exnova(email, senha)
    
    log_info("A tentar conectar à Exnova...")
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
        nome_usuario = perfil.get('name', 'Utilizador')
        log_info(f"Olá, {w}{nome_usuario}{c}! Bot a iniciar em modo de servidor.")
    except Exception as e:
        log_warning(f"Não foi possível obter o perfil do utilizador. A continuar com valores padrão. Erro: {e}")
        log_info(f"Olá! Bot a iniciar em modo de servidor.")
    
    minuto_anterior, analise_feita = -1, False
    log_info("Bot iniciado. A entrar no ciclo de análise...")
    
    while state.stop:
        try:
            timestamp = time.time()
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
                direcao_final, nome_estrategia_usada = strategy_rejection_candle(velas, config), "Rejeição de Pavio"
                
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
    
    health_check_thread = Thread(target=run_health_check_server, daemon=True)
    health_check_thread.start()
    
    websocket_thread = Thread(target=start_websocket_server_sync, args=(bot_state,), daemon=True)
    websocket_thread.start()
    
    # ### CORREÇÃO FINAL ### Executa a lógica principal diretamente para manter o programa vivo
    try:
        main_bot_logic(bot_state)
    except KeyboardInterrupt:
        log_warning("\nBot interrompido pelo usuário.")
        bot_state.stop = False
    except Exception as e:
        log_error(f"Erro fatal ao iniciar o bot: {e}")
        traceback.print_exc()
    finally:
        log(b, "Encerrando o bot.");
        sys.exit()

if __name__ == "__main__":
    main()
