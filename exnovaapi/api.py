# coding: utf-8
import json
import logging
import ssl
import threading
import time
import requests
from exnovaapi.ws.client import ExnovaWs
import exnovaapi.global_value as global_value
from collections import defaultdict, deque
from exnovaapi.http.login import Login

class Exnovaapi(object):

    def __init__(self, email, password, host="exnova.com"):
        self.email = email
        self.password = password
        self.host = host
        self.https_url = f"https://{self.host}"
        self.wss_url = f"wss://{self.host}/echo/websocket" # URL corrigido
        self.websocket_client = None
        self.websocket_thread = None
        self.ssid = None
        self.profile = type('obj', (object,), {'msg': None})
        self.candles = defaultdict(lambda: None)
        self.orders = {}
        self.balances_raw = None
        self.socket_option_closed = {}

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
        """Cria e inicia a thread do cliente WebSocket."""
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
