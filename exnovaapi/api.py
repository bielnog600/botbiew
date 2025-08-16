# python
from exnovaapi.ws.client import ExnovaWs # Renomeado para corresponder ao ficheiro
import exnovaapi.constants as OP_code
import exnovaapi.country_id as Country
import threading
import time
import json
import logging
import operator
import exnovaapi.global_value as global_value
from collections import defaultdict
from collections import deque
from exnovaapi.expiration import get_expiration_time, get_remaning_time
from exnovaapi.version_control import api_version
from datetime import datetime, timedelta
from random import randint
import queue
from exnovaapi.http.login import Login
from exnovaapi.http.auth import Auth
from exnovaapi.http.loginv2 import Loginv2


def nested_dict(n, type):
    if n == 1:
        return defaultdict(type)
    else:
        return defaultdict(lambda: nested_dict(n - 1, type))


class Exnovaapi:
    __version__ = api_version

    def __init__(self, email, password, host="exnova.com"):
        self.size = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
                     3600, 7200, 14400, 28800, 43200, 86400, 604800, 2592000]
        self.email = email
        self.password = password
        self.host = host
        self.suspend = 0.5
        self.thread = None
        self.subscribe_candle = []
        self.subscribe_candle_all_size = []
        self.subscribe_mood = []
        self.subscribe_indicators = []
        self.get_digital_spot_profit_after_sale_data = nested_dict(2, int)
        self.get_realtime_strike_list_temp_data = {}
        self.get_realtime_strike_list_temp_expiration = 0
        self.SESSION_HEADER = {
            "User-Agent": r"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36"}
        self.SESSION_COOKIE = {}
        self.q = queue.Queue(maxsize=4)
        
        # --- Instanciação de objetos de estado ---
        from exnovaapi.ws.chanels.ssid import Ssid
        self.timesync = Ssid()
        from exnovaapi.ws.chanels.profile import Profile
        self.profile = Profile()
        from exnovaapi.ws.chanels.candles import GetCandles
        self.candles = GetCandles()
        
        # --- Dicionários para dados recebidos ---
        self.api_option_init_all_result = None
        self.api_option_init_all_result_v2 = None
        self.balances_raw = None
        self.orders = {}
        self.socket_option_closed = {}
        self.real_time_candles = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
        self.candle_generated_check = defaultdict(lambda: defaultdict(dict))
        self.candle_generated_all_size_check = defaultdict(dict)
        self.traders_mood = {}
        self.order_binary = {}
        self.listinfodata = defaultdict(dict)
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
        self.financial_information = None
        self.leaderboard_deals_client = None
        self.instruments = None
        self.training_balance_reset_request = None
        self.auto_margin_call_changed_respond = None
        self.tpsl_changed_respond = None
        self.order_data = None
        self.deferred_orders = None
        self.positions = None
        self.position = None
        self.position_history = None
        self.position_history_v2 = None
        self.available_leverages = None
        self.order_canceled = None
        self.close_position_data = None
        self.overnight_fee = None
        self.socket_option_opened = {}
        self.live_deal_data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: deque(list(), 100))))
        self.user_profile_client = None
        self.leaderboard_userinfo_deals_client = None
        self.users_availability = None
        self.digital_payout = None
        self.blitz_payout = None
        self.buy_forex_id = None
        self.cancel_order_forex = None
        self.fechadas_forex = None
        self.positions_forex = None
        self.pendentes_forex = None
        self.leverage_forex = None
        self.all_realtime_candles = {}

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
        login_proc = Loginv2(self)
        return login_proc.call(sms_code)

    def send_sms_code(self, method, token):
        auth_proc = Auth(self)
        return auth_proc.send_sms_code(method, token)
        
    # --- Métodos adicionais do ficheiro original ---
    def get_financial_information(self, activeId):
        self.financial_information = None
        self.send_websocket_request("get-financial-information", {"active_id": activeId})
        while self.financial_information is None:
            time.sleep(0.1)
        return self.financial_information
        
    def Get_Leader_Board(self, country_id, user_country_id, from_position, to_position,
                                  near_traders_country_count, near_traders_count, top_country_count, top_count, top_type):
        msg = {
            "name": "get-leader-board",
            "version": "2.0",
            "body": {
                "country_id": country_id,
                "user_country_id": user_country_id,
                "from_position": from_position,
                "to_position": to_position,
                "near_traders_country_count": near_traders_country_count,
                "near_traders_count": near_traders_count,
                "top_country_count": top_country_count,
                "top_count": top_count,
                "top_type": top_type
            }
        }
        self.send_websocket_request("sendMessage", msg)
        
    def get_instruments(self, type):
        msg = {"name": "get-instruments", "version": "1.0", "body": {"type": type}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_options(self, limit):
        msg = {"name": "get-options", "version": "1.0", "body": {"limit": limit}}
        self.send_websocket_request("sendMessage", msg)
        
    def buyv3_by_raw_expired(self, price, active_id, direction, option, expired, request_id):
        msg = {
            "name": "binary-options.open-option", "version": "2.0",
            "body": {
                "user_balance_id": int(global_value.balance_id),
                "active_id": active_id,
                "option_type_id": option,
                "direction": direction.lower(),
                "expired": int(expired),
                "price": price,
            }
        }
        self.send_websocket_request("sendMessage", msg, request_id)
        
    def sell_option(self, options_ids):
        msg = {"name": "sell-options", "version": "1.0", "body": {"options_ids": options_ids}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_strike_list(self, ACTIVES, duration):
        msg = {"name": "get-strike-list", "version": "1.0", "body": {"active": ACTIVES, "expiration_period": duration}}
        self.send_websocket_request("sendMessage", msg)
        
    def subscribe_instrument_quites_generated(self, ACTIVE, expiration_period):
        msg = {"name": "instrument-quotes-generated", "params": {"routingFilters": {"active": ACTIVE, "expiration_period": expiration_period}}}
        self.send_websocket_request("subscribeMessage", msg)
        
    def unsubscribe_instrument_quites_generated(self, ACTIVE, expiration_period):
        msg = {"name": "instrument-quotes-generated", "params": {"routingFilters": {"active": ACTIVE, "expiration_period": expiration_period}}}
        self.send_websocket_request("unsubscribeMessage", msg)
        
    def place_blitz_option(self, instrument_id, amount):
        req_id = f"place_blitz_{int(time.time())}"
        msg = {"name": "blitz-options.place-blitz-option", "version": "1.0", "body": {"instrument_id": instrument_id, "amount": str(amount)}}
        self.send_websocket_request("sendMessage", msg, req_id)
        return req_id
        
    def close_digital_option(self, position_id):
        msg = {"name": "digital-options.close-position", "version": "1.0", "body": {"position_id": position_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_digital_position(self, position_id):
        msg = {"name": "digital-options.get-position", "version": "1.0", "body": {"position_id": position_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def buy_order(self, **kwargs):
        msg = {"name": "place-order-temp", "version": "4.0", "body": kwargs}
        self.send_websocket_request("sendMessage", msg)
        
    def change_auto_margin_call(self, ID_Name, ID, auto_margin_call):
        msg = {"name": "change-auto-margin-call", "version": "1.0", "body": {ID_Name: ID, "auto_margin_call": auto_margin_call}}
        self.send_websocket_request("sendMessage", msg)
        
    def change_order(self, **kwargs):
        msg = {"name": "change-tpsl", "version": "1.0", "body": kwargs}
        self.send_websocket_request("sendMessage", msg)
        
    def get_pending(self, instrument_type):
        msg = {"name": "get-deferred-orders", "version": "1.0", "body": {"instrument_type": instrument_type}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_position_history(self, instrument_type):
        msg = {"name": "get-history-positions", "version": "2.0", "body": {"instrument_type": instrument_type}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_position_history_v2(self, instrument_type, limit, offset, start, end):
        msg = {"name": "get-history-positions-v2", "version": "1.0", "body": {"instrument_type": instrument_type, "limit": limit, "offset": offset, "start": start, "end": end}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_available_leverages(self, instrument_type, active_id):
        msg = {"name": "get-available-leverages", "version": "1.0", "body": {"instrument_type": instrument_type, "active_id": active_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def cancel_order(self, order_id):
        msg = {"name": "cancel-order", "version": "1.0", "body": {"order_id": order_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def close_position(self, position_id):
        msg = {"name": "close-position", "version": "1.0", "body": {"position_id": position_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def get_overnight_fee(self, instrument_type, active_id):
        msg = {"name": "get-overnight-fee", "version": "1.0", "body": {"instrument_type": instrument_type, "active_id": active_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def Subscribe_Live_Deal(self, name, active_id, _type):
        msg = {"name": name, "params": {"routingFilters": {"active_id": active_id, "type": _type}}}
        self.send_websocket_request("subscribeMessage", msg)
        
    def Unscribe_Live_Deal(self, name, active_id, _type):
        msg = {"name": name, "params": {"routingFilters": {"active_id": active_id, "type": _type}}}
        self.send_websocket_request("unsubscribeMessage", msg)
        
    def Get_User_Profile_Client(self, user_id):
        msg = {"name": "get-user-profile-client", "version": "1.0", "body": {"user_id": user_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def Request_Leaderboard_Userinfo_Deals_Client(self, user_id, country_id):
        msg = {"name": "request-leaderboard-userinfo-deals-client", "version": "1.0", "body": {"user_id": user_id, "country_id": country_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def Get_Users_Availability(self, user_id):
        msg = {"name": "get-users-availability", "version": "1.0", "body": {"user_id": user_id}}
        self.send_websocket_request("sendMessage", msg)
        
    def subscribe_digital_price_splitter(self, asset_id):
        msg = {"name": "price-splitter.client-price-generated", "params": {"routingFilters": {"instrument_type": "digital-option", "asset_id": asset_id}}}
        self.send_websocket_request("subscribeMessage", msg)
        
    def unsubscribe_digital_price_splitter(self, asset_id):
        msg = {"name": "price-splitter.client-price-generated", "params": {"routingFilters": {"instrument_type": "digital-option", "asset_id": asset_id}}}
        self.send_websocket_request("unsubscribeMessage", msg)
        
    def logout(self):
        self.send_websocket_request("logout", {})

    def place_digital_option_v2(self, instrument_id, active_id, amount):
        req_id = f"place_digital_v2_{int(time.time())}"
        msg = {"name": "digital-options.place-digital-option", "version": "3.0", "body": {"instrument_id": instrument_id, "asset_id": active_id, "amount": str(amount)}}
        self.send_websocket_request("sendMessage", msg, req_id)
        return req_id
        
    def place_blitz_option_v2(self, instrument_id, active_id, amount):
        req_id = f"place_blitz_v2_{int(time.time())}"
        msg = {"name": "blitz-options.place-blitz-option", "version": "1.0", "body": {"instrument_id": instrument_id, "asset_id": active_id, "amount": str(amount)}}
        self.send_websocket_request("sendMessage", msg, req_id)
        return req_id
        
    def buy_order_forex(self, leverage, par, direcao, valor_entrada, preco_entrada, win, lose):
        msg = {
            "name": "marginal-forex.place-stop-order", "version": "1.0",
            "body": {
                "side": str(direcao), "user_balance_id": int(global_value.balance_id),
                "count": str(valor_entrada), "instrument_id": f"mf.{par}",
                "instrument_active_id": int(par), "leverage": str(leverage),
                "stop_price": str(preco_entrada),
                "take_profit": {"type": "price", "value": str(win)},
                "stop_loss": {"type": "price", "value": str(lose)}
            }
        }
        self.send_websocket_request("sendMessage", msg)

