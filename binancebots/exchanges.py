from abc import ABC, abstractmethod
import asyncio, datetime
from .connections import ConnectionManager
from .orderbooks import OrderBook
import asyncio, json, datetime, hashlib, hmac, urllib, httpx, websockets
class Exchange(ABC):
	def __init__(self, connection_manager: ConnectionManager):
		'''Initalize an exchange object'''
		self.connection_manager = connection_manager
		self.request_queue = asyncio.Queue()
		self.limits = []
		self.sent_requests = {}
		self.send_requests_task = asyncio.create_task(self.send_requests())
		self.ws_parse_task = asyncio.create_task(self.ws_parse())
		self.order_books = {}
		self.unhandled_order_book_updates = {}


	def close(self):
		'''Cancel the objects asyncio tasks'''
		self.send_requests_task.cancel()
		self.ws_parse_task.cancel()

	async def send_requests(self):
		'''Method to send requests once they have been added to the request queue and the request won't go over the request limits'''
		while True:
			send_request, weights = await self.request_queue.get()
			await self.wait_to_send_request(weights)
			send_request.set()
			
			for weight_type, weight in weights.items():
				if weight_type not in self.sent_requests:
					self.sent_requests[weight_type] = []
				self.sent_requests[weight_type].append((datetime.datetime.now().timestamp(), weight))


	async def wait_to_send_request(self, weight: dict):
		'''Waits for the required time to be able to send a request with the given weight'''
		for weight_type, requests in self.sent_requests.items():
			for limit_type, time, limit in self.limits:
				if limit_type != weight_type or limit_type not in weight:
					continue
				now = datetime.datetime.now().timestamp()
				relevant_requests = [req for req in requests if now - req[0] < time]
				spent = sum(req[0] for req in relevant_requests)
				
				if spent + weight[limit_type] < limit:
					continue
				total_spent = 0
				
				for request_time, spent in reversed(relevant_requests):
					total_spent += spent
				
					if total_spent + weight[limit_type] > limit:
						await asyncio.sleep(limit - (now - request_time))
						break	

				


	async def submit_request(self, request, weights: dict = {}): 
		'''Submits a request to the queue and waits for the response'''
		send_request = asyncio.Event()
		await self.request_queue.put((send_request, weights))
		await send_request.wait()
		return await request

	async def ws_parse(self):
		'''Gets new responses from the websocket connections and sends parses them'''
		while True:
			message = await self.connection_manager.ws_q.get()
			self.parse_order_book_update(message)
			self.connection_manager.ws_q.task_done()


	@abstractmethod
	def parse_order_book_update(self, message):
		'''Updates the orderbooks with the message from the order book websockets'''

	@abstractmethod
	def sign_params(self, secret_key: str, params: dict = {}) -> dict:
		'''Signs the parameters with the secret key'''		
	
	@abstractmethod
	async def get_exchange_info(self):
		'''Gets the exchange info from the api to populate data'''

	@abstractmethod
	async def get_account_balance(self, api_key, secret_key) -> dict:
		'''Gets the account balance of the accout with the given api_key'''
	
	@abstractmethod
	async def subscribe_to_order_books(self, *currencies) -> None:
		'''Start listening to orderbooks'''
	
	@abstractmethod
	async def market_order(self, pair: str, side: str, base_volume: float) -> dict:
		'''Places a market order. Side is either BUY or SELL'''


	@abstractmethod
	async def limit_order(self, pair: str, side: str, price: float, base_volume: float) -> dict: 
		'''Places a limit order, similar to market_order'''



class BinanceSpot(Exchange):
	def sign_params(secret_key: str, params: dict = None):
		if params is None:
			params = {}
		timestamp = int(datetime.datetime.now().timestamp() * 1000)
		params['timestamp'] = str(timestamp)
		params['signature'] = hmac.new(secret_key.encode('utf-8'), urllib.parse.urlencode(params).encode('utf-8'), hashlib.sha256).hexdigest()
		return params
	

	async def get_exchange_info(self):
		self.exchange_info = await self.submit_request(self.connection_manager.rest_get('/v3/exchangeInfo'), {'REQUEST_WEIGHT': 10, 'RAW_REQUESTS': 1})
		self.limits = []
		times = {'SECOND': 1, 'MINUTE': 60, 'DAY': 24 * 60 * 60}
		for limit in self.exchange_info['rateLimits']:
				self.limits.append((limit['rateLimitType'], times[limit['interval']] * limit['intervalNum'], limit['limit'])) 
			
		for symbol in self.exchange_info['symbols']:
			pass	
		return self.exchange_info

	def parse_order_book_update(self, message):
		if 'stream' in message and 'depth' in message['stream']:
			symbol = message['stream'].split('@')[0]
			if symbol not in self.order_books:
				self.unhandled_order_book_updates[symbol].append(message['data'])
				return
			self.order_books[symbol].update(message['data'])
		else:
			print('Unhandled book update', message)


	async def get_account_balance(self, api_key, secret_key) -> dict:
		params = BinanceSpot.sign_params(secret_key)
		headers = {'X-MBX-APIKEY': api_key}
		response = await self.submit_request(self.connection_manager.rest_get('/v3/account', params=params, headers=headers), {'REQUEST_WEIGHT': 10, 'RAW_REQUESTS': 1})
		return response

	async def subscribe_to_order_books(self, *symbols) -> None:
		to_subscribe = set(s.lower() for s in symbols if s not in self.order_books)
		for s in to_subscribe:
			self.unhandled_order_book_updates[s] = []

		ws_request = {
			'method': 'SUBSCRIBE',
			'params': [s + '@depth@100ms' for s in to_subscribe]
		}
		await self.connection_manager.ws_send(ws_request)
		await asyncio.gather(*(self.get_depth_snapshots(s) for s in to_subscribe))
		
		for s in to_subscribe:
			for update in self.unhandled_order_book_updates[s]:
				self.order_books.update(update)
			del self.unhandled_order_book_updates[s]


	async def get_depth_snapshots(self, *symbols):
		for symbol in symbols:
			params = {
				'symbol': symbol.upper(),
				'limit': 100
			}

			response = await self.submit_request(self.connection_manager.rest_get('/v3/depth', params=params), {'REQUEST_WEIGHT': 1, 'RAW_REQUESTS': 1})
			self.order_books[symbol.lower()] = OrderBook(response['lastUpdateId'], {'bids': response['bids'], 'asks': response['asks']})



	async def market_order(self, pair, side, base_volume):
		pass
	
	async def limit_order(self, pair, side, price, base_volume):
		pass
