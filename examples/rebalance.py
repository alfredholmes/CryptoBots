import sys
sys.path.append("./")
import keys
from binancebots.orderbooks import OrderBookManager
from binancebots.accounts import SpotAccount

import asyncio



async def main():
	order_books = OrderBookManager()
	acc = SpotAccount(keys.API, keys.SECRET, order_books)


	await acc.get_account_data()
	print(acc.spot_balances)


	await acc.close()
	

if __name__ == '__main__':
	asyncio.run(main())