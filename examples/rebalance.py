import sys
sys.path.append("./")
import keys
from binancebots.orderbooks import OrderBookManager
from binancebots.accounts import SpotAccount

import asyncio



async def main():
	acc = SpotAccount(keys.API, keys.SECRET)
	await acc.get_account_data()

	await acc.trade_to_portfolio({'BTC': 0.3333333333333333, 'ETH': 0.3333333333333333, 'USDT': 0.3333333333333333})

	await acc.close()
	

if __name__ == '__main__':
	asyncio.run(main())