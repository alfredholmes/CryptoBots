import sys
sys.path.append("./")
import keys
from binancebots.orderbooks import OrderBookManager
from binancebots.account import account


import httpx
import asyncio



async def main():
	acc = account(keys.API, keys.SECRET)


	await acc.get_account_data()
	print(acc.spot_balances)

	await acc.close()

if __name__ == '__main__':
	asyncio.run(main())