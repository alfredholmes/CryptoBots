'''Save to orderbook

Script to demonstate websocket order book updates and saving the data to a sqlite database

Author: 
    Alfred Holmes

'''
import sys
sys.path.append("./")


from cryptobots import Binance

import peewee as pw

from cryptobots.exchanges import Trade

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


class Trade(BaseModel):
    market = pw.ForeignKeyField(Market, on_delete='CASCADE', backref='trades')
    time = pw.IntegerField()
    buy = pw.BooleanField() #True if maker is buyer
    price = pw.FloatField()
    volume = pw.FloatField()

def dump_updates(market, orderbook):
    updates = []
    for price, volume in orderbook.bids.items():
        updates.append(BookUpdate(market=market, time=orderbook.previous_time, buy=True, price=price, volume=volume))
    for price, volume in orderbook.asks.items():
        updates.append(BookUpdate(market=market, time=orderbook.previous_time, buy=False, price=price, volume=volume))

    return updates

   

async def handle_order_book_updates(update_queues):
    tasks = [asyncio.create_task(q.get(), name=m) for m, q in update_queues.items()] 

    to_handle, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        await task

    updates = []
           
    for task in to_handle:
        update = task.result()
        time = update['time']
        for price, volume in update['bids']:
            updates.append(BookUpdate(market=int(task.get_name()), time=time, buy=True, price=price, volume=volume))
        for price, volume in update['asks']:
            updates.append(BookUpdate(market=int(task.get_name()), time=time, buy=False, price=price, volume=volume))
        update_queues[int(task.get_name())].task_done()


    return updates

    


async def handle_trades(trade_queues):
    tasks = [asyncio.create_task(q.get(), name=m) for m, q in trade_queues.items()]
    await asyncio.wait(tasks)

    to_handle, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        await task

    updates = []
           
    for task in to_handle:
        update = task.result()
        updates.append(Trade(market=int(task.get_name()), time=update.time, buy=update.buy, price=update.price, volume=update.volume))


    return updates


async def main(args):


    with database: 
        database.create_tables([Asset, Market, BookUpdate, Trade])

    markets = [(a.split('-')[0], a.split('-')[1]) for a in args]
    async with Binance() as exchange:

        print('Subscribing to orderbooks')
        await exchange.subscribe_to_order_books(*markets)
        await exchange.subscribe_to_trade_streams(*markets)
        
        print('listening to updates')
        update_queues = {}
        trade_queues = {}
        market_objects = {}
        for market in markets:
            print(market)
            base, _ = Asset.get_or_create(name=market[0]) 
            quote, _ = Asset.get_or_create(name=market[1])
            m, _ = Market.get_or_create(base=base, quote=quote)
            
            update_queues[m.id] = exchange.order_books[market].passthrough_updates()
            trade_queues[m.id] = exchange.trade_queues[market]
            market_objects[market] = m

        updates = []
        trades = []

        updates_between_dumps = 10 ** 5
        updates_since_dump = updates_between_dumps
        tasks = [
                    asyncio.create_task(handle_trades(trade_queues), name='0'),
                    asyncio.create_task(handle_order_book_updates(update_queues), name='1')
                    ]
        
        while True:
            if len(updates) > 200:
                updates_since_dump += len(updates)
                if updates_since_dump >= updates_between_dumps:
                    print('dumping updates')
                    for market in markets:
                        updates.extend(dump_updates(market_objects[market], exchange.order_books[market]))

                    updates_since_dump = 0
                print('writing updates')
                BookUpdate.bulk_create(updates)
                Trade.bulk_create(trades)
                updates = []
                trades = []

            

            to_handle, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            
            for task in to_handle:
                if task.get_name() == '0':
                    #trade update
                    trades.extend(task.result())
                    tasks[0] = asyncio.create_task(handle_trades(trade_queues), name='0')
                elif task.get_name() == '1':
                    updates.extend(task.result())
                    tasks[1] = asyncio.create_task(handle_order_book_updates(update_queues), name='1')


if __name__=='__main__':
    asyncio.run(main(sys.argv[1:]))
