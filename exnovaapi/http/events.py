"""Module for IQ Option http login resource."""

from exnovaapi.http.resource import Resource


class Events(Resource):

    url = ""

    def send_http(self,method, data=None, headers=None):

        return self.api.send_http_request_v2(method=method, url=self.api.url_events,data=data)

    def __call__(self,method,data,headers=None):
         
        return self.send_http(method=method,data=data,headers=headers)
