import datetime

from exnovaapi.ws.chanels.base import Base


class Get_instruments(Base):
    name = "sendMessage"
    def __call__(self,types):
        data = {
        "name":"get-instruments",
        "version":"4.0",
        "body":{"type":types}
        }

        self.send_websocket_request(self.name, data)
