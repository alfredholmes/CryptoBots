'''Ticker

Script to demonstate websocket order book updates 

Author: 
    Alfred Holmes

'''


import asyncio

import sys
sys.path.append("./")

from cryptobots import Binance



async def main(args):

    print('connecting...')
    markets = [(a.split('-')[0], a.split('-')[1]) for a in args]
    async with Binance() as binance:
        print('subscribing to trades')
        await binance.subscribe_to_trade_streams(*markets)

        for i in range(10):
            trade = await binance.trade_queues[markets[0]].get()
            print(trade.price, trade.volume)
            binance.trade_queues[markets[0]].task_done()

        print('closing connections...')

if __name__=='__main__':
    asyncio.run(main(sys.argv[1:]))
