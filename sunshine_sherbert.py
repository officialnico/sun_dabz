#TODO accurate bid ask prices
import ccxt
import time
import pprint
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from unicorn_fy.unicorn_fy import UnicornFy
import threading
import os
import datetime
import sys

class Manager:

    exchange = ccxt.binance({'enableRateLimit': True})

    def __init__(self, symbol_list=["BNB/BTC","XMR/BTC","ETH/BTC"], in_order=False, a=1):
        self.symbol_list = symbol_list
        self.in_order = in_order
        self.a = 1

    def run(self):

        box_list = list()

        for x in self.symbol_list:
            b = Box(x)
            b.run()
            box_list.append(b)

    #SuperClass Variables: a (time coefficient), in_order, box_list
    def set_in_order(self, bool):
        self.in_order = bool

    def get_in_order(self):
        return self.in_order

    def set_a(self, time_coefficient):
        self.a = time_coefficient

    def get_a(self):
        return self.a

    def get_box_list(self):
        return self.box_list

class Box(Manager):
    def __init__(self, symbol_ccxt):
        super().__init__()

        #SuperClass Variables Temporary Placeholders
        self.a = super().get_a()
        self.in_order = super().get_in_order()
        self.exchange = super().exchange #All boxes connect to this exchange object for rate limiter

        #symbols (different ones for CCXT API and Unicorn websocket API)
        self.symbol_ccxt = symbol_ccxt
        self.symbol_unicorn = self.ccxtToUnicorn(symbol_ccxt)

        #Change vars
        self.change24hr = None
        self.change5min = None
        self.change1hour = None  # WORKS
        self.change1min = None
        self.change1min_PREV = None
        self.price = None

        #Websocket API
        self.binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")  # websocket connection
        self.binance_websocket_api_manager.create_stream(["ticker", "trade"], [self.symbol_unicorn])

        #Threads for streaming prices from both API's
        self.t1 = threading.Thread(target=self.stream, name="unicorn_stream") #24hr & Price stream from ccxt
        self.min_candles_Thread = threading.Thread(target=self.stream_minute_candles)
        self.hr_candles_Thread = threading.Thread(target=self.stream_hour_candles)
        self.stream_price_Thread = threading.Thread(target=self.stream_price)
        self.min5_candles_Thread = threading.Thread(target=self.stream_5min_candle)
        self.main_Thread = threading.Thread(target=self.main) #Main Thread

    #Streams
    def stream(self):  # streams 24hour ticker

        while True:
            oldest_stream_data_from_stream_buffer = self.binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer:
                stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)
                # pprint.pprint(stream_data)

                if (stream_data['event_type'] == "24hrTicker"):
                    # set 24hr change to the value there
                    self.change24hr = float(stream_data['data'][0]['price_change_percent'])

            time.sleep(super().get_a() * (1 / 2))

    def stream_price(self):

        binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")
        # binance_websocket_api_manager.create_stream(['trade', 'kline_1m'], ['bnbbtc'])
        binance_websocket_api_manager.create_stream(["trade"], [self.symbol_unicorn])

        while True:
            oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer:
                unicorn_fied_stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)
                # pprint.pprint(unicorn_fied_stream_data)
                self.price = float(unicorn_fied_stream_data["price"])
            time.sleep(super().get_a() * (1 / 2))

    def stream_hour_candles(self):
        while (1):
            data_hour = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1h', limit=2)
            open = data_hour[0][4]
            close = self.price

            self.change1hour = ((close - open) / open) * 100
            time.sleep(super().get_a() * (1 / 2))

    def stream_minute_candles(self):
        while (1):
            data_min = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1m', limit=3)
            open_prev = data_min[0][4]
            close_prev = data_min[1][4]

            self.change1min_PREV = ((close_prev - open_prev) / open_prev) * 100
            close = self.price
            self.change1min = ((close - close_prev) / close_prev) * 100

            time.sleep(super().get_a() * (1 / 2))

    def stream_5min_candle(self):
        while (1):
            data_hour = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='5m', limit=2)
            open = data_hour[0][4]

            close = self.price
            self.change5min = ((close - open) / open) * 100
            time.sleep(super().get_a() * (1 / 2))

    #Functions
    def printBools(self, clear=False): #TODO Remove later
        while (1):
            print("change1min_PREV>=0.04", self.change1min_PREV >= 0.04, round(self.change1min_PREV, 3), "%")
            print("change1min>=0.07", self.change1min >= 0.07, round(self.change1min, 3), "%")
            print("change5min>=0.22", self.change5min >= 0.22, round(self.change5min, 3), "%")
            print("change1hour>=0.3", self.change1hour >= 0.3, round(self.change1hour, 3), "%")

            time.sleep(1*super().get_a())
            if clear: clearScreen()

    def ccxtToUnicorn(self, s):
        s = s.replace('/', "")
        s = s.lower()
        return s

    def printTime(self, print=True):
        now = datetime.datetime.now()
        s = now.strftime("%Y-%m-%d %H:%M:%S")
        if print==True: print(s)
        return s

    def restart(self):  # works
        os.execl(sys.executable, sys.executable, *sys.argv)

    #Main Functions
    def main(self):

        #Display Initiation
        print(self.symbol_ccxt, self.printTime(print=False))

        while (1):

            conditional = (self.change1min_PREV >= 0.04) and (self.change1min >= 0.07) and (self.change5min >= 0.22) and (
                        self.change1hour >= 0.3) and (self.change24hr >= 4)

            if (not super().get_in_order() and conditional):
                print(self.change1min_PREV >= 0.04, self.change1min >= 0.07, self.change5min >= 0.22, self.change1hour >= 0.3,
                      self.change24hr >= 4)
                logLine = self.printTime() + " " + str(conditional) + "\n"
                print("purchase()")
                # doc = open("log.txt", 'a')
                # doc.write(logLine)
                # doc.close()

            time.sleep(super().get_a() * (1 / 2))

    def run(self):
        #Start Streams
        self.t1.start()
        self.stream_price_Thread.start()

        while (self.price is None):
            time.sleep(1/3)

        self.min_candles_Thread.start()
        self.hr_candles_Thread.start()
        self.min5_candles_Thread.start()

        while(self.change1min is None or self.change1min_PREV is None or self.change1hour is None or self.change5min is None or self.change24hr is None):
            time.sleep(1/3)

        self.main_Thread.start()

class Radar(Manager):
    def __init__(self, symbol_list=["BNB/BTC","XMR/BTC","ETH/BTC","BTG/BTC","KNC/BTC","ETC/BTC"]): #TODO make actual full list of coins
        super().__init__()
        self.symbol_list = symbol_list
        self.refined_list = []
        self.stay_alive = True

    #Find symbols that meet the criteria
    def scan(self):
        for x in self.symbol_list:
            change_24hr = self.get_change_24hr(x)
            change_1hr = self.get_change_1hr(x)
            ref_list=[]
            if(change_24hr >= 4 and change_1hr >= 0.3): ref_list.append(x)
        self.refined_list=ref_list

        print(self.refined_list)

    def get_change_24hr(self, symbol_ccxt):
        tick = Manager.exchange.fetchTicker(symbol_ccxt)
        return tick['percentage']

    def get_change_1hr(self, symbol_ccxt):
        data_hour = Manager.exchange.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=2)
        open = data_hour[0][4]
        close = data_hour[1][4]

        change1hour = ((close - open) / open) * 100
        return change1hour

    def frequent_scanner(self):
        while(self.stay_alive):
            scan()
            time.sleep(60*60)

    def run(self):


a = Manager(symbol_list=["BNB/BTC","XMR/BTC","ETH/BTC","BTG/BTC","KNC/BTC","ETC/BTC"])
#a.run()
rad = Radar()
rad.scan()
