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

		self.trades = []


	#parse updates
	def update(self, new_data):
		
		#check to see if the update has been applied already
		if new_data['u'] < self.last_id:
			return
		

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


class TradeStream:
	def __init__(self, initial_id):
		self.trades = []
		self.initial_id = initial_id
		#dicts to saves the differences between the 100ms orderbook and the current orderbook in the same format as the binance updates
		self.bid_modifyer = {}
		self.ask_modifyer = {}


	def add_trade(self, orderbook, trade_id, timestamp, side, price, volume):
		if self.initial_id > trade_id:
			return

		self.trades.append([trade_id, timestamp, side, price, volume])

		#side is True if buyer is the market maker (market sell order was executed) and false otherwise
		if side:
			if price in self.bid_modifyer:
				self.bid_modifyer[price] -= volume
			elif price in orderbook.bids:
				self.bid_modifyer[price] = orderbook.bids[price] - volume
			else:
				self.bid_modifyer[price] = -volume
		else:
			if price in self.ask_modifyer:
				self.ask_modifyer[price] -= volume
			elif price in orderbook.asks:
				self.ask_modifyer[price] = orderbook.asks[price] - volume
			else:
				self.bid_modifyer[price] = -volume

	def clear(self):
		self.trades = []
		self.bid_modifyer = {}
		self.ask_modifyer = {}


class OrderBookManager:
	def __init__(self):
		self.initialized = False
	

	async def connect(self, listen_to_trades=False, uri="wss://stream.binance.com:9443/stream"):
		self.client = await websockets.client.connect(uri, ssl=True)
		self.id = 0
		#automatically parse messages as they arrive
		self.q = asyncio.Queue()
		self.socket_listener = asyncio.create_task(self.listen())
		self.http_client = httpx.AsyncClient()

		self.books = {}
		self.trades = {}
		self.to_parse = []

		self.requests = {}

		self.initialized = True
		self.websocket_parser = asyncio.create_task(self.parse())
		self.tradestreams = {}
		self.listen_to_trades=listen_to_trades
		self.trade_q = asyncio.Queue()

	async def subscribe_to_depths(self, *symbols):
		if not self.initialized:
			await self.connect()
		
		to_subscribe = [s for s in symbols if s not in self.books]

		#subscribe
		self.id += 1

		data = {
			"method": "SUBSCRIBE",
			"params": [s + '@depth@100ms' for s in to_subscribe],
			"id": self.id
		}

		self.requests[self.id] = {'data': data, 'response': None}
		await self.client.send(json.dumps(data))

		await self.get_depth_snapshots(*to_subscribe)

	async def get_depth_snapshots(self, *symbols):
		
		for symbol in symbols:
			params = {
				'symbol': symbol.upper(),
				'limit': 1000
			}

			
			r = await self.http_client.get('https://api.binance.com/api/v3/depth', params=params)

			response = json.loads(r.text)
			self.books[symbol] = OrderBook(response['lastUpdateId'], {'bids': response['bids'], 'asks': response['asks']})


			if self.listen_to_trades:
				await self.subscribe_to_trade(symbol)

	async def subscribe_to_depth(self, symbol):
		
		#subscribe to the websocket stream
		if symbol in self.books:
			#already subscribed
			return
		self.id += 1
		data = {
			"method": "SUBSCRIBE",
			"params": [symbol + '@depth@100ms'],
			"id": self.id 
		}


		self.requests[self.id] = {'data': data, 'response': None}
		await self.client.send(json.dumps(data))
		#get depth the snapshot
		params = {
			'symbol': symbol.upper(),
			'limit': 1000
		}

		r = await self.http_client.get('https://api.binance.com/api/v3/depth', params=params)

		response = json.loads(r.text)
		self.books[symbol] = OrderBook(response['lastUpdateId'], {'bids': response['bids'], 'asks': response['asks']})

		if self.listen_to_trades:
			await self.subscribe_to_trade(symbol)
	


	async def subscribe_to_trade(self, symbol):
		if symbol not in self.books:
			await self.subscribe_to_depth(symbol)
		if symbol in self.trades:
			return
		self.id += 1
		data = {
			"method": "SUBSCRIBE",
			"params": [symbol + '@trade'],
			"id": self.id
		}

		self.requests[self.id] = {'data': data, 'response': None}
		await self.client.send(json.dumps(data))
		self.tradestreams[symbol] = TradeStream(self.books[symbol].last_id)


	async def parse(self):
		while  True:
			try:
				message = await self.q.get()
				if 'stream' in message and 'depth' in message['stream']:
					symbol = message['stream'].split('@')[0]
					self.books[symbol].update(message['data'])
					if symbol in self.tradestreams:
						if self.listen_to_trades:
							await self.trade_q.put((symbol, message['data'], self.tradestreams[symbol].trades[:], dict(self.tradestreams[symbol].ask_modifyer), dict(self.tradestreams[symbol].bid_modifyer)))

						self.tradestreams[symbol].clear()
				elif 'stream' in message and 'trade' in message['stream']:
					symbol = message['stream'].split('@')[0]
					self.tradestreams[symbol].add_trade(self.books[symbol], message['data']['E'], message['data']['t'], message['data']['m'], float(message['data']['p']), float(message['data']['q']))
				elif 'result' in message and message['result'] is None:
					self.requests[int(message['id'])] = True
				else:
					print('Unandled WSS message: ', message, ' | Request: ', self.requests[message['id']])

				self.q.task_done()
			except KeyError as e:
				#TODO: Better error handling
				print('Key error: ', e)

	async def unsubscribe_to_depth(self, symbol):
		self.id += 1
		data = {
			"method": "UNSUBSCRIBE",
			"params": [symbol + '@depth@100ms'],
			"id": self.id 
		}

		self.requests[self.id] = {'data': data, 'response': None} 

		await self.client.send(json.dumps(data))
		del self.books[symbol]

	async def unsubscribe_to_trade(self, symbol):
		self.id += 1
		data = {
			"method": "UNSUBSCRIBE",
			"params": [symbol + '@trade'],
			"id": self.id
		}

		self.requests[self.id] = {'data': data, 'response': None}

		await self.client.send(json.dumps(data))	
		del self.tradestreams[symbol]


	async def listen(self):
		async for message in self.client:
			await self.q.put(json.loads(message))
	

	async def close_connection(self):
		if self.initialized:	
			await self.http_client.aclose()
			await self.client.close()
			self.socket_listener.cancel()
			self.websocket_parser.cancel()



	def market_price(self, buy, symbol, volume = 0):
		if symbol not in self.books:
			print(symbol, 'missing!')
			return
		elif buy:
			return self.books[symbol].market_buy_price(volume)
		else:
			return self.books[symbol].market_sell_price(volume)




async def main():

	manager = OrderBookManager()

	await manager.connect(True)
	
	print('Subscribing to btcusdt')
	await manager.subscribe_to_depth('btcusdt')
	print('done')
	
	#wait 1 second just to allow streams to start
	await asyncio.sleep(2)

	while True:

		print(manager.books['btcusdt'].market_buy_price(0))
		print(manager.books['btcusdt'].market_sell_price(0))
		await asyncio.sleep(0.1)

		




	await manager.close_connection()		



if __name__ == '__main__':
	asyncio.run(main())
