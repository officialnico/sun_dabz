import csv
import os
import pathlib
import numpy as np
import matplotlib.pyplot as plt
import ccxt

wallet = {}
data_list = []
filename = None
exchange = ccxt.binance()

def toBitcoin(symbol, amount):
    if(symbol=="BTC"):
        return amount
    elif(symbol=="USDT"):
        #return amount/getBitcoinPrice()
        return a

    data=exchange.fetchTicker(symbol+"/BTC")
    print(data)

def getBitcoinPrice():
     exchange.fetchTicker("BTC/USDT")

for x in os.listdir("./"):
    if('.csv' in x):
        filename = x
        break

if(not filename):
    print("Download binance refferal data .csv file into: ", pathlib.Path(__file__).parent.absolute())
    exit()

with open(filename, newline='') as csvfile:
     spamreader = csv.reader(csvfile, delimiter=' ', quotechar='|')
     for row in spamreader:
         if(len(row)==1):
             continue
         data = row[1].split(',')
         data_list.append(data)
         print(data)

for x in data_list:
    time = x[0]
    amount = float(x[1])
    symbol = x[2]

    if(symbol not in wallet):
        wallet.update({symbol:amount})
    else:
        wallet[symbol] += amount

for symbol in wallet:
    amount = wallet[symbol]
    print(toBitcoin(symbol, amount))

print(wallet)



#get the total ticoin value for bitcoin, will have to make a toBitcoin function tomorrow