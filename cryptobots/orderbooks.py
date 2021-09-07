import asyncio

import json

#basic local orderbook implementation 
class OrderBook:
	def __init__(self, last_id, bids, asks):
		self.last_id = last_id
		#parse initial order book

		
		self.bids = {float(bid[0]): float(bid[1]) for bid in bids}

		self.asks = {float(ask[0]): float(ask[1]) for ask in asks}

		self.trades = []


	#parse updates
	def update(self, time, bids, asks):
		
		#check to see if the update has been applied already
		if time < self.last_id:
			return
		

		for bid in bids:

			price, quantity = float(bid[0]), float(bid[1])
			
			if quantity == 0:
				self.bids.pop(price, None)
			else:
				self.bids[price] = quantity

		for ask in asks:
			
			price, quantity = float(ask[0]), float(ask[1])
			if quantity == 0:
				self.asks.pop(price, None)
			else:
				self.asks[price] = quantity

		

		self.trades = []


	def market_buy_price(self, volume = 0):
		if volume == 0:
			return sorted(self.asks.keys())[0]

		to_buy = volume
		bought = 0
		spent = 0

		for ask in sorted(self.asks.keys()):
			if self.asks[ask] < to_buy:
				to_buy -= self.asks[ask]
				bought += self.asks[ask]
				spent += ask * self.asks[ask]
			else:
				bought += to_buy
				spent += ask * to_buy 
				to_buy = 0
				break

		return spent / volume

	def market_buy_price_quote_volume(self, volume):
		'''Calculates the price if an order were to be placed with volume quote volume'''	
		
		if volume == 0:
			return sorted(self.asks.keys())[0]
		to_sell = volume
		bought = 0
		
		for ask in sorted(self.asks.keys()):
			offered = self.asks[ask] * ask
			if offered < to_sell:
				to_sell -= offered
				bought += self.asks[ask]
			else:
				bought += to_sell / ask
				to_sell = 0
		return volume / bought

	def market_sell_price(self, volume = 0):
		if volume == 0:
			return sorted(self.bids.keys(), reverse=True)[0]

		to_sell = volume
		sold = 0
		received = 0


		for bid in sorted(self.bids.keys(), reverse=True):
			if self.bids[bid] < to_sell:
				to_sell -= self.bids[bid]
				sold += self.bids[bid]
				received += bid * self.bids[bid]
			else:
				sold += to_sell
				received += bid * to_sell
				to_sell = 0

				break

		return received / volume

	def market_sell_price_quote_volume(self, volume):
		to_buy = volume
		sold = 0
		for bid in sorted(self.bids.keys(), reverse=True):
			
			offered = self.bids[bid] * bid
			if offered < to_buy:
				to_buy -= offered
				sold += self.bids[bid]
			else:
				sold += to_buy / bid
				to_buy = 0
		return volume / sold


	def mid_price(self):
		return (self.market_buy_price() + self.market_sell_price()) / 2
