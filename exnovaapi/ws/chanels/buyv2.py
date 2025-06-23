
from datetime import datetime, timedelta
import exnovaapi.global_value as global_value
from exnovaapi.ws.chanels.base import Base
from exnovaapi.expiration import get_expiration_time


class Buyv2(Base):

    name = "sendMessage"

    def __call__(self, price, active, direction, duration):

        exp, idx = get_expiration_time(
            int(self.api.timesync.server_timestamp), duration)

        if idx < 5:
            option = 3  # turbo
        else:
            option = 1  # non-turbo / binary

        data = {
            "price": price,
            "act": active,
            "exp": int(exp),
            "type": option,
            "direction": direction.lower(),
            "user_balance_id": int(global_value.balance_id),
            "time": self.api.timesync.server_timestamp
        }

        self.send_websocket_request(self.name, data)
