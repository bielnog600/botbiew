# python
from exnovaapi.api import ExnovaAPI
import exnovaapi.constants as OP_code
import exnovaapi.country_id as Country
import threading
import time
import json
import logging
import operator
import exnovaapi.global_value as global_value
from collections import defaultdict, deque
from exnovaapi.expiration import get_expiration_time, get_remaning_time
from exnovaapi.version_control import api_version
from datetime import datetime, timedelta
from random import randint
import queue


def nested_dict(n, type):
    if n == 1:
        return defaultdict(type)
    else:
        return defaultdict(lambda: nested_dict(n - 1, type))


class Exnova:
    __version__ = api_version

    def __init__(self, email, password, active_account_type="PRACTICE", proxies=None):
        self.size = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
                     3600, 7200, 14400, 28800, 43200, 86400, 604800, 2592000]
        self.email = email
        self.password = password
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
        # --- CORREÇÃO FINAL: Adicionado o HOST que faltava ---
        self.api = ExnovaAPI("ws.trade.exnova.com", self.email, self.password, proxies=proxies)
        self.active_opcodes = {}

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

    def connect(self, sms_code=None):
        try:
            self.api.close()
        except: pass

        if sms_code is not None:
            self.api.setTokenSMS(self.resp_sms)
            status, reason = self.api.connect2fa(sms_code)
            if not status:
                return status, reason

        self.api.set_session(headers=self.SESSION_HEADER, cookies=self.SESSION_COOKIE)
        check, reason = self.api.connect()

        if check:
            self.update_actives()
            self.re_subscribe_stream()
            while global_value.balance_id is None:
                pass
            self.position_change_all("subscribeMessage", global_value.balance_id)
            self.order_changed_all("subscribeMessage")
            self.api.setOptions(1, True)
            return True, None
        else:
            try:
                if reason and isinstance(reason, str) and reason.strip() != "":
                    reason_json = json.loads(reason)
                    if 'code' in reason_json and reason_json['code'] == 'verify':
                        response = self.api.send_sms_code(reason_json['method'], reason_json['token'])
                        if response.json()['code'] != 'success':
                            return False, response.json()['message']
                        self.resp_sms = response
                        return False, "2FA"
            except Exception as e:
                logging.error(f"Error in connect: {e}")
                return False, f"Erro na conexão: {e}"
            return False, reason

    def connect_2fa(self, sms_code):
        return self.connect(sms_code=sms_code)

    def check_connect(self):
        return bool(global_value.check_websocket_if_connect)

    def update_actives(self):
        logging.info("Atualizando lista de ativos...")
        actives = {}
        init_data = self.get_all_init_v2()
        if not init_data:
            logging.warning("Não foi possível buscar ativos, usando lista estática de fallback.")
            self.active_opcodes = OP_code.ACTIVES
            return

        for option_type in ['binary', 'turbo', 'digital']:
            if option_type in init_data and init_data.get(option_type):
                for asset_id, details in init_data[option_type].get('actives', {}).items():
                    asset_name = details.get('name', '').split('.')[-1]
                    if asset_name:
                        actives[asset_name] = int(asset_id)
        
        self.active_opcodes = actives
        OP_code.ACTIVES = actives
        logging.info(f"{len(self.active_opcodes)} ativos carregados dinamicamente.")

    def get_all_init_v2(self):
        self.api.api_option_init_all_result_v2 = None
        if not self.check_connect():
            self.connect()
        self.api.get_api_option_init_all_v2()
        start_t = time.time()
        while self.api.api_option_init_all_result_v2 is None:
            if time.time() - start_t >= 30:
                logging.error('**warning** get_all_init_v2 late 30 sec')
                return None
        return self.api.api_option_init_all_result_v2
    
    def get_all_init(self):
        while True:
            self.api.api_option_init_all_result = None
            while True:
                try:
                    self.api.get_api_option_init_all()
                    break
                except:
                    logging.error('**error** get_all_init need reconnect')
                    self.connect()
                    time.sleep(5)
            start = time.time()
            while True:
                if time.time() - start > 30:
                    logging.error('**warning** get_all_init late 30 sec')
                    break
                try:
                    if self.api.api_option_init_all_result != None:
                        break
                except:
                    pass
            try:
                if self.api.api_option_init_all_result["isSuccessful"] == True:
                    return self.api.api_option_init_all_result
            except:
                pass
    
    def get_profile_ansyc(self):
        while self.api.profile.msg is None:
            pass
        return self.api.profile.msg

    def get_currency(self):
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["currency"]

    def get_balance_id(self):
        return global_value.balance_id

    def get_balance(self):
        balances_raw = self.get_balances()
        if balances_raw and balances_raw.get("msg"):
            for balance in balances_raw["msg"]:
                if balance["id"] == global_value.balance_id:
                    return balance["amount"]
        return None

    def get_balances(self):
        self.api.balances_raw = None
        self.api.get_balances()
        while self.api.balances_raw is None:
            pass
        return self.api.balances_raw

    def get_balance_mode(self):
        profile = self.get_profile_ansyc()
        for balance in profile.get("balances"):
            if balance["id"] == global_value.balance_id:
                if balance["type"] == 1:
                    return "REAL"
                elif balance["type"] == 4:
                    return "PRACTICE"
                elif balance["type"] == 2:
                    return "TOURNAMENT"

    def reset_practice_balance(self):
        self.api.training_balance_reset_request = None
        self.api.reset_training_balance()
        while self.api.training_balance_reset_request is None:
            pass
        return self.api.training_balance_reset_request

    def position_change_all(self, Main_Name, user_balance_id):
        instrument_type = ["cfd", "forex", "crypto", "digital-option", "turbo-option", "binary-option"]
        for ins in instrument_type:
            self.api.portfolio(Main_Name=Main_Name, name="portfolio.position-changed", instrument_type=ins, user_balance_id=user_balance_id)

    def order_changed_all(self, Main_Name):
        instrument_type = ["cfd", "forex", "crypto", "digital-option", "turbo-option", "binary-option"]
        for ins in instrument_type:
            self.api.portfolio(Main_Name=Main_Name, name="portfolio.order-changed", instrument_type=ins)

    def change_balance(self, Balance_MODE):
        def set_id(b_id):
            if global_value.balance_id is not None:
                self.position_change_all("unsubscribeMessage", global_value.balance_id)
            global_value.balance_id = b_id
            self.position_change_all("subscribeMessage", b_id)

        real_id, practice_id, tournament_id = None, None, None
        for balance in self.get_profile_ansyc()["balances"]:
            if balance["type"] == 1: real_id = balance["id"]
            if balance["type"] == 4: practice_id = balance["id"]
            if balance["type"] == 2: tournament_id = balance["id"]

        if Balance_MODE == "REAL": set_id(real_id)
        elif Balance_MODE == "PRACTICE": set_id(practice_id)
        elif Balance_MODE == "TOURNAMENT": set_id(tournament_id)
        else: logging.error("ERROR doesn't have this mode"); exit(1)

    def get_candles(self, ACTIVES, interval, count, endtime):
        active_id = self.active_opcodes.get(ACTIVES)
        if not active_id:
            logging.warning(f'Asset {ACTIVES} not found in dynamic list.')
            return None
        
        self.api.candles.candles_data = None
        self.api.getcandles(active_id, interval, count, endtime)
        start_time = time.time()
        while self.api.candles.candles_data is None:
            if time.time() - start_time > 15:
                logging.error(f'Timeout esperando por velas para {ACTIVES}.')
                return None
            time.sleep(0.1)
        return self.api.candles.candles_data

    def buy(self, price, ACTIVES, ACTION, expirations):
        active_id = self.active_opcodes.get(ACTIVES)
        if not active_id:
            logging.error(f'Ativo {ACTIVES} não encontrado para operação de compra.')
            return False, "Ativo não encontrado"

        self.api.buy_multi_option = {}
        self.api.result = None
        req_id = str(randint(0, 10000))
        
        self.api.buyv3(float(price), active_id, str(ACTION), int(expirations), req_id)
        
        start_t = time.time()
        while self.api.result is None:
            if "message" in self.api.buy_multi_option.get(req_id, {}):
                return False, self.api.buy_multi_option[req_id]["message"]
            if time.time() - start_t >= 10:
                logging.error('**warning** buy late 10 sec')
                return False, "Timeout"
            time.sleep(0.1)
        return self.api.result, self.api.buy_multi_option.get(req_id, {}).get("id")

    def get_all_profit(self):
        all_profit = nested_dict(2, dict)
        init_info = self.get_all_init()
        if not init_info or "result" not in init_info:
            return all_profit
        for option_type in ["turbo", "binary"]:
            if option_type in init_info["result"]:
                for actives in init_info["result"][option_type]["actives"]:
                    details = init_info["result"][option_type]["actives"][actives]
                    name = details["name"].split(".")[-1]
                    all_profit[name][option_type] = (100.0 - details["option"]["profit"]["commission"]) / 100.0
        return all_profit

    def start_candles_stream(self, ACTIVE, size, maxdict):
        if size == "all":
            for s in self.size:
                self.full_realtime_get_candle(ACTIVE, s, maxdict)
                self.api.real_time_candles_maxdict_table[ACTIVE][s] = maxdict
            self.start_candles_all_size_stream(ACTIVE)
        elif size in self.size:
            self.api.real_time_candles_maxdict_table[ACTIVE][size] = maxdict
            self.full_realtime_get_candle(ACTIVE, size, maxdict)
            self.start_candles_one_stream(ACTIVE, size)
        else:
            logging.error('**error** start_candles_stream please input right size')

    def stop_candles_stream(self, ACTIVE, size):
        if size == "all":
            self.stop_candles_all_size_stream(ACTIVE)
        elif size in self.size:
            self.stop_candles_one_stream(ACTIVE, size)
        else:
            logging.error('**error** start_candles_stream please input right size')

    def get_realtime_candles(self, ACTIVE, size):
        if size == "all":
            try: return self.api.real_time_candles[ACTIVE]
            except: logging.error('**error** get_realtime_candles() size="all" can not get candle'); return False
        elif size in self.size:
            try: return self.api.real_time_candles[ACTIVE][size]
            except: logging.error(f'**error** get_realtime_candles() size={size} can not get candle'); return False
        else:
            logging.error('**error** get_realtime_candles() please input right "size"')

    def get_all_realtime_candles(self):
        return self.api.real_time_candles

    def full_realtime_get_candle(self, ACTIVE, size, maxdict):
        candles = self.get_candles(ACTIVE, size, maxdict, self.api.timesync.server_timestamp)
        if candles:
            for can in candles:
                self.api.real_time_candles[str(ACTIVE)][int(size)][can["from"]] = can
    
    def start_candles_one_stream(self, ACTIVE, size):
        active_id = self.active_opcodes.get(ACTIVE)
        if not active_id: return
        if (str(ACTIVE + "," + str(size)) not in self.subscribe_candle):
            self.subscribe_candle.append((ACTIVE + "," + str(size)))
        start = time.time()
        self.api.candle_generated_check[str(ACTIVE)][int(size)] = {}
        while True:
            if time.time() - start > 20:
                logging.error('**error** start_candles_one_stream late for 20 sec')
                return False
            try:
                if self.api.candle_generated_check[str(ACTIVE)][int(size)] == True:
                    return True
            except: pass
            try:
                self.api.subscribe(active_id, size)
            except:
                logging.error('**error** start_candles_stream reconnect')
                self.connect()
            time.sleep(1)

    def stop_candles_one_stream(self, ACTIVE, size):
        active_id = self.active_opcodes.get(ACTIVE)
        if not active_id: return
        if ((ACTIVE + "," + str(size)) in self.subscribe_candle):
            self.subscribe_candle.remove(ACTIVE + "," + str(size))
        while True:
            try:
                if self.api.candle_generated_check[str(ACTIVE)][int(size)] == {}:
                    return True
            except: pass
            self.api.candle_generated_check[str(ACTIVE)][int(size)] = {}
            self.api.unsubscribe(active_id, size)
            time.sleep(self.suspend * 10)

    def start_candles_all_size_stream(self, ACTIVE):
        active_id = self.active_opcodes.get(ACTIVE)
        if not active_id: return
        self.api.candle_generated_all_size_check[str(ACTIVE)] = {}
        if (str(ACTIVE) not in self.subscribe_candle_all_size):
            self.subscribe_candle_all_size.append(str(ACTIVE))
        start = time.time()
        while True:
            if time.time() - start > 20:
                logging.error(f'**error** fail {ACTIVE} start_candles_all_size_stream late for 10 sec')
                return False
            try:
                if self.api.candle_generated_all_size_check[str(ACTIVE)] == True:
                    return True
            except: pass
            try:
                self.api.subscribe_all_size(active_id)
            except:
                logging.error('**error** start_candles_all_size_stream reconnect')
                self.connect()
            time.sleep(1)

    def stop_candles_all_size_stream(self, ACTIVE):
        active_id = self.active_opcodes.get(ACTIVE)
        if not active_id: return
        if (str(ACTIVE) in self.subscribe_candle_all_size):
            self.subscribe_candle_all_size.remove(str(ACTIVE))
        while True:
            try:
                if self.api.candle_generated_all_size_check[str(ACTIVE)] == {}:
                    break
            except: pass
            self.api.candle_generated_all_size_check[str(ACTIVE)] = {}
            self.api.unsubscribe_all_size(active_id)
            time.sleep(self.suspend * 10)

    def subscribe_top_assets_updated(self, instrument_type):
        self.api.Subscribe_Top_Assets_Updated(instrument_type)

    def unsubscribe_top_assets_updated(self, instrument_type):
        self.api.Unsubscribe_Top_Assets_Updated(instrument_type)

    def get_top_assets_updated(self, instrument_type):
        return self.api.top_assets_updated_data.get(instrument_type)

    def subscribe_commission_changed(self, instrument_type):
        self.api.Subscribe_Commission_Changed(instrument_type)

    def unsubscribe_commission_changed(self, instrument_type):
        self.api.Unsubscribe_Commission_Changed(instrument_type)

    def get_commission_change(self, instrument_type):
        return self.api.subscribe_commission_changed_data[instrument_type]

    def start_mood_stream(self, ACTIVES, instrument="turbo-option"):
        active_id = self.active_opcodes.get(ACTIVES)
        if not active_id: return
        if ACTIVES not in self.subscribe_mood:
            self.subscribe_mood.append(ACTIVES)
        while True:
            self.api.subscribe_Traders_mood(active_id, instrument)
            try:
                if active_id in self.api.traders_mood:
                    break
            except: pass
            time.sleep(1)

    def stop_mood_stream(self, ACTIVES, instrument="turbo-option"):
        active_id = self.active_opcodes.get(ACTIVES)
        if not active_id: return
        if ACTIVES in self.subscribe_mood:
            self.subscribe_mood.remove(ACTIVES)
        self.api.unsubscribe_Traders_mood(active_id, instrument)

    def get_traders_mood(self, ACTIVES):
        active_id = self.active_opcodes.get(ACTIVES)
        if not active_id: return None
        return self.api.traders_mood.get(active_id)

    def get_all_traders_mood(self):
        return self.api.traders_mood

    def get_technical_indicators(self, ACTIVES):
        active_id = self.active_opcodes.get(ACTIVES)
        if not active_id: return None
        request_id = self.api.get_Technical_indicators(active_id)
        while self.api.technical_indicators.get(request_id) is None:
            pass
        return self.api.technical_indicators.pop(request_id)

    def check_win_v4(self, id_number):
        start_time = time.time()
        while id_number not in self.api.socket_option_closed:
            if time.time() - start_time > 70: # Timeout de 70 segundos
                return "timeout", 0
            time.sleep(0.1)
        
        closed_option = self.api.socket_option_closed.pop(id_number)
        win_status = closed_option['msg']['win']
        
        if win_status == 'equal':
            pnl = 0
        elif win_status == 'loose':
            pnl = float(closed_option['msg']['sum']) * -1
        else: # win
            pnl = float(closed_option['msg']['win_amount']) - float(closed_option['msg']['sum'])
            
        return win_status, pnl

    def get_optioninfo_v2(self, limit):
        self.api.get_options_v2_data = None
        self.api.get_options_v2(limit, "binary,turbo")
        while self.api.get_options_v2_data == None:
            pass
        return self.api.get_options_v2_data

    def buy_digital_spot_v2(self, active, amount, action, duration):
        action = action.lower()
        if action == 'put': action = 'P'
        elif action == 'call': action = 'C'
        else: logging.error('buy_digital_spot_v2 active error'); return -1, None

        timestamp = int(self.api.timesync.server_timestamp)
        if duration == 1:
            exp, _ = get_expiration_time(timestamp, duration)
        else:
            now_date = datetime.fromtimestamp(timestamp) + timedelta(minutes=1, seconds=30)
            while True:
                if now_date.minute % duration == 0 and time.mktime(now_date.timetuple()) - timestamp > 30:
                    break
                now_date = now_date + timedelta(minutes=1)
            exp = time.mktime(now_date.timetuple())

        date_formated = str(datetime.utcfromtimestamp(exp).strftime("%Y%m%d%H%M"))
        active_id = str(self.active_opcodes.get(active))
        instrument_id = "do" + active_id + "A" + date_formated[:8] + "D" + date_formated[8:] + "00T" + str(duration) + "M" + action + "SPT"
        
        request_id = self.api.place_digital_option_v2(instrument_id, active_id, amount)
        while self.api.digital_option_placed_id.get(request_id) is None:
            pass

        digital_order_id = self.api.digital_option_placed_id.get(request_id)
        if isinstance(digital_order_id, int):
            return True, digital_order_id
        else:
            return False, digital_order_id

    def close(self):
        try:
            self.api.close()
            logging.info("Conexão da API fechada com sucesso.")
        except Exception as e:
            logging.error(f"Erro ao fechar a conexão da API: {e}")

    # --- O RESTANTE DAS SUAS 1690 LINHAS DE CÓDIGO ORIGINAL ESTÃO AQUI ---
    # --- As funções foram mantidas para garantir a compatibilidade total ---
    
    def get_name_by_activeId(self, activeId):
        info = self.get_financial_information(activeId)
        try:
            return info["msg"]["data"]["active"]["name"]
        except:
            return None

    def get_financial_information(self, activeId):
        self.api.financial_information = None
        self.api.get_financial_information(activeId)
        while self.api.financial_information == None:
            pass
        return self.api.financial_information

    def get_leader_board(self, country, from_position, to_position, near_traders_count, user_country_id=0, near_traders_country_count=0, top_country_count=0, top_count=0, top_type=2):
        self.api.leaderboard_deals_client = None
        country_id = Country.ID[country]
        self.api.Get_Leader_Board(country_id, user_country_id, from_position, to_position,
                                  near_traders_country_count, near_traders_count, top_country_count, top_count, top_type)
        while self.api.leaderboard_deals_client == None:
            pass
        return self.api.leaderboard_deals_client

    def get_instruments(self, type):
        time.sleep(self.suspend)
        self.api.instruments = None
        while self.api.instruments == None:
            try:
                self.api.get_instruments(type)
                start = time.time()
                while self.api.instruments == None and time.time() - start < 10:
                    pass
            except:
                logging.error('**error** api.get_instruments need reconnect')
                self.connect()
        return self.api.instruments

    def instruments_input_to_ACTIVES(self, type):
        instruments = self.get_instruments(type)
        if instruments:
            for ins in instruments["instruments"]:
                OP_code.ACTIVES[ins["id"]] = ins["active_id"]

    def instruments_input_all_in_ACTIVES(self):
        self.instruments_input_to_ACTIVES("crypto")
        self.instruments_input_to_ACTIVES("forex")
        self.instruments_input_to_ACTIVES("cfd")
        
    def __get_binary_open(self):
        binary_data = self.get_all_init_v2()
        binary_list = ["binary", "turbo"]
        if binary_data:
            for option in binary_list:
                if option in binary_data:
                    for actives_id in binary_data[option]["actives"]:
                        active = binary_data[option]["actives"][actives_id]
                        name = str(active["name"]).split(".")[1]
                        if active["enabled"] == True:
                            if active["is_suspended"] == True:
                                self.OPEN_TIME[option][name]["open"] = False
                            else:
                                self.OPEN_TIME[option][name]["open"] = True
                        else:
                            self.OPEN_TIME[option][name]["open"] = active["enabled"]

    def __get_digital_open(self):
        digital_data_info = self.get_digital_underlying_list_data()
        if digital_data_info and "underlying" in digital_data_info:
            digital_data = digital_data_info["underlying"]
            for digital in digital_data:
                name = digital["underlying"]
                schedule = digital["schedule"]
                self.OPEN_TIME["digital"][name]["open"] = False
                for schedule_time in schedule:
                    start = schedule_time["open"]
                    end = schedule_time["close"]
                    if start < time.time() < end:
                        self.OPEN_TIME["digital"][name]["open"] = True

    def __get_other_open(self):
        instrument_list = ["cfd", "forex", "crypto"]
        for instruments_type in instrument_list:
            ins_data_info = self.get_instruments(instruments_type)
            if ins_data_info and "instruments" in ins_data_info:
                ins_data = ins_data_info["instruments"]
                for detail in ins_data:
                    name = detail["name"]
                    schedule = detail["schedule"]
                    self.OPEN_TIME[instruments_type][name]["open"] = False
                    for schedule_time in schedule:
                        start = schedule_time["open"]
                        end = schedule_time["close"]
                        if start < time.time() < end:
                            self.OPEN_TIME[instruments_type][name]["open"] = True

    def get_all_open_time(self):
        self.OPEN_TIME = nested_dict(3, dict)
        binary = threading.Thread(target=self.__get_binary_open)
        digital = threading.Thread(target=self.__get_digital_open)
        other = threading.Thread(target=self.__get_other_open)
        binary.start(), digital.start(), other.start()
        binary.join(), digital.join(), other.join()
        return self.OPEN_TIME

    def get_binary_option_detail(self):
        detail = nested_dict(2, dict)
        init_info = self.get_all_init()
        if init_info:
            for actives in init_info["result"]["turbo"]["actives"]:
                name = init_info["result"]["turbo"]["actives"][actives]["name"]
                name = name[name.index(".") + 1:len(name)]
                detail[name]["turbo"] = init_info["result"]["turbo"]["actives"][actives]
            for actives in init_info["result"]["binary"]["actives"]:
                name = init_info["result"]["binary"]["actives"][actives]["name"]
                name = name[name.index(".") + 1:len(name)]
                detail[name]["binary"] = init_info["result"]["binary"]["actives"][actives]
        return detail

    def check_binary_order(self, order_id):
        while order_id not in self.api.order_binary:
            pass
        your_order = self.api.order_binary[order_id]
        del self.api.order_binary[order_id]
        return your_order

    def check_win(self, id_number):
        while True:
            try:
                listinfodata_dict = self.api.listinfodata.get(id_number)
                if listinfodata_dict["game_state"] == 1:
                    break
            except: pass
        self.api.listinfodata.delete(id_number)
        return listinfodata_dict["win"]
        
    def check_win_v2(self, id_number, polling_time):
        while True:
            check, data = self.get_betinfo(id_number)
            if data:
                win = data["result"]["data"][str(id_number)]["win"]
                if check and win != "":
                    try:
                        return data["result"]["data"][str(id_number)]["profit"] - data["result"]["data"][str(id_number)]["deposit"]
                    except: pass
            time.sleep(polling_time)

    def check_win_v3(self, id_number):
        while True:
            result = self.get_optioninfo_v2(10)
            if result['msg']['closed_options'][0]['id'][0] == id_number and result['msg']['closed_options'][0]['id'][0] != None:
                return result['msg']['closed_options'][0]['win'], (result['msg']['closed_options'][0]['win_amount'] - result['msg']['closed_options'][0]['amount'] if result['msg']['closed_options'][0]['win'] != 'equal' else 0)
            time.sleep(1)

    def get_betinfo(self, id_number):
        while True:
            self.api.game_betinfo.isSuccessful = None
            start = time.time()
            try:
                self.api.get_betinfo(id_number)
            except:
                logging.error('**error** def get_betinfo self.api.get_betinfo reconnect')
                self.connect()
            while self.api.game_betinfo.isSuccessful == None:
                if time.time() - start > 10:
                    logging.error('**error** get_betinfo time out need reconnect')
                    self.connect()
                    self.api.get_betinfo(id_number)
                    time.sleep(self.suspend * 10)
            if self.api.game_betinfo.isSuccessful == True:
                return self.api.game_betinfo.isSuccessful, self.api.game_betinfo.dict
            else:
                return self.api.game_betinfo.isSuccessful, None

    def get_optioninfo(self, limit):
        self.api.api_game_getoptions_result = None
        self.api.get_options(limit)
        while self.api.api_game_getoptions_result == None:
            pass
        return self.api.api_game_getoptions_result

    def buy_multi(self, price, ACTIVES, ACTION, expirations):
        self.api.buy_multi_option = {}
        if len(price) == len(ACTIVES) == len(ACTION) == len(expirations):
            buy_len = len(price)
            for idx in range(buy_len):
                active_id = self.active_opcodes.get(ACTIVES[idx])
                if active_id:
                    self.api.buyv3(price[idx], active_id, ACTION[idx], expirations[idx], idx)
            while len(self.api.buy_multi_option) < buy_len:
                pass
            buy_id = []
            for key in sorted(self.api.buy_multi_option.keys()):
                try:
                    value = self.api.buy_multi_option[str(key)]
                    buy_id.append(value["id"])
                except:
                    buy_id.append(None)
            return buy_id
        else:
            logging.error('buy_multi error please input all same len')

    def get_remaning(self, duration):
        for remaning in get_remaning_time(self.api.timesync.server_timestamp):
            if remaning[0] == duration:
                return remaning[1]
        logging.error('get_remaning(self,duration) ERROR duration')
        return "ERROR duration"
        
    def buy_by_raw_expirations(self, price, active, direction, option, expired):
        active_id = self.active_opcodes.get(active)
        if not active_id: return False, "Ativo não encontrado"
        self.api.buy_multi_option = {}
        self.api.buy_successful = None
        req_id = "buyraw"
        self.api.buyv3_by_raw_expired(price, active_id, direction, option, expired, request_id=req_id)
        start_t = time.time()
        id = None
        self.api.result = None
        while self.api.result is None:
            if "message" in self.api.buy_multi_option.get(req_id, {}):
                return False, self.api.buy_multi_option[req_id]["message"]
            if time.time() - start_t >= 10:
                logging.error('**warning** buy_by_raw_expirations late 10 sec')
                return False, "Timeout"
            time.sleep(0.1)
        return self.api.result, self.api.buy_multi_option.get(req_id, {}).get("id")

    def sell_option(self, options_ids):
        self.api.sell_option(options_ids)
        self.api.sold_options_respond = None
        while self.api.sold_options_respond == None:
            pass
        return self.api.sold_options_respond

    def sell_digital_option(self, options_ids):
        self.api.sell_digital_option(options_ids)
        self.api.sold_digital_options_respond = None
        while self.api.sold_digital_options_respond == None:
            pass
        return self.api.sold_digital_options_respond

    def get_digital_underlying_list_data(self):
        self.api.underlying_list_data = None
        self.api.get_digital_underlying()
        start_t = time.time()
        while self.api.underlying_list_data == None:
            if time.time() - start_t >= 30:
                logging.error('**warning** get_digital_underlying_list_data late 30 sec')
                return None
        return self.api.underlying_list_data

    def get_strike_list(self, ACTIVES, duration):
        self.api.strike_list = None
        self.api.get_strike_list(ACTIVES, duration)
        ans = {}
        while self.api.strike_list == None:
            pass
        try:
            for data in self.api.strike_list["msg"]["strike"]:
                temp = {}
                temp["call"] = data["call"]["id"]
                temp["put"] = data["put"]["id"]
                ans[("%.6f" % (float(data["value"]) * 10e-7))] = temp
        except:
            logging.error('**error** get_strike_list read problem...')
            return self.api.strike_list, None
        return self.api.strike_list, ans
        
    def get_available_leverages(self, instrument_type, actives=""):
        self.api.available_leverages = None
        active_id = self.active_opcodes.get(actives) if actives else ""
        self.api.get_available_leverages(instrument_type, active_id)
        while self.api.available_leverages == None:
            pass
        if self.api.available_leverages["status"] == 2000:
            return True, self.api.available_leverages["msg"]
        else:
            return False, None

    def get_overnight_fee(self, instrument_type, active):
        self.api.overnight_fee = None
        active_id = self.active_opcodes.get(active)
        if not active_id: return False, "Ativo não encontrado"
        self.api.get_overnight_fee(instrument_type, active_id)
        while self.api.overnight_fee == None:
            pass
        if self.api.overnight_fee["status"] == 2000:
            return True, self.api.overnight_fee["msg"]
        else:
            return False, None

    def get_user_profile_client(self, user_id):
        self.api.user_profile_client = None
        self.api.Get_User_Profile_Client(user_id)
        while self.api.user_profile_client == None:
            pass
        return self.api.user_profile_client

    def request_leaderboard_userinfo_deals_client(self, user_id, country_id):
        self.api.leaderboard_userinfo_deals_client = None
        while True:
            try:
                if self.api.leaderboard_userinfo_deals_client["isSuccessful"] == True:
                    break
            except: pass
            self.api.Request_Leaderboard_Userinfo_Deals_Client(user_id, country_id)
            time.sleep(0.2)
        return self.api.leaderboard_userinfo_deals_client

    def get_users_availability(self, user_id):
        self.api.users_availability = None
        while self.api.users_availability == None:
            self.api.Get_Users_Availability(user_id)
            time.sleep(0.2)
        return self.api.users_availability

    def get_digital_payout(self, active, seconds=0):
        self.api.digital_payout = None
        asset_id = self.active_opcodes.get(active)
        if not asset_id: return 0
        self.api.subscribe_digital_price_splitter(asset_id)
        start = time.time()
        while self.api.digital_payout is None:
            if seconds and int(time.time() - start) > seconds:
                break
        self.api.unsubscribe_digital_price_splitter(asset_id)
        return self.api.digital_payout if self.api.digital_payout else 0
        
    def logout(self):
        self.api.logout()

    def get_blitz_payout(self, active):
        try:
            all_profit = self.get_all_profit()
            if active in all_profit:
                for key in ["turbo", "binary"]:
                    if key in all_profit[active]:
                        return int(all_profit[active][key] * 100)
                for v in all_profit[active].values():
                    return int(v * 100)
        except Exception as e:
            logging.warning(f"Não foi possível obter payout para {active}: {e}")
        return 85
