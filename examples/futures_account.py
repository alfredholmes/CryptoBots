import sys
sys.path.append("./")
import keys
from binancebots.accounts import USDTFuturesAccount 

import asyncio

async def main():
	account = USDTFuturesAccount(keys.API, keys.SECRET)
	await account.connect()
	
	await account.orderbook_manager.subscribe_to_depths('btcusdt')
	await account.market_buy('BTC', 'USDT', 0.001)

	await account.close()


if __name__=='__main__':
	asyncio.run(main())
