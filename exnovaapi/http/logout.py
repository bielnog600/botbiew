from exnovaapi.http.resource import Resource


class Logout(Resource):
    url = ""

    def _post(self, data=None, headers=None):

        return self.api.send_http_request_v2(method="POST", url=self.api.url_logout,data=data, headers=headers)

    def __call__(self):
       
        return self._post()

