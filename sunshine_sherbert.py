import time
import threading
import os
import datetime
import sys
import webbrowser

from tqdm import tqdm
from colorama import Fore
from yaspin import yaspin
from yaspin.spinners import Spinners

import ccxt
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from unicorn_fy.unicorn_fy import UnicornFy


class Manager:

    # Initialization
    def __init__(self, in_order=False, a=1, mega_markets=None):

        #Super Variables
        self.in_order = in_order
        self.a = 1
        self.box_list = list()
        self.total_profit = 0

        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.stay_alive = True

        if os.name == 'nt':
            chrome_path = "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
            webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(chrome_path))

        if (mega_markets is None):
            self.mega_markets = self.load_markets()
        else:
            self.mega_markets = mega_markets

    # Main Functions
    def run(self):
        self.rad = Radar(self)
        self.rad.run()

    def shutdown(self,override=False):
        self.stay_alive = False
        while(self.in_order):
            time.sleep(1)
        print("Shutdown...")
        self.shutdown_boxes()
        self.rad.stay_alive = False

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
    def box_list_append(self, symbol_ccxt):
        for x in self.box_list:
            if(x.get_symbol() == symbol_ccxt):
                return
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


class Box:

    # Initialization
    def __init__(self, SUPER, symbol_ccxt, messages=False):

        self.SUPER = SUPER

        # TODO remove
        #print("box init:", symbol_ccxt, len(threading.enumerate()), threading.enumerate())

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

        # Thread Control
        self.stay_alive = True
        self.shut_down_count = 0
        self.messages = messages
        self.paused = False

        # Threads for streaming prices from both API's
        self.t1 = threading.Thread(target=self.stream, name="box_price&24hr_change")  # 24hr & Price stream from ccxt
        self.min_candles_Thread = threading.Thread(target=self.stream_minute_candles, name="box_min_candles")
        self.hr_candles_Thread = threading.Thread(target=self.stream_hour_candles, name="box_hour_candles")
        self.min5_candles_Thread = threading.Thread(target=self.stream_5min_candle, name="box_min5_candles")
        self.main_Thread = threading.Thread(target=self.main, name="box_main")  # Main Thread

        # Transaction data
        self.profit = None

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
            except ccxt.NetworkError as e:
                # print("Error (non critical):", e)
                time.sleep(1)

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
                # print("Error (non critical):", e)
                time.sleep(1)
            time.sleep(self.SUPER.a * (1 / 2))

        self.shut_down_count += 1
        if (self.messages): print(self.symbol_ccxt, "5min stream succesfully shut down")

    # Functions
    def printBools(self, clear=False):  # TODO Remove later
        while (self.stay_alive):
            print("change1min_PREV>=0.04", self.change1min_PREV >= 0.04, round(self.change1min_PREV, 3), "%")
            print("change1min>=0.07", self.change1min >= 0.07, round(self.change1min, 3), "%")
            print("change5min>=0.22", self.change5min >= 0.22, round(self.change5min, 3), "%")
            print("change1hour>=0.3", self.change1hour >= 0.3, round(self.change1hour, 3), "%")

            time.sleep(1 * self.SUPER.a)
            if clear: clearScreen()

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
        print(self.symbol_ccxt, self.tran.printTime(display=False))

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
        spinner = yaspin(Spinners.moon, text="Box loading...")
        spinner.start()

        # Start Streams
        self.t1.start()

        if (self.price is None): spinner.text = "loading price"
        while (self.price is None):
            time.sleep(1 / 3)
        if (self.price is None): spinner.text = "loading tran"

        self.min_candles_Thread.start()
        self.hr_candles_Thread.start()
        self.min5_candles_Thread.start()

        while (
                self.change1min is None or self.change1min_PREV is None or self.change1hour is None or self.change5min is None or self.change24hr is None or self.ask is None or self.bid is None):  # TODO check tran

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
        spinner.stop()

        self.main_Thread.start()

    def purchase(self):
        self.SUPER.pause_others(self.symbol_ccxt)
        self.SUPER.in_order = True
        self.tran.purchase()
        self.SUPER.total_profit += self.tran.get_profit()  # TODO fix
        self.tran.reset()
        self.SUPER.in_order = False
        print("TOTALPROFIT->", self.SUPER.total_profit)
        self.SUPER.pause_others(self.symbol_ccxt, pause=False)

    def stop(self):
        if (self.messages): print(self.symbol_ccxt, "Shutting down...")
        self.stay_alive = False
        while (self.shut_down_count != 6):
            time.sleep(1 / 3)

        print(self.symbol_ccxt, "Succesfully Closed")

    # Pausing
    def pause(self):
        self.paused = True

    def unpause(self):
        self.paused = False


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
        bar = tqdm(total=len(refined_mega_markets), position=0, leave=False,
                   bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Fore.RESET))

        for x in refined_mega_markets:
            change24temp = self.get_change_24hr(x)
            if (change24temp >= 4 and self.get_change_1hr(x) >= 0.3 and self.get_volume_24hr(x) > 270033):
                ref_list.append(x)
            elif (change24temp < 3 or self.get_change_1hr(x) < 0.2 or self.get_volume_24hr(x) < 250033):
                refined_mega_markets.remove(x)
                bar.update(1)
            bar.set_description("Scanning...".format(x))
            bar.update(1)
            if(not self.stay_alive):
                break

        bar.close()

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
                bar.update(1)
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

        print("Scan Completed", ref_list)
        if (len(refined_mega_markets) < 2):
            self.SUPER.load_markets(store=True)

        return ref_list

    # Data retrieval
    def get_change_24hr(self, symbol_ccxt):
        try:
            tick = self.SUPER.exchange.fetchTicker(symbol_ccxt)
            return tick['percentage']
        except ccxt.NetworkError as e:
            print(e)
            time.sleep(1)
            self.get_change_24hr(symbol_ccxt)

    def get_volume_24hr(self, symbol_ccxt):  # TODO try using 1hr volume instead to guarantee trades
        try:
            data_hour = self.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='1d', limit=1)
            return data_hour[0][5]
        except ccxt.NetworkError as e:
            print(e)
            time.sleep(1)
            self.get_volume_24hr(symbol_ccxt)

    def get_change_1hr(self, symbol_ccxt):
        try:
            data_hour = self.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=2)
            open = data_hour[0][4]
            close = data_hour[1][4]

            change1hour = ((close - open) / open) * 100
            return change1hour
        except ccxt.NetworkError as e:
            print(e)
            time.sleep(1)
            self.get_change_1hr(symbol_ccxt)

    def get_volume_1hr(self):
        try:
            data_hour = self.SUPER.exchange.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=1)
            print(data_hour[0][5]) #TODO remove
            return data_hour[0][5]
        except ccxt.NetworkError as e:
            print(e)
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
            print(e)
            time.sleep(1)
            self.get_change_1w(symbol_ccxt)

    #Active updater
    def update_boxes(self):  # TODO fix boxes get deleted

        while (self.stay_alive):

            while (self.SUPER.in_order or self.paused):
                time.sleep(5)

            if (not self.SUPER.in_order):
                scan_l = self.scan()

                for x in self.SUPER.box_list:
                    if (x.get_symbol() not in scan_l and len(self.SUPER.box_list) == 2 and len(scan_l) == 2):
                        self.SUPER.box_list_remove(x)
                    elif (x.get_symbol() in scan_l):
                        scan_l.remove(x.get_symbol())

                for s in scan_l:
                    if (len(self.SUPER.box_list) < 2):
                        self.SUPER.box_list_append(s)
                        #print("append", s)

                # TODO remove
                print("--current boxes---")
                for x in self.SUPER.box_list:
                    print(x)
                print("------------------")

            while(self.paused):
                time.sleep(5)

            if (len(self.SUPER.box_list) < 2):
                for  x in range(0, 3):
                    time.sleep(10)

                    if(not self.stay_alive):
                        break
            else:
                for x in range(0, 3):
                    time.sleep(25)
                    if(not self.stay_alive):
                        break

        print("update_boxes shut")


class Transaction:  # TODO not working yet only layout

    # Initialize
    def __init__(self, BOX, symbol_unicorn):
        print("BOX", BOX)
        self.BOX = BOX

        self.purchase_price = None
        self.stay_alive = True
        self.symbol_unicorn = symbol_unicorn
        self.a = 1
        self.shut_down_count = 0

        self.profit = 0
        self.sell_price = None
        self.budget = 0.0092  # 50 USD in BTC

        # self.binance_websocket_api_manager = BinanceWebSocketApiManager(exchange="binance.com")  # websocket connection
        # self.binance_websocket_api_manager.create_stream(["ticker"], [self.symbol_unicorn])

    # transaction functions
    def purchase(self):
        self.a = 1 / 14
        self.  der()
        self.maintain()
        self.a = 1

    # Submits best bid and waits until filled
    def sell(self, best_bid):
        self.sell_price = best_bid  # TODO fix to work with binance
        self.profit = self.sell_price - self.purchase_price
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

        print(self.profit)
        s = ""
        s = self.printTime() + " " + str(self.purchase_price) + str(self.sell_price) + " " + str(self.profit) + "\n"
        print(s)

    def submit_order(self):  # Sumbits the order to binance and waits until the order is filled to proceed

        # filled = False
        filled = True  # TODO remove

        # TODO submit bid and dont come back until success

        while (not filled):
            time.sleep(self.a)

        self.purchase_price = self.BOX.ask  # Change this later

        self.BOX.SUPER.open_chart(self.BOX.symbol_ccxt)

        print("Order Submitted:", self.symbol_unicorn, "{:.8f}".format(self.purchase_price))  # TODO remove

    def reset(self):
        self.profit = 0
        self.sell_price = None

    # Util
    def printTime(self, display=True):  # TODO double method you could just make the box use this
        now = datetime.datetime.now()
        s = now.strftime("%Y-%m-%d %H:%M:%S")
        if (display): print(s)
        return s

    def get_profit(self):
        return self.profit


if __name__ == "__main__":

    def thread_display(str=""):
        # TODO remove
        print(str, len(threading.enumerate()), threading.enumerate())


    man = Manager()
    man.run()
#     man.open_chart("BNB/BTC")

