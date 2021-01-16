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
		
		#check to see if the update has been applied already
		if new_data['u'] < self.last_id:
			print('New data is not new!')
			return
		#apply update
		#todo check the update ids are valid
		for bid in new_data['b']:

			price, quantity = float(bid[0]), float(bid[1])
			
			if quantity == 0:
				self.bids.pop(price, None)
			else:
				self.bids[price] = quantity

		for ask in new_data['a']:
			price, quantity = float(ask[0]), float(ask[1])
			if quantity == 0:
				self.asks.pop(price, None)
			else:
				self.asks[price] = quantity




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


	def market_sell_price(self, volume = 0):
		if volume == 0:
			return sorted(self.bids.keys(), reverse=True)[0]

		to_sell = volume
		sold = 0
		recived = 0

		for bid in sorted(self.bids.keys(), reverse=True):
			if self.bids[bid] < to_sell:
				to_sell -= self.bids[bid]
				sold += self.bids[bid]
				recived += bid * self.bids[bid]
			else:
				sold += to_sell
				recived += bid * to_sell
				to_sell = 0
				break

		return recived / volume


class OrderBookManager:
	async def connect(self, uri="wss://stream.binance.com:9443/stream"):
		self.client = await websockets.client.connect(uri, ssl=True)
		self.id = 0
		#automatically parse messages as they arrive
		self.q = asyncio.Queue()
		self.socket_listener = asyncio.create_task(self.listen())
		self.http_client = httpx.AsyncClient()

		self.books = {}
		self.to_parse = []

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
			'symbol': symbol.upper(),
			'limit': 1000
		}

		r = await self.http_client.get('https://api.binance.com/api/v3/depth', params=params)

		response = json.loads(r.text)

		self.books[symbol] = OrderBook(response['lastUpdateId'], {'bids': response['bids'], 'asks': response['asks']})
		
	async def parse(self):
	
		while  True:
			message = await self.q.get()
			if 'stream' in message:
				symbol = message['stream'].split('@')[0]
				self.books[symbol].update(message['data'])
			else:
				print(message)

			self.q.task_done()


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


	async def listen(self):
		async for message in self.client:
			await self.q.put(json.loads(message))
	

	async def close_connection(self):
		self.socket_listener.cancel()
		await self.http_client.aclose()
		await self.client.close()









async def main():

	manager = OrderBookManager()

	await manager.connect()
	
	print('Subscribing to btcusdt')
	await manager.subscribe_to_depth('btcusdt')
	print('done')
	
	#wait 1 second just to allow streams to start
	asyncio.create_task(manager.parse())
	await asyncio.sleep(2)

	while True:

		print(manager.books['btcusdt'].market_buy_price(0))
		print(manager.books['btcusdt'].market_sell_price(0))
		print()
		await asyncio.sleep(0.1)

		


	#get the price to buy 1 btc on a market trade
	#print(manager.get_market_buy_price('btcusdt', 1))


	await manager.close_connection()		



if __name__ == '__main__':
	asyncio.run(main())