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

        for i in range(10):
            for market in markets:
                print(f'{market[0]}-{market[1]}')
                print('---------------------------')
                print('Bid \t\t | Volume ')
                print('---------------------------')
                for v in binance.order_books[market].get_bids():
                    print(f'{v} \t | {binance.order_books[market].bids[v]}')
                print('---------------------------')
                print('Ask \t\t | Volume')
                print('---------------------------')
                for v in binance.order_books[market].get_asks():
                    print(f'{v} \t | {binance.order_books[market].asks[v]}')
                print('---------------------------')
            await asyncio.sleep(1)

        print('closing connections...')

if __name__=='__main__':
    asyncio.run(main(sys.argv[1:]))
