'''Binance Account

Script to demonstrate binance account interaction, script calculates the value of the spot account in BTC and USDT 

Author: 
	Alfred Holmes

'''


import asyncio

import sys
sys.path.append("./")


from cryptobots.connections import ConnectionManager
from cryptobots.exchanges import BinanceSpot
from cryptobots.accounts import Account 
from cryptobots.trader import Trader
import keys
import datetime



async def main():

	#connect to FTX spot api endpoints
	async with ConnectionManager('https://api.binance.com', 'wss://stream.binance.com:9443/stream') as connection_manager:
		binance = BinanceSpot(connection_manager)	
		await binance.get_exchange_info()

		account = Account(keys.API, keys.SECRET, binance) 
		await account.get_balance()	
		trader = Trader(account, binance, account.balance, [asset for asset in account.balance], ['BTC', 'USDT'])
		await trader.get_trading_markets()	
		print(datetime.datetime.now(), 'BTC: ', sum(trader.portfolio_values(account.balance).values()), ' USDT:', sum(trader.portfolio_values(account.balance, 'USDT').values()))

if __name__=='__main__':
	asyncio.run(main())
