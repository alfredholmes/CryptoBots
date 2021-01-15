import asyncio

import websockets, httpx
import json

#basic local orderbook implementation 
class OrderBook:
	def __init__(self, last_id, initial):
		self.book = initial
		self.last_id = last_id
		#parse initial order book

		
		self.bids = {float(bid[0]): float(bid[1]) for bid in initial['bids']}

		self.asks = {float(ask[0]): float(ask[1]) for ask in initial['asks']}



	#parse updates
	def update(self, new_data):
		print(new_data)
		#check to see if the update has been applied already
		if new_data['u'] < self.last_id:
			print('New data is not new!')
			return
		#apply update
		#todo check the update ids are valid
		for bid in new_data['b']:
			price, quantity = float(bid[0]), float(bid[1])
			if quantity == 0:
				del self.bids[price]
			else:
				self.bids[price] = quantity

		for ask in new_data['a']:
			price, quantity = float(ask[0]), float(ask[1])
			if quantity == 0:
				del self.asks[price]
			else:
				self.asks[price] = quantity




	def market_buy_price(volume = 0):
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


	def market_sell_price(volume = 0):
		if volume == 0:
			return sorted(self.bid_prices)

		to_sell = volume
		sold = 0
		recived = 0

		for bid in sorted(self.bids.keys()):
			if self.bids[bid] < to_sell:
				to_sell -= self.bids[bid]
				sold += self.bids[bid]
				recived += bid * self.bids[bid]
			else:
				sold += to_sell
				recived += bid * self.bids[bid]
				to_sell = 0
				break

		return reviced / volume


class OrderBookManager:
	async def connect(self):
		uri = "wss://stream.binance.com:9443/stream"
		self.client = await websockets.client.connect(uri, ssl=True)
		self.id = 0
		#automatically parse messages as they arrive
		self.socket_listener = asyncio.create_task(self.parse())
		self.http_client = httpx.AsyncClient()

		self.books = {}

		self.requests = {}


	async def subscribe_to_depth(self, symbol):

		#subscribe to the websocket stream
		self.id += 1
		data = {
			"method": "SUBSCRIBE",
			"params": [symbol + '@depth@100ms'],
			"id": self.id 
		}


		self.requests[self.id] = {'data': data, 'response': 'response not yet recived'}
		await self.client.send(json.dumps(data))

		#get depth the snapshot
		params = {
			'symbol': symbol,
			'limit': 1000
		}

		r = await self.http_client.get('https://api.binance.com/api/v3/depth', params=params)

		response = json.loads(r.text)

		self.books[symbol] = OrderBook(response['lastUpdateId'], {'bids': response['bids'], 'asks': response['asks']})


	async def unsubscribe_to_depth(self, symbol):
		self.id += 1
		data = {
			"method": "UNSUBSCRIBE",
			"params": [symbol + '@depth@100ms'],
			"id": self.id 
		}

		self.requests[self.id] = {'data': data, 'response': 'response not yet recived'}


		await self.client.send(json.dumps(data))
		del self.books[symbol]


	async def parse(self):
		async for message in self.client:
			decoded = json.loads(message)
			#check to see if this is the response to a subscription
			if 'id' in decoded:
				self.requests[decoded['id']]['response'] = decoded['result']
				if decoded['result'] is not None:
					#should handle this better
					print('Error with request ', decoded['id'], self.requests[decoded['id']])
				continue
			if 'stream' in decoded:
				if 'depth' in decoded['stream']:
					
					self.books[decoded['stream'].split('@')[0]].update(decoded['data'])

	

	async def close_connection(self):
		self.socket_listener.cancel()
		await self.http_client.aclose()
		await self.client.close()



	#returns the best possible market buy price for the volume and the volume left over from the current order book snapshot
	def get_market_buy_price(self, symbol, volume=0):
		#check to see if the symbol is being tracked
		if symbol not in self.books:
			print('Symbol', symbol, 'missing from local books')
			return

		to_buy = volume
		bought = 0
		paid = 0
		for ask in self.books[symbol]['bids']:
			price, vol = float(ask[0]), float(ask[1])
			if vol < to_buy:
				to_buy -= vol
				bought += vol
				paid += vol * price
			else:
				bought += to_buy
				paid += to_buy * price
				to_buy = 0
				break





		return paid / bought, volume - bought



	#returns the best possible sell price for the volume and the volume left over from the current order book snapshot
	def get_market_sell_price(self, symbol, volume=0):
		#check to see if the symbol is being tracked
		if symbol not in self.books:
			print('Symbol', symbol, 'missing from local books')
			return

		to_sell = volume
		sold = 0
		reviced = 0
		for ask in self.books[symbol]['asks']:
			price, vol = float(ask[0]), float(ask[1])

			if vol < to_sell:
				to_sell -= vol
				sold += vol
				reviced += vol * price
			else:
				
				sold += to_sell
				reviced += to_sell * price
				to_sell = 0

		return reviced / sold, volume - sold



async def main():

	manager = OrderBookManager()

	await manager.connect()
	
	await manager.subscribe_to_depth('BTCUSDT')
	
	#wait 1 second just to allow streams to start
	await asyncio.sleep(2)


	#get the price to buy 1 btc on a market trade
	#print(manager.get_market_buy_price('btcusdt', 1))


	await manager.close_connection()		



if __name__ == '__main__':
	asyncio.run(main())