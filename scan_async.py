from sunshine_sherbert import Manager as M
from tqdm import tqdm
from colorama import Fore
import time
import asyncio

class ScanBetter:

    def __init__(self, SUPER):
        self.SUPER = SUPER
        self.stay_alive = self.SUPER.stay_alive
        self.paused = self.SUPER.in_order

    async def scan(self):
        # Although this isnt pretty its efficient and it works, after being tested multiple times with different methods of execution
        ref_list = []
        print(self.SUPER)
        await self.SUPER.exchange_async.load_markets()
        symbols = self.SUPER.exchange_async.symbols
        refined_mega_markets = self.SUPER.get_markets()

        dis = self.SUPER.display
        if (dis):
            bar = tqdm(total=len(refined_mega_markets), position=0, leave=False,
                       bar_format="{l_bar}%s{bar}%s{r_bar}" % (Fore.GREEN, Fore.RESET))
        else:
            print("Scanning...", len(refined_mega_markets), "markets")

        for x in refined_mega_markets:
            change24temp = await self.get_change_24hr(x)
            while (change24temp is None):  # TODO check over, should help
                change24temp = await self.get_change_24hr(x)
                await asyncio.sleep(2)
            if (change24temp >= 4 and (await self.get_change_1hr(x)) >= 0.3 and await self.get_volume_1hr(x) > 98247):  # 369214.97
                ref_list.append(x)

            elif (change24temp < 3 or (await self.get_change_1hr(x)) < 0.2 or await self.get_volume_24hr(x) < 250033):
                refined_mega_markets.remove(x)
                if (dis):
                    bar.update(1)

            if (dis):
                bar.set_description("Scanning...".format(x))
                bar.update(1)

            if (not self.stay_alive or self.SUPER.in_order):
                if (dis): bar.close()
                return

        if (dis): bar.close()

        if (len(ref_list) > 2):
            m1 = None
            m2 = None
            max_symbol = ref_list[0]
            max_change = await self.get_change_1w(max_symbol)
            for x in ref_list:
                change_w = await self.get_change_1w(x)
                if (change_w > max_change):
                    max_change = change_w
                    max_symbol = x
                if (dis): bar.update(1)
            m1 = max_symbol
            ref_list.remove(m1)

            max_symbol = ref_list[0]
            max_change = await self.get_change_1w(max_symbol)
            for x in ref_list:
                change_w = await self.get_change_1w(x)
                if (change_w > max_change):
                    max_change = change_w
                    max_symbol = x
            m2 = max_symbol
            ref_list = [m1, m2]

        self.SUPER.set_markets(refined_mega_markets)

        if (self.stay_alive and ref_list):
            print("Scan Completed", ref_list)
        if (len(refined_mega_markets) < 2):
            self.SUPER.load_markets(store=True)

        await self.SUPER.exchange_async.close()
        return ref_list

    #First async test
    async def get_change_24hr(self, symbol_ccxt):

        try:
            tick = await self.SUPER.exchange_async.fetchTicker(symbol_ccxt)
            return tick['percentage']
        except ccxt.NetworkError as e:
            print("RC24:",e)
            await asyncio.sleep(1)

    #---------------- #second
    async def get_change_1hr(self, symbol_ccxt):
        try:
            data_hour = await self.SUPER.exchange_async.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=2)
            open = data_hour[0][4]
            if(len(data_hour)<2):print(data_hour, symbol_ccxt) #TODO remove
            close = data_hour[len(data_hour)-1][4]

            change1hour = ((close - open) / open) * 100
            return change1hour
        except ccxt.NetworkError as e:
            print("C1R",e)
            await asyncio.sleep(1)
    #-------------------]

    async def get_change_1w(self, symbol_ccxt):
        try:
            data_hour = await self.SUPER.exchange_async.fetchOHLCV(symbol_ccxt, timeframe='1w', limit=2)
            open = data_hour[0][4]
            close = data_hour[len(data_hour)-1][4]

            change1w = ((close - open) / open) * 100
            return change1w
        except ccxt.NetworkError as e:
            print("C1WR",e)
            await asyncio.sleep(1)

    async def get_volume_1hr(self, symbol_ccxt):
        try:
            data_hour = await self.SUPER.exchange_async.fetchOHLCV(symbol_ccxt, timeframe='1h', limit=1)
            return data_hour[0][5]
        except ccxt.NetworkError as e:
            print("V24R",e)
            await asyncio.sleep(1)

    async def get_volume_24hr(self, symbol_ccxt):  # TODO try using 1hr volume instead to guarantee trades
        try:
            data_hour = None
            while(data_hour is None):
                data_hour = await self.SUPER.exchange_async.fetchOHLCV(symbol_ccxt, timeframe='1d', limit=1)
            return data_hour[0][5]
        except ccxt.NetworkError as e:
            print("V24R:",e)
            asyncio.sleep(1)


if __name__=="__main__":
    man = M()
    s = ScanBetter(man)
    t = time.time()
    asyncio.get_event_loop().run_until_complete(s.scan())
    print(time.time()-t)
