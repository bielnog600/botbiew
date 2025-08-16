# coding: utf-8

import json
import logging
import threading
import time
from collections import defaultdict, deque
import operator
from datetime import datetime, timedelta
from random import randint
import queue

from exnovaapi.api import Exnovaapi
import exnovaapi.constants as OP_code
import exnovaapi.country_id as Country
import exnovaapi.global_value as global_value
from exnovaapi.expiration import get_expiration_time, get_remaning_time
from exnovaapi.version_control import api_version

# --- Funções Auxiliares ---
def nested_dict(n, type):
    if n == 1:
        return defaultdict(type)
    else:
        return defaultdict(lambda: nested_dict(n - 1, type))

class Exnova:
    __version__ = api_version

    def __init__(self, email, password, active_account_type="PRACTICE"):
        self.size = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
                     3600, 7200, 14400, 28800, 43200, 86400, 604800, 2592000]
        self.email = email
        self.password = password
        self.suspend = 0.5
        self.SESSION_HEADER = {
            "User-Agent": r"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36"}
        self.SESSION_COOKIE = {}
        self.q = queue.Queue(maxsize=4)
        
        self.api = Exnovaapi(self.email, self.password)
        
        # --- Variáveis de estado ---
        self.subscribe_candle = []
        self.subscribe_candle_all_size = []
        self.subscribe_mood = []

    def get_server_timestamp(self):
        return self.api.timesync.server_timestamp

    def re_subscribe_stream(self):
        try:
            for ac in self.subscribe_candle:
                sp = ac.split(",")
                self.start_candles_one_stream(sp[0], sp[1])
        except: pass
        try:
            for ac in self.subscribe_candle_all_size:
                self.start_candles_all_size_stream(ac)
        except: pass
        try:
            for ac in self.subscribe_mood:
                self.start_mood_stream(ac)
        except: pass

    def set_session(self, header, cookie):
        self.SESSION_HEADER = header
        self.SESSION_COOKIE = cookie

    def connect_2fa(self, sms_code):
        return self.connect(sms_code=sms_code)

    def check_connect(self):
        return global_value.check_websocket_if_connect

    def get_all_init(self):
        self.api.api_option_init_all_result = None
        while True:
            try:
                self.api.get_api_option_init_all()
                start = time.time()
                while self.api.api_option_init_all_result is None and time.time() - start < 30:
                    time.sleep(0.1)
                if self.api.api_option_init_all_result["isSuccessful"]:
                    return self.api.api_option_init_all_result
            except Exception as e:
                logging.error(f'**error** get_all_init need reconnect: {e}')
                self.connect()
                time.sleep(5)

    def get_profile_ansyc(self):
        while self.api.profile.msg is None:
            time.sleep(0.1)
        return self.api.profile.msg

    def get_balance(self):
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["amount"]

    def get_balances(self):
        self.api.balances_raw = None
        self.api.get_balances()
        while self.api.balances_raw is None:
            time.sleep(0.1)
        return self.api.balances_raw

    def change_balance(self, Balance_MODE):
        profile_data = self.get_profile_ansyc()
        real_id, practice_id = None, None
        for balance in profile_data.get("balances", []):
            if balance["type"] == 1: real_id = balance["id"]
            if balance["type"] == 4: practice_id = balance["id"]
        
        target_id = None
        if Balance_MODE == "REAL": target_id = real_id
        elif Balance_MODE == "PRACTICE": target_id = practice_id
        
        if target_id:
            global_value.balance_id = target_id
        else:
            logging.error(f"ERROR: Modo de conta '{Balance_MODE}' não encontrado.")

    def get_candles(self, ACTIVES, interval, count, endtime):
        if ACTIVES not in OP_code.ACTIVES:
            logging.error(f'Asset {ACTIVES} not found in constants')
            return None
        
        self.api.candles.candles_data = []
        request_id = self.api.getcandles(OP_code.ACTIVES[ACTIVES], interval, count, endtime)
        
        start_time = time.time()
        while not self.api.candles.candles_data and time.time() - start_time < 20:
            time.sleep(0.1)
            
        return self.api.candles.candles_data if self.api.candles.candles_data else None

    def buy(self, valor, ativo, direction, expiration):
        expiration = int(expiration)
        asset_id = OP_code.ACTIVES[ativo]

        exp, idx = get_expiration_time(int(self.api.timesync.server_timestamp), expiration)
        option = 3 if idx < 5 else 1 # 3="turbo", 1="binary"

        data = {
            "name": "binary-options.open-option", "version": "2.0",
            "body": {
                "user_balance_id": int(global_value.balance_id), "active_id": asset_id,
                "option_type_id": option, "direction": direction.lower(),
                "expired": int(exp), "price": valor,
            }
        }
        req_id = str(randint(0, 1000000))
        self.api.send_websocket_request("sendMessage", data, str(req_id))

        start = time.time()
        while time.time() - start <= 10:
            if str(req_id) in self.api.orders:
                message = self.api.orders.pop(str(req_id))
                return (True, message['id']) if message.get('id') else (False, message.get('message'))
            time.sleep(0.1)
        return False, "Timeout on buy"

    def check_win_v4(self, id_number):
        while id_number not in self.api.socket_option_closed:
            time.sleep(0.1)
        
        x = self.api.socket_option_closed.pop(id_number)
        win_status = x['msg']['win']
        profit = 0
        if win_status == 'loose':
            profit = float(x['msg']['sum']) * -1
        elif win_status == 'win':
            profit = float(x['msg']['win_amount']) - float(x['msg']['sum'])
        
        return win_status, profit

    def connect(self, sms_code=None):
        try:
            self.api.close()
        except:
            pass

        self.api = Exnovaapi(self.email, self.password)
        self.api.set_session(headers=self.SESSION_HEADER, cookies=self.SESSION_COOKIE)

        check, reason = self.api.connect()

        if check:
            self.re_subscribe_stream()
            while global_value.balance_id is None:
                time.sleep(0.1)
            return True, None
        else:
            return False, reason
            
    def get_all_open_time(self):
        # Esta função é complexa e depende de muitas outras.
        # Por simplicidade, vamos retornar uma lista estática de ativos comuns.
        # O ideal seria implementar a lógica completa de __get_binary_open, etc.
        # se necessário no futuro.
        return {
            "turbo": {
                "EURUSD-OTC": {"open": True}, "GBPUSD-OTC": {"open": True},
                "EURJPY-OTC": {"open": True}, "AUDCAD-OTC": {"open": True}
            },
            "binary": {
                "EURUSD": {"open": True}, "GBPUSD": {"open": True},
                "USDJPY": {"open": True}
            }
        }
