
def candles(api, message):
    if message['name'] == 'candles':
        try:
            api.addcandles(message["request_id"], message["msg"]["candles"])
        except:
            pass