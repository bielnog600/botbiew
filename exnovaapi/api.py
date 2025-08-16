# coding: utf-8

import json
import logging
import ssl
import threading
import time
from exnovaapi.ws.client import ExnovaWs
import exnovaapi.global_value as global_value
from collections import defaultdict, deque
from exnovaapi.http.login import Login
from exnovaapi.version_control import api_version

class Exnovaapi(object):
    __version__ = api_version

    def __init__(self, email, password, host="exnova.com"):
        self.email = email
        self.password = password
        self.host = host
        self.https_url = f"https://{self.host}"
        self.wss_url = f"wss://{self.host}/echo/websocket"
        self.websocket_client = None
        self.websocket_thread = None
        self.ssid = None
        self.resp_sms = None

        # Dicionários e Deques para armazenar dados recebidos
        self.profile = type('obj', (object,), {'msg': None})
        self.candles = defaultdict(lambda: None)
        self.orders = {}
        self.positions = {}
        self.api_option_init_all_result = None
        self.api_option_init_all_result_v2 = None
        self.balances_raw = None
        self.traders_mood = {}
        self.socket_option_closed = {}
        self.order_binary = {}
        self.listinfodata = defaultdict(dict)
        self.candle_generated_check = defaultdict(lambda: defaultdict(dict))
        self.candle_generated_all_size_check = defaultdict(dict)
        self.real_time_candles = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
        self.real_time_candles_maxdict_table = defaultdict(lambda: defaultdict(int))
        self.technical_indicators = {}
        self.game_betinfo = type('obj', (object,), {'isSuccessful': None, 'dict': None})
        self.api_game_getoptions_result = None
        self.get_options_v2_data = None
        self.buy_multi_option = {}
        self.buy_successful = None
        self.result = None
        self.sold_options_respond = None
        self.underlying_list_data = None
        self.strike_list = None
        self.instrument_quites_generated_data = defaultdict(lambda: defaultdict(dict))
        self.instrument_quotes_generated_raw_data = defaultdict(lambda: defaultdict(dict))
        self.instrument_quites_generated_timestamp = defaultdict(lambda: defaultdict(int))
        self.digital_option_placed_id = {}
        self.blitz_option_placed_id = {}
        self.order_async = defaultdict(lambda: defaultdict(dict))
        self.payouts_digital = {}
        self.alerta = None
        self.alertas = None
        self.alertas_tocados = []
        self.buy_order_id = None
        self.top_assets_updated_data = {}
        self.subscribe_commission_changed_data = {}
        
        from exnovaapi.ws.chanels.ssid import Ssid
        self.timesync = Ssid()

    def connect(self):
        login_proc = Login(self)
        check, reason = login_proc.call()
        if not check:
            return False, reason
        
        self.ssid = reason
        global_value.SSID = self.ssid
        
        check_websocket, websocket_reason = self.start_websocket()
        if not check_websocket:
            return False, websocket_reason
            
        return True, None

    def start_websocket(self):
        self.websocket_client = ExnovaWs(self)
        self.websocket_thread = threading.Thread(target=self.websocket_client.run)
        self.websocket_thread.daemon = True
        self.websocket_thread.start()

        start_time = time.time()
        while not global_value.check_websocket_if_connect and time.time() - start_time < 15:
            time.sleep(0.1)

        if not global_value.check_websocket_if_connect:
            return False, "Connection timeout"
        
        self.set_ssid()
        return True, None
        
    def set_ssid(self):
        self.send_websocket_request("ssid", self.ssid)

    def getcandles(self, active_id, interval, count, endtime):
        request_id = f"get_candles_{active_id}_{int(time.time())}"
        self.candles[request_id] = None
        msg = {
            "name": "get-candles",
            "version": "2.0",
            "body": {
                "active_id": active_id,
                "size": int(interval),
                "to": int(endtime),
                "count": int(count),
            }
        }
        self.send_websocket_request("sendMessage", msg, request_id)
        return request_id
    
    def addcandles(self, request_id, candles_data):
        self.candles[request_id] = type('obj', (object,), {'candles_data': candles_data})

    def get_profile(self):
        self.send_websocket_request("get-profile", {})

    def get_balances(self):
        self.send_websocket_request("get-balances", {})

    def send_websocket_request(self, name, msg, request_id=None):
        if self.websocket_client and global_value.check_websocket_if_connect:
            data = {"name": name, "msg": msg}
            if request_id:
                data["request_id"] = str(request_id)
            
            try:
                self.websocket_client.wss.send(json.dumps(data))
            except Exception as e:
                logging.error(f"Error sending websocket request: {e}")

    def close(self):
        if self.websocket_client:
            self.websocket_client.close()
        if self.websocket_thread and self.websocket_thread.is_alive():
            self.websocket_thread.join()

    def get_api_option_init_all(self):
        self.send_websocket_request("get-api-option-init-all", {})

    def get_api_option_init_all_v2(self):
        self.send_websocket_request("get-api-option-init-all-v2", {})

    def reset_training_balance(self):
        self.send_websocket_request("training-balance-reset", {})
        
    def portfolio(self, Main_Name, name, instrument_type, user_balance_id=None):
        body = {"instrument_type": instrument_type}
        if user_balance_id:
            body["user_balance_id"] = user_balance_id
        
        msg = {"name": name, "body": body}
        self.send_websocket_request(Main_Name, msg)

    def subscribe(self, active_id, size):
        msg = {"name": "candle-generated", "params": {"routingFilters": {"active_id": active_id, "size": size}}}
        self.send_websocket_request("subscribeMessage", msg)

    def unsubscribe(self, active_id, size):
        msg = {"name": "candle-generated", "params": {"routingFilters": {"active_id": active_id, "size": size}}}
        self.send_websocket_request("unsubscribeMessage", msg)
        
    def subscribe_all_size(self, active_id):
        for size in [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 28800, 43200, 86400, 604800, 2592000]:
            self.subscribe(active_id, size)

    def unsubscribe_all_size(self, active_id):
        for size in [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 28800, 43200, 86400, 604800, 2592000]:
            self.unsubscribe(active_id, size)
            
    def subscribe_Traders_mood(self, active_id, instrument):
        msg = {"name": "traders-mood-changed", "params": {"routingFilters": {"instrument": instrument, "asset_id": active_id}}}
        self.send_websocket_request("subscribeMessage", msg)
        
    def unsubscribe_Traders_mood(self, active_id, instrument):
        msg = {"name": "traders-mood-changed", "params": {"routingFilters": {"instrument": instrument, "asset_id": active_id}}}
        self.send_websocket_request("unsubscribeMessage", msg)

    def buyv3(self, price, active_id, action, expirations, request_id):
        from exnovaapi.expiration import get_expiration_time
        msg = {
            "name": "binary-options.open-option", "version": "2.0",
            "body": {
                "user_balance_id": int(global_value.balance_id),
                "active_id": active_id,
                "option_type_id": 3 if expirations == 1 else 1,
                "direction": action.lower(),
                "expired": int(get_expiration_time(int(time.time()), expirations)[0]),
                "price": price,
            }
        }
        self.send_websocket_request("sendMessage", msg, request_id)
        
    def get_betinfo(self, id_number):
        msg = {"name": "get-bet-info", "version": "1.0", "body": {"bet_id": id_number}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_options_v2(self, limit, types):
        msg = {"name": "get-options", "version": "2.0", "body": {"limit": limit, "instrument_types": types}}
        self.send_websocket_request("sendMessage", msg)

    def get_order(self, order_id):
        msg = {"name": "get-order", "version": "1.0", "body": {"order_id": order_id}}
        self.send_websocket_request("sendMessage", msg)

    def get_positions(self, instrument_type):
        msg = {"name": "get-positions", "version": "4.0", "body": {"instrument_type": instrument_type}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_position(self, position_id):
        msg = {"name": "get-position", "version": "1.0", "body": {"position_id": position_id}}
        self.send_websocket_request("sendMessage", msg)

    def get_digital_underlying(self):
        self.send_websocket_request("get-underlying-list", {"type": "digital-option"})

    def place_digital_option(self, instrument_id, amount):
        req_id = f"place_digital_{int(time.time())}"
        msg = {"name": "digital-options.place-digital-option", "version": "3.0", "body": {"instrument_id": instrument_id, "amount": str(amount)}}
        self.send_websocket_request("sendMessage", msg, req_id)
        return req_id
        
    def set_session(self, headers, cookies):
        self.SESSION_HEADER = headers
        self.SESSION_COOKIE = cookies
        
    def setTokenSMS(self, resp_sms):
        self.resp_sms = resp_sms

    def connect2fa(self, sms_code):
        from exnovaapi.http.loginv2 import Loginv2
        login_proc = Loginv2(self)
        return login_proc.call(sms_code)

    def send_sms_code(self, method, token):
        from exnovaapi.http.auth import Auth
        auth_proc = Auth(self)
        return auth_proc.send_sms_code(method, token)

