
import time

class Base(object):

    def __init__(self, api):

        self.api = api

    def send_websocket_request(self, name, msg,request_id=""):

        if request_id == '':
            request_id = int(str(time.time()).split('.')[1])
        return self.api.send_websocket_request(name, msg,request_id)
