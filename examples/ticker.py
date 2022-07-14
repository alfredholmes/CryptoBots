'''Ticker

Script to demonstate websocket order book updates 

Author: 
    Alfred Holmes

'''


import asyncio

import sys
sys.path.append("./")


from cryptobots import FTX
from cryptobots import Binance



async def main(args):

    #connect to FTX spot
    print('connecting...')
    async with FTX() as ftx, Binance() as binance:
        print('subscribing to order books')
        await ftx.subscribe_to_order_books(('BTC', 'USD'))
        await binance.subscribe_to_order_books(('BTC', 'USDT'))

        for i in range(10):
            print(ftx.order_books[('BTC', 'USD')].mid_price(), binance.order_books[('BTC', 'USDT')].mid_price())
            await asyncio.sleep(1)

if __name__=='__main__':
    asyncio.run(main(sys.argv[1:]))
