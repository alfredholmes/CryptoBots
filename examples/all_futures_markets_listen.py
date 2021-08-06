import sys
sys.path.append("./")
from binancebots.orderbooks import OrderBookManager
from binancebots.marketmeta import get_futures_markets

import httpx
import asyncio



async def main():
	manager = OrderBookManager()
	await manager.connect(False, 'wss://fstream.binance.com/stream', 'https://fapi.binance.com/fapi/v1/')

	markets = await get_futures_markets()
	

	symbols = []
	for base, quotes in markets.items():
		for q, trading, contract_type in quotes:
			if trading == 'TRADING' and q == 'USDT' and contract_type == 'PERPETUAL':	
				symbols.append((base + q).lower())

	await manager.subscribe_to_depths(*symbols)
	while True:
		try:
			print('Unhandled updates:', sum([len(q)for q in  manager.unhandled_book_updates.values()]))
			for s in symbols:
				print(s, 'Market buy price:', manager.books[s].market_buy_price(), ' Market sell price', manager.books[s].market_sell_price())
			await asyncio.sleep(1)
		except:
			break
	await manager.close_connection()
if __name__ == '__main__':

	asyncio.run(main())
