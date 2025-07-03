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

from colorama import init, Fore
from configobj import ConfigObj
from exnovaapi.stable_api import Exnova

# --- Inicialização ---
init(autoreset=True)
g, y, r, w, c, b = Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.WHITE, Fore.CYAN, Fore.BLUE

# --- Fila e Clientes para WebSocket (se necessário no futuro) ---
signal_queue = queue.Queue()
connected_clients = set()

# --- Funções de Log ---
def log(cor, mensagem):
    print(f"{cor}[{datetime.now().strftime('%H:%M:%S')}] {w}{mensagem}")

def log_info(msg): log(c, msg)
def log_success(msg): log(g, msg)
def log_warning(msg): log(y, msg)
def log_error(msg): log(r, msg)

# --- Banner ---
def exibir_banner():
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

# --- Funções de Análise Técnica e Estratégias ---

def validar_e_limpar_velas(velas_raw):
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
        if all(key in vela_padronizada for key in chaves_obrigatorias):
            velas_limpas.append(vela_padronizada)
    return velas_limpas

def catalogar_estrategias(api, state, params):
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
    if len(closes) < period + 1: return None
    sma = deque(maxlen=period)
    for close in closes[- (period + 1):]: sma.append(sum(closes[-(period):])/period)
    if len(sma) < 2 or sma[-2] == 0: return None
    return sma[-1] > sma[-2]

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
    vela_anterior = velas[-2]; o, h, l, c = vela_anterior['open'], vela_anterior['high'], vela_anterior['low'], vela_anterior['close']
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
        sup_level = sup_levels[0]; target_price = sup_level + p['Proximity'] * p['Point']
        if last['low'] <= target_price and last['close'] >= sup_level: return 'BUY'
    if not nano_up and res_levels and last['close'] < last['open']:
        res_level = res_levels[0]; target_price = res_level - p['Proximity'] * p['Point']
        if last['high'] >= target_price and last['close'] <= res_level: return 'SELL'
    return None

def strategy_flow(velas, p):
    if len(velas) < p['MAPeriod'] + 3: return None
    nano_up = sma_slope([v['close'] for v in velas], p['MAPeriod'])
    if nano_up is None: return None
    last_candles = velas[-3:]
    if nano_up and all(v['close'] > v['open'] for v in last_candles): return 'BUY'
    if not nano_up and all(v['close'] < v['open'] for v in last_candles): return 'SELL'
    return None

def strategy_patterns(velas, p):
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
    candles_to_check, body_max_ratio, min_indecisive_count = 3, 0.4, 2
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

# --- Classes e Funções de Gestão ---
class BotState:
    def __init__(self):
        self.stop = True
        self.lucro_total = 0.0
        self.win_count = 0
        self.loss_count = 0
        self.gale_wins = {f"g{i}": 0 for i in range(1, 11)}
        self.operacao_lock = Lock()
        self.strategy_performance = {}

def carregar_credenciais():
    if os.path.exists('credenciais.txt'):
        try:
            with open('credenciais.txt', 'r') as f: e_enc, s_enc = f.read().strip().split('\n')
            return base64.b64decode(e_enc).decode(), base64.b64decode(s_enc).decode()
        except Exception: log_error("Arquivo 'credenciais.txt' corrompido."); sys.exit()
    return None, None

def salvar_credenciais(e, s):
    try:
        with open('credenciais.txt', 'w') as f: f.write(f"{base64.b64encode(e.encode()).decode()}\n{base64.b64encode(s.encode()).decode()}")
        log_success("Credenciais salvas.")
    except Exception as ex: log_error(f"Erro ao salvar credenciais: {ex}")

def carregar_configuracoes():
    try:
        cfg = ConfigObj('config.txt', encoding='utf8')
        ajustes, martingale, soros = cfg.get('AJUSTES', {}), cfg.get('MARTINGALE', {}), cfg.get('SOROS', {})
        return {'conta': ajustes.get('conta', 'PRACTICE').upper(), 'pay_minimo': float(ajustes.get('pay_minimo', 80)), 'valor_entrada': float(ajustes.get('valor_entrada', 1)), 'stop_win': float(ajustes.get('stop_win', 10)), 'stop_loss': float(ajustes.get('stop_loss', 10)), 'expiracao': int(ajustes.get('expiracao', 1)), 'usar_mg': martingale.get('usar_martingale', 'NAO').upper() == 'SIM', 'mg_niveis': int(martingale.get('niveis', 2)), 'mg_fator': float(martingale.get('fator', 2.0)), 'mg_inverter': martingale.get('inverter_no_gale', 'NAO').upper() == 'SIM', 'usar_soros': soros.get('usar_soros', 'NAO').upper() == 'SIM', 'soros_niveis': int(soros.get('niveis', 3))}
    except Exception as e: log_error(f"Erro ao ler o arquivo de configuração: {e}"); sys.exit()

def exibir_placar(state, config):
    print(y + "\n" + "="*12 + " PLACAR " + "="*12)
    print(f"{g}>> WIN de Primeira: {w}{state.win_count - sum(state.gale_wins.values())}")
    if config['usar_mg']:
        for i in range(1, config['mg_niveis'] + 1): print(f"{g}>> WIN no Gale {i}: {w}{state.gale_wins.get(f'g{i}', 0)}")
    print(f"{r}>> LOSS (Final): {w}{state.loss_count}")
    print(y + "="*32)

def checar_stop(state, config):
    if state.lucro_total >= config['stop_win']: state.stop = False; print(f"\n{g}STOP WIN ATINGIDO! Lucro: {state.lucro_total:.2f}")
    elif state.lucro_total <= -config['stop_loss']: state.stop = False; print(f"\n{r}STOP LOSS ATINGIDO! Prejuízo: {state.lucro_total:.2f}")

def compra_thread(api, ativo, valor, direcao, expiracao, tipo_op, state, config, cifrao):
    log_info(f"THREAD DE COMPRA INICIADA para o ativo {ativo}.")
    try:
        with state.operacao_lock:
            log_info(f"LOCK ADQUIRIDO para o ativo {ativo}.")
            entrada_atual = valor
            direcao_atual, niveis_mg = direcao, config['mg_niveis'] if config['usar_mg'] else 0
            
            for i in range(niveis_mg + 1):
                if not state.stop: break
                
                gale_info = f"(Gale {i})" if i > 0 else "(Entrada Principal)"
                log_info(f"ORDEM {gale_info}: {ativo} | {cifrao}{entrada_atual:.2f} | {direcao_atual.upper()} | {expiracao}M")
                
                if tipo_op == 'digital':
                    check, id_ordem = api.buy_digital_spot(ativo, entrada_atual, direcao_atual, expiracao)
                else:
                    check, id_ordem = api.buy(entrada_atual, ativo, direcao_atual, expiracao)

                if not check:
                    log_error(f"Falha ao abrir ordem no Gale {i}. ID: {id_ordem}")
                    time.sleep(3)
                    continue

                log_warning(f"Ordem {id_ordem} aberta. Aguardando resultado...")
                resultado, status_encontrado = 0.0, False
                tempo_limite = time.time() + expiracao * 60 + 15
                while time.time() < tempo_limite:
                    if tipo_op == 'digital':
                        status, lucro = api.check_win_digital_v2(id_ordem)
                    else:
                        status, lucro = api.check_win_v4(id_ordem)
                    
                    if status:
                        resultado = lucro
                        status_encontrado = True
                        break
                    time.sleep(0.5)
                
                if not status_encontrado:
                    log_error(f"Timeout ao verificar resultado da ordem {id_ordem}.")
                    continue

                state.lucro_total += resultado
                
                if resultado > 0:
                    log_success(f"RESULTADO: WIN {gale_info} | Lucro: {cifrao}{resultado:.2f} | Total: {cifrao}{state.lucro_total:.2f}")
                    if i == 0: state.win_count += 1
                    else: state.gale_wins[f'g{i}'] += 1
                    break
                
                elif resultado == 0:
                    log_warning(f"RESULTADO: EMPATE {gale_info}. Repetindo a mão.")
                    continue
                else:
                    log_error(f"RESULTADO: LOSS {gale_info} | Prejuízo: {cifrao}{resultado:.2f} | Total: {cifrao}{state.lucro_total:.2f}")
                    if i < niveis_mg:
                        entrada_atual *= config['mg_fator']
                        if config['mg_inverter']:
                            direcao_atual = 'put' if direcao_atual == 'call' else 'call'
                    else:
                        state.loss_count += 1
                        log_error("Fim dos Martingales. Resultado final: LOSS")
                
                checar_stop(state, config)
            
            exibir_placar(state, config)
            checar_stop(state, config)

    except Exception as e:
        log_error(f"ERRO CRÍTICO NA THREAD DE COMPRA: {e}")
        traceback.print_exc()

def obter_melhor_par(api, payout_minimo):
    all_assets, all_profits, ativos = api.get_all_open_time(), api.get_all_profit(), {}
    for tipo_mercado in ['binary', 'turbo']:
        if tipo_mercado in all_assets:
            for ativo, info in all_assets[tipo_mercado].items():
                if info.get('open', False):
                    try:
                        payout = api.get_digital_payout(ativo) if tipo_mercado == 'digital' else all_profits.get(ativo, {}).get(tipo_mercado, 0)
                        payout *= 100
                        if payout >= payout_minimo and (ativo not in ativos or payout > ativos[ativo]['payout']):
                             ativos[ativo] = {'payout': payout, 'tipo': 'binary' if tipo_mercado == 'turbo' else tipo_mercado}
                    except: continue
    if not ativos: return None, None, None
    
    melhor_par = max(ativos, key=lambda k: ativos[k]['payout'])
    return melhor_par, ativos[melhor_par]['tipo'], ativos[melhor_par]['payout']

def main():
    exibir_banner()
    
    config = carregar_configuracoes()
    email, senha = carregar_credenciais()
    if not email or not senha:
        log_warning("Nenhum arquivo 'credenciais.txt' encontrado.")
        email = input("Digite seu email: ")
        senha = getpass.getpass("Digite sua senha: ")
        salvar_credenciais(email, senha)

    log_info("Conectando à Exnova API...")
    API = Exnova(email, senha)
    check, reason = API.connect()
    if not check:
        log_error(f"Falha na conexão: {reason}")
        sys.exit()
    log_success("Conexão estabelecida com sucesso!")
    
    API.change_balance(config['conta'])
    perfil = API.get_profile_ansyc()
    cifrao, nome_usuario, saldo_inicial = perfil['currency_char'], perfil['name'], API.get_balance()
    
    log_info(f"Olá, {w}{nome_usuario}{c}! Iniciando o bot.")
    log_info(f"Conta: {w}{config['conta']} {c}| Saldo: {w}{cifrao}{saldo_inicial:.2f}")
    log_info(f"Stop Win: {g}{cifrao}{config['stop_win']:.2f} {c}| Stop Loss: {r}{cifrao}{config['stop_loss']:.2f}")

    state = BotState()
    
    print(f"\n{g}Escolha o modo de operação:")
    print(f" {w}1 - {c}CATALOGAR e depois Operar (Recomendado)")
    print(f" {w}2 - {c}Operar AGORA com Modo Híbrido (Sem catalogar)")
    modo_operacao = input(f"{g}--> {w}")

    PARAMS = {
        'MAPeriod': 5, 'MaxLevels': 10, 'Proximity': 7.0, 'Point': 1e-6, 'FlowCandles': 3,
        'RejectionWickMinRatio': 0.6, 
        'RejectionBodyMaxRatio': 0.3,
        'RejectionOppositeWickMaxRatio': 0.15,
        'IndecisionCandles': 3,
        'IndecisionBodyMaxRatio': 0.4,
        'IndecisionMinCount': 2
    }
    
    if modo_operacao == '1':
        catalogar_estrategias(API, state, PARAMS)
    
    minuto_anterior, operacao_feita_neste_minuto = -1, False
    log_info("Aguardando oportunidade de mercado...")
    print()

    while state.stop:
        try:
            timestamp = API.get_server_timestamp()
            minuto_atual = datetime.fromtimestamp(timestamp).minute
            segundos = datetime.fromtimestamp(timestamp).second

            if minuto_atual != minuto_anterior:
                operacao_feita_neste_minuto = False
                minuto_anterior = minuto_atual

            if 0 <= segundos <= 55 and not operacao_feita_neste_minuto:
                LIMPAR_LINHA = "\x1b[K"
                status_msg = f"{c}Buscando oportunidade... (Payout >= {w}{config['pay_minimo']}%{c})"
                print(f"\r{status_msg}{LIMPAR_LINHA}", end="")

                ativo, tipo_op, payout = obter_melhor_par(API, config['pay_minimo'])
                
                if not ativo:
                    time.sleep(2)
                    continue

                velas = validar_e_limpar_velas(API.get_candles(ativo, 60, 150, time.time()))
                
                if not velas or len(velas) < 20:
                    time.sleep(0.5)
                    continue

                if is_market_indecisive(velas, PARAMS):
                    log_warning(f"Mercado com muitos pavios/indecisão em {ativo}. Nenhuma operação será feita.")
                    time.sleep(5)
                    continue

                direcao_final = None
                dados_do_ativo = state.strategy_performance.get(ativo)

                if dados_do_ativo:
                    cod_est = dados_do_ativo['best_strategy']
                    strategy_function = globals().get(f'strategy_{cod_est}')
                    if strategy_function:
                        sinal = strategy_function(velas, PARAMS)
                        if sinal:
                            direcao_final = {'BUY': 'call', 'SELL': 'put'}.get(sinal)
                            log_success(f"SINAL ENCONTRADO via '{cod_est.upper()}': {direcao_final.upper()} em {ativo}!")
                else:
                    strategies_to_check = [
                        ('PULLBACK MQL', 'mql_pullback'), 
                        ('FLUXO', 'flow'), 
                        ('PADRÕES', 'patterns'),
                        ('REJEIÇÃO', 'rejection_candle')
                    ]
                    for nome_est, cod_est in strategies_to_check:
                        strategy_function = globals().get(f'strategy_{cod_est}')
                        if strategy_function:
                            sinal = strategy_function(velas, PARAMS)
                            if sinal:
                                direcao_final = {'BUY': 'call', 'SELL': 'put'}.get(sinal)
                                log_success(f"SINAL ENCONTRADO via '{nome_est}': {direcao_final.upper()} em {ativo}!")
                                break
                
                if direcao_final:
                    Thread(target=compra_thread, args=(API, ativo, config['valor_entrada'], direcao_final, config['expiracao'], tipo_op, state, config, cifrao)).start()
                    operacao_feita_neste_minuto = True
                    log_warning("Aguardando 30s após a operação para evitar entradas duplicadas.")
                    print()
                    time.sleep(30)
            else:
                if operacao_feita_neste_minuto: continue

                LIMPAR_LINHA = "\x1b[K"
                tempo_restante = 60 - segundos
                lucro_cor = g if state.lucro_total > 0 else r
                mensagem = f"{y}>> Próxima janela em {w}{tempo_restante:02d}s...{y} [Lucro Atual: {lucro_cor}{cifrao}{state.lucro_total:.2f}{y}]"
                print(f"\r{mensagem}{LIMPAR_LINHA}", end="")
                time.sleep(1)

        except Exception as e:
            print()
            log_error(f"ERRO INESPERADO NO LOOP PRINCIPAL: {e}")
            traceback.print_exc()
            time.sleep(10)
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_warning("\nBot interrompido pelo usuário.")
    finally:
        log(b, "Encerrando o bot.")
        sys.exit(
