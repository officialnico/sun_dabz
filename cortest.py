
import asyncio
import functools
import os
import sys
import ccxt.async_support as ccxt  # noqa: E402
from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from unicorn_fy.unicorn_fy import UnicornFy
import threading
import time


class Streamer:

    def __init__(self, symbol_ccxt):
        self.exchange_async = getattr(ccxt, 'binance')({'enableRateLimit': True})  # 'verbose': True
        self.stay_alive = True
        self.paused = False

        self.symbol_ccxt = "BNB/BTC"
        self.symbol_unicorn = "bnbbtc"
        self.a = 1 / 2

        self.price = None
        self.change1hour = None
        self.change1min_PREV = None
        self.change1min = None
        self.change24hr = None
        self.change5min = None

        threading.Thread(name="stream",target=self.stream).start()

        self.run_async()

    async def run_async(self):
        coroutines = [self.stream_hour_candles(), self.stream_minute_candles()]
        res = await asyncio.gather(*coroutines)
        print('hookers and blow')
        return res

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

            time.sleep(self.a * (1 / 4))

        binance_websocket_api_manager.stop_manager_with_all_streams()
        self.shut_down_count += 2
        if (self.messages): print(self.symbol_ccxt, "24hr stream succesfully shut down", "\n")

    async def stream_hour_candles(self):
        while(self.stay_alive):
            try:
                data_hour = await self.exchange_async.fetch_ohlcv(self.symbol_ccxt,timeframe='1h', limit=2)
                open = data_hour[0][4]
                close = data_hour[1][4]
                change1hour = ((close - open) / open) * 100
                print(change1hour)

            except ccxt.NetworkError as e:
                print("EN:", e)
            #await self.exchange_async.close()
            await asyncio.sleep(1)

    async def stream_minute_candles(self):

        while (self.stay_alive):
            try:

                data_min = await self.exchange_async.fetch_ohlcv(self.symbol_ccxt, timeframe='1m', limit=3)

                open_prev = data_min[0][4]
                close_prev = data_min[1][4]

                self.change1min_PREV = ((close_prev - open_prev) / open_prev) * 100
                close = self.price
                self.change1min = ((close - close_prev) / close_prev) * 100
                print('>',self.change1min, self.change1min_PREV)

            except ccxt.NetworkError as e:
                # print("Error (non critical):", e)
                print("1M", e)
                await asyncio.sleep(1)
            #await self.exchange_async.close()
            await asyncio.sleep(1)

    async def stream_5min_candles(self):
        while (self.stay_alive):
            try:
                data_hour = await self.exchange_async.fetch_ohlcv(self.symbol_ccxt, timeframe='5m', limit=2)
                open = data_hour[0][4]
                close = data_hour[1][4]
                change1hour = ((close - open) / open) * 100
                print(change1hour)

            except ccxt.NetworkError as e:
                print("EN:", e)
            # await self.exchange_async.close()
            await asyncio.sleep(1)

if __name__ == '__main__':

    st = Streamer("BNB/BTC")
    asyncio.get_event_loop().run_until_complete(st.run_async())