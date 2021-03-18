#Script to record the limit order book data from the web socket streams. The current goal is to save the orders to a CSV file.


#There are 5 types of order for the orderbook:
#Limit Buy, Limit Sell, Limit Cancel
#Market Buy, Market Sell
#
# We can only infer aggregated trades from the websocket streams but this is still quite valuable data, and we don't save the initial state of the order book, this can be inferred from the existence of succesful market trades.
#
# Each order (aggregated trade) has 5 properties:
# Pair, Type, Timestamp, Price, Volume


import sys

sys.path.append("./")
import keys
from binancebots.orderbooks import OrderBookManager

import httpx
import asyncio




async def main(symbols):
	manager = OrderBookManager()
	

	await manager.connect(True)
	await manager.subscribe_to_trade('btcusdt')

	while True:
		try:
			data = await manager.trade_q.get()
			print(data)
		except:
			pass
	await manager.close_connection()


if __name__ == '__main__':
	import sys

	asyncio.run(main(sys.argv[1:]))
