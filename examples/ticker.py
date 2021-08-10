import sys
sys.path.append("./")
from binancebots.orderbooks import OrderBookManager
from binancebots.binance import connectionManager

import asyncio



async def main(symbols):
	connection_manager = connectionManager('https://api.binance.com/api', 'wss://stream.binance.com:9443/stream')
	await connection_manager.ws_connect()
	manager = OrderBookManager()
	await manager.connect(connection_manager)
	
	await manager.subscribe_to_depths(*symbols)
	while True:
		try:
			for s in symbols:
				print(s, 'Market buy price:', manager.books[s].market_buy_price(), ' Market sell price', manager.books[s].market_sell_price())
			await asyncio.sleep(1)
		except:
			break
	await manager.close_connection()
if __name__ == '__main__':
	import sys

	asyncio.run(main(sys.argv[1:]))
