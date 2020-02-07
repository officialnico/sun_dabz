import ccxt
import time
import pprint
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from unicorn_fy.unicorn_fy import UnicornFy
import threading
import os

symbol_ccxt = 'BNB/USDT'
symbol_unicorn = "bnbusdt"


change24hr = None
change5min = None
change1hour = None #WORKS
change1min = None
change1min_PREV = None

####TEST FOR CONDITIONAL
first_time = True

price = None #works
in_order = False
a = 1 #Time coefficient #! Lower -> Faster   Higher -> Slower

total_profit = 0
fees = 0





exchange = ccxt.binance(
    {'enableRateLimit': True})  # this option enables the built-in rate limiter (no ip ban)

def stream(): #streams 24hour ticker

    while True:
        oldest_stream_data_from_stream_buffer = binance_websocket_api_manager.pop_stream_data_from_stream_buffer()
        if oldest_stream_data_from_stream_buffer:
            stream_data = UnicornFy.binance_com_websocket(oldest_stream_data_from_stream_buffer)
            #pprint.pprint(stream_data)

            if(stream_data['event_type']=="24hrTicker"):
            #set 24hr change to the value there
                global change24hr
                change24hr=float(stream_data['data'][0]['price_change_percent'])

            time.sleep(a*(1/2))

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
            time.sleep(a*(1/2))


def stream_hour_candles(): #WORKS
    while(1):
        data_hour = exchange.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=2)
        global change1hour
        open = data_hour[0][4]

        close = price
        change1hour = ((close - open) / open) * 100
        time.sleep(a*(1/2))

def stream_minute_candles():
    while(1):
        data_min = exchange.fetchOHLCV(symbol_ccxt, timeframe='1m', limit=3)
        global change1min_PREV

        open_prev = data_min[0][4]
        close_prev = data_min[1][4]
        change1min_PREV = ((close_prev - open_prev) / open_prev) * 100

        global change1min
        close= price
        change1min = ((close - close_prev) / close_prev) * 100

        time.sleep(a*(1/2))

def stream_5min_candle():
    while(1):
        data_hour = exchange.fetchOHLCV(symbol_ccxt, timeframe='5m', limit=2)
        global change5min
        open = data_hour[0][4]

        close = price
        change5min = ((close - open) / open) * 100
        time.sleep(a*(1/2))

def purchase():
    global in_order
    in_order=True

    #submit best bid
    #if gotten, set purchase price
    #for now we'll use the price as purchase price
    purchase_price = price #TODO make purchase price the actual one
    maintain(purchase_price) #TODO send tradeID as well
    return

def sell():
    global in_order
    in_order=False
    return price #TODO actual sell price

def maintain(purchase_price):
    fake_attempts = open("fake_attempts.txt", 'a')
    Thresh = purchase_price - (0.015 / 100) * purchase_price
    Goal = purchase_price + (0.02 / 100) * purchase_price
    sell_price = None
    i = 0

    while(in_order):
        if(price>=Goal):
            if(i==0):
                Thresh = purchase_price
                Goal = price + (0.02 / 100) * price
                i+=1
            elif(i>0):
                Thresh = price - (0.02 / 100) * price
                Goal = price + (0.02 / 100) * price
                i+=1
            print("GOAL")
        if(price<Thresh):
            print("SELL") #TODO make sell() function
            sell_price=sell()

        #print(Thresh)
        time.sleep((1/4)*a)

    profit = sell_price-purchase_price
    global total_profit
    total_profit += profit
    print(profit)
    s =""
    s = str(time.time()) + " " + str(purchase_price) + str(sell_price) + " " + str(profit)
    fake_attempts.write(s)
    fake_attempts.close()

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
min5_candles_Thread = threading.Thread(target=stream_5min_candle)
time.sleep(3)

min5_candles_Thread.start()
stream_price_Thread.start()
min_candles_Thread.start()
hr_candles_Thread.start()
time.sleep(2) #let the thread start


while(1):
    # print("Change1Min:", change1min)
    # print("Change1Min_Prev:", change1min_PREV)
    # print("24Hr:",change24hr)
    # print("5min:",change5min)

    conditional = (change1min_PREV>=0.04) and (change1min>=0.07) and (change5min>=0.22) and (change1hour>=0.3) and (change24hr>=4)
    print(conditional)
    # if(conditional and not in_order):
    #     purchase()

    ### !! TEST ###+---
    if(not in_order):
        print("PURCHASE")
        purchase()

    if(conditional and not in_order and  first_time):
        purchase()
        s = str(time.time()) + " " + str(conditional)
        doc = open("log.txt", 'a')
        doc.write(s)
        doc.close()


    print("change1min_PREV>=0.04",change1min_PREV>=0.04)
    print("change1min>=0.07",change1min>=0.07)
    print("change5min>=0.22",change5min>=0.22)
    print("change1hour>=0.3",change1hour>=0.3)
    print("change24hr>=4",change24hr>=4)
    print("TOTAL PROFITS -> ", total_profit)

    ### !! TEST ###+---

    time.sleep(a*(1/2))
    #os.system('cls' if os.name == 'nt' else 'clear') #clears screen

