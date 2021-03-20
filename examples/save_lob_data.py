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

import csv


FILE = 'btcusdt_trades.csv'

async def main(symbols):
	manager = OrderBookManager()
	

	await manager.connect(True)
	await manager.subscribe_to_trade('btcusdt')

	orders = []

	while True:
		symbol, orderbook_update, trades, ask_modifyer, bid_modifyer = await manager.trade_q.get()
		#orderbook updates
		#assume all orders take place at the start of the interval - updates to the orderbook should happen before matched to market orders
		order_time = int(orderbook_update['E']) - 100 #(100ms update interval)
		#get all the releavant prices
		
		ask_difference = dict(ask_modifyer)

		for update in orderbook_update['a']:
			price = float(update[0])
			volume = float(update[1])
			if price in ask_modifyer:
				ask_difference[price] = ask_modifyer[price] - volume	
			else:
				ask_difference[price] = -volume

		bid_difference = dict(bid_modifyer)

		for update in orderbook_update['b']:
			price = float(update[0])
			volume = float(update[1])
			if price in bid_modifyer:
				
				bid_difference[price] = bid_modifyer[price] - volume
			else:
				bid_difference[price] = -volume

		#deal with market trades
		for price, volume in ask_difference.items():
			if volume > 0: #positive volume implies cancellations
				orders.append([symbol, 'LIMIT_SELL_CANCEL', order_time, price, volume])
			elif volume < 0: #negative
				orders.append([symbol, 'LIMIT_SELL', order_time, price, -volume])
			#0 implies no limit order placed
			
		for price, volume in bid_difference.items():
			if volume > 0:
				orders.append([symbol, 'LIMIT_BUY_CANCEL', order_time, price, volume])
			elif volume < 0:
				orders.append([symbol, 'LIMIT_BUY', order_time, price, -volume])
				
		
		for trade in trades:
			if trade[2]:
				orders.append([symbol, 'MARKET_SELL', trade[0], trade[3], trade[4]])
			else:
				orders.append([symbol, 'MARKET_BUY', trade[0], trade[3], trade[4]])
			

		if len(orders) > 100:
			#print(orders)
			with open(FILE, 'a') as csvfile:
				writer = csv.writer(csvfile)
				for order in orders:
					writer.writerow(order)
					
			orders = []
		
		manager.trade_q.task_done()
		await asyncio.sleep(0.05)
		print(manager.trade_q.qsize())

	await manager.close_connection()


if __name__ == '__main__':
	import sys

	asyncio.run(main(sys.argv[1:]))
