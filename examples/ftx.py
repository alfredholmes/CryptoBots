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
from cryptobots.trader import Trader
import keys_ftx as keys




async def main():

	#connect to FTX spot api endpoints
	async with ConnectionManager('https://ftx.com', 'wss://ftx.com/ws') as connection_manager:
		ftx = FTXSpot(connection_manager)	
		await ftx.get_exchange_info()

		account = FTXAccount(keys.API, keys.SECRET, ftx, keys.SUBACCOUNT) 
		await account.subscribe_to_user_data()
			
		print(account)
		assets = ['BTC', 'ETH', 'SOL', 'USD']
		
		trader = Trader(account, ftx, assets, ['USD'])
		await trader.get_trading_markets(100000)
		target_portfolio = {'BTC': 0.0, 'ETH': 0.2, 'SOL': 0.5, 'USD': 0.0}
		#target_portfolio = {'MTL': 0.0, 'BTC': 1.0, 'ETH': 0.0, 'SOL': 0.0, 'USD': 0.0}



		await trader.trade_to_portfolio(target_portfolio, 'USD')

if __name__=='__main__':
	asyncio.run(main())
