#TODO Time coefficient
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

        box_list = list()
        for i in symbol_list:
            box_list.append(Box(i))

        self.box_list = box_list

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

        #SuperClass Variables Temporary Placeholders #TODO: Inherit these variables from parent class
        self.a = Manager.get_a()
        self.in_order = Manager.get_in_order()
        self.exchange = Manager.exchange #All boxes connect to this exchange object for rate limiter

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

        #Start Streams
        self.t1.start()
        self.stream_price_Thread.start()
        time.sleep(3)
        self.min_candles_Thread.start()
        self.hr_candles_Thread.start()
        self.min5_candles_Thread.start()
        time.sleep(4.2) #Crucial, allows for loading of streams
        self.main_Thread.start()

        #Display Initiation
        self.printTime()
        print(symbol_ccxt)

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

                time.sleep(Manager.get_a() * (1 / 2))

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
                time.sleep(Manager.get_a() * (1 / 2))

    def stream_hour_candles(self):
        while (1):
            data_hour = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1h', limit=2)
            open = data_hour[0][4]
            close = self.price

            self.change1hour = ((close - open) / open) * 100
            time.sleep(Manager.get_a() * (1 / 2))

    def stream_minute_candles(self):
        while (1):
            data_min = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1m', limit=3)
            open_prev = data_min[0][4]
            close_prev = data_min[1][4]

            self.change1min_PREV = ((close_prev - open_prev) / open_prev) * 100
            close = self.price
            self.change1min = ((close - close_prev) / close_prev) * 100

            time.sleep(Manager.get_a() * (1 / 2))

    def stream_5min_candle(self):
        while (1):
            data_hour = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='5m', limit=2)
            open = data_hour[0][4]

            close = self.price
            self.change5min = ((close - open) / open) * 100
            time.sleep(Manager.get_a() * (1 / 2))

    #Functions
    def printBools(self): #TODO Remove later
        while (1):
            print("change1min_PREV>=0.04", self.change1min_PREV >= 0.04, round(self.change1min_PREV, 3), "%")
            print("change1min>=0.07", self.change1min >= 0.07, round(self.change1min, 3), "%")
            print("change5min>=0.22", self.change5min >= 0.22, round(self.change5min, 3), "%")
            print("change1hour>=0.3", self.change1hour >= 0.3, round(self.change1hour, 3), "%")
            if (self.change24hr is None):
                print("24hrchange is none fixing...")
                time.sleep(5)
                if (self.change24hr is None):
                    self.restart()
                else:
                    clearScreen()
            else:
                print("change24hr>=4", self.change24hr >= 4, round(self.change24hr, 3), "%")

            time.sleep(1*Manager.get_a())
            # clearScreen()

    def ccxtToUnicorn(self, s):
        s = s.replace('/', "")
        s = s.lower()
        return s

    def printTime(self):
        now = datetime.datetime.now()
        s = now.strftime("%Y-%m-%d %H:%M:%S")
        print(s)
        return s

    #Main loop
    def main(self):
        while (1):

            conditional = (self.change1min_PREV >= 0.04) and (self.change1min >= 0.07) and (self.change5min >= 0.22) and (
                        self.change1hour >= 0.3) and (self.change24hr >= 4)

            if (not Manager.get_in_order() and conditional):
                print(self.change1min_PREV >= 0.04, self.change1min >= 0.07, self.change5min >= 0.22, self.change1hour >= 0.3,
                      self.change24hr >= 4)
                logLine = printTime() + " " + str(conditional) + "\n"
                purchase()
                doc = open("log.txt", 'a')
                doc.write(logLine)
                doc.close()

            time.sleep(Manager.get_a() * (1 / 2))

Manager()
# a = Box("BNB/BTC")
# Box("XMR/BTC")
# Box("ETH/BTC")

