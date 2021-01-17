import sys
sys.path.append("./")
import keys
from binancebots.orderbooks import OrderBookManager
from binancebots.accounts import SpotAccount

import asyncio



async def main():
	acc = SpotAccount(keys.API, keys.SECRET)


	await acc.track_orderbooks('btcusdt', 'ethusdt','ethbtc')
	portfolio = await acc.weighted_portfolio()
	


	await acc.close()
	

if __name__ == '__main__':
	asyncio.run(main())