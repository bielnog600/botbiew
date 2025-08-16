# coding: utf-8

import json
import logging
import ssl
import threading
import time
from collections import defaultdict
from threading import Thread

from websocket import create_connection

from exnovaapi.api import ExnovaAPI
from exnovaapi.constants import constants
from exnovaapi.http.login import Login
from exnovaapi.http.loginv2 import Loginv2
from exnovaapi.http.getprofile import Getprofile
from exnovaapi.http.auth import Auth
from exnovaapi.http.billing import Billing
from exnovaapi.ws.client import ExnovaWs
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

# In Python 2, unicode is a separate type from str
# In Python 3, str is unicode, and there is a separate bytes type
# pylint: disable=redefined-builtin
try:
    unicode
except NameError:
    unicode = str


class Exnova:
    """Class for communication with Exnova API."""

    def __init__(self, host="exnova.com", proxies=None):
        """
        :param str host: The hostname or ip address of a Exnova server.
        :param dict proxies: (optional) The http request proxies.
        """
        self.https_url = "https://{host}/api".format(host=host)
        # --- CORREÇÃO: Garante que o protocolo websocket (wss) é usado ---
        self.wss_url = "wss://{host}/echo/websocket".format(host=host)
        self.websocket_client = None
        self.api = ExnovaAPI(host, proxies)
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
        self.get_order = GetOrder()
        self.get_positions = GetPositions()
        self.get_position = GetPosition()
        self.get_available_leverages = GetAvailableLeverages()
        self.get_tpsl = GetTpsl()
        self.close_position = ClosePosition()
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
        self.get_instruments = GetInstruments()

        self.timesync = Ssid()
        self.websocket_thread = None

        self.is_connected = False
        self.connect_wock = threading.Lock()

    @property
    def websocket(self):
        """Property to get websocket.
        :returns: The instance of :class:`ExnovaWs`.
        """
        return self.websocket_client

    @websocket.setter
    def websocket(self, websocket):
        """Method to set websocket."""
        self.websocket_client = websocket

    def get_ssid(self):
        return self.api.ssid

    def set_ssid(self, ssid):
        self.api.ssid = ssid

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.websocket_client.close()
        self.websocket_thread.join()

    def get_key(self, key):
        if key in self.api.http.headers:
            return self.api.http.headers[key]
        return None

    def get_headers(self):
        return self.api.http.headers

    def set_headers(self, headers):
        self.api.http.headers = headers

    def del_key(self, key):
        if key in self.api.http.headers:
            del self.api.http.headers[key]

    def get_cookies(self):
        return self.api.http.cookies

    def set_cookies(self, cookies):
        self.api.http.cookies = cookies

    def get_instruments(self, type, only_active=False):
        """
        type: "cfd", "forex", "crypto", "digital", "binary"
        """
        self.api.get_instruments(type)
        while self.api.instruments is None:
            pass

        if only_active:
            return [x for x in self.api.instruments if x['is_enabled']]

        return self.api.instruments

    def get_financial_stats(self, instrument_type, active, country_id, user_group_id):
        self.get_financial_stats.send_margin_call(instrument_type, active, country_id, user_group_id)
        while self.get_financial_stats.isSuccessful is False:
            pass
        return self.get_financial_stats.data

    def get_api_option_init_all(self):
        self.api_option_init_all.send_get_api_option_init_all()
        while self.api_option_init_all.isSuccessful is False:
            pass
        return self.api_option_init_all.data

    def get_underlying_list(self, type):
        self.underlying_list.send_underlying_list(type)
        while self.underlying_list.isSuccessful is False:
            pass
        return self.underlying_list.data

    def get_leader_board(self, country, user_country, from_position, to_position, near_traders_country_count,
                         near_traders_count, top_country_count, top_count, top_type):
        self.leaderboard.send_leader_board(country, user_country, from_position, to_position,
                                           near_traders_country_count, near_traders_count, top_country_count,
                                           top_count, top_type)
        while self.leaderboard.isSuccessful is False:
            pass
        return self.leaderboard.data

    def get_user_top_traders_rating(self, country_id, user_group_id):
        self.user_top_traders_rating.send_user_top_traders_rating(country_id, user_group_id)
        while self.user_top_traders_rating.isSuccessful is False:
            pass
        return self.user_top_traders_rating.data

    def get_alerts(self, asset_ids, type):
        self.alerts.send_alerts(asset_ids, type)
        while self.alerts.isSuccessful is False:
            pass
        return self.alerts.data

    def put_alert(self, asset_id, instrument_type, value, value_type, triggered_type, expiration):
        self.put_alert.send_put_alert(asset_id, instrument_type, value, value_type, triggered_type, expiration)
        while self.put_alert.isSuccessful is False:
            pass
        return self.put_alert.data

    def remove_alerts(self, alert_ids, type):
        self.remove_alerts.send_remove_alerts(alert_ids, type)
        while self.remove_alerts.isSuccessful is False:
            pass
        return self.remove_alerts.data

    def put_price_move(self, asset_id, instrument_type, value, value_type, triggered_type, expiration):
        self.put_price_move.send_put_price_move(asset_id, instrument_type, value, value_type, triggered_type,
                                                expiration)
        while self.put_price_move.isSuccessful is False:
            pass
        return self.put_price_move.data

    def remove_price_moves(self, price_move_ids, type):
        self.remove_price_moves.send_remove_price_moves(price_move_ids, type)
        while self.remove_price_moves.isSuccessful is False:
            pass
        return self.remove_price_moves.data

    def get_leader_board_user_info_deals(self, user_id, country):
        self.get_leader_board_user_info_deals.send_leader_board_user_info_deals(user_id, country)
        while self.get_leader_board_user_info_deals.isSuccessful is False:
            pass
        return self.get_leader_board_user_info_deals.data

    def sell_option(self, options_ids):
        self.sell_option.send_sell_option(options_ids)
        while self.sell_option.isSuccessful is False:
            pass
        return self.sell_option.data

    def reset_training_balance(self):
        self.training_balance_reset.send_training_balance_reset()
        while self.training_balance_reset.isSuccessful is False:
            pass
        return self.training_balance_reset.data

    def get_candles_history(self, active, timeframe, count, to):
        self.candles_history.send_candles_history(active, timeframe, count, to)
        while self.candles_history.isSuccessful is False:
            pass
        return self.candles_history.data

    def get_commissions(self, instrument_type):
        self.commissions.send_commissions(instrument_type)
        while self.commissions.isSuccessful is False:
            pass
        return self.commissions.data

    def get_overnight_fee(self, instrument_type):
        self.overnight_fee.send_overnight_fee(instrument_type)
        while self.overnight_fee.isSuccessful is False:
            pass
        return self.overnight_fee.data

    def get_available_assets(self, instrument_type):
        self.available_assets.send_available_assets(instrument_type)
        while self.available_assets.isSuccessful is False:
            pass
        return self.available_assets.data

    def get_copy_trades_config(self, user_id, with_settings):
        self.copy_trades_config.send_copy_trades_config(user_id, with_settings)
        while self.copy_trades_config.isSuccessful is False:
            pass
        return self.copy_trades_config.data

    def get_copy_trades_instruments(self, user_id):
        self.copy_trades_instruments.send_copy_trades_instruments(user_id)
        while self.copy_trades_instruments.isSuccessful is False:
            pass
        return self.copy_trades_instruments.data

    def get_initialization_data(self):
        self.get_initialization_data.send_get_initialization_data()
        while self.get_initialization_data.isSuccessful is False:
            pass
        return self.get_initialization_data.data

    def get_financial_information(self, active_id):
        self.financial_information.send_financial_information(active_id)
        while self.financial_information.isSuccessful is False:
            pass
        return self.financial_information.data

    def get_strike_list(self, instrument_type, active_id):
        self.strike_list.send_strike_list(instrument_type, active_id)
        while self.strike_list.isSuccessful is False:
            pass
        return self.strike_list.data

    def get_list_info_data(self, lists_ids):
        self.list_info_data.send_list_info_data(lists_ids)
        while self.list_info_data.isSuccessful is False:
            pass
        return self.list_info_data.data

    def get_order(self, order_id):
        self.get_order.send_get_order(order_id)
        while self.get_order.isSuccessful is False:
            pass
        return self.get_order.data

    def get_positions(self, instrument_type):
        self.get_positions.send_get_positions(instrument_type)
        while self.get_positions.isSuccessful is False:
            pass
        return self.get_positions.data

    def get_position(self, position_id):
        self.get_position.send_get_position(position_id)
        while self.get_position.isSuccessful is False:
            pass
        return self.get_position.data

    def get_available_leverages(self, instrument_type, active_id):
        self.get_available_leverages.send_get_available_leverages(instrument_type, active_id)
        while self.get_available_leverages.isSuccessful is False:
            pass
        return self.get_available_leverages.data

    def get_tpsl(self, position_id):
        self.get_tpsl.send_get_tpsl(position_id)
        while self.get_tpsl.isSuccessful is False:
            pass
        return self.get_tpsl.data

    def get_pending_orders(self, instrument_types):
        self.get_pending_orders.send_get_pending_orders(instrument_types)
        while self.get_pending_orders.isSuccessful is False:
            pass
        return self.get_pending_orders.data

    def set_auto_margin_call(self, from_balance, to_balance):
        self.set_auto_margin_call.send_set_auto_margin_call(from_balance, to_balance)
        while self.set_auto_margin_call.isSuccessful is False:
            pass
        return self.set_auto_margin_call.data

    def set_leverage(self, position_id, leverage):
        self.set_leverage.send_set_leverage(position_id, leverage)
        while self.set_leverage.isSuccessful is False:
            pass
        return self.set_leverage.data

    def set_tpsl(self, position_id, take_profit, stop_lose, use_trail_stop):
        self.set_tpsl.send_set_tpsl(position_id, take_profit, stop_lose, use_trail_stop)
        while self.set_tpsl.isSuccessful is False:
            pass
        return self.set_tpsl.data

    def cancel_tpsl(self, position_id):
        self.cancel_tpsl.send_cancel_tpsl(position_id)
        while self.cancel_tpsl.isSuccessful is False:
            pass
        return self.cancel_tpsl.data

    def place_pending_order(self, instrument_type, active_id, limit_price, direction, amount, expiration,
                            expiration_type):
        self.place_pending_order.send_place_pending_order(instrument_type, active_id, limit_price, direction, amount,
                                                          expiration, expiration_type)
        while self.place_pending_order.isSuccessful is False:
            pass
        return self.place_pending_order.data

    def cancel_pending_order(self, order_ids):
        self.cancel_pending_order.send_cancel_pending_order(order_ids)
        while self.cancel_pending_order.isSuccessful is False:
            pass
        return self.cancel_pending_order.data

    def close_position(self, position_id):
        self.close_position.send_close_position(position_id)
        while self.close_position.isSuccessful is False:
            pass
        return self.close_position.data

    def buy_place_cancel_order(self, order_id):
        self.buy_place_cancel_order.send_buy_place_cancel_order(order_id)
        while self.buy_place_cancel_order.isSuccessful is False:
            pass
        return self.buy_place_cancel_order.data

    def buy_place_close_order(self, order_id):
        self.buy_place_close_order.send_buy_place_close_order(order_id)
        while self.buy_place_close_order.isSuccessful is False:
            pass
        return self.buy_place_close_order.data

    def get_training_balance(self):
        self.training_balance.send_training_balance()
        while self.training_balance.isSuccessful is False:
            pass
        return self.training_balance.data

    def get_profile_ansyc(self):
        """
        return user profile
        """
        self.profile.send_get_profile()
        while self.profile.isSuccessful is False:
            pass
        return self.profile.data

    def get_candles(self, active_id, time_interval, count, end_time):
        """
        :param int active_id: The active/asset id.
        :param int time_interval: The time interval of the candles.
        :param int count: The count of the candles.
        :param int end_time: The end time of the candles.
        """
        self.candles.send_get_candles(active_id, time_interval, count, end_time)
        while self.candles.isSuccessful is False:
            pass
        return self.candles.candles_data

    # ------------------------------------------------------------------------

    def start_candles_stream(self, active_id, time_interval):
        """
        :param int active_id: The active/asset id.
        :param int time_interval: The time interval of the candles.
        """
        self.candles.subscribe(active_id, time_interval)

    def stop_candles_stream(self, active_id, time_interval):
        """
        :param int active_id: The active/asset id.
        :param int time_interval: The time interval of the candles.
        """
        self.candles.unsubscribe(active_id, time_interval)

    def start_instrument_quotes_stream(self, active_id, instrument_type):
        self.instrument_quotes_generated.subscribe(active_id, instrument_type)

    def stop_instrument_quotes_stream(self, active_id, instrument_type):
        self.instrument_quotes_generated.unsubscribe(active_id, instrument_type)

    def start_mood_stream(self, active_id):
        """
        :param int active_id: The active/asset id.
        """
        self.traders_mood.subscribe(active_id)

    def stop_mood_stream(self, active_id):
        """
        :param int active_id: The active/asset id.
        """
        self.traders_mood.unsubscribe(active_id)

    def start_candle_generated_v2(self, active_id, timeframe):
        self.candle_generated_v2.subscribe(active_id, timeframe)

    def stop_candle_generated_v2(self, active_id, timeframe):
        self.candle_generated_v2.unsubscribe(active_id, timeframe)

    def start_user_profile_client(self):
        self.user_profile_client.subscribe()

    def stop_user_profile_client(self):
        self.user_profile_client.unsubscribe()

    def start_user_settings_client(self):
        self.user_settings_client.subscribe()

    def stop_user_settings_client(self):
        self.user_settings_client.unsubscribe()

    def start_feed_price_generated(self, active_id, instrument_type):
        self.feed_price_generated.subscribe(active_id, instrument_type)

    def stop_feed_price_generated(self, active_id, instrument_type):
        self.feed_price_generated.unsubscribe(active_id, instrument_type)

    def start_top_assets_updated(self, instrument_type):
        self.top_assets_updated.subscribe(instrument_type)

    def stop_top_assets_updated(self, instrument_type):
        self.top_assets_updated.unsubscribe(instrument_type)

    def start_live_deal_binary_option_placed(self, asset_id):
        self.live_deal_binary_option_placed.subscribe(asset_id)

    def stop_live_deal_binary_option_placed(self, asset_id):
        self.live_deal_binary_option_placed.unsubscribe(asset_id)

    def start_live_deal_digital_option(self, asset_id):
        self.live_deal_digital_option.subscribe(asset_id)

    def stop_live_deal_digital_option(self, asset_id):
        self.live_deal_digital_option.unsubscribe(asset_id)

    def start_live_deal_cfd(self, instrument_type, asset_id):
        self.live_deal_cfd.subscribe(instrument_type, asset_id)

    def stop_live_deal_cfd(self, instrument_type, asset_id):
        self.live_deal_cfd.unsubscribe(instrument_type, asset_id)

    def buy(self, amount, active_id, direction, duration):
        """
        :param int amount: The amount to bet.
        :param int active_id: The active/asset id.
        :param str direction: The direction of the bet ('call' or 'put').
        :param int duration: The duration of the bet in minutes.
        """
        self.buy_v3.send_buy(amount, active_id, direction, duration)
        while self.buy_v3.isSuccessful is False:
            pass
        return self.buy_v3.data

    def buyV4(self, price, active, direction, type, option_type_id, user_balance_id):
        self.buy_v4.send_buy(price, active, direction, type, option_type_id, user_balance_id)
        while self.buy_v4.isSuccessful is False:
            pass
        return self.buy_v4.data

    def buy_digital_spot(self, active_id, amount, direction, duration):
        self.digital_placing.send_digital_placing(active_id, amount, direction, duration)
        while self.digital_placing.isSuccessful is False:
            pass
        return self.digital_placing.data

    def change_balance(self, balance_id):
        self.profile.send_change_balance(balance_id)
        while self.profile.balance_id != balance_id:
            pass
        return self.profile.balance_id

    def check_connect(self):
        # pylint: disable=no-member
        return self.websocket_thread.is_alive()

    def connect(self):
        """
        Connect to Exnova server.
        """
        self.websocket_client = ExnovaWs(self)
        self.websocket_thread = Thread(target=self.websocket_client.run, daemon=True)
        self.websocket_thread.start()

        self.timesync.subscribe_ssid()

        while self.is_connected is False:
            pass

        self.get_profile_ansyc()

        check, reason = self.check_verification()
        if check is False:
            return check, reason

        return True, None

    def check_verification(self):
        if self.profile.data:
            if self.profile.data['is_verified'] is False:
                return False, 'Please verify your account'
        return True, None


if __name__ == '__main__':
    pass
