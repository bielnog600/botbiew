from exnovaapi.ws.chanels.base import Base


class Ssid(Base):
    name = "ssid"

    def __call__(self, ssid):

        self.send_websocket_request(self.name, ssid)
