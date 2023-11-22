'''Save to orderbook

Script to demonstate websocket order book updates and saving the data to a sqlite database

Author: 
    Alfred Holmes

'''
import sys
sys.path.append("./")


from cryptobots import Binance

import peewee as pw

import asyncio

database = pw.SqliteDatabase('market_data.db', pragmas={'foreign_keys': 1})

class BaseModel(pw.Model):
    class Meta:
        database = database

class Asset(BaseModel):
    name = pw.CharField(unique=True)

class Market(BaseModel):
    base = pw.ForeignKeyField(Asset, on_delete='CASCADE', backref='markets')
    quote = pw.ForeignKeyField(Asset, on_delete='CASCADE', backref='market_quotes')


class BookUpdate(BaseModel):
    market = pw.ForeignKeyField(Market, on_delete='CASCADE', backref='updates')
    time = pw.IntegerField()
    buy = pw.BooleanField()  #True for buy
    price = pw.FloatField()
    volume = pw.FloatField()






async def main(args):


    with database: 
        database.create_tables([Asset, Market, BookUpdate])

    markets = [(a.split('-')[0], a.split('-')[1]) for a in args]
    async with Binance() as exchange:

        print('Subscribing to orderbooks')
        await exchange.subscribe_to_order_books(*markets)
        
        print('listening to updates')
        update_queues = {}
        for market in markets:
            print(market)
            base, _ = Asset.get_or_create(name=market[0]) 
            quote, _ = Asset.get_or_create(name=market[1])
            m, _ = Market.get_or_create(base=base, quote=quote)
            
            update_queues[m.id] = exchange.order_books[market].passthrough_updates()

        updates = []
        while True:
            if len(updates) > 200:
                print('writing updates')
                BookUpdate.bulk_create(updates)
                updates = []
            to_handle, pending = await asyncio.wait([asyncio.create_task(q.get(), name=m) for m, q in update_queues.items()], return_when=asyncio.FIRST_COMPLETED)
            for task in to_handle:
                update = task.result()
                time = update['time']
                for price, volume in update['bids']:
                    updates.append(BookUpdate(market=int(task.get_name()), time=time, buy=True, price=price, volume=volume))
                for price, volume in update['asks']:
                    updates.append(BookUpdate(market=int(task.get_name()), time=time, buy=False, price=price, volume=volume))
                update_queues[int(task.get_name())].task_done()

if __name__=='__main__':
    asyncio.run(main(sys.argv[1:]))
