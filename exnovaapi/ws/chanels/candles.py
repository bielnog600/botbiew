
from exnovaapi.ws.chanels.base import Base
import time
from random import randint

class GetCandles(Base):

    name = "sendMessage"

    def __call__(self, active_id, interval, count,endtime):

        data = {"name":"get-candles",
                "version":"2.0",
                "body":{
                        "active_id":int(active_id),
                        "split_normalization": True,
                        "size":interval,#time size sample:if interval set 1 mean get time 0~1 candle 
                        "to":int(endtime),   #int(self.api.timesync.server_timestamp),
                        "count":count,#get how many candle
                        "":active_id
                        }
                }
        request = int(randint(0, 1000000)) 
        return self.send_websocket_request(self.name, data, request)
