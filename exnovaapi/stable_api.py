# coding: utf-8

"""
stable_api_updated.py
---------------------
Implementação completa e atualizada da classe Exnova, consolidando:
- Imports corrigidos e ampliados
- Assinatura do __init__ retrocompatível (email, password, active_account_type) + novos (host, proxies)
- Setup de URLs HTTPS/WSS
- Instanciação de todos os canais WebSocket conforme solicitado
- Propriedades e métodos utilitários (websocket property, get/set ssid, context manager, close, connect)
- Stubs seguros para métodos referenciados no restante do projeto (ex.: get_profile_ansyc),
  evitando quebrar o código se a implementação concreta estiver nos canais.

Observação: Esta classe depende do pacote "exnovaapi" e seus submódulos, conforme os imports abaixo.
"""

import json
import logging
import ssl
import threading
import time
from collections import defaultdict, deque
from threading import Thread
import operator
from datetime import datetime, timedelta
from random import randint
import queue

# Removido: from websocket import create_connection (não utilizado)

# API principal
from exnovaapi.api import Exnovaapi
# Removido: from exnovaapi.constants import constants (não utilizado)

# HTTP endpoints
from exnovaapi.http.getprofile import Getprofile

# WebSocket core
from exnovaapi.ws.client import ExnovaWs

# Canais WS
from exnovaapi.ws.chanels.buyv3 import Buyv3
from exnovaapi.ws.chanels.buyv4 import Buyv4
from exnovaapi.ws.chanels.candles import GetCandles
from exnovaapi.ws.chanels.digital_placing import DigitalPlacing
from exnovaapi.ws.chanels.financial_information import FinancialInformation
from exnovaapi.ws.chanels.get_financial_stats import GetFinancialStats
from exnovaapi.ws.chanels.get_instruments import GetInstruments
from exnovaapi.ws.chanels.instrument_quotes_generated import InstrumentQuotesGenerated
from exnovaapi.ws.chanels.list_info_data import ListInfoData
from exnovaapi.ws.chanels.portfolio import Portfolio
from exnovaapi.ws.chanels.profile import Profile
from exnovaapi.ws.chanels.quotes import Quotes
from exnovaapi.ws.chanels.ssid import Ssid
from exnovaapi.ws.chanels.strike_list import StrikeList
from exnovaapi.ws.chanels.traders_mood import TradersMood
from exnovaapi.ws.chanels.training_balance import TrainingBalancen
from exnovaapi.ws.chanels.buy_place_cancel_order import BuyPlaceCancelOrder
from exnovaapi.ws.chanels.buy_place_close_order import BuyPlaceCloseOrder
from exnovaapi.ws.chanels.get_order import GetOrder
from exnovaapi.ws.chanels.get_positions import GetPositions
from exnovaapi.ws.chanels.get_position import GetPosition
from exnovaapi.ws.chanels.get_available_leverages import GetAvailableLeverages
from exnovaapi.ws.chanels.get_tpsl import GetTpsl
from exnovaapi.ws.chanels.close_position import ClosePosition
from exnovaapi.ws.chanels.get_initialization_data import GetInitializationData
from exnovaapi.ws.chanels.underlying_list import UnderlyingList
from exnovaapi.ws.chanels.set_auto_margin_call import SetAutoMarginCall
from exnovaapi.ws.chanels.set_leverage import SetLeverage
from exnovaapi.ws.chanels.set_tpsl import SetTpsl
from exnovaapi.ws.chanels.cancel_tpsl import CancelTpsl
from exnovaapi.ws.chanels.get_pending_orders import GetPendingOrders
from exnovaapi.ws.chanels.place_pending_order import PlacePendingOrder
from exnovaapi.ws.chanels.cancel_pending_order import CancelPendingOrder
from exnovaapi.ws.chanels.margin_call import MarginCall
from exnovaapi.ws.chanels.candles_generated import CandlesGenerated
from exnovaapi.ws.chanels.deferred_orders import DeferredOrders
from exnovaapi.ws.chanels.copy_trades_placing import CopyTradesPlacing
from exnovaapi.ws.chanels.copy_trades_closing import CopyTradesClosing
from exnovaapi.ws.chanels.copy_trades_config import CopyTradesConfig
from exnovaapi.ws.chanels.copy_trades_instruments import CopyTradesInstruments
from exnovaapi.ws.chanels.available_assets import AvailableAssets
from exnovaapi.ws.chanels.commissions import Commissions
from exnovaapi.ws.chanels.overnight_fee import OvernightFee
from exnovaapi.ws.chanels.api_option_init_all import GetApiOptionInitAll
from exnovaapi.ws.chanels.candle_generated_v2 import CandleGeneratedV2
from exnovaapi.ws.chanels.user_profile_client import UserProfileClient
from exnovaapi.ws.chanels.user_settings_client import UserSettingsClient
from exnovaapi.ws.chanels.feed_price_generated import FeedPriceGenerated
from exnovaapi.ws.chanels.alerts import Alerts
from exnovaapi.ws.chanels.client_alert_changed import ClientAlertChanged
from exnovaapi.ws.chanels.client_alert_removed import ClientAlertRemoved
from exnovaapi.ws.chanels.client_alert_triggered import ClientAlertTriggered
from exnovaapi.ws.chanels.put_alert import PutAlert
from exnovaapi.ws.chanels.remove_alerts import RemoveAlerts
from exnovaapi.ws.chanels.leaderboard import Leaderboard
from exnovaapi.ws.chanels.user_top_traders_rating import UserTopTradersRating
from exnovaapi.ws.chanels.top_assets_updated import TopAssetsUpdated
from exnovaapi.ws.chanels.live_deal_binary_option_placed import LiveDealBinaryOptionPlaced
from exnovaapi.ws.chanels.live_deal_digital_option import LiveDealDigitalOption
from exnovaapi.ws.chanels.live_deal_cfd import LiveDealCfd
from exnovaapi.ws.chanels.client_price_move_changed import ClientPriceMoveChanged
from exnovaapi.ws.chanels.client_price_move_removed import ClientPriceMoveRemoved
from exnovaapi.ws.chanels.client_price_move_triggered import ClientPriceMoveTriggered
from exnovaapi.ws.chanels.put_price_move import PutPriceMove
from exnovaapi.ws.chanels.remove_price_moves import RemovePriceMoves
from exnovaapi.ws.chanels.get_leader_board_user_info_deals import GetLeaderBoardUserInfoDeals
from exnovaapi.ws.chanels.sold_options import SoldOptions
from exnovaapi.ws.chanels.sell_option import SellOption
from exnovaapi.ws.chanels.option import Option
from exnovaapi.ws.chanels.digital_option_placed import DigitalOptionPlaced
from exnovaapi.ws.chanels.training_balance_reset import TrainingBalanceReset
from exnovaapi.ws.chanels.candles_history import CandlesHistory

# Complementos do arquivo original
import exnovaapi.constants as OP_code
import exnovaapi.country_id as Country
import exnovaapi.global_value as global_value
from exnovaapi.expiration import get_expiration_time, get_remaning_time
from exnovaapi.version_control import api_version

try:
    unicode
except NameError:
    unicode = str


# ---------- util global (fora da classe!) ----------
def nested_dict(n, typ):
    """Cria um defaultdict recursivo: nested_dict(3, dict) -> dict de 3 níveis."""
    if n == 1:
        return defaultdict(typ)
    return defaultdict(lambda: nested_dict(n - 1, typ))


class Exnova:
    """Class for communication with Exnova API."""
    __version__ = api_version

    def __init__(self, email=None, password=None, active_account_type="PRACTICE", host="exnova.com", proxies=None):
        """
        Compatível com assinaturas antigas e adiciona novos parâmetros:
        - email, password, active_account_type (compat)
        - host, proxies (novos)
        """
        # --- Campos tradicionais usados em diversos métodos do projeto ---
        self.size = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
                     3600, 7200, 14400, 28800, 43200, 86400, 604800, 2592000]
        self.email = email
        self.password = password
        self.active_account_type = active_account_type
        self.suspend = 0.5
        self.thread = None
        self.subscribe_candle = []
        self.subscribe_candle_all_size = []
        self.subscribe_mood = []
        self.subscribe_indicators = []
        self.get_digital_spot_profit_after_sale_data = defaultdict(lambda: defaultdict(int))
        self.get_realtime_strike_list_temp_data = {}
        self.get_realtime_strike_list_temp_expiration = 0
        self.SESSION_HEADER = {
            "User-Agent": r"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.139 Safari/537.36"
        }
        self.SESSION_COOKIE = {}
        self.q = queue.Queue(maxsize=4)

        # --- Novos campos / correções ---
        self.https_url = f"https://{host}/api"
        self.wss_url = f"wss://{host}/echo/websocket"
        self.websocket_client = None
        self.websocket_thread = None
        self.is_connected = False
        self.connect_wock = threading.Lock()

        # API + canais
        self.api = Exnovaapi(host, proxies)
        self.instruments = None
        self.ssid = None
        self.profile = Profile()
        self.change_balance_id = None
        self.candles = GetCandles()
        self.instrument_quotes_generated = InstrumentQuotesGenerated()
        self.traders_mood = TradersMood()
        self.buy_v3 = Buyv3()
        self.buy_v4 = Buyv4()
        self.list_info_data = ListInfoData()
        self.strike_list = StrikeList()
        self.digital_placing = DigitalPlacing()
        self.financial_information = FinancialInformation()
        self.training_balance = TrainingBalancen()
        self.buy_place_cancel_order = BuyPlaceCancelOrder()
        self.buy_place_close_order = BuyPlaceCloseOrder()

        # Renomeados para não colidirem com métodos homônimos
        self.get_order_ch = GetOrder()
        self.get_positions_ch = GetPositions()
        self.get_position_ch = GetPosition()
        self.get_available_leverages_ch = GetAvailableLeverages()
        self.close_position_ch = ClosePosition()
        self.get_instruments_ch = GetInstruments()

        self.get_tpsl = GetTpsl()
        self.get_initialization_data = GetInitializationData()
        self.underlying_list = UnderlyingList()
        self.set_auto_margin_call = SetAutoMarginCall()
        self.set_leverage = SetLeverage()
        self.set_tpsl = SetTpsl()
        self.cancel_tpsl = CancelTpsl()
        self.get_pending_orders = GetPendingOrders()
        self.place_pending_order = PlacePendingOrder()
        self.cancel_pending_order = CancelPendingOrder()
        self.margin_call = MarginCall()
        self.candles_generated = CandlesGenerated()
        self.deferred_orders = DeferredOrders()
        self.copy_trades_placing = CopyTradesPlacing()
        self.copy_trades_closing = CopyTradesClosing()
        self.copy_trades_config = CopyTradesConfig()
        self.copy_trades_instruments = CopyTradesInstruments()
        self.available_assets = AvailableAssets()
        self.commissions = Commissions()
        self.overnight_fee = OvernightFee()
        self.api_option_init_all = GetApiOptionInitAll()
        self.candle_generated_v2 = CandleGeneratedV2()
        self.user_profile_client = UserProfileClient()
        self.user_settings_client = UserSettingsClient()
        self.feed_price_generated = FeedPriceGenerated()
        self.alerts = Alerts()
        self.client_alert_changed = ClientAlertChanged()
        self.client_alert_removed = ClientAlertRemoved()
        self.client_alert_triggered = ClientAlertTriggered()
        self.put_alert = PutAlert()
        self.remove_alerts = RemoveAlerts()
        self.leaderboard = Leaderboard()
        self.user_top_traders_rating = UserTopTradersRating()
        self.top_assets_updated = TopAssetsUpdated()
        self.live_deal_binary_option_placed = LiveDealBinaryOptionPlaced()
        self.live_deal_digital_option = LiveDealDigitalOption()
        self.live_deal_cfd = LiveDealCfd()
        self.client_price_move_changed = ClientPriceMoveChanged()
        self.client_price_move_removed = ClientPriceMoveRemoved()
        self.client_price_move_triggered = ClientPriceMoveTriggered()
        self.put_price_move = PutPriceMove()
        self.remove_price_moves = RemovePriceMoves()
        self.get_leader_board_user_info_deals = GetLeaderBoardUserInfoDeals()
        self.sold_options = SoldOptions()
        self.sell_option = SellOption()
        self.option = Option()
        self.digital_option_placed = DigitalOptionPlaced()
        self.training_balance_reset = TrainingBalanceReset()
        self.candles_history = CandlesHistory()
        self.portfolio = Portfolio()
        self.get_financial_stats = GetFinancialStats()
        self.quotes = Quotes()
        self.timesync = Ssid()


    # ------------------------------------------------------------------
    # Propriedades e utilitários
    # ------------------------------------------------------------------
    @property
    def websocket(self):
        return self.websocket_client

    @websocket.setter
    def websocket(self, websocket):
        self.websocket_client = websocket

    def get_ssid(self):
        return self.api.ssid

    def set_ssid(self, ssid):
        self.api.ssid = ssid

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ------------------------------------------------------------------
    # Ciclo de vida da conexão
    # ------------------------------------------------------------------
    def close(self):
        """
        Fecha o cliente WebSocket e aguarda o término da thread.
        Seguro para ser chamado múltiplas vezes.
        """
        try:
            if self.websocket_client:
                try:
                    self.websocket_client.close()
                except Exception:
                    pass
        finally:
            if self.websocket_thread and self.websocket_thread.is_alive():
                try:
                    self.websocket_thread.join(timeout=2)
                except Exception:
                    pass

    def connect(self):
        """
        Inicializa o cliente WS (ExnovaWs) em thread daemon, sincroniza SSID
        e checa verificação de conta.
        Retorna (True, None) em caso de sucesso, ou (False, "motivo").
        """
        with self.connect_wock:
            self.websocket_client = ExnovaWs(self)
            self.websocket_thread = Thread(target=self.websocket_client.run, daemon=True)
            self.websocket_thread.start()

            # Solicita sincronização de SSID via canal apropriado
            try:
                self.timesync.subscribe_ssid()
            except Exception:
                # Alguns builds usam outro nome de método; a chamada é "best effort".
                pass

            # Aguarda o flag de conexão
            start = time.time()
            while not self.is_connected and (time.time() - start) < 20:
                time.sleep(0.01)

            if not self.is_connected:
                return False, "Timeout conectando WebSocket"

            # Busca/assina perfil logo após conectar
            self.get_profile_ansyc()
            check, reason = self.check_verification()
            if not check:
                return False, reason

            return True, None

    def check_verification(self):
        """
        Valida se a conta está verificada. Mantém a semântica original:
        retorna (True, None) se ok ou (False, 'mensagem') se não-verificada.
        """
        if getattr(self, "profile", None) and getattr(self.profile, "data", None):
            # Alguns clientes usam chave direta; garantimos acesso seguro:
            is_verified = self.profile.data.get("is_verified")
            if is_verified is False:
                return False, "Please verify your account"
        return True, None

    # Hooks chamados pelo cliente WS (se suportado)
    def _on_ws_open(self):
        self.is_connected = True

    def _on_ws_close(self):
        self.is_connected = False

    def _on_ws_error(self, err):
        logging.error("WebSocket error: %s", err)

    # ------------------------------------------------------------------
    # Stubs / utilitários compatíveis
    # ------------------------------------------------------------------
    def get_profile_ansyc(self):
        """
        Assina/solicita dados de perfil e devolve o payload do perfil.
        - Tenta WS (Profile.subscribe)
        - Tenta fallback HTTP (Getprofile) se disponível
        - Aguarda até o dado aparecer em self.api.profile.msg
        Retorna dict (ou {} se não disponível).
        """
        # Tentativa via canal WS
        try:
            if hasattr(self.profile, "subscribe"):
                self.profile.subscribe()
        except Exception:
            pass

        # Fallback HTTP (best-effort)
        try:
            gp = Getprofile()
            if hasattr(gp, "send"):
                gp.send(self)
        except Exception:
            pass

        # Aguarda até 20s por self.api.profile.msg
        start = time.time()
        while getattr(self.api, "profile", None) is not None and getattr(self.api.profile, "msg", None) is None:
            if time.time() - start > 20:
                break
            time.sleep(0.05)

        return getattr(self.api.profile, "msg", {}) or {}


    def get_server_timestamp(self):
        return self.api.timesync.server_timestamp

    def re_subscribe_stream(self):
        try:
            for ac in self.subscribe_candle:
                sp = ac.split(",")
                self.start_candles_one_stream(sp[0], sp[1])
        except:
            pass
        # -----------------
        try:
            for ac in self.subscribe_candle_all_size:
                self.start_candles_all_size_stream(ac)
        except:
            pass
        # -------------reconnect subscribe_mood
        try:
            for ac in self.subscribe_mood:
                self.start_mood_stream(ac)
        except:
            pass

    def set_session(self, header, cookie):
        self.SESSION_HEADER = header
        self.SESSION_COOKIE = cookie

    def check_connect(self):
        if not global_value.check_websocket_if_connect:
            return False
        else:
            return True
        # wait for timestamp getting

    # _________________________UPDATE ACTIVES OPCODE_____________________
    def get_all_ACTIVES_OPCODE(self):
        return OP_code.ACTIVES

    def update_ACTIVES_OPCODE(self):
        # update from binary option
        self.get_ALL_Binary_ACTIVES_OPCODE()
        # crypto /forex/cfd
        self.instruments_input_all_in_ACTIVES()
        dicc = {}
        for lis in sorted(OP_code.ACTIVES.items(), key=operator.itemgetter(1)):
            dicc[lis[0]] = lis[1]
        OP_code.ACTIVES = dicc

    def get_name_by_activeId(self, activeId):
        info = self.get_financial_information(activeId)
        try:
            return info["msg"]["data"]["active"]["name"]
        except:
            return None

    def get_financial_information(self, activeId):
        self.api.financial_information = None
        self.api.get_financial_information(activeId)
        while self.api.financial_information is None:
            pass
        return self.api.financial_information

    def get_leader_board(self, country, from_position, to_position, near_traders_count, user_country_id=0, near_traders_country_count=0, top_country_count=0, top_count=0, top_type=2):
        self.api.leaderboard_deals_client = None

        country_id = Country.ID[country]
        self.api.Get_Leader_Board(country_id, user_country_id, from_position, to_position,
                                  near_traders_country_count, near_traders_count, top_country_count, top_count, top_type)

        while self.api.leaderboard_deals_client is None:
            pass
        return self.api.leaderboard_deals_client

    def get_instruments(self, type):
        # type="crypto"/"forex"/"cfd"
        time.sleep(self.suspend)
        self.api.instruments = None
        while self.api.instruments is None:
            try:
                self.api.get_instruments(type)
                start = time.time()
                while self.api.instruments is None and time.time() - start < 10:
                    pass
            except:
                logging.error('**error** api.get_instruments need reconnect')
                self.connect()
        return self.api.instruments

    def instruments_input_to_ACTIVES(self, type):
        instruments = self.get_instruments(type)
        for ins in instruments["instruments"]:
            OP_code.ACTIVES[ins["id"]] = ins["active_id"]

    def instruments_input_all_in_ACTIVES(self):
        self.instruments_input_to_ACTIVES("crypto")
        self.instruments_input_to_ACTIVES("forex")
        self.instruments_input_to_ACTIVES("cfd")

    def get_ALL_Binary_ACTIVES_OPCODE(self):
        init_info = self.get_all_init()
        for dirr in (["binary", "turbo"]):
            for i in init_info["result"][dirr]["actives"]:
                OP_code.ACTIVES[(init_info["result"][dirr]["actives"][i]["name"]).split(".")[1]] = int(i)

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
                    if self.api.api_option_init_all_result is not None:
                        break
                except:
                    pass
            try:
                if self.api.api_option_init_all_result["isSuccessful"] is True:
                    return self.api.api_option_init_all_result
            except:
                pass

    def get_all_init_v2(self):
        self.api.api_option_init_all_result_v2 = None

        if self.check_connect() is False:
            self.connect()

        self.api.get_api_option_init_all_v2()
        start_t = time.time()
        while self.api.api_option_init_all_result_v2 is None:
            if time.time() - start_t >= 30:
                logging.error('**warning** get_all_init_v2 late 30 sec')
                return None
        return self.api.api_option_init_all_result_v2

    def __get_binary_open(self):
        # for turbo and binary pairs
        binary_data = self.get_all_init_v2()
        binary_list = ["binary", "turbo"]
        if binary_data:
            for option in binary_list:
                if option in binary_data:
                    for actives_id in binary_data[option]["actives"]:
                        active = binary_data[option]["actives"][actives_id]
                        name = str(active["name"]).split(".")[1]
                        if active["enabled"] is True:
                            if active["is_suspended"] is True:
                                self.OPEN_TIME[option][name]["open"] = False
                            else:
                                self.OPEN_TIME[option][name]["open"] = True
                        else:
                            self.OPEN_TIME[option][name]["open"] = active["enabled"]

                        # update actives opcode
                        OP_code.ACTIVES[name] = int(actives_id)

    def __get_digital_open(self):
        # for digital options
        digital_data = self.get_digital_underlying_list_data()["underlying"]

        for digital in digital_data:
            name = digital["underlying"]
            schedule = digital["schedule"]
            self.OPEN_TIME["digital"][name]["open"] = False
            for schedule_time in schedule:
                start = schedule_time["open"]
                end = schedule_time["close"]
                if start < time.time() < end:
                    self.OPEN_TIME["digital"][name]["open"] = True

            # update digital actives opcode
            active_id_valor = digital['active_id']
            OP_code.ACTIVES[name] = active_id_valor

    def __get_other_open(self):
        # Crypto and etc pairs
        instrument_list = ["cfd", "forex", "crypto"]
        for instruments_type in instrument_list:
            ins_data = self.get_instruments(instruments_type)["instruments"]
            for detail in ins_data:
                name = detail["name"]
                schedule = detail["schedule"]
                self.OPEN_TIME[instruments_type][name]["open"] = False
                for schedule_time in schedule:
                    start = schedule_time["open"]
                    end = schedule_time["close"]
                    if start < time.time() < end:
                        self.OPEN_TIME[instruments_type][name]["open"] = True

                # update actives opcode
                active_id_valor = detail['active_id']
                OP_code.ACTIVES[name] = active_id_valor

    def get_all_open_time(self):
        # all pairs opened
        self.OPEN_TIME = nested_dict(3, dict)

        binary = threading.Thread(target=self.__get_binary_open)
        digital = threading.Thread(target=self.__get_digital_open)
        other = threading.Thread(target=self.__get_other_open)

        binary.start(); digital.start(); other.start()
        binary.join(); digital.join(); other.join()

        # ordenate updated actives opcode
        OP_code.ACTIVES = dict(sorted(OP_code.ACTIVES.items(), key=operator.itemgetter(1)))

        return self.OPEN_TIME

    def get_binary_option_detail(self):
        detail = nested_dict(2, dict)
        init_info = self.get_all_init()
        for actives in init_info["result"]["turbo"]["actives"]:
            name = init_info["result"]["turbo"]["actives"][actives]["name"]
            name = name[name.index(".") + 1:len(name)]
            detail[name]["turbo"] = init_info["result"]["turbo"]["actives"][actives]

        for actives in init_info["result"]["binary"]["actives"]:
            name = init_info["result"]["binary"]["actives"][actives]["name"]
            name = name[name.index(".") + 1:len(name)]
            detail[name]["binary"] = init_info["result"]["binary"]["actives"][actives]
        return detail

    def get_all_profit(self):
        all_profit = nested_dict(2, dict)
        init_info = self.get_all_init()
        for actives in init_info["result"]["turbo"]["actives"]:
            name = init_info["result"]["turbo"]["actives"][actives]["name"]
            name = name[name.index(".") + 1:len(name)]
            all_profit[name]["turbo"] = (
                100.0 - init_info["result"]["turbo"]["actives"][actives]["option"]["profit"]["commission"]
            ) / 100.0

        for actives in init_info["result"]["binary"]["actives"]:
            name = init_info["result"]["binary"]["actives"][actives]["name"]
            name = name[name.index(".") + 1:len(name)]
            all_profit[name]["binary"] = (
                100.0 - init_info["result"]["binary"]["actives"][actives]["option"]["profit"]["commission"]
            ) / 100.0
        return all_profit


    def get_currency(self):
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["currency"]

    def get_balance_id(self):
        return global_value.balance_id

    def get_balance(self):
        balances_raw = self.get_balances()
        for balance in balances_raw["msg"]:
            if balance["id"] == global_value.balance_id:
                return balance["amount"]

    def get_balances(self):
        self.api.balances_raw = None
        self.api.get_balances()
        while self.api.balances_raw is None:
            pass
        return self.api.balances_raw

    def get_balance_mode(self):
        profile = self.get_profile_ansyc()
        for balance in profile.get("balances", []):
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
        instrument_type = ["cfd", "forex", "crypto", "blitz-option",
                           "digital-option", "turbo-option", "binary-option"]
        for ins in instrument_type:
            self.api.portfolio(Main_Name=Main_Name, name="portfolio.position-changed",
                               instrument_type=ins, user_balance_id=user_balance_id)

    def order_changed_all(self, Main_Name):
        instrument_type = ["cfd", "forex", "crypto", "blitz-option",
                           "digital-option", "turbo-option", "binary-option"]
        for ins in instrument_type:
            self.api.portfolio(Main_Name=Main_Name, name="portfolio.order-changed", instrument_type=ins)

    def change_balance(self, Balance_MODE):
        def set_id(b_id):
            if global_value.balance_id is not None:
                self.position_change_all("unsubscribeMessage", global_value.balance_id)
            global_value.balance_id = b_id
            self.position_change_all("subscribeMessage", b_id)

        real_id = None
        practice_id = None
        tournament_id = None

        for balance in self.get_profile_ansyc().get("balances", []):
            if balance["type"] == 1:
                real_id = balance["id"]
            if balance["type"] == 4:
                practice_id = balance["id"]
            if balance["type"] == 2:
                tournament_id = balance["id"]

        if Balance_MODE == "REAL":
            set_id(real_id)
        elif Balance_MODE == "PRACTICE":
            set_id(practice_id)
        elif Balance_MODE == "TOURNAMENT":
            set_id(tournament_id)
        else:
            logging.error("ERROR doesn't have this mode")
            raise SystemExit(1)

    def get_candles(self, ACTIVES, interval, count, endtime):
        request_id = ''
        if ACTIVES not in OP_code.ACTIVES:
            print('Asset {} not found in constants'.format(ACTIVES))
            return None

        while True:
            try:
                request_id = self.api.getcandles(OP_code.ACTIVES[ACTIVES], interval, count, endtime)
                # Adiciona um pequeno atraso para evitar busy-waiting
                start_time = time.time()
                while self.check_connect() and request_id not in self.api.candles:
                    if time.time() - start_time > 10:  # Tempo limite de 10 segundos
                        self.connect()
                        break
                    time.sleep(0.1)
                if request_id in self.api.candles:
                    break
            except TimeoutError as te:
                logging.error(te)
                self.connect()
            except Exception as e:
                logging.error('**error** get_candles necessário reconectar: {}'.format(e))
                self.connect()
            time.sleep(0.1)
        return self.api.candles.pop(request_id).candles_data

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
            try:
                return self.api.real_time_candles[ACTIVE]
            except:
                logging.error('**error** get_realtime_candles() size="all" can not get candle')
                return False
        elif size in self.size:
            try:
                return self.api.real_time_candles[ACTIVE][size]
            except:
                logging.error('**error** get_realtime_candles() size=' + str(size) + ' can not get candle')
                return False
        else:
            logging.error('**error** get_realtime_candles() please input right "size"')

    def get_all_realtime_candles(self):
        return self.api.real_time_candles

    def full_realtime_get_candle(self, ACTIVE, size, maxdict):
        candles = self.get_candles(ACTIVE, size, maxdict, self.api.timesync.server_timestamp)
        for can in candles:
            self.api.real_time_candles[str(ACTIVE)][int(size)][can["from"]] = can

    def start_candles_one_stream(self, ACTIVE, size):
        if (str(ACTIVE + "," + str(size)) not in self.subscribe_candle):
            self.subscribe_candle.append((ACTIVE + "," + str(size)))
        start = time.time()
        self.api.candle_generated_check[str(ACTIVE)][int(size)] = {}
        while True:
            if time.time() - start > 20:
                logging.error('**error** start_candles_one_stream late for 20 sec')
                return False
            try:
                if self.api.candle_generated_check[str(ACTIVE)][int(size)] is True:
                    return True
            except:
                pass
            try:
                self.api.subscribe(OP_code.ACTIVES[ACTIVE], size)
            except:
                logging.error('**error** start_candles_stream reconnect')
                self.connect()
            time.sleep(1)

    def stop_candles_one_stream(self, ACTIVE, size):
        if (ACTIVE + "," + str(size)) in self.subscribe_candle:
            self.subscribe_candle.remove(ACTIVE + "," + str(size))
        while True:
            try:
                if self.api.candle_generated_check[str(ACTIVE)][int(size)] == {}:
                    return True
            except:
                pass
            self.api.candle_generated_check[str(ACTIVE)][int(size)] = {}
            self.api.unsubscribe(OP_code.ACTIVES[ACTIVE], size)
            time.sleep(self.suspend * 10)

    def start_candles_all_size_stream(self, ACTIVE):
        self.api.candle_generated_all_size_check[str(ACTIVE)] = {}
        if (str(ACTIVE) not in self.subscribe_candle_all_size):
            self.subscribe_candle_all_size.append(str(ACTIVE))
        start = time.time()
        while True:
            if time.time() - start > 20:
                logging.error('**error** fail ' + ACTIVE + ' start_candles_all_size_stream late for 10 sec')
                return False
            try:
                if self.api.candle_generated_all_size_check[str(ACTIVE)] is True:
                    return True
            except:
                pass
            try:
                self.api.subscribe_all_size(OP_code.ACTIVES[ACTIVE])
            except:
                logging.error('**error** start_candles_all_size_stream reconnect')
                self.connect()
            time.sleep(1)

    def stop_candles_all_size_stream(self, ACTIVE):
        if str(ACTIVE) in self.subscribe_candle_all_size:
            self.subscribe_candle_all_size.remove(str(ACTIVE))
        while True:
            try:
                if self.api.candle_generated_all_size_check[str(ACTIVE)] == {}:
                    break
            except:
                pass
            self.api.candle_generated_all_size_check[str(ACTIVE)] = {}
            self.api.unsubscribe_all_size(OP_code.ACTIVES[ACTIVE])
            time.sleep(self.suspend * 10)

    def subscribe_top_assets_updated(self, instrument_type):
        self.api.Subscribe_Top_Assets_Updated(instrument_type)

    def unsubscribe_top_assets_updated(self, instrument_type):
        self.api.Unsubscribe_Top_Assets_Updated(instrument_type)

    def get_top_assets_updated(self, instrument_type):
        if instrument_type in self.api.top_assets_updated_data:
            return self.api.top_assets_updated_data[instrument_type]
        else:
            return None

    def subscribe_commission_changed(self, instrument_type):
        self.api.Subscribe_Commission_Changed(instrument_type)

    def unsubscribe_commission_changed(self, instrument_type):
        self.api.Unsubscribe_Commission_Changed(instrument_type)

    def get_commission_change(self, instrument_type):
        return self.api.subscribe_commission_changed_data[instrument_type]

    def start_mood_stream(self, ACTIVES, instrument="turbo-option"):
        if ACTIVES not in self.subscribe_mood:
            self.subscribe_mood.append(ACTIVES)

        while True:
            self.api.subscribe_Traders_mood(OP_code.ACTIVES[ACTIVES], instrument)
            try:
                _ = self.api.traders_mood[OP_code.ACTIVES[ACTIVES]]
                break
            except:
                time.sleep(5)

    def stop_mood_stream(self, ACTIVES, instrument="turbo-option"):
        if ACTIVES in self.subscribe_mood:
            self.subscribe_mood.remove(ACTIVES)
        self.api.unsubscribe_Traders_mood(OP_code.ACTIVES[ACTIVES], instrument)

    def get_traders_mood(self, ACTIVES):
        return self.api.traders_mood[OP_code.ACTIVES[ACTIVES]]

    def get_all_traders_mood(self):
        return self.api.traders_mood

    def get_technical_indicators(self, ACTIVES):
        request_id = self.api.get_Technical_indicators(OP_code.ACTIVES[ACTIVES])
        while self.api.technical_indicators.get(request_id) is None:
            pass
        return self.api.technical_indicators[request_id]

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
            except:
                pass
        self.api.listinfodata.delete(id_number)
        return listinfodata_dict["win"]


    def check_win_v2(self, id_number, polling_time):
        while True:
            check, data = self.get_betinfo(id_number)
            win = data["result"]["data"][str(id_number)]["win"]
            if check and win != "":
                try:
                    return data["result"]["data"][str(id_number)]["profit"] - data["result"]["data"][str(id_number)]["deposit"]
                except:
                    pass
            time.sleep(polling_time)

    def check_win_v4(self, id_number):
        while True:
            try:
                if self.api.socket_option_closed[id_number] is not None:
                    break
            except:
                pass
        x = self.api.socket_option_closed[id_number]
        return x['msg']['win'], (0 if x['msg']['win'] == 'equal' else float(x['msg']['sum']) * -1 if x['msg']['win'] == 'loose' else float(x['msg']['win_amount']) - float(x['msg']['sum']))

    def check_win_v3(self, id_number):
        while True:
            result = self.get_optioninfo_v2(10)
            if result['msg']['closed_options'][0]['id'][0] == id_number and result['msg']['closed_options'][0]['id'][0] is not None:
                return result['msg']['closed_options'][0]['win'], (result['msg']['closed_options'][0]['win_amount'] - result['msg']['closed_options'][0]['amount'] if result['msg']['closed_options'][0]['win'] != 'equal' else 0)
            time.sleep(1)

    def get_betinfo(self, id_number):
        while True:
            self.api.game_betinfo.isSuccessful = None
            start = time.time()
            try:
                self.api.get_betinfo(id_number)
            except:
                logging.error('**error** def get_betinfo  self.api.get_betinfo reconnect')
                self.connect()
            while self.api.game_betinfo.isSuccessful is None:
                if time.time() - start > 10:
                    logging.error('**error** get_betinfo time out need reconnect')
                    self.connect()
                    self.api.get_betinfo(id_number)
                    time.sleep(self.suspend * 10)
            if self.api.game_betinfo.isSuccessful is True:
                return self.api.game_betinfo.isSuccessful, self.api.game_betinfo.dict
            else:
                return self.api.game_betinfo.isSuccessful, None
            time.sleep(self.suspend * 10)

    def get_optioninfo(self, limit):
        self.api.api_game_getoptions_result = None
        self.api.get_options(limit)
        while self.api.api_game_getoptions_result is None:
            pass
        return self.api.api_game_getoptions_result

    def get_optioninfo_v2(self, limit):
        self.api.get_options_v2_data = None
        self.api.get_options_v2(limit, "binary,turbo")
        while self.api.get_options_v2_data is None:
            pass
        return self.api.get_options_v2_data

    def buy_multi(self, price, ACTIVES, ACTION, expirations):
        self.api.buy_multi_option = {}
        if len(price) == len(ACTIVES) == len(ACTION) == len(expirations):
            buy_len = len(price)
            for idx in range(buy_len):
                self.api.buyv3(price[idx], OP_code.ACTIVES[ACTIVES[idx]], ACTION[idx], expirations[idx], idx)
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

    def get_remaining(self, duration):
        for remaining in get_remaning_time(self.api.timesync.server_timestamp):
            if remaining[0] == duration:
                return remaining[1]
        logging.error('get_remaining(self,duration) ERROR duration')
        return "ERROR duration"

    def buy_by_raw_expirations(self, price, active, direction, option, expired):
        self.api.buy_multi_option = {}
        self.api.buy_successful = None
        req_id = "buyraw"
        try:
            self.api.buy_multi_option[req_id]["id"] = None
        except:
            pass
        self.api.buyv3_by_raw_expired(price, OP_code.ACTIVES[active], direction, option, expired, request_id=req_id)
        start_t = time.time()
        id_ = None
        self.api.result = None
        while self.api.result is None or id_ is None:
            try:
                if "message" in self.api.buy_multi_option[req_id].keys():
                    logging.error('**warning** buy' + str(self.api.buy_multi_option[req_id]["message"]))
                    return False, self.api.buy_multi_option[req_id]["message"]
            except:
                pass
            try:
                id_ = self.api.buy_multi_option[req_id]["id"]
            except:
                pass
            if time.time() - start_t >= 5:
                logging.error('**warning** buy late 5 sec')
                return False, None
        return self.api.result, self.api.buy_multi_option[req_id]["id"]

    # Mantida a API canônica original:
    def buy(self, price, ACTIVES, ACTION, expirations):
        self.api.buy_multi_option = {}
        self.api.buy_successful = None
        req_id = str(randint(0, 10000))
        try:
            self.api.buy_multi_option[req_id]["id"] = None
        except:
            pass
        self.api.buyv3(float(price), OP_code.ACTIVES[ACTIVES], str(ACTION), int(expirations), req_id)
        start_t = time.time()
        id_ = None
        self.api.result = None
        while self.api.result is None or id_ is None:
            try:
                if "message" in self.api.buy_multi_option[req_id].keys():
                    return False, self.api.buy_multi_option[req_id]["message"]
            except:
                pass
            try:
                id_ = self.api.buy_multi_option[req_id]["id"]
            except:
                pass
            if time.time() - start_t >= 5:
                logging.error('**warning** buy late 5 sec')
                return False, None
        return self.api.result, self.api.buy_multi_option[req_id]["id"]

    def sell_option(self, options_ids):
        self.api.sell_option(options_ids)
        self.api.sold_options_respond = None
        while self.api.sold_options_respond is None:
            pass
        return self.api.sold_options_respond

    def sell_digital_option(self, options_ids):
        self.api.sell_digital_option(options_ids)
        self.api.sold_digital_options_respond = None
        while self.api.sold_digital_options_respond is None:
            pass
        return self.api.sold_digital_options_respond

    def sell_blitz_option(self, options_ids):
        self.api.sell_blitz_option(options_ids)
        self.api.sold_blitz_options_respond = None
        while self.api.sold_blitz_options_respond is None:
            pass
        return self.api.sold_blitz_options_respond

    def get_digital_underlying_list_data(self):
        self.api.underlying_list_data = None
        self.api.get_digital_underlying()
        start_t = time.time()
        while self.api.underlying_list_data is None:
            if time.time() - start_t >= 30:
                logging.error('**warning** get_digital_underlying_list_data late 30 sec')
                return None
        return self.api.underlying_list_data

    def get_blitz_underlying_list_data(self):
        self.api.underlying_list_data = None
        self.api.get_blitz_underlying()
        start_t = time.time()
        while self.api.underlying_list_data is None:
            if time.time() - start_t >= 30:
                logging.error('**warning** get_blitz_underlying_list_data late 30 sec')
                return None
        return self.api.underlying_list_data

    def get_strike_list(self, ACTIVES, duration):
        self.api.strike_list = None
        self.api.get_strike_list(ACTIVES, duration)
        ans = {}
        while self.api.strike_list is None:
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

    def subscribe_strike_list(self, ACTIVE, expiration_period):
        self.api.subscribe_instrument_quites_generated(ACTIVE, expiration_period)

    def unsubscribe_strike_list(self, ACTIVE, expiration_period):
        del self.api.instrument_quites_generated_data[ACTIVE]
        self.api.unsubscribe_instrument_quites_generated(ACTIVE, expiration_period)

    def get_instrument_quites_generated_data(self, ACTIVE, duration):
        while self.api.instrument_quotes_generated_raw_data[ACTIVE][duration * 60] == {}:
            pass
        return self.api.instrument_quotes_generated_raw_data[ACTIVE][duration * 60]

    def get_realtime_strike_list(self, ACTIVE, duration):
        while True:
            if not self.api.instrument_quites_generated_data[ACTIVE][duration * 60]:
                pass
            else:
                break
        ans = {}
        now_timestamp = self.api.instrument_quites_generated_timestamp[ACTIVE][duration * 60]

        while ans == {}:
            if self.get_realtime_strike_list_temp_data == {} or now_timestamp != self.get_realtime_strike_list_temp_expiration:
                raw_data, strike_list = self.get_strike_list(ACTIVE, duration)
                self.get_realtime_strike_list_temp_expiration = raw_data["msg"]["expiration"]
                self.get_realtime_strike_list_temp_data = strike_list
            else:
                strike_list = self.get_realtime_strike_list_temp_data

            profit = self.api.instrument_quites_generated_data[ACTIVE][duration * 60]
            for price_key in strike_list:
                try:
                    side_data = {}
                    for side_key in strike_list[price_key]:
                        detail_data = {}
                        profit_d = profit[strike_list[price_key][side_key]]
                        detail_data["profit"] = profit_d
                        detail_data["id"] = strike_list[price_key][side_key]
                        side_data[side_key] = detail_data
                    ans[price_key] = side_data
                except:
                    pass
        return ans

    def get_digital_current_profit(self, ACTIVE, duration):
        profit = self.api.instrument_quites_generated_data[ACTIVE][duration * 60]
        for key in profit:
            if key.find("SPT") != -1:
                return profit[key]
        return False

    def get_blitz_current_profit(self, ACTIVE, duration):
        profit = self.api.instrument_quites_generated_data[ACTIVE][duration * 60]
        for key in profit:
            if key.find("SPT") != -1:
                return profit[key]
        return False

    def buy_digital_spot(self, active, amount, action, duration):
        action = action.lower()
        if action == 'put':
            action = 'P'
        elif action == 'call':
            action = 'C'
        else:
            logging.error('buy_digital_spot active error')
            return -1, None
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

        dateFormated = str(datetime.utcfromtimestamp(exp).strftime("%Y%m%d%H%M"))
        instrument_id = "do" + active + dateFormated + "PT" + str(duration) + "M" + action + "SPT"
        request_id = self.api.place_digital_option(instrument_id, amount)

        while self.api.digital_option_placed_id.get(request_id) is None:
            pass
        digital_order_id = self.api.digital_option_placed_id.get(request_id)
        if isinstance(digital_order_id, int):
            return True, digital_order_id
        else:
            return False, digital_order_id

    def buy_blitz_spot(self, active, amount, action, duration):
        action = action.lower()
        if action == 'put':
            action = 'P'
        elif action == 'call':
            action = 'C'
        else:
            logging.error('buy_blitz_spot active error')
            return -1, None

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

        dateFormated = str(datetime.utcfromtimestamp(exp).strftime("%Y%m%d%H%M"))
        instrument_id = "do" + active + dateFormated + "PT" + str(duration) + "M" + action + "SPT"
        request_id = self.api.place_blitz_option(instrument_id, amount)

        while self.api.blitz_option_placed_id.get(request_id) is None:
            pass
        blitz_order_id = self.api.blitz_option_placed_id.get(request_id)
        if isinstance(blitz_order_id, int):
            return True, blitz_order_id
        else:
            return False, blitz_order_id

    # Removida a versão incompleta/duplicada de get_digital_spot_profit_after_sale (aqui fica a boa)
    def get_digital_spot_profit_after_sale(self, position_id):
        def get_instrument_id_to_bid(data, instrument_id):
            for row in data["msg"]["quotes"]:
                if row["symbols"][0] == instrument_id:
                    return row["price"]["bid"]
            return None

        while self.get_async_order(position_id)["position-changed"] == {}:
            pass

        position = self.get_async_order(position_id)["position-changed"]["msg"]
        if position["instrument_id"].find("MPSPT"):
            z = False
        elif position["instrument_id"].find("MCSPT"):
            z = True
        else:
            logging.error('get_digital_spot_profit_after_sale position error' + str(position["instrument_id"]))
            return None

        ACTIVES = position['raw_event']['instrument_underlying']
        amount = max(position['raw_event']["buy_amount"], position['raw_event']["sell_amount"])
        start_duration = position["instrument_id"].find("PT") + 2
        end_duration = start_duration + position["instrument_id"][start_duration:].find("M")
        duration = int(position["instrument_id"][start_duration:end_duration])
        z2 = False

        getAbsCount = position['raw_event']["count"]
        instrumentStrikeValue = position['raw_event']["instrument_strike_value"] / 1000000.0
        spotLowerInstrumentStrike = position['raw_event']["extra_data"]["lower_instrument_strike"] / 1000000.0
        spotUpperInstrumentStrike = position['raw_event']["extra_data"]["upper_instrument_strike"] / 1000000.0

        aVar = position['raw_event']["extra_data"]["lower_instrument_id"]
        aVar2 = position['raw_event']["extra_data"]["upper_instrument_id"]
        getRate = position['raw_event']["currency_rate"]

        instrument_quites_generated_data = self.get_instrument_quites_generated_data(ACTIVES, duration)

        f_tmp = get_instrument_id_to_bid(instrument_quites_generated_data, aVar)
        if f_tmp is not None:
            self.get_digital_spot_profit_after_sale_data[position_id]["f"] = f_tmp
            f = f_tmp
        else:
            f = self.get_digital_spot_profit_after_sale_data[position_id]["f"]

        f2_tmp = get_instrument_id_to_bid(instrument_quites_generated_data, aVar2)
        if f2_tmp is not None:
            self.get_digital_spot_profit_after_sale_data[position_id]["f2"] = f2_tmp
            f2 = f2_tmp
        else:
            f2 = self.get_digital_spot_profit_after_sale_data[position_id]["f2"]

        if (spotLowerInstrumentStrike != instrumentStrikeValue) and f is not None and f2 is not None:
            if (spotLowerInstrumentStrike > instrumentStrikeValue or instrumentStrikeValue > spotUpperInstrumentStrike):
                if z:
                    instrumentStrikeValue = (spotUpperInstrumentStrike - instrumentStrikeValue) / abs(spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                    f = abs(f2 - f)
                else:
                    instrumentStrikeValue = (instrumentStrikeValue - spotUpperInstrumentStrike) / abs(spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                    f = abs(f2 - f)
            elif z:
                f += ((instrumentStrikeValue - spotLowerInstrumentStrike) / (spotUpperInstrumentStrike - spotLowerInstrumentStrike)) * (f2 - f)
            else:
                instrumentStrikeValue = (spotUpperInstrumentStrike - instrumentStrikeValue) / (spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                f -= f2
            f = f2 + (instrumentStrikeValue * f)

        if z2:
            pass
        if f is not None:
            price = (f / getRate)
            return price * getAbsCount - amount
        else:
            return None

    def get_blitz_spot_profit_after_sale(self, position_id):
        def get_instrument_id_to_bid(data, instrument_id):
            for row in data["msg"]["quotes"]:
                if row["symbols"][0] == instrument_id:
                    return row["price"]["bid"]
            return None

        while self.get_async_order(position_id)["position-changed"] == {}:
            pass

        position = self.get_async_order(position_id)["position-changed"]["msg"]
        if position["instrument_id"].find("MPSPT"):
            z = False
        elif position["instrument_id"].find("MCSPT"):
            z = True
        else:
            logging.error('get_digital_spot_profit_after_sale position error' + str(position["instrument_id"]))
            return None

        ACTIVES = position['raw_event']['instrument_underlying']
        amount = max(position['raw_event']["buy_amount"], position['raw_event']["sell_amount"])
        start_duration = position["instrument_id"].find("PT") + 2
        end_duration = start_duration + position["instrument_id"][start_duration:].find("M")
        duration = int(position["instrument_id"][start_duration:end_duration])
        z2 = False

        getAbsCount = position['raw_event']["count"]
        instrumentStrikeValue = position['raw_event']["instrument_strike_value"] / 1000000.0
        spotLowerInstrumentStrike = position['raw_event']["extra_data"]["lower_instrument_strike"] / 1000000.0
        spotUpperInstrumentStrike = position['raw_event']["extra_data"]["upper_instrument_strike"] / 1000000.0

        aVar = position['raw_event']["extra_data"]["lower_instrument_id"]
        aVar2 = position['raw_event']["extra_data"]["upper_instrument_id"]
        getRate = position['raw_event']["currency_rate"]

        instrument_quites_generated_data = self.get_instrument_quites_generated_data(ACTIVES, duration)

        f_tmp = get_instrument_id_to_bid(instrument_quites_generated_data, aVar)
        if f_tmp is not None:
            self.get_digital_spot_profit_after_sale_data[position_id]["f"] = f_tmp
            f = f_tmp
        else:
            f = self.get_digital_spot_profit_after_sale_data[position_id]["f"]

        f2_tmp = get_instrument_id_to_bid(instrument_quites_generated_data, aVar2)
        if f2_tmp is not None:
            self.get_digital_spot_profit_after_sale_data[position_id]["f2"] = f2_tmp
            f2 = f2_tmp
        else:
            f2 = self.get_digital_spot_profit_after_sale_data[position_id]["f2"]

        if (spotLowerInstrumentStrike != instrumentStrikeValue) and f is not None and f2 is not None:
            if (spotLowerInstrumentStrike > instrumentStrikeValue or instrumentStrikeValue > spotUpperInstrumentStrike):
                if z:
                    instrumentStrikeValue = (spotUpperInstrumentStrike - instrumentStrikeValue) / abs(spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                    f = abs(f2 - f)
                else:
                    instrumentStrikeValue = (instrumentStrikeValue - spotUpperInstrumentStrike) / abs(spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                    f = abs(f2 - f)
            elif z:
                f += ((instrumentStrikeValue - spotLowerInstrumentStrike) / (spotUpperInstrumentStrike - spotLowerInstrumentStrike)) * (f2 - f)
            else:
                instrumentStrikeValue = (spotUpperInstrumentStrike - instrumentStrikeValue) / (spotUpperInstrumentStrike - spotLowerInstrumentStrike)
                f -= f2
            f = f2 + (instrumentStrikeValue * f)

        if z2:
            pass
        if f is not None:
            price = (f / getRate)
            return price * getAbsCount - amount
        else:
            return None


    def buy_digital(self, amount, instrument_id):
        self.api.digital_option_placed_id = None
        self.api.place_digital_option(instrument_id, amount)
        start_t = time.time()
        while self.api.digital_option_placed_id is None:
            if time.time() - start_t > 30:
                logging.error('buy_digital loss digital_option_placed_id')
                return False, None
        return True, self.api.digital_option_placed_id

    def close_digital_option(self, position_id):
        self.api.result = None
        while self.get_async_order(position_id)["position-changed"] == {}:
            pass
        position_changed = self.get_async_order(position_id)["position-changed"]["msg"]
        self.api.close_digital_option(position_changed["external_id"])
        while self.api.result is None:
            pass
        return self.api.result

    def check_win_digital(self, buy_order_id, polling_time):
        while True:
            time.sleep(polling_time)
            data = self.get_digital_position(buy_order_id)
            if data["msg"]["position"]["status"] == "closed":
                if data["msg"]["position"]["close_reason"] == "default":
                    return data["msg"]["position"]["pnl_realized"]
                elif data["msg"]["position"]["close_reason"] == "expired":
                    return data["msg"]["position"]["pnl_realized"] - data["msg"]["position"]["buy_amount"]

    def check_win_digital_v2(self, buy_order_id):
        while self.get_async_order(buy_order_id)["position-changed"] == {}:
            pass
        order_data = self.get_async_order(buy_order_id)["position-changed"]["msg"]
        if order_data is not None:
            if order_data["status"] == "closed":
                if order_data["close_reason"] == "expired":
                    return True, order_data["close_profit"] - order_data["invest"]
                elif order_data["close_reason"] == "default":
                    return True, order_data["pnl_realized"]
            else:
                return False, None
        else:
            return False, None

    def buy_blitz(self, amount, instrument_id):
        self.api.blitz_option_placed_id = None
        self.api.place_blitz_option(instrument_id, amount)
        start_t = time.time()
        while self.api.blitz_option_placed_id is None:
            if time.time() - start_t > 30:
                logging.error('buy_blitz loss blitz_option_placed_id')
                return False, None
        return True, self.api.blitz_option_placed_id

    def close_blitz_option(self, position_id):
        self.api.result = None
        while self.get_async_order(position_id)["position-changed"] == {}:
            pass
        position_changed = self.get_async_order(position_id)["position-changed"]["msg"]
        self.api.close_blitz_option(position_changed["external_id"])
        while self.api.result is None:
            pass
        return self.api.result

    def check_win_blitz(self, buy_order_id, polling_time):
        while True:
            time.sleep(polling_time)
            data = self.get_blitz_position(buy_order_id)
            if data["msg"]["position"]["status"] == "closed":
                if data["msg"]["position"]["close_reason"] == "default":
                    return data["msg"]["position"]["pnl_realized"]
                elif data["msg"]["position"]["close_reason"] == "expired":
                    return data["msg"]["position"]["pnl_realized"] - data["msg"]["position"]["buy_amount"]

    def check_win_blitz_v2(self, buy_order_id):
        while self.get_async_order(buy_order_id)["position-changed"] == {}:
            pass
        order_data = self.get_async_order(buy_order_id)["position-changed"]["msg"]
        if order_data is not None:
            if order_data["status"] == "closed":
                if order_data["close_reason"] == "expired":
                    return True, order_data["close_profit"] - order_data["invest"]
                elif order_data["close_reason"] == "default":
                    return True, order_data["pnl_realized"]
            else:
                return False, None
        else:
            return False, None

    def buy_order(self, instrument_type, instrument_id, side, amount, leverage,
                  type, limit_price=None, stop_price=None,
                  stop_lose_kind=None, stop_lose_value=None,
                  take_profit_kind=None, take_profit_value=None,
                  use_trail_stop=False, auto_margin_call=False, use_token_for_commission=False):
        self.api.buy_order_id = None
        self.api.buy_order(
            instrument_type=instrument_type, instrument_id=instrument_id,
            side=side, amount=amount, leverage=leverage,
            type=type, limit_price=limit_price, stop_price=stop_price,
            stop_lose_value=stop_lose_value, stop_lose_kind=stop_lose_kind,
            take_profit_value=take_profit_value, take_profit_kind=take_profit_kind,
            use_trail_stop=use_trail_stop, auto_margin_call=auto_margin_call,
            use_token_for_commission=use_token_for_commission
        )
        while self.api.buy_order_id is None:
            pass
        check, data = self.get_order(self.api.buy_order_id)
        while data["status"] == "pending_new":
            check, data = self.get_order(self.api.buy_order_id)
            time.sleep(1)

        if check:
            if data["status"] != "rejected":
                return True, self.api.buy_order_id
            else:
                return False, data["reject_status"]
        else:
            return False, None

    def change_auto_margin_call(self, ID_Name, ID, auto_margin_call):
        self.api.auto_margin_call_changed_respond = None
        self.api.change_auto_margin_call(ID_Name, ID, auto_margin_call)
        while self.api.auto_margin_call_changed_respond is None:
            pass
        if self.api.auto_margin_call_changed_respond["status"] == 2000:
            return True, self.api.auto_margin_call_changed_respond
        else:
            return False, self.api.auto_margin_call_changed_respond

    def change_order(self, ID_Name, order_id,
                     stop_lose_kind, stop_lose_value,
                     take_profit_kind, take_profit_value,
                     use_trail_stop, auto_margin_call):
        check = True
        if ID_Name == "position_id":
            check, order_data = self.get_order(order_id)
            position_id = order_data["position_id"]
            ID = position_id
        elif ID_Name == "order_id":
            ID = order_id
        else:
            logging.error('change_order input error ID_Name')
            return False, None

        if check:
            self.api.tpsl_changed_respond = None
            self.api.change_order(
                ID_Name=ID_Name, ID=ID,
                stop_lose_kind=stop_lose_kind, stop_lose_value=stop_lose_value,
                take_profit_kind=take_profit_kind, take_profit_value=take_profit_value,
                use_trail_stop=use_trail_stop)
            self.change_auto_margin_call(ID_Name=ID_Name, ID=ID, auto_margin_call=auto_margin_call)
            while self.api.tpsl_changed_respond is None:
                pass
            if self.api.tpsl_changed_respond["status"] == 2000:
                return True, self.api.tpsl_changed_respond["msg"]
            else:
                return False, self.api.tpsl_changed_respond
        else:
            logging.error('change_order fail to get position_id')
            return False, None

    def get_async_order(self, buy_order_id):
        return self.api.order_async[buy_order_id]

    def get_order(self, buy_order_id):
        self.api.order_data = None
        self.api.get_order(buy_order_id)
        while self.api.order_data is None:
            pass
        if self.api.order_data["status"] == 2000:
            return True, self.api.order_data["msg"]
        else:
            return False, None

    def get_pending(self, instrument_type):
        self.api.deferred_orders = None
        self.api.get_pending(instrument_type)
        while self.api.deferred_orders is None:
            pass
        if self.api.deferred_orders["status"] == 2000:
            return True, self.api.deferred_orders["msg"]
        else:
            return False, None

    def get_positions(self, instrument_type):
        self.api.positions = None
        self.api.get_positions(instrument_type)
        while self.api.positions is None:
            pass
        if self.api.positions["status"] == 2000:
            return True, self.api.positions["msg"]
        else:
            return False, None

    def get_position(self, buy_order_id):
        self.api.position = None
        check, order_data = self.get_order(buy_order_id)
        position_id = order_data["position_id"]
        self.api.get_position(position_id)
        while self.api.position is None:
            pass
        if self.api.position["status"] == 2000:
            return True, self.api.position["msg"]
        else:
            return False, None

    def get_digital_position_by_position_id(self, position_id):
        self.api.position = None
        self.api.get_digital_position(position_id)
        while self.api.position is None:
            pass
        return self.api.position

    def get_digital_position(self, order_id):
        self.api.position = None
        while self.get_async_order(order_id)["position-changed"] == {}:
            pass
        position_id = self.get_async_order(order_id)["position-changed"]["msg"]["external_id"]
        self.api.get_digital_position(position_id)
        while self.api.position is None:
            pass
        return self.api.position

    def get_blitz_position_by_position_id(self, position_id):
        self.api.position = None
        self.api.get_blitz_position(position_id)
        while self.api.position is None:
            pass
        return self.api.position

    def get_blitz_position(self, order_id):
        self.api.position = None
        while self.get_async_order(order_id)["position-changed"] == {}:
            pass
        position_id = self.get_async_order(order_id)["position-changed"]["msg"]["external_id"]
        self.api.get_blitz_position(position_id)
        while self.api.position is None:
            pass
        return self.api.position

    def get_position_history(self, instrument_type):
        self.api.position_history = None
        self.api.get_position_history(instrument_type)
        while self.api.position_history is None:
            pass
        if self.api.position_history["status"] == 2000:
            return True, self.api.position_history["msg"]
        else:
            return False, None

    def get_position_history_v2(self, instrument_type, limit, offset, start, end):
        self.api.position_history_v2 = None
        self.api.get_position_history_v2(instrument_type, limit, offset, start, end)
        while self.api.position_history_v2 is None:
            pass
        if self.api.position_history_v2["status"] == 2000:
            return True, self.api.position_history_v2["msg"]
        else:
            return False, None

    def get_available_leverages(self, instrument_type, actives=""):
        self.api.available_leverages = None
        if actives == "":
            self.api.get_available_leverages(instrument_type, "")
        else:
            self.api.get_available_leverages(instrument_type, OP_code.ACTIVES[actives])
        while self.api.available_leverages is None:
            pass
        if self.api.available_leverages["status"] == 2000:
            return True, self.api.available_leverages["msg"]
        else:
            return False, None

    def cancel_order(self, buy_order_id):
        self.api.order_canceled = None
        self.api.cancel_order(buy_order_id)
        while self.api.order_canceled is None:
            pass
        if self.api.order_canceled["status"] == 2000:
            return True
        else:
            return False

    def close_position(self, position_id):
        check, data = self.get_order(position_id)
        if data["position_id"] is not None:
            self.api.close_position_data = None
            self.api.close_position(data["position_id"])
            while self.api.close_position_data is None:
                pass
            if self.api.close_position_data["status"] == 2000:
                return True
            else:
                return False
        else:
            return False

    def close_position_v2(self, position_id):
        while self.get_async_order(position_id) is None:
            pass
        position_changed = self.get_async_order(position_id)
        self.api.close_position(position_changed["id"])
        while self.api.close_position_data is None:
            pass
        if self.api.close_position_data["status"] == 2000:
            return True
        else:
            return False

    def get_overnight_fee(self, instrument_type, active):
        self.api.overnight_fee = None
        self.api.get_overnight_fee(instrument_type, OP_code.ACTIVES[active])
        while self.api.overnight_fee is None:
            pass
        if self.api.overnight_fee["status"] == 2000:
            return True, self.api.overnight_fee["msg"]
        else:
            return False, None

    def get_option_open_by_other_pc(self):
        return self.api.socket_option_opened

    def del_option_open_by_other_pc(self, id_):
        del self.api.socket_option_opened[id_]

    def opcode_to_name(self, opcode):
        return list(OP_code.ACTIVES.keys())[list(OP_code.ACTIVES.values()).index(opcode)]

    def subscribe_live_deal(self, name, active, _type, buffersize):
        active_id = OP_code.ACTIVES[active]
        self.api.Subscribe_Live_Deal(name, active_id, _type)

    def unscribe_live_deal(self, name, active, _type):
        active_id = OP_code.ACTIVES[active]
        self.api.Unscribe_Live_Deal(name, active_id, _type)

    def set_blitz_live_deal_cb(self, cb):
        self.api.blitz_live_deal_cb = cb

    def set_digital_live_deal_cb(self, cb):
        self.api.digital_live_deal_cb = cb

    def set_binary_live_deal_cb(self, cb):
        self.api.binary_live_deal_cb = cb

    def get_live_deal(self, name, active, _type):
        return self.api.live_deal_data[name][active][_type]

    def pop_live_deal(self, name, active, _type):
        return self.api.live_deal_data[name][active][_type].pop()

    def clear_live_deal(self, name, active, _type, buffersize):
        self.api.live_deal_data[name][active][_type] = deque(list(), buffersize)


    def buy_digital_spot_v2(self, active, amount, action, duration):
        action = action.lower()
        if action == 'put':
            action = 'P'
        elif action == 'call':
            action = 'C'
        else:
            logging.error('buy_digital_spot_v2 active error')
            return -1, None

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
        active_id = str(OP_code.ACTIVES[active])
        instrument_id = "do" + active_id + "A" + date_formated[:8] + "D" + date_formated[8:] + "00T" + str(duration) + "M" + action + "SPT"
        logger = logging.getLogger(__name__)
        logger.info(instrument_id)
        request_id = self.api.place_digital_option_v2(instrument_id, active_id, amount)

        while self.api.digital_option_placed_id.get(request_id) is None:
            pass
        digital_order_id = self.api.digital_option_placed_id.get(request_id)
        if isinstance(digital_order_id, int):
            return True, digital_order_id
        else:
            return False, digital_order_id

    def buy_blitz_spot_v2(self, active, amount, action, duration):
        action = action.lower()
        if action == 'put':
            action = 'P'
        elif action == 'call':
            action = 'C'
        else:
            logging.error('buy_blitz_spot_v2 active error')
            return -1, None

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
        active_id = str(OP_code.ACTIVES[active])
        instrument_id = "do" + active_id + "A" + date_formated[:8] + "D" + date_formated[8:] + "00T" + str(duration) + "M" + action + "SPT"
        logger = logging.getLogger(__name__)
        logger.info(instrument_id)
        request_id = self.api.place_blitz_option_v2(instrument_id, active_id, amount)

        while self.api.blitz_option_placed_id.get(request_id) is None:
            pass
        blitz_order_id = self.api.blitz_option_placed_id.get(request_id)
        if isinstance(blitz_order_id, int):
            return True, blitz_order_id
        else:
            return False, blitz_order_id

    def get_digital_payout(self, par):
        asset_id = OP_code.ACTIVES[par]
        t = time.time()
        try:
            if t - int(self.api.payouts_digital[asset_id]['hora']) <= 300:
                return self.api.payouts_digital[asset_id]['pay']
        except:
            pass

        self.api.payouts_digital[asset_id] = None
        data = {
            "name": "price-splitter.client-price-generated",
            "version": "1.0",
            "params": {
                "routingFilters": {
                    "instrument_type": "digital-option",
                    "asset_id": str(asset_id)
                }
            }
        }
        self.api.send_websocket_request(name="subscribeMessage", msg=data)

        start = time.time()
        while self.api.payouts_digital[asset_id] is None:
            if int(time.time() - start) > 10:
                name = "unsubscribeMessage"
                data = {
                    "name": "price-splitter.client-price-generated",
                    "version": "1.0",
                    "params": {
                        "routingFilters": {
                            "instrument_type": "digital-option",
                            "asset_id": int(asset_id)
                        }
                    }
                }
                self.api.send_websocket_request(name, msg=data)
                return 0

        name = "unsubscribeMessage"
        data = {
            "name": "price-splitter.client-price-generated",
            "version": "1.0",
            "params": {
                "routingFilters": {
                    "instrument_type": "digital-option",
                    "asset_id": int(asset_id)
                }
            }
        }
        self.api.send_websocket_request(name, msg=data)
        return self.api.payouts_digital[asset_id]['pay']

    def logout(self):
        self.api.logout()

    # --- Alertas ---
    def start_subscribe_alerts(self):
        name = "subscribeMessage"
        data = {"name": "alert-triggered"}
        self.api.send_websocket_request(name, data)

    def criar_alerta(self, active, instrument_type, value):
        self.api.alerta = None
        asset_id = OP_code.ACTIVES[active]
        name = "sendMessage"
        data = {
            "name": "create-alert",
            "version": "1.0",
            "body": {
                "asset_id": int(asset_id),
                "instrument_type": instrument_type,
                "type": "price",
                "value": value,
                "activations": 1
            }
        }
        self.api.send_websocket_request(name, data)
        while self.api.alerta is None:
            time.sleep(0.01)
            pass
        return self.api.alerta

    def get_alerta(self):
        self.api.alertas = None
        name = "sendMessage"
        data = {
            "name": "get-alerts",
            "version": "1.0",
            "body": {
                "asset_id": 0,
                "type": ""
            }
        }
        self.api.send_websocket_request(name, data)

        while self.api.alertas is None:
            time.sleep(0.01)
            pass

        if self.api.alertas != []:
            for i in self.api.alertas:
                i['par'] = list(OP_code.ACTIVES.keys())[list(OP_code.ACTIVES.values()).index(i['asset_id'])]
        return self.api.alertas

    def delete_alerta(self, id_):
        self.api.alerta = None
        name = "sendMessage"
        data = {
            "name": "delete-alert",
            "version": "1.0",
            "body": {"id": id_}
        }
        self.api.send_websocket_request(name, data)
        while self.api.alerta is None:
            time.sleep(0.01)
            pass
        return self.api.alerta

    def alertas_realtime(self):
        return self.api.alertas_tocados

    def start_candles_stream_v2(self, ativo, size):
        asset_id = OP_code.ACTIVES[ativo]
        name = "subscribeMessage"
        data = {
            "name": "candle-generated",
            "params": {
                "routingFilters": {
                    "active_id": str(asset_id),
                    "size": int(size)
                }
            }
        }
        self.api.send_websocket_request(name, data)

    def get_all_realtime(self):
        return self.api.all_realtime_candles

    # ---------- Forex marginal ----------
    def leverage_marginal_forex(self, par):
        self.api.leverage_forex = None
        name = "sendMessage"
        data = {
            "name": "marginal-forex-instruments.get-underlying-list",
            "version": "1.0",
            "body": {}
        }
        self.api.send_websocket_request(name, data)
        while self.api.leverage_forex is None:
            time.sleep(0.3)
            pass

        leverage = self.api.leverage_forex
        try:
            for i in leverage["msg"]['items']:
                if par in i['name']:
                    leverage = i['max_leverages']['0']
            return leverage
        except:
            return None

    def buy_marginal_forex(self, par, direcao, valor_entrada, preco_entrada, win, lose):
        self.api.buy_forex_id = None
        leverage = self.leverage_marginal_forex(par)
        par_id = OP_code.ACTIVES[par]

        name = "sendMessage"
        data = {
            "name": "marginal-forex.place-stop-order",
            "version": "1.0",
            "body": {
                "side": str(direcao),
                "user_balance_id": int(global_value.balance_id),
                "count": str(valor_entrada),
                "instrument_id": "mf." + str(par_id),
                "instrument_active_id": int(par_id),
                "leverage": str(leverage),
                "stop_price": str(preco_entrada),
                "take_profit": {"type": "price", "value": str(win)},
                "stop_loss": {"type": "price", "value": str(lose)}
            }
        }
        self.api.send_websocket_request(name, data)
        self.api.buy_order_forex(leverage, par_id, direcao, valor_entrada, preco_entrada, win, lose)

        while self.api.buy_forex_id is None:
            time.sleep(0.3)
            pass

        if self.api.buy_forex_id["status"] == 2000:
            return True, self.api.buy_forex_id["msg"]["id"]
        else:
            return False, self.api.buy_forex_id["msg"]

    def buy_forex(self, par, direcao, valor_entrada, multiplicador=None, preco_entrada=None, preco_profit=None, preco_lose=None):
        if direcao == 'call':
            direcao = 'buy'
        if direcao == 'put':
            direcao = 'sell'

        if preco_entrada is None:
            tipo = 'market'
        else:
            tipo = 'limit'

        if preco_lose is None:
            auto_margin = True
        else:
            auto_margin = False

        if multiplicador is None:
            st, msg = self.get_available_leverages("forex", par)
            if st is True:
                multiplicador = msg['leverages'][-1]['regulated_default']
            else:
                multiplicador = 100

        name = "sendMessage"
        data = {
            "name": "place-order-temp",
            "version": "4.0",
            "body": {
                "user_balance_id": int(global_value.balance_id),
                "client_platform_id": 9,
                "instrument_type": "forex",
                "instrument_id": str(par),
                "side": str(direcao),
                "type": str(tipo),
                "amount": float(valor_entrada),
                "leverage": int(multiplicador),
                "limit_price": preco_entrada,
                "stop_price": 0,
                "auto_margin_call": bool(auto_margin),
                "use_trail_stop": "false",
                "take_profit_value": preco_profit,
                "take_profit_kind": "price",
                "stop_lose_value": preco_lose,
                "stop_lose_kind": "price"
            }
        }
        self.api.send_websocket_request(name, data)

        while self.api.buy_order_id is None:
            pass
        check, data = self.get_order(self.api.buy_order_id)
        while data["status"] == "pending_new":
            check, data = self.get_order(self.api.buy_order_id)
            time.sleep(1)

        if check:
            if data["status"] != "rejected":
                return True, self.api.buy_order_id
            else:
                return False, data["reject_status"]
        else:
            return False, None

    def cancel_marginal_forex(self, id_):
        self.api.cancel_order_forex = None
        name = "sendMessage"
        data = {
            "name": "marginal-forex.cancel-pending-order",
            "version": "1.0",
            "body": {
                "order_id": id_
            }
        }
        # Corrigido typo aqui:
        self.api.send_websocket_request(name, data)

        while self.api.cancel_order_forex is None:
            time.sleep(0.3)
            pass

        if self.api.cancel_order_forex["status"] == 2000:
            return True, self.api.cancel_order_forex["msg"]
        else:
            return False, self.api.cancel_order_forex["msg"]

    def get_fechadas_marginal_forex(self):
        self.api.fechadas_forex = None
        user_id = self.api.profile.msg['user_id']
        name = "sendMessage"
        data = {
            "name": "portfolio.get-history-positions",
            "version": "2.0",
            "body": {
                "user_id": user_id,
                "user_balance_id": int(global_value.balance_id),
                "instrument_types": ["marginal-forex"],
                "offset": 0,
                "limit": 30
            }
        }
        self.api.send_websocket_request(name, data)

        while self.api.fechadas_forex is None:
            time.sleep(0.5)
            pass

        if self.api.fechadas_forex["status"] == 2000:
            return True, self.api.fechadas_forex["msg"]
        else:
            return False, self.api.fechadas_forex["msg"]

    def get_positions_marginal_forex(self):
        self.api.positions_forex = None
        name = "sendMessage"
        data = {
            "name": "portfolio.get-positions",
            "version": "4.0",
            "body": {
                "offset": 0,
                "limit": 100,
                "user_balance_id": int(global_value.balance_id),
                "instrument_types": [
                    "marginal-forex",
                    "marginal-cfd",
                    "marginal-crypto"
                ]
            }
        }
        self.api.send_websocket_request(name, data)

        while self.api.positions_forex is None:
            time.sleep(0.5)
            pass

        if self.api.positions_forex["status"] == 2000:
            return True, self.api.positions_forex["msg"]
        else:
            return False, self.api.positions_forex["msg"]

    def get_pendentes_forex(self):
        self.api.pendentes_forex = None
        name = "sendMessage"
        data = {
            "name": "portfolio.get-orders",
            "version": "2.0",
            "body": {
                "user_balance_id": int(global_value.balance_id),
                "kind": "deferred"
            }
        }
        self.api.send_websocket_request(name, data)

        while self.api.pendentes_forex is None:
            time.sleep(0.5)
            pass

        if self.api.pendentes_forex["status"] == 2000:
            return True, self.api.pendentes_forex["msg"]
        else:
            return False, self.api.pendentes_forex["msg"]

    def get_instrument(self, active, exp, direcao, timeframe):
        if direcao == 'call':
            dir_ = 'C'
        else:
            dir_ = 'P'
        date_formated = str(datetime.utcfromtimestamp(exp).strftime("%Y%m%d%H%M"))
        instrument_id = "do" + str(active) + "A" + date_formated[:8] + "D" + date_formated[8:] + "00T" + str(timeframe) + "M" + dir_ + "SPT"
        return str(instrument_id)

    # Renomeada para não colidir com a outra assinatura:
    def buy_digital_spot_v2_local(self, ativo, valor, direcao, timeframe):
        timeframe = int(timeframe)
        asset_id = OP_code.ACTIVES[ativo]

        timestamp = int(time.time())
        if timeframe == 1:
            exp, _ = get_expiration_time(timestamp, timeframe)
        else:
            now_date = datetime.fromtimestamp(timestamp) + timedelta(minutes=1, seconds=30)
            while True:
                if now_date.minute % timeframe == 0 and time.mktime(now_date.timetuple()) - timestamp > 30:
                    break
                now_date = now_date + timedelta(minutes=1)
            exp = time.mktime(now_date.timetuple())

        instrument_id = self.get_instrument(asset_id, exp, direcao, timeframe)

        name = "sendMessage"
        data = {
            "name": "digital-options.place-digital-option",
            "version": "3.0",
            "body": {
                "user_balance_id": int(global_value.balance_id),
                "instrument_id": instrument_id,
                "amount": str(valor),
                "instrument_index": 0,
                "asset_id": int(asset_id),
            }
        }
        req_id = str(randint(0, 100000))
        self.api.send_websocket_request(name, data, req_id)

        start = time.time()
        while True:
            time.sleep(0.1)
            if time.time() - start <= 5:
                try:
                    message = self.api.orders[str(req_id)]
                    break
                except Exception:
                    pass
            else:
                return False, None
        try:
            return True, message['id']
        except:
            return False, message['message']

    # Renomeada para não colidir com buy() canônica:
    def buy_binary_local(self, valor, ativo, direction, expiration):
        expiration = int(expiration)
        self.q.put(1)

        asset_id = OP_code.ACTIVES[ativo]
        name = "sendMessage"
        exp, idx = get_expiration_time(int(self.api.timesync.server_timestamp), expiration)
        if idx < 5:
            option = 3  # "turbo"
        else:
            option = 1  # "binary"
        data = {
            "name": "binary-options.open-option",
            "version": "2.0",
            "body": {
                "user_balance_id": int(global_value.balance_id),
                "active_id": asset_id,
                "option_type_id": option,
                "direction": direction.lower(),
                "expired": int(exp),
                "price": valor,
                "refund_value": 0,
                "profit_percent": 0,
            }
        }

        req_id = int(randint(0, 1000000))
        self.api.send_websocket_request(name, data, str(req_id))

        time.sleep(1)
        self.q.get()

        start = time.time()
        while True:
            time.sleep(0.1)
            if time.time() - start <= 5:
                try:
                    message = self.api.orders[str(req_id)]
                    break
                except Exception:
                    pass
            else:
                return False, None

        try:
            return True, message['id']
        except:
            return False, message['message']
