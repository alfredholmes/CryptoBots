import sys
sys.path.append("./")
import keys
from orderbooks import OrderBookManager
from account import account


import httpx
import asyncio



async def main():
	client = httpx.AsyncClient()
	order_books = OrderBookManager()
	acc = account(client, keys.API, keys.SECRET, order_books)


	await acc.get_account_data()
	print(acc.spot_balances)

	await client.aclose()

if __name__ == '__main__':
	asyncio.run(main())