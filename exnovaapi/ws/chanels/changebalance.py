
import datetime

from exnovaapi.ws.chanels.base import Base
class Changebalance(Base):

    name = "api_profile_changebalance"

    def __call__(self, balance_id):


        data = {
            "balance_id":balance_id
        }

        self.send_websocket_request(self.name, data)
