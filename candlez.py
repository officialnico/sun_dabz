import ccxt
import time
import pprint
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from unicorn_fy.unicorn_fy import UnicornFy
import threading

symbol_ccxt = 'BNB/USDT'
symbol_unicorn = "bnbusdt"

change24hr = None
change1day = None
change1hour = None #WORKS
change1min = None
change1min_PREV = None

price = None #works

exchange = ccxt.binance(
    {'enableRateLimit': True})  # this option enables the built-in rate limiter (no ip ban)



def stream():

    while True:
        oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
        if oldest_stream_data_from_stream_buffer:
            stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)
            #pprint.pprint(stream_data)

            if(stream_data['event_type']=="24hrTicker"):
            #set 24hr change to the value there
                global change24hr
                change24hr=stream_data['data'][0]['price_change_percent'] ## TODO: Change this

            time.sleep(1/2)

def stream_price():

    binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")
    # binance_websocket_api_manager.create_stream(['trade', 'kline_1m'], ['bnbbtc'])
    binance_websocket_api_manager.create_stream(["trade"], [symbol_unicorn])

    while True:
        oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
        if oldest_stream_data_from_stream_buffer:
            global price
            unicorn_fied_stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)
            # pprint.pprint(unicorn_fied_stream_data)
            price = float(unicorn_fied_stream_data["price"])
            #print(price)
            time.sleep(1/2)


def stream_hour_candles(): #WORKS
    while(1):
        data_hour = exchange.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=2)
        global change1hour
        open = data_hour[0][4]

        close = price
        change1hour = ((close - open) / open) * 100
        time.sleep(1/2)

def stream_minute_candles():
    while(1):
        data_min = exchange.fetchOHLCV(symbol_ccxt, timeframe='1m', limit=3)
        global change1min_PREV

        open_prev = data_min[0][4]
        close_prev = data_min[1][4]
        change1min_PREV = ((close_prev - open_prev) / open_prev) * 100

        global change1min
        close = price
        change1min = ((close - close_prev) / close_prev) * 100

        print("Change1Min:",change1min)
        print("Change1Min_Prev:",change1min_PREV)
        time.sleep(1/2)


#24hr change
#1hr change
#1min change
#1min prev change

price = exchange.fetchOHLCV(symbol_ccxt, timeframe='1m', limit=1)[0][4]

binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")
binance_websocket_api_manager.create_stream(["ticker","trade"], [symbol_unicorn])
t1 = threading.Thread(target=stream, name="unicorn_stream")
t1.start()

min_candles_Thread = threading.Thread(target=stream_minute_candles)
hr_candles_Thread = threading.Thread(target=stream_hour_candles)
stream_price_Thread = threading.Thread(target=stream_price)
time.sleep(3)

stream_price_Thread.start()
min_candles_Thread.start()
hr_candles_Thread.start()
time.sleep(2) #let the thread start


while(1):
    # print("1hr->",change1hour)
    # print("24hr:",change24hr)

    time.sleep(1)
