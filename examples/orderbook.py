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
        print('subscribing to order books')
        await binance.subscribe_to_order_books(*markets)

        for i in range(100):
            for market in markets:
                print(f'{market[0]}-{market[1]}:', binance.order_books[market].mid_price())
            await asyncio.sleep(1)

        print('closing connections...')

if __name__=='__main__':
    asyncio.run(main(sys.argv[1:]))
