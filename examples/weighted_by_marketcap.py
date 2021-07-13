import sys
sys.path.append("./")
import keys
from binancebots.accounts import SpotAccount

import asyncio

TRADE_FROM = 'BUSD'
SELECTION = ['BNB', 'ADA', 'DOT', 'UNI','BCH', 'LTC', 'SOL', 'LINK', 'MATIC', 'THETA']

#Supply to calculate market cap, data from coinmarketcap.com
SUPPLY = {'BNB': 153432897, 'ADA': 32041069499, 'DOT': 974829029, 'UNI': 587291071, 'BCH': 18788269, 'LTC': 66752415, 'SOL': 272637428, 'LINK': 438509554, 'MATIC': 6330554997, 'THETA': 1000000000}
async def main():
	#create SpotAccount object to manage the account
	acc = SpotAccount(keys.API, keys.SECRET)
	orderbook_manager = acc.orderbook_manager

	#subscribe to the depths of the selection
	await orderbook_manager.subscribe_to_depths(*((s + TRADE_FROM).lower() for s in SELECTION))

	#calculate the target portfolio...
	target_portfolio = {s: SUPPLY[s] * orderbook_manager.books[(s + TRADE_FROM).lower()].market_buy_price() for s in SELECTION}

	target_portfolio['BUSD'] = 0
	print('Attempting to trade to ', target_portfolio)

	await acc.trade_to_portfolio(target_portfolio)
	
	weighted = await acc.weighted_portfolio()
	print('Final portfolio: ', weighted)

	await acc.close()
	

if __name__ == '__main__':
	asyncio.run(main())
