import sys
sys.path.append("./")
import keys
from binancebots.orderbooks import OrderBookManager
from binancebots.accounts import SpotAccount

import asyncio



async def main():
	acc = SpotAccount(keys.API, keys.SECRET)
	await acc.get_account_data()

	weighted_portfolio = await acc.weighted_portfolio(['USDT', 'BTC', 'ETH'])
	print(weighted_portfolio)

	await acc.close()
	

if __name__ == '__main__':
	asyncio.run(main())