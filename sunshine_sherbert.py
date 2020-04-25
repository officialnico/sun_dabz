#TODO check if starting Manager in_order=True works
import time
import threading
import os
import datetime
import sys
import webbrowser
import signal

from tqdm import tqdm
from colorama import Fore
from yaspin import yaspin
from yaspin.spinners import Spinners

import ccxt
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from unicorn_fy.unicorn_fy import UnicornFy

import sqlite3
from os import path

class Manager:

    # Initialization
    def __init__(self, in_order=False, a=1, mega_markets=None, display=True):

        #Super Variables
        self.in_order = in_order
        self.a = 1
        self.box_list = list()
        self.total_profit = 0

        os.chdir(sys.path[0])
        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.stay_alive = True
        self.display = display

        if os.name == 'nt':
            chrome_path = "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
            webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_path))

        if (mega_markets is None):
            self.mega_markets = self.load_markets()
        else:
            self.mega_markets = mega_markets

        signal.signal(signal.SIGINT, self.keyboardInterruptHandler)

    # Main Functions
    def run(self, updater=True):
        self.rad = Radar(self)
        if(updater):
            self.rad.run()

    def shutdown(self,override=True):

        try:
            self.stay_alive = False
            self.spinner = yaspin(Spinners.noise, text="Shutting down...")
            self.spinner.start()
            if(not self.display):
                self.spinner.stop()
            self.shutdown_boxes()
            self.rad.stay_alive = False
            if(override):
                self.in_order = False #Dangerous
        except Exception as e:
            print(e)
            quit()

    #Box Controls
    def shutdown_boxes(self):
        if (self.box_list):
            for x in self.box_list:
                x.stop()

    def pause_others(self, symbol_ccxt, pause=True):

        if (pause):
            self.rad.paused = True

        else:
            self.rad.paused = False

        for x in self.box_list:
            if (x.get_symbol() != symbol_ccxt):
                if (pause):
                    x.pause()
                    print("Pausing ", str(x))
                else:
                    print("Unpausing", str(x))
                    x.unpause()

    # SuperClass Variable fetchers/getters: a (time coefficient), in_order, box_list
    def box_list_append(self, symbol_ccxt, open_chart=False):
        for x in self.box_list:
            if(x.get_symbol() == symbol_ccxt):
                return
        if(open_chart):
            self.open_chart(symbol_ccxt)
        b = Box(self, symbol_ccxt)
        b.run()
        self.box_list.append(b)

    def box_list_remove(self, box):
        print('rmv->', box)  # TODO remove
        if (box in self.box_list):
            self.box_list.remove(box)
            box.stop()

    # Important Data Retrieval
    def load_markets(self, store=False):
        # Will fetch all /BTC markets
        exchange = self.exchange

        arr = []
        exchange.load_markets()
        symbols = exchange.symbols  # get a list of symbols
        for x in symbols:
            if ("/BTC" in x):
                arr.append(x)

        if (store): self.mega_markets = arr

        return arr

    def get_markets(self):
        return self.mega_markets

    def set_markets(self, new_mega_markets):
        self.mega_markets = new_mega_markets

    #Utilities
    def open_chart(self, symbol_ccxt):
        web_symbol = symbol_ccxt.replace("/", "_")
        url = "binance.com/en/trade/" + web_symbol
        webbrowser.get('chrome').open_new(url)

    def keyboardInterruptHandler(self, signal, frame):
        self.shutdown()


class Box:

    # Initialization
    def __init__(self, SUPER, symbol_ccxt, messages=False):

        self.SUPER = SUPER

        # symbols (different ones for CCXT API and Unicorn websocket API)
        self.symbol_ccxt = symbol_ccxt
        self.symbol_unicorn = self.ccxtToUnicorn(symbol_ccxt)

        # Transaction handler initializer
        self.tran = Transaction(self, self.symbol_unicorn)
        self.total_profit = 0

        # Change vars
        self.change24hr = None  # >=4
        self.change5min = None  # >=0.22
        self.change1hour = None  # >=0.3
        self.change1min = None  # >=0.07
        self.change1min_PREV = None  # >=0.04
        self.price = None

        # Transaction variables
        self.ask = None
        self.bid = None
        self.ask_quantity = None
        self.bid_quantity = None
        self.buys = 0
        self.sells = 0

        # Thread Control
        self.stay_alive = True
        self.shut_down_count = 0
        self.messages = messages
        self.paused = self.SUPER.in_order

        # Threads for streaming prices from both API's
        self.t1 = threading.Thread(target=self.stream, name="box_price&24hr_change")  # 24hr & Price stream from ccxt
        self.min_candles_Thread = threading.Thread(target=self.stream_minute_candles, name="box_min_candles")
        self.hr_candles_Thread = threading.Thread(target=self.stream_hour_candles, name="box_hour_candles")
        self.min5_candles_Thread = threading.Thread(target=self.stream_5min_candle, name="box_min5_candles")
        self.main_Thread = threading.Thread(target=self.main, name="box_main")  # Main Thread

        # Transaction data
        self.profit = None
        self.dat = Data(self)

    def __str__(self):
        return "Box:" + self.symbol_ccxt

    # Streams
    def stream(self):  # streams 24hour ticker & Asks Bids

        binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")  # websocket connection
        binance_websocket_api_manager.create_stream(["ticker", "trade"],
                                                        [self.symbol_unicorn])  # TODO we might be able to put this in self
        i = 0
        while (self.stay_alive):
            oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
            if oldest_stream_data_from_stream_buffer:
                stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)

                if (stream_data['event_type'] == "24hrTicker"):
                    # set 24hr change to the value there
                    self.change24hr = float(stream_data['data'][0]['price_change_percent'])
                    self.bid = float(stream_data["data"][0]["best_bid_price"])
                    self.ask = float(stream_data["data"][0]["best_ask_price"])
                    self.ask_quantity = float(stream_data["data"][0]["best_ask_quantity"])
                    self.bid_quantity = float(stream_data["data"][0]["best_bid_quantity"])
                    if (i == 0):  # Will make loading boxes much faster
                        self.price = float(stream_data['data'][0]['last_price'])
                        i += 1
                elif (stream_data["event_type"] == "trade"):
                    self.price = float(stream_data["price"])

            while (self.paused):
                time.sleep(5)

            time.sleep(self.SUPER.a * (1 / 4))

        binance_websocket_api_manager.stop_manager_with_all_streams()
        self.shut_down_count += 2
        if (self.messages): print(self.symbol_ccxt, "24hr stream succesfully shut down", "\n")

    def stream_hour_candles(self):
        while (self.stay_alive):
            try:
                data_hour = self.SUPER.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1h', limit=2)
                open = data_hour[0][4]
                close = self.price

                self.change1hour = ((close - open) / open) * 100

            # except Exception as e:
            #     print("E:",e)
            except ccxt.NetworkError as e:
                print("EN:",e)
            # except ccxt.NetworkError as e:
            #     if(e is requests.exceptions.ConnectionError):
            #         print("Connection ended shutting down")
            #         self.man.shutdown()
            #     time.sleep(1)

            while (self.paused):
                time.sleep(5)
            time.sleep(self.SUPER.a * (1 / 2))

        self.shut_down_count += 1
        if (self.messages): print(self.symbol_ccxt, "Hour stream succesfully shut down", "\n")

    def stream_minute_candles(self):
        while (self.stay_alive):
            try:
                data_min = self.SUPER.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='1m', limit=3)
                open_prev = data_min[0][4]
                close_prev = data_min[1][4]

                self.change1min_PREV = ((close_prev - open_prev) / open_prev) * 100
                close = self.price
                self.change1min = ((close - close_prev) / close_prev) * 100
            except ccxt.NetworkError as e:
                # print("Error (non critical):", e)
                print("1M", e)
                time.sleep(1)

            while (self.paused):
                time.sleep(5)
            time.sleep(self.SUPER.a * (1 / 2))

        self.shut_down_count += 1
        if (self.messages): print(self.symbol_ccxt, "Minutes stream succesfully shut down", "\n")

    def stream_5min_candle(self):
        while (self.stay_alive):
            try:
                data_hour = self.SUPER.exchange.fetchOHLCV(self.symbol_ccxt, timeframe='5m', limit=2)
                open = data_hour[0][4]
                close = self.price
                self.change5min = ((close - open) / open) * 100
            except ccxt.NetworkError as e:
                print("5M:",e)
                time.sleep(1)
            time.sleep(self.SUPER.a * (1 / 2))

        self.shut_down_count += 1
        if (self.messages): print(self.symbol_ccxt, "5min stream succesfully shut down")

    # Functions
    def ccxtToUnicorn(self, s):
        s = s.replace('/', "")
        s = s.lower()
        return s

    def printTime(self, display=True):
        now = datetime.datetime.now()
        s = now.strftime("%Y-%m-%d %H:%M:%S")
        if (display): print(s)
        return s

    def restart(self):  # works
        os.execl(sys.executable, sys.executable, *sys.argv)

    def get_symbol(self):
        return self.symbol_ccxt

    # Main Functions
    def main(self):

        # Display Initiation
        print(self.symbol_ccxt, self.printTime(display=False),"VOL24:",self.SUPER.rad.get_volume_24hr(self.symbol_ccxt))

        while (self.stay_alive):

            conditional = (self.change1min_PREV >= 0.04) and (self.change1min >= 0.07) and (
                        self.change5min >= 0.22) and (
                                  self.change1hour >= 0.3) and (self.change24hr >= 4)

            if (not self.SUPER.in_order and conditional):
                print(self.change1min_PREV >= 0.04, self.change1min >= 0.07, self.change5min >= 0.22,
                      self.change1hour >= 0.3,
                      self.change24hr >= 4)
                # logLine = self.printTime() + " " + str(conditional) + "\n"
                self.purchase()

            time.sleep(self.SUPER.a * (1 / 2))

        self.shut_down_count += 1
        if (self.messages): print("\n", self.symbol_ccxt, "Main thread shut down")

    def run(self):

        self.stay_alive = self.SUPER.stay_alive
        if(not self.SUPER.stay_alive):
            return

        # Start loading spinner
        dis = self.SUPER.display
        if(dis):
            spinner = yaspin(Spinners.moon, text="Box loading...")
            spinner.start()

        # Start Streams
        self.t1.start()

        if (self.price is None):
            if(dis): spinner.text = "loading price"
        while (self.price is None):
            time.sleep(1 / 3)

        self.min_candles_Thread.start()
        self.hr_candles_Thread.start()
        self.min5_candles_Thread.start()

        while (self.change1min is None or self.change1min_PREV is None or self.change1hour is None or self.change5min is None
                    or self.change24hr is None or self.ask is None or self.bid is None):  # TODO check tran

            if(dis):
                if (self.change1min is None):
                    spinner.text = "loading change1min"
                elif (self.change1min_PREV is None):
                    spinner.text = "loading change1min_PREV"
                elif (self.change1hour is None):
                    spinner.text = "loading change1hour"
                elif (self.change5min is None):
                    spinner.text = "loading change5min"
                elif (self.change24hr is None):
                    spinner.text = "loading change24hr"
                elif (self.ask is None):
                    spinner.text = "loading tran.ask"
                elif (self.bid is None):
                    spinner.text = "loading tran.bid"

            time.sleep(1 / 3)

        # End spinner
        if(dis):
            spinner.stop()

        self.main_Thread.start()
        self.dat.open()

    def purchase(self):
        self.SUPER.pause_others(self.symbol_ccxt)
        self.SUPER.in_order = True
        self.tran.purchase()
        self.SUPER.total_profit += self.tran.get_profit()  # TODO fix
        self.tran.reset()
        self.SUPER.in_order = False
        print("TOTALPROFIT->", self.form(self.SUPER.total_profit))
        self.SUPER.pause_others(self.symbol_ccxt, pause=False)

    def stop(self):
        self.dat.close()
        if (self.messages): print(self.symbol_ccxt, "Shutting down...")
        self.stay_alive = False
        while (self.shut_down_count != 6):
            time.sleep(1 / 3)

        self.dat.close()
        print(self.symbol_ccxt, "Succesfully Closed")

    # Pausing
    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False

    #util
    def form(self, s):
        return "{:.8f}".format(s)


class Radar:

    # Initialization
    def __init__(self, SUPER):
        # print("SELF", self)
        # print("SUPER", SUPER)
        self.SUPER = SUPER

        self.stay_alive = True
        self.update_boxes_Thread = threading.Thread(target=self.update_boxes, name="update_boxes_Thread")  # Main Thread
        self.paused = False

    # Process
    def run(self):
        self.update_boxes_Thread.start()

    def stop(self):
        self.stay_alive = False

    # Find symbols that meet the criteria
    def scan(self):
        # Although this isnt pretty its efficient and it works, after being tested multiple times with different methods of execution
        ref_list = []
        refined_mega_markets = self.SUPER.get_markets()

        dis = self.SUPER.display
        if(dis):
            bar = tqdm(total=len(refined_mega_markets), position=0, leave=False,
                       bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Fore.RESET))
        else:
            print("Scanning...", len(refined_mega_markets), "markets")

        for x in refined_mega_markets:
            change24temp = self.get_change_24hr(x)
            while(change24temp is None): #TODO check over, should help
                change24temp = self.get_change_24hr(x)
                time.sleep(2)
            if (change24temp >= 4 and self.get_change_1hr(x) >= 0.3 and self.get_volume_24hr(x) > 270033): #369214.97
                ref_list.append(x)

            elif (change24temp < 3 or self.get_change_1hr(x) < 0.2 or self.get_volume_24hr(x) < 250033):
                refined_mega_markets.remove(x)
                if(dis):
                    bar.update(1)

            if(dis):
                bar.set_description("Scanning...".format(x))
                bar.update(1)

            if(not self.stay_alive or self.SUPER.in_order):
                if(dis): bar.close()
                return

        if(dis):bar.close()

        if (len(ref_list) > 2):
            m1 = None
            m2 = None
            max_symbol = ref_list[0]
            max_change = self.get_change_1w(max_symbol)
            for x in ref_list:
                change_w = self.get_change_1w(x)
                if (change_w > max_change):
                    max_change = change_w
                    max_symbol = x
                if(dis): bar.update(1)
            m1 = max_symbol
            ref_list.remove(m1)

            max_symbol = ref_list[0]
            max_change = self.get_change_1w(max_symbol)
            for x in ref_list:
                change_w = self.get_change_1w(x)
                if (change_w > max_change):
                    max_change = change_w
                    max_symbol = x
            m2 = max_symbol
            ref_list = [m1, m2]

        self.SUPER.set_markets(refined_mega_markets)

        if(self.stay_alive and ref_list):
            print("Scan Completed", ref_list)
        if (len(refined_mega_markets) < 2):
            self.SUPER.load_markets(store=True)

        return ref_list

    # Request data retrieval
    def get_change_24hr(self, symbol_ccxt):
        try:
            tick = self.SUPER.exchange.fetchTicker(symbol_ccxt)
            return tick['percentage']
        except ccxt.NetworkError as e:
            print("RC24:",e)
            time.sleep(1)
            self.get_change_24hr(symbol_ccxt)

    def get_volume_24hr(self, symbol_ccxt):  # TODO try using 1hr volume instead to guarantee trades
        try:
            data_hour = None
            while(data_hour is None):
                data_hour = self.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='1d', limit=1)

            return data_hour[0][5]
        except ccxt.NetworkError as e:
            print("V24R:",e)
            time.sleep(1)
            self.get_volume_24hr(symbol_ccxt)

    def get_change_1hr(self, symbol_ccxt):
        try:
            data_hour = self.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=2)
            open = data_hour[0][4]
            if(len(data_hour)<2):print(data_hour, symbol_ccxt) #TODO remove
            close = data_hour[len(data_hour)-1][4]

            change1hour = ((close - open) / open) * 100
            return change1hour
        except ccxt.NetworkError as e:
            print("C1R",e)
            time.sleep(1)
            self.get_change_1hr(symbol_ccxt)

    def get_volume_1hr(self, symbol_ccxt):
        try:
            data_hour = self.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=1)
            return data_hour[0][5]
        except ccxt.NetworkError as e:
            print("V24R",e)
            time.sleep(1)
            self.get_volume_1hr(symbol_ccxt)

    def get_change_1w(self, symbol_ccxt):
        try:
            data_hour = self.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='1w', limit=2)
            open = data_hour[0][4]
            close = data_hour[1][4]

            change1w = ((close - open) / open) * 100
            return change1w
        except ccxt.NetworkError as e:
            print("C1WR",e)
            time.sleep(1)
            self.get_change_1w(symbol_ccxt)

    def get_change_1yr(self, symbol_ccxt):
        try:
            data_hour = self.BOX.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='1M', limit=12)
            open = data_hour[0][3]
            l = len(data_hour)-1
            if(l<0):
                print("Error#537")
                return None
            close = data_hour[l][4]
            change1yr = ((close - open) / open) * 100

            return change1yr
        except ccxt.NetworkError as e:
            print("C1YR",e)
            time.sleep(1)
            self.get_change_1yr(symbol_ccxt)

    def get_change_10min(self, symbol_ccxt):
        try:
            data_hour = self.BOX.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='5m', limit=3)
            open = data_hour[0][4]
            close = data_hour[2][4]

            change1yr = ((close - open) / open) * 100
            return change1yr
        except ccxt.NetworkError as e:
            print("C10mR:",e)
            time.sleep(1)
            self.get_change_10(symbol_ccxt)

    #Actives updater
    def update_boxes(self):  # TODO fix boxes get deleted

        while (self.stay_alive):

            while (self.SUPER.in_order or self.paused):
                time.sleep(5)

            if (not self.SUPER.in_order):
                scan_l = self.scan()
                if(not scan_l): (scan_l) #TODO remove

                for x in self.SUPER.box_list:
                    if (x.get_symbol() not in scan_l and len(self.SUPER.box_list) == 2):
                        self.SUPER.box_list_remove(x)
                    elif (x.get_symbol() in scan_l):
                        scan_l.remove(x.get_symbol())

                for s in scan_l:
                    if (len(self.SUPER.box_list) < 2):
                        self.SUPER.box_list_append(s)
                        #print("append", s)

                #Display boxes
                if(self.SUPER.stay_alive and not self.SUPER.in_order):
                    print("--current boxes---")
                    for x in self.SUPER.box_list:
                        print(x)
                    print("------------------")

            while(self.paused):
                time.sleep(5)

            if (len(self.SUPER.box_list) < 2):
                for  x in range(0, 35): #Todo lower numbers
                    time.sleep(1)

                    if(not self.stay_alive):
                        break
            else:
                for x in range(0, 65):
                    time.sleep(1)
                    if(not self.stay_alive):
                        break
        self.SUPER.spinner.stop()


class Transaction:  # TODO not working yet only layout

    # Initialize
    def __init__(self, BOX, symbol_unicorn):
        self.BOX = BOX

        self.purchase_price = None
        self.stay_alive = True
        self.symbol_unicorn = symbol_unicorn
        self.a = 1
        self.shut_down_count = 0

        self.profit = 0
        self.sell_price = None
        self.budget = 0.0092  # 50 USD in BTC

    # transaction functions
    def purchase(self):
        self.a = 1 / 14
        self.submit_order()
        self.BOX.buys += 1
        self.maintain()
        self.a = 1

    # Submits best bid and waits until filled
    def sell(self, best_bid):
        self.sell_price = best_bid  # TODO fix to work with binance
        self.profit = self.sell_price - self.purchase_price
        self.BOX.sells += 1
        self.BOX.dat.sell()
        return self.BOX.bid

    def maintain(self):
        Thresh = self.purchase_price - ((0.015 / 100) * self.purchase_price)
        Goal = self.purchase_price + ((0.02 / 100) * self.purchase_price)
        i = 0

        while (self.BOX.stay_alive):
            best_bid = self.BOX.bid
            if (best_bid >= Goal):
                if (not i):
                    Thresh = self.purchase_price
                    Goal = best_bid + (0.02 / 100) * best_bid
                    i += 1
                else:
                    Thresh = best_bid - (0.02 / 100) * best_bid
                    Goal = best_bid + (0.02 / 100) * best_bid
                    i += 1
                print("GOAL", "{:.8f}".format(best_bid))
            if (best_bid < Thresh and (best_bid - self.purchase_price) > 0):
                print("SELL", "{:.8f}".format(best_bid))  # TODO make sell() function
                self.sell(best_bid)  # TODO change this
                break

            # print(Thresh)
            time.sleep(self.a)

        print(self.profit, type(self.profit))

        print('{:.8f}'.format(round(self.profit,8)))
        s = ""
        s = self.BOX.printTime() + " " + str(self.purchase_price) + str(self.sell_price) + " " + str('{:.8f}'.format(self.profit)) + "\n"
        print(s)

    def submit_order(self):  # Sumbits the order to binance and waits until the order is filled to proceed

        # filled = False
        filled = True  # TODO remove
        #submit bid and dont come back until success
        while (not filled):
            time.sleep(self.a)
        self.purchase_price = self.BOX.ask  # Change this later
        self.BOX.buys += 1
        self.BOX.dat.buy()

        print("Order Submitted:", self.symbol_unicorn, "{:.8f}".format(self.purchase_price))  # TODO remove

    def reset(self):
        self.profit = 0
        self.sell_price = None

    # Util
    def get_profit(self):
        return self.profit


class Data(Radar):

    def __init__(self, BOX):

        #Inheritance
        self.BOX = BOX
        self.SUPER = BOX.SUPER

        #Performance data
        self.startTime_box = None
        self.startTime_transaction = None

        #Logs
        self.log = ""

        #SQLite Connector
        self.symbol_ccxt = BOX.symbol_ccxt
        self.conn = sqlite3.connect("transactions.db",timeout=10)
        self.c = self.conn.cursor()

        #Empty Database Check
        self.c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        if(not self.c.fetchall()):
            self.initialize()

    #SQLite Database Initializer
    def initialize(self):

        self.c.execute("""CREATE TABLE transactions (

                        box_hash integer,
                        datetime text,
                        symbol text,

                        vol24 double,
                        vol1hr double,
                        change1yr double,
                        change24hr double,
                        change1hr double,
                        change10min double,
                        change5min double,
                        change1min double,
                        change1min_prev double,

                        purchase_price double,
                        sell_price double,
                        quantity double,
                        profit double,

                        duration_of_cycle double,
                        program_version double
                )""")

        self.c.execute("""CREATE TABLE box_history (

                        box_hash integer,
                        datetime text,
                        symbol text,

                        vol24 double,
                        vol1hr double,
                        change1yr double,
                        change24hr double,
                        change1hr double,
                        change10min double,
                        change5min double,
                        change1min double,
                        change1min_prev double,

                        profit double,
                        num_buys integer,
                        num_sales integer,

                        duration double,
                        program_version double

                )""")

        self.conn.commit()
        print("Database Initialized")

    #main functions
    def open(self):

        self.startTime_box = time.time()

        self.box_hash = hash(self.BOX)
        datetime = self.BOX.printTime(display=False)
        symbol = self.BOX.symbol_ccxt

        vol24 = Radar.get_volume_24hr(self, self.symbol_ccxt)
        vol1hr = Radar.get_volume_1hr(self, self.symbol_ccxt)
        change1yr = Radar.get_change_1yr(self, self.symbol_ccxt)
        change24hr=self.BOX.change24hr
        change1hr=self.BOX.change1hour
        change10min=Radar.get_change_10min(self, self.symbol_ccxt)
        change5min=self.BOX.change5min
        change1min=self.BOX.change1min
        change1min_PREV=self.BOX.change1min_PREV

        duration = None
        program_version = self.last_mod()

        self.c.execute("""INSERT INTO box_history (box_hash, datetime, symbol, vol24, vol1hr, change1yr,
                        change24hr, change1hr, change10min, change5min, change1min, change1min_PREV, program_version) VALUES (?, ?, ?, ?,?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (self.box_hash, datetime, symbol, vol24, "{:.1f}".format(vol1hr), "{:.8f}".format(change1yr),
                            "{:.8f}".format(change24hr), "{:.8f}".format(change1hr), "{:.8f}".format(change10min), "{:.8f}".format(change5min),
                              "{:.8f}".format(change1min), "{:.8f}".format(change1min_PREV), program_version)
                       )

        self.conn.commit()

    def buy(self):

        conn = sqlite3.connect("transactions.db", timeout=10)
        c = conn.cursor()
        self.startTime_transaction = time.time()

        datetime = self.BOX.printTime(display=False)
        symbol = self.BOX.symbol_ccxt
        vol24 = Radar.get_volume_24hr(self, self.symbol_ccxt)
        vol1hr = Radar.get_volume_1hr(self, self.symbol_ccxt)
        change1yr = Radar.get_change_1yr(self, self.symbol_ccxt)
        change24hr=self.BOX.change24hr
        change1hr=self.BOX.change1hour
        change10min=Radar.get_change_10min(self, self.symbol_ccxt)
        change5min=self.BOX.change5min
        change1min=self.BOX.change1min
        change1min_PREV=self.BOX.change1min_PREV
        purchase_price = self.BOX.tran.purchase_price
        program_version = self.last_mod()

        c.execute("""INSERT INTO transactions
                    (box_hash, datetime, symbol, vol24, vol1hr, change1yr,
                    change24hr, change1hr, change10min,
                    change5min, change1min, change1min_PREV, purchase_price, program_version)
                    VALUES (?, ?, ?, ?,?, ?, ?,?, ?, ?, ?, ?, ?, ?)
                    """, (self.box_hash, datetime,  symbol, vol24, "{:.1f}".format(vol1hr), "{:.8f}".format(change1yr),
                        "{:.8f}".format(change24hr), "{:.8f}".format(change1hr), "{:.8f}".format(change10min), "{:.8f}".format(change5min), "{:.8f}".format(change1min),
                          "{:.8f}".format(change1min_PREV), "{:.8f}".format(purchase_price), program_version)
                    )

        conn.commit()

    def sell(self):

        duration_transaction = time.time() - self.startTime_transaction
        profit = self.BOX.tran.profit
        sell_price = self.BOX.tran.sell_price
        quantity = None #TODO fix

        conn = sqlite3.connect("transactions.db", timeout=10)
        c = conn.cursor()

        c.execute("""
                    UPDATE transactions
                    SET profit = ?, duration_of_cycle = ?, sell_price = ?, quantity = ?
                    WHERE box_hash = ?;
                    """, ("{:.8f}".format(profit), int(duration_transaction), "{:.8f}".format(sell_price), quantity, self.box_hash))

        conn.commit()

    def close(self):
        duration_box = time.time() - self.startTime_box
        box_profit = self.BOX.total_profit

        conn = sqlite3.connect("transactions.db", timeout=10)
        c = conn.cursor()
        c.execute("""
                    UPDATE box_history
                    SET profit = ?, duration = ?, num_buys = ?, num_sales = ?
                    WHERE box_hash = ?;
                    """, ("{:.8f}".format(box_profit), int(duration_box), self.BOX.buys, self.BOX.sells, self.box_hash))
        conn.commit()

    #Util
    def log(self, str):
        self.log += str + "\n"

    def timestamp_to_date(self, timestamp):
        dt_object = datetime.datetime.fromtimestamp(timestamp)
        s = str(dt_object)
        i = s.index('.')
        s = s[:i]
        return s

    def last_mod(self, filename="sunshine_sherbert.py"):
        lastmodified = os.stat(filename).st_mtime
        return self.timestamp_to_date(lastmodified)



if __name__ == "__main__":

    def thread_display(str=""):
        # TODO remove
        print(str, len(threading.enumerate()), threading.enumerate())


    if("-s" in sys.argv):
        man = Manager(display=False)
        man.run()
    else:
        man = Manager(display=False)
        man.run()