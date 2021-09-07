'''Ticker

Script to demonstate websocket order book updates 

Author: 
	Alfred Holmes

'''


import asyncio

import sys
sys.path.append("./")


from cryptobots.connections import ConnectionManager
from cryptobots.exchanges import FTXSpot
from cryptobots.accounts import FTXAccount 
import keys_ftx as keys




async def main(args):

	#connect to FTX spot
	async with ConnectionManager('https://ftx.com', 'wss://ftx.com/ws') as connection_manager:
		ftx = FTXSpot(connection_manager)	
		await ftx.get_exchange_info()
		
		pairs = [tuple(pair.split('-')) for pair in args]
		await ftx.subscribe_to_order_books(*pairs)
		
		while True:
			for pair in pairs:
				print(pair[0] + '-' + pair[1] + ' mid price: ',ftx.order_books[pair].mid_price())	
			print()
			await asyncio.sleep(0.5)


if __name__=='__main__':
	asyncio.run(main(sys.argv[1:]))
