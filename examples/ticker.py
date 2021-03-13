import sys
sys.path.append("./")
import keys
from binancebots.orderbooks import OrderBookManager


import httpx
import asyncio



async def main(symbols):
	print(symbols)
	manager = OrderBookManager()
	await manager.connect()
	
	await manager.subscribe_to_depths('btcusdt', 'ethusdt')
	asyncio.create_task(manager.parse())
	while True:
		for s in symbols:
			print(s, 'market buy price:', manager.books[s].market_buy_price(), 'market sell price', manager.books[s].market_sell_price())
		await asyncio.sleep(10)

if __name__ == '__main__':
	import sys

	asyncio.run(main(sys.argv[1:]))
