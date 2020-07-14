# Buying low, selling high
The Simple idea is to buy low and sell high on binance 1 minute candles (checkout the async branch)

## Manager(in_order=False, a=1, mega_markets=None, display=True):
### run(updater=True)

  -> Activates whole process

## Radar
### update_boxes(): 

  -> scans

  -> adds new boxes

  -> removes old boxes

  -> constant thread other than when in order

  -> slower when in an order
  

### scan():

-> returns markets suitable for box creation 
      {s1, s2}
      
-> searches through all markets and decreases the number by half until 0

## Box
Monitors a coin and controls the transaction object, telling it when to buy and sell
### Run()
Starts the box on a separate thread


## Transactions
A swiss army knife of functions you would need to buy and sell



![](images/sunset.jpg)
![](images/dabs.jpg)
