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
from tqdm import tqdm
from colorama import Fore

class Manager:

    #One Exchange to be used by subclasses
    exchange = ccxt.binance({'enableRateLimit': True})

    #Initialization
    def __init__(self, in_order=False, a=1):
        self.in_order = in_order
        self.a = 1
        self.mega_markets = self.load_markets()
        self.box_list = list()

        #Create folder for market efficiency



    #Main Functions
    def run(self):
        self.rad = Radar()
        self.rad.run()

    def shutdown_boxes(self):
        if(len(self.box_list)>0):
            for x in self.box_list:
                x.stop()

    #SuperClass Variable fetchers/getters: a (time coefficient), in_order, box_list
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

    def set_box_list(self, box_list):
        self.box_list = box_list

    #Important Data Retrieval
    def load_markets(self):
        #Will fetch all /BTC markets
        arr = []
        exchange.load_markets()
        symbols = exchange.symbols  # get a list of symbols
        for x in symbols:
            if("/BTC" in x):
                arr.append(x)

        return arr

    def get_markets(self):
        return self.mega_markets

    def set_markets(self, new_mega_markets):
        self.mega_markets = new_mega_markets

class Box(Manager):

    #Initialization
    def __init__(self, symbol_ccxt, messages=False):

        #Super class initializer
        super().__init__()

        #symbols (different ones for CCXT API and Unicorn websocket API)
        self.symbol_ccxt = symbol_ccxt
        self.symbol_unicorn = self.ccxtToUnicorn(symbol_ccxt)

        #Change vars
        self.change24hr = None #>=4
        self.change5min = None #>=0.22
        self.change1hour = None #>=0.3
        self.change1min = None #>=0.07
        self.change1min_PREV = None #>=0.04
        self.price = None

        #Thread Control
        self.stay_alive = True
        self.shut_down_count = 0
        self.messages = messages

        #Threads for streaming prices from both API's
        self.t1 = threading.Thread(target=self.stream, name="t1") #24hr & Price stream from ccxt
        self.min_candles_Thread = threading.Thread(target=self.stream_minute_candles, name="min_candles")
        self.hr_candles_Thread = threading.Thread(target=self.stream_hour_candles, name="hour_candles")
        self.stream_price_Thread = threading.Thread(target=self.stream_price, name="price")
        self.min5_candles_Thread = threading.Thread(target=self.stream_5min_candle,name="min5_candles")
        self.main_Thread = threading.Thread(target=self.main,name="main") #Main Thread

    def __str__(self):
        return "Box:"+self.symbol_ccxt

    #Streams
    def stream(self):  #streams 24hour ticker

        binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")  # websocket connection
        binance_websocket_api_manager.create_stream(["ticker", "trade"], [self.symbol_unicorn])

        while (self.stay_alive):
            oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer:
                stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)

                if (stream_data['event_type'] == "24hrTicker"):
                    # set 24hr change to the value there
                    self.change24hr = float(stream_data['data'][0]['price_change_percent'])

            time.sleep(super().get_a() * (1 / 2))

        binance_websocket_api_manager.stop_manager_with_all_streams()
        self.shut_down_count +=1
        if(self.messages):print(self.symbol_ccxt,"24hr stream succesfully shut down","\n")

    def stream_price(self):

        binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")  # websocket connection
        binance_websocket_api_manager.create_stream(["trade"], [self.symbol_unicorn])

        while(self.stay_alive):
            oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer:
                unicorn_fied_stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)
                # pprint.pprint(unicorn_fied_stream_data)
                self.price = float(unicorn_fied_stream_data["price"])
            time.sleep(super().get_a() * (1 / 2))

        binance_websocket_api_manager.stop_manager_with_all_streams()
        self.shut_down_count += 1
        if(self.messages):print(self.symbol_ccxt,"Price stream succesfully shut down","\n")

    def stream_hour_candles(self):
        while (self.stay_alive):
            data_hour = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1h', limit=2)
            open = data_hour[0][4]
            close = self.price

            self.change1hour = ((close - open) / open) * 100
            time.sleep(super().get_a() * (1 / 2))

        self.shut_down_count += 1
        if(self.messages):print(self.symbol_ccxt,"Hour stream succesfully shut down","\n")

    def stream_minute_candles(self):
        while (self.stay_alive):
            data_min = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1m', limit=3)
            open_prev = data_min[0][4]
            close_prev = data_min[1][4]

            self.change1min_PREV = ((close_prev - open_prev) / open_prev) * 100
            close = self.price
            self.change1min = ((close - close_prev) / close_prev) * 100

            time.sleep(super().get_a() * (1 / 2))

        self.shut_down_count += 1
        if(self.messages):print(self.symbol_ccxt,"Minutes stream succesfully shut down","\n")

    def stream_5min_candle(self):
        while (self.stay_alive):
            data_hour = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='5m', limit=2)
            open = data_hour[0][4]

            close = self.price
            self.change5min = ((close - open) / open) * 100
            time.sleep(super().get_a() * (1 / 2))

        self.shut_down_count += 1
        if(self.messages):print(self.symbol_ccxt,"5min stream succesfully shut down")

    def stream_ask_price(self): #purchasing price
        binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")  # websocket connection


    def stream_bid_price(self):
        pass

    #Functions
    def printBools(self, clear=False): #TODO Remove later
        while (self.stay_alive):
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
        if(print): print(s)
        return s

    def restart(self):  # works
        os.execl(sys.executable, sys.executable, *sys.argv)

    def get_symbol(self):
        return self.symbol_ccxt

    #Main Functions
    def main(self):

        #Display Initiation
        print(self.symbol_ccxt, self.printTime(print=False))

        while (self.stay_alive):

            conditional = (self.change1min_PREV >= 0.04) and (self.change1min >= 0.07) and (self.change5min >= 0.22) and (
                        self.change1hour >= 0.3) and (self.change24hr >= 4)

            if (not super().get_in_order() and conditional):
                print(self.change1min_PREV >= 0.04, self.change1min >= 0.07, self.change5min >= 0.22, self.change1hour >= 0.3,
                      self.change24hr >= 4)
                #logLine = self.printTime() + " " + str(conditional) + "\n"
                print("purchase()")

            time.sleep(super().get_a() * (1 / 2))

        self.shut_down_count += 1
        if(self.messages):print("\n",self.symbol_ccxt, "Main thread shut down")

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

    def stop(self):
        if(self.messages):print(self.symbol_ccxt,"Shutting down...")
        self.stay_alive = False
        while(self.shut_down_count!=6):
            time.sleep(1/3)
        print(self.symbol_ccxt, "Succesfully Closed")

#TODO scan keeps deleting most of the markets
class Radar(Manager):

    #Initialization
    def __init__(self):
        super().__init__()
        self.stay_alive = True
        self.update_boxes_Thread = threading.Thread(target=self.update_boxes, name="update_boxes_Thread")  # Main Thread

    #Find symbols that meet the criteria
    def scan(self):
        ref_list = []
        temp_str = "" #TODO remove
        refined_mega_markets = super().get_markets()
        bar = tqdm(total=len(refined_mega_markets),position=0,leave=False,bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Fore.RESET))
        for x in refined_mega_markets:
            change24temp = self.get_change_24hr(x)
            if(change24temp >= 4 and self.get_change_1hr(x) >= 0.3 and self.get_volume_24hr(x)>270033):
                ref_list.append(x)
            elif(change24temp<3 or self.get_change_1hr(x) < 0.2 or self.get_volume_24hr(x)<250033):
                refined_mega_markets.remove(x)
                temp_str += "->" + x + "change24: " + str(change24temp) + "change1hr: "+ str(self.get_change_1hr(x)) + "\n" #TODO remove
                bar.update(1)
            bar.set_description("Scanning...".format(x))
            bar.update(1)
        bar.close()
        if(len(ref_list)>2):
            m1 = None
            m2 = None
            max_symbol = ref_list[0]
            max_change = self.get_change_1w(max_symbol)
            for x in ref_list:
                change_w = self.get_change_1w(x)
                if(change_w>max_change):
                    max_change = change_w
                    max_symbol = x
                bar.update(1)
            m1 = max_symbol
            ref_list.remove(m1)

            max_symbol = ref_list[0]
            max_change = self.get_change_1w(max_symbol)
            for x in ref_list:
                change_w = self.get_change_1w(x)
                if(change_w>max_change):
                    max_change = change_w
                    max_symbol = x
            m2 =  max_symbol
            ref_list = [m1,m2]

        super().set_markets(refined_mega_markets)
        print("Scan Completed", ref_list)
        print(temp_str) #TODO remove
        return ref_list

    def get_volume_24hr(self, symbol_ccxt):
        data_hour = Manager.exchange.fetchOHLCV(symbol_ccxt, timeframe='1d', limit=1)
        return data_hour[0][5]

    def get_change_24hr(self, symbol_ccxt):
        tick = Manager.exchange.fetchTicker(symbol_ccxt)
        return tick['percentage']

    def get_change_1hr(self, symbol_ccxt):
        data_hour = Manager.exchange.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=2)
        open = data_hour[0][4]
        close = data_hour[1][4]

        change1hour = ((close - open) / open) * 100
        return change1hour

    def get_change_1w(self, symbol_ccxt):
        data_hour = Manager.exchange.fetchOHLCV(symbol_ccxt, timeframe='1w', limit=2)
        open = data_hour[0][4]
        close = data_hour[1][4]

        change1w = ((close - open) / open) * 100
        return change1w

    def update_boxes(self):
        while(self.stay_alive):
            while(super().get_in_order()):
                time.sleep(5)
            if(not super().get_in_order()):
                new_list = self.scan()

                #Dynamic Remove
                new_box_list = list()
                current_boxes = super().get_box_list()
                for x in current_boxes:
                    if(x.get_symbol() in new_list): #TODO verify if this actually works
                        new_list.remove(x.get_symbol())
                        new_box_list.append(x)
                    elif(len(current_boxes)==2):
                        x.stop()

                #Add and run only those not added previously
                for x in new_list:
                    b = Box(x)
                    b.run()
                    new_box_list.append(b)

                super().set_box_list(new_box_list)

                #TODO Remove
                for x in new_box_list:
                    print(x.get_symbol())
                temp = super().get_box_list()
                print("--current boxes---")
                for x in temp:
                    print(x.get_symbol())
                print("------------------")


            if(len(super().get_box_list())<=1): time.sleep(5)
            if(len(super().get_box_list())>1): time.sleep(20*60)
            #time.sleep(60*30)

    def run(self):
        self.update_boxes_Thread.start()

class Transaction(Box): #TODO not working yet only layout
    def __init__(self):
        super().__init__()
        self.purchase_price = None

    def purchase(self):
        pass

    def sell(self):
        pass

    def maintain(self):
        pass

    def set_box(self,):
        self.box = box

exchange = ccxt.binance({'enableRateLimit': True})



man = Manager()
man.run()

# rad = Radar()
#
# rad.run()

time.sleep(1)

#
# #TEST
# for x in s1:
#     print(x)
#     print("change1hr",rad.get_change_1hr(x))
#     print("change24hr",rad.get_change_24hr(x))
#     print("volume", rad.get_volume_24hr(x))
#     print("------")
#
# print("==========")
#
# for x in s2:
#     print(x)
#     print("change1hr",rad.get_change_1hr(x))
#     print("change24hr",rad.get_change_24hr(x))
#     print("volume",rad.get_volume_24hr(x))
#     print("------")
# #TEST
#
