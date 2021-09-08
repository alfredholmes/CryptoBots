'''FTX

Script to FTX order placement and account information 

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




async def main():

	#connect to FTX spot api endpoints
	async with ConnectionManager('https://ftx.com', 'wss://ftx.com/ws') as connection_manager:
		ftx = FTXSpot(connection_manager)	
		await ftx.get_exchange_info()

		account = FTXAccount(keys.API, keys.SECRET, ftx, keys.SUBACCOUNT) 
		await account.subscribe_to_user_data()
		
		print(account)
		#print('Buying 10 dollars worth of BTC with USD')
		#await account.market_order('BTC', 'USD', 'BUY', quote_volume=10)
		#await asyncio.sleep(0.1) #sleep to allow orders to process
		#print(account)

if __name__=='__main__':
	asyncio.run(main())
