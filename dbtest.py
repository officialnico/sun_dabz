import sqlite3
from os import path



#conn = sqlite3.connect("transactions.db")
conn = sqlite3.connect(":memory:")

c = conn.cursor()


c.execute("""CREATE TABLE purchases (
                box_hash integer, 
                vol24 double,
                vol1hr double,
                change24hr double,
                change1hr dowuble,
                change10min double,
                change5min double,
                change1min double,
                change1min_prev double,
                completed integer,
                
                version double
        )""")
c.execute("""CREATE TABLE sales (
                hbox_hash integer, 
                vol24 double,
                vol1hr double,
                change24hr double,
                change1hr double,
                change10min double,
                change5min double,
                change1min double,
                change1min_prev double,        
                
                profit double,
                duration_of_cycle double,
                version double,
                date text
        )""")

conn.commit()
print(__hash__)