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

from yaspin import yaspin
from yaspin.spinners import Spinners


class Manager:

    #One Exchange to be used by subclasses
    exchange = ccxt.binance({'enableRateLimit': True})

    #Initialization
    def __init__(self, in_order=False, a=1, mega_markets = None):
        self.in_order = in_order
        self.a = 1
        self.box_list = list()


        if(mega_markets is None): self.mega_markets = self.load_markets()
        else: self.mega_markets = mega_markets

    #Main Functions
    def run(self):
        self.rad = Radar()
        self.rad.run()

    def shutdown_boxes(self):
        if(len(self.box_list)>0):
            for x in self.box_list:
                x.stop()

    def pause_others(self, symbol_ccxt, pause = True ):

        if(pause):
            self.tran.paused = True
            self.rad.paused = True

        else:
            self.rad.paused = False
            self.tran.paused = False

        for x in self.box_list:
            if(x.get_symbol()!=symbol_ccxt):
                if(pause):
                    x.pause()
                    print("Pausing ", str(x))
                else:
                    print("Unpausing", str(x))
                    x.unpause()

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

    def box_list_append(self, symbol_ccxt):
        b = Box(symbol_ccxt)
        b.run()
        self.box_list.append(b)

    def box_list_remove(self, box):
        print('rmv->',box) #TODO remove
        if(box in self.box_list):
            self.box_list.remove(box)
            box.stop()

    #Important Data Retrieval
    def load_markets(self, store=False):
        #Will fetch all /BTC markets
        exchange = ccxt.binance({'enableRateLimit': True}) #Hackaround, it was not seeing the top one

        arr = []
        exchange.load_markets()
        symbols = exchange.symbols  # get a list of symbols
        for x in symbols:
            if("/BTC" in x):
                arr.append(x)

        if(store):self.mega_markets=arr

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

        # Transaction handler initializer
        self.tran = Transaction(self.symbol_unicorn)
        self.total_profit = 0

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
        self.paused = False

        #Threads for streaming prices from both API's
        self.t1 = threading.Thread(target=self.stream, name="unicorn: price and 24hr change") #24hr & Price stream from ccxt
        self.min_candles_Thread = threading.Thread(target=self.stream_minute_candles, name="min_candles")
        self.hr_candles_Thread = threading.Thread(target=self.stream_hour_candles, name="hour_candles")
        self.min5_candles_Thread = threading.Thread(target=self.stream_5min_candle,name="min5_candles")
        self.main_Thread = threading.Thread(target=self.main,name="main") #Main Thread

        #Transaction data
        self.profit = None

    def __str__(self):
        return "Box:"+self.symbol_ccxt

    #Streams
    def stream(self):  #streams 24hour ticker

        binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")  # websocket connection
        binance_websocket_api_manager.create_stream(["ticker", "trade"], [self.symbol_unicorn]) #TODO we might be able to put this in self
        i=0
        while (self.stay_alive):
            oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer:
                stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)

                if(stream_data['event_type'] == "24hrTicker"):
                    # set 24hr change to the value there
                    self.change24hr = float(stream_data['data'][0]['price_change_percent'])
                    if(i==0): #Will make loading boxes much faster
                        self.price=float(stream_data['data'][0]['last_price'])
                        i+=1
                elif(stream_data["event_type"]=="trade"):
                    self.price = float(stream_data["price"])

            while(self.paused):
                time.sleep(5)

            time.sleep(super().get_a() * (1 / 4))

        binance_websocket_api_manager.stop_manager_with_all_streams()
        self.shut_down_count +=2
        if(self.messages):print(self.symbol_ccxt,"24hr stream succesfully shut down","\n")

    def stream_hour_candles(self):
        while (self.stay_alive):
            try:
                data_hour = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1h', limit=2)
                open = data_hour[0][4]
                close = self.price

                self.change1hour = ((close - open) / open) * 100
            except ccxt.NetworkError as e:
                #print("Error (non critical):", e)
                time.sleep(1)

            while (self.paused):
                time.sleep(5)
            time.sleep(super().get_a() * (1 / 2))

        self.shut_down_count += 1
        if(self.messages):print(self.symbol_ccxt,"Hour stream succesfully shut down","\n")

    def stream_minute_candles(self):
        while (self.stay_alive):
            try:
                data_min = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1m', limit=3)
                open_prev = data_min[0][4]
                close_prev = data_min[1][4]

                self.change1min_PREV = ((close_prev - open_prev) / open_prev) * 100
                close = self.price
                self.change1min = ((close - close_prev) / close_prev) * 100
            except ccxt.NetworkError as e:
                #print("Error (non critical):", e)
                time.sleep(1)

            while (self.paused):
                time.sleep(5)
            time.sleep(super().get_a() * (1 / 2))

        self.shut_down_count += 1
        if(self.messages):print(self.symbol_ccxt,"Minutes stream succesfully shut down","\n")

    def stream_5min_candle(self):
        while (self.stay_alive):
            try:
                data_hour = Manager.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='5m', limit=2)
                open = data_hour[0][4]
                close = self.price
                self.change5min = ((close - open) / open) * 100
            except ccxt.NetworkError as e:
                #print("Error (non critical):", e)
                time.sleep(1)
            time.sleep(super().get_a() * (1 / 2))

        self.shut_down_count += 1
        if(self.messages):print(self.symbol_ccxt,"5min stream succesfully shut down")

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

    def printTime(self, display=True):
        now = datetime.datetime.now()
        s = now.strftime("%Y-%m-%d %H:%M:%S")
        if(display): print(s)
        return s

    def restart(self):  # works
        os.execl(sys.executable, sys.executable, *sys.argv)

    def get_symbol(self):
        return self.symbol_ccxt

    #Main Functions
    def main(self):

        #Display Initiation
        print(self.symbol_ccxt, self.tran.printTime(display=False))

        while (self.stay_alive):

            conditional = (self.change1min_PREV >= 0.04) and (self.change1min >= 0.07) and (self.change5min >= 0.22) and (
                        self.change1hour >= 0.3) and (self.change24hr >= 4)

            if (not super().get_in_order() and conditional):
                print(self.change1min_PREV >= 0.04, self.change1min >= 0.07, self.change5min >= 0.22, self.change1hour >= 0.3,
                      self.change24hr >= 4)
                #logLine = self.printTime() + " " + str(conditional) + "\n"
                self.purchase()

            time.sleep(super().get_a() * (1 / 2))

        self.shut_down_count += 1
        if(self.messages):print("\n",self.symbol_ccxt, "Main thread shut down")

    def run(self):

        #Start loading spinner
        spinner = yaspin(Spinners.moon, text="Box loading...")
        spinner.start()

        #Start Streams
        self.t1.start()

        if(self.price is None): spinner.text = "loading price"
        while (self.price is None):
            time.sleep(1/3)
        if (self.price is None): spinner.text = "loading tran"

        self.min_candles_Thread.start()
        self.hr_candles_Thread.start()
        self.min5_candles_Thread.start()
        self.tran.run()

        while(self.change1min is None or self.change1min_PREV is None or self.change1hour is None or self.change5min is None or self.change24hr is None or self.tran.ask is None or self.tran.bid is None): #TODO check tran

            if(self.change1min is None): spinner.text = "loading change1min"
            elif(self.change1min_PREV is None): spinner.text =  "loading change1min_PREV"
            elif(self.change1hour is None): spinner.text = "loading change1hour"
            elif(self.change5min is None): spinner.text = "loading change5min"
            elif(self.change24hr is None): spinner.text = "loading change24hr"
            elif(self.tran.ask is None): spinner.text =  "loading tran.ask"
            elif(self.tran.bid is None): spinner.text =  "loading tran.bid"

            time.sleep(1/3)

        #End spinner
        spinner.stop()

        self.main_Thread.start()

    def purchase(self):
        super().pause_others(self.symbol_ccxt)
        self.in_order = True
        self.tran.purchase()
        self.total_profit+=self.tran.get_profit() #TODO fix
        self.tran.reset()
        self.in_order = False
        print("PROFIT->",self.total_profit)
        super().pause_others(self.symbol_ccxt, pause=False)

    def stop(self):
        if(self.messages):print(self.symbol_ccxt,"Shutting down...")
        self.stay_alive = False
        while(self.shut_down_count!=6):
            time.sleep(1/3)
        self.tran.stop()
        print(self.symbol_ccxt, "Succesfully Closed")

    #Pausing
    def pause(self):
        self.paused = True
        self.tran.paused = True

    def unpause(self):
        self.paused = False
        self.tran.paused = False

class Radar(Manager):

    #Initialization
    def __init__(self):
        super().__init__()
        self.stay_alive = True
        self.update_boxes_Thread = threading.Thread(target=self.update_boxes, name="update_boxes_Thread")  # Main Thread
        self.paused = False

    #Find symbols that meet the criteria
    def scan(self):
        #Although this isnt pretty its efficient and it works, after being tested multiple times with different methods of execution
        ref_list = []
        refined_mega_markets = super().get_markets()
        bar = tqdm(total=len(refined_mega_markets),position=0,leave=False,bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Fore.RESET))
        time1 = time.time() #TODO remove
        for x in refined_mega_markets:
            change24temp = self.get_change_24hr(x)
            if(change24temp >= 4 and self.get_change_1hr(x) >= 0.3 and self.get_volume_24hr(x)>270033):
                ref_list.append(x)
            elif(change24temp<3 or self.get_change_1hr(x) < 0.2 or self.get_volume_24hr(x)<250033):
                refined_mega_markets.remove(x)
                bar.update(1)
            bar.set_description("Scanning...".format(x))
            bar.update(1)
        bar.close()
        time2 = time.time() #TODO remove
        print(time2-time1) #todo remove
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

        # #TODO remove---
        # for x in refined_mega_markets:
        #     change1hr = self.get_change_1hr(x)
        #     vol24 = self.get_volume_24hr(x)
        #     print(x)
        #     print("\t","change24temp<3", change24temp<3,change24temp)
        #     print("\t", "change1hr<0.2", change1hr<0.2,change1hr)
        #     print("\t", "vol24<250033", vol24<250033,vol24)
        # # TODO remove---

        print("Scan Completed", ref_list, len(super().get_markets()))
        if(len(refined_mega_markets)<=1):
            print("load_markets()")
            super().load_markets(store=True)

        return ref_list

    def get_volume_24hr(self, symbol_ccxt): #TODO try using 1hr volume instead to guarantee trades
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

    def update_boxes(self): #TODO fix boxes get deleted
        #TODO increase volume
        while(self.stay_alive):
            while(super().get_in_order()):
                time.sleep(5)
            if(not super().get_in_order()):
                scan_l = self.scan()

                for x in super().get_box_list():
                    if(x.get_symbol() not in scan_l and len(super().get_box_list())==2 and len(scan_l)==2):
                        super().box_list_remove(x)
                    elif(x.get_symbol() in scan_l):
                        scan_l.remove(x.get_symbol())

                for s in scan_l:
                    if(len(super().get_box_list())<2):
                        super().box_list_append(s)
                        print("append",s)

                #TODO remove
                print("--current boxes---")
                for x in super().get_box_list():
                    print(x)
                print("------------------")

            if(self.paused):
                time.sleep(5)

            if(len(super().get_box_list())<=1): time.sleep(60)
            elif(len(super().get_box_list())>1): time.sleep(60*20)

    def run(self):
        self.update_boxes_Thread.start()

class Transaction(): #TODO not working yet only layout

    #Initialize
    def __init__(self, symbol_unicorn):
        self.purchase_price = None
        self.stay_alive = True
        self.symbol_unicorn = symbol_unicorn
        self.a = 1
        self.shut_down_count = 0
        self.paused = False

        self.ask = None #TODO
        self.bid = None

        self.profit = 0
        self.sell_price = None
        self.budget = 0.0092 #50 USD in BTC

        self.stream_bids_Thread = threading.Thread(target=self.stream_bids, name="bids thread")
        self.stream_asks_Thread = threading.Thread(target=self.stream_asks, name="asks thread")

        self.binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")  # websocket connection
        self.binance_websocket_api_manager.create_stream(["ticker"], [self.symbol_unicorn])

    #transaction functions
    def purchase(self):
        self.a = 1/14
        self.submit_order()
        self.maintain()
        self.a = 1

    #Submits best bid and waits until filled
    def sell(self, best_bid):
        self.sell_price = best_bid #TODO fix to work with binance
        self.profit = self.sell_price - self.purchase_price
        return self.bid

    def maintain(self):
        Thresh = self.purchase_price - ((0.015 / 100) * self.purchase_price)
        Goal = self.purchase_price + ((0.02 / 100) * self.purchase_price)
        i = 0

        while (self.stay_alive):
            best_bid = self.bid
            if (best_bid >= Goal):
                if (i == 0):
                    Thresh = self.purchase_price
                    Goal = best_bid + (0.02 / 100) * best_bid
                    i += 1
                elif (i > 0):
                    Thresh = best_bid - (0.02 / 100) * best_bid
                    Goal = best_bid + (0.02 / 100) * best_bid
                    i += 1
                print("GOAL", round(best_bid, 5))
            if (best_bid < Thresh and (best_bid - self.purchase_price) > 0):
                print("SELL", round(best_bid, 5))  # TODO make sell() function
                self.sell(best_bid) #TODO change this
                break

            # print(Thresh)
            time.sleep(self.a)


        print(self.profit)
        s = ""
        s = self.printTime() + " " + str(self.purchase_price) + str(self.sell_price) + " " + str(self.profit) + "\n"
        print(s)

    def submit_order(self): #Sumbits the order to binance and waits until the order is filled to proceed

        #filled = False
        filled = True #TODO remove

        # TODO submit bid and dont come back until success

        while(not filled):
            time.sleep(self.a)

        self.purchase_price = self.ask #Change this later
        print("order submitted", self.symbol_unicorn) #TODO remove

    #Streams
    def stream_bids(self):
        while (self.stay_alive):
            oldest_stream_data_from_stream_buffer = self.binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer:
                data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)
                self.bid = float(data["data"][0]["best_bid_price"])

            if(self.paused):
                time.sleep(5)
            time.sleep(self.a)
        self.binance_websocket_api_manager.stop_manager_with_all_streams() #Stops stream for both threads
        self.shut_down_count += 1

    def stream_asks(self):
        while (self.stay_alive):
            oldest_stream_data_from_stream_buffer = self.binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer:
                data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)
                self.ask = float(data["data"][0]["best_ask_price"])

            if(self.paused):
                time.sleep(5)
            time.sleep(self.a)
        self.shut_down_count += 1

    #main functions
    def run(self,loadingbar=False):
        if(loadingbar):
            # Start loading spinner
            spinner = yaspin(Spinners.earth, text="Transaction handler loading...")
            spinner.start()

        self.stream_bids_Thread.start()
        self.stream_asks_Thread.start()
        while(self.ask is None or self.bid is None):
            time.sleep(1/2)

        if(loadingbar):
            spinner.stop()

    def stop(self):
        self.stay_alive = False
        while(self.shut_down_count!=2):
            time.sleep(1/3)

    def reset(self):
        self.profit = 0
        self.sell_price = None

    #Util
    def printTime(self, display=True): #TODO double method you could just make the box use this
        now = datetime.datetime.now()
        s = now.strftime("%Y-%m-%d %H:%M:%S")
        if(display): print(s)
        return s

    def get_profit(self):
        return self.profit


man = Manager()
man.run()

# tran = Transaction("BNB/BTC")
# tran.run(loadingbar=True)
# tran.purchase()
