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

		self.volume_filters = {}
		self.volume_renderers = {}
		self.price_renderers = {}
		self.exchange_info = None

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

	async def market_buy_price(pair, **kwargs):
		if pair.lower() not in self.order_books:
			await self.subscribe_to_order_books(pair)
		if 'volume' in kwargs:
			return self.order_books[pair.lower()].market_buy_price(kwargs['volume'])
		if 'quote_volume' in kwargs:
			return self.order_books[pair.lower()].market_buy_price_quote_volume(kwargs['volume'])
		else:
			return self.order_books[pair.lower()].market_buy_price()
	
	async def market_sell_price(pair, **kwargs):
		if pair.lower() not in self.order_books:
			await self.subscribe_to_order_books(pair)
		if 'volume' in kwargs:
			return self.order_books[pair.lower()].market_sell_price(kwargs['volume'])
		if 'quote_volume' in kwargs:
			return self.order_books[pair.lower()].market_sell_price_quote_volume(kwargs['volume'])
		else:
			return self.order_books[pair.lower()].market_sell_price()


	@abstractmethod
	async def subscribe_to_order_books(self, *currencies) -> None:
		'''Start listening to orderbooks'''
	
	@abstractmethod
	async def market_order(self, pair: str, side: str, base_volume: float) -> dict:
		'''Places a market order. Side is either BUY or SELL'''


	@abstractmethod
	async def limit_order(self, pair: str, side: str, price: float, base_volume: float) -> dict: 
		'''Places a limit order, similar to market_order'''
	

	@abstractmethod
	async def filter_volume(self, pair: str, base_volume: float) -> float:
		'''Returns a valid trading volume close to the requested'''

	
	@abstractmethod	
	async def render_volume(self, pair: str, base_volume: float) -> str:
		'''Renders the tradding volume as a string to be sent in the request'''


	def filter_volume(self, pair: str, base_volume: float, price: float) -> float:
		'''Returns a valid trading volume close to the requested'''
		for volume_filter in self.volume_filters[pair.upper()].values():
			base_volume = volume_filter.filter(base_volume, price)
	
	def render_volume(self, pair: str, base_volume: float) -> str:
		'''Renders the tradding volume as a string to be sent in the request'''
		return self.volume_renderes[pair.upper()].render(base_volume)
	
	def render_price(self, pair: str, price: float) -> str:
		return self.price_renderes[pair.upper()].render(price)

class VolumeFilterParameters(ABC):
	pass

class VolumeFilter(ABC):
	def __init__(self, parameters: VolumeFilterParameters):
		self.parameters = parameters

	@abstractmethod
	def filter(self, volume: float, price: float) -> float:
		pass

class MinNotionalParameters(VolumeFilterParameters):
	def __init__(self, min_notional):
		self.min_notional = min_notional

class MinNotionalFilter(VolumeFilter):
	def filter(self, volume: float, price: float) -> float:
		if volume * price < self.parameters.min_notional:
			return 0
		else:
			return price

class MinMaxParameters(VolumeFilterParameters):
	def __init__(self, min_volume, max_volume):
		self.min_volume = min_volume
		self.max_volume = max_volume

class MinMaxFilter(VolumeFilter):
	def filter(self, volume: float, price: float) -> float:
		if volume < self.parameters.min_volume:
			return 0
		if volume > self.max_volume:
			return self.parameters.max_volume

		return volume


class FloatRenderer:
	def __init__(self, precision, tick_size):
		self.precision = precision
		self.tick_size = tick_size


	def render(self, value: float) -> str:
		n_ticks = int(value / self.tick_size)
		return '{0:.' + str(self.precision) + 'f}'.format(n_ticks * self.tick_size)


class BinanceSpot(Exchange):
	def sign_params(secret_key: str, params: dict = None):
		if params is None:
			params = {}
		timestamp = int(datetime.datetime.now().timestamp() * 1000)
		params['timestamp'] = str(timestamp)
		params['signature'] = hmac.new(secret_key.encode('utf-8'), urllib.parse.urlencode(params).encode('utf-8'), hashlib.sha256).hexdigest()
		return params

	async def signed_get(self, endpoint, api_key, secret_key, **kwargs):
		params = {} if 'params' not in kwargs else kwargs['params']	
		headers = {} if 'headers' not in kwargs else kwargs['headers']	
		weights = {'RAW_REQUESTS': 1} if 'weights' not in kwargs else kwargs['weights']	

		headers['X-MBX-APIKEY'] = api_key
		BinanceSpot.sign_params(secret_key, params)

		return await self.submit_request(self.connection_manager.rest_get(endpoint, params=params, headers = headers), weights)

	async def signed_post(self, endpoint, api_key, secret_key, **kwargs):
		params = {} if 'params' not in kwargs else kwargs['params']	
		headers = {} if 'headers' not in kwargs else kwargs['headers']	
		weights = {'RAW_REQUESTS': 1} if 'weights' not in kwargs else kwargs['weights']	
		
		headers['X-MBX-APIKEY'] = api_key
		BinanceSpot.sign_params(secret_key, params)

		
		return await self.submit_request(self.connection_manager.rest_post(endpoint, params=params, headers = headers), weights)

	async def get_exchange_info(self, cache = True):
		if self.exchange_info is not None and cache:
			return self.exchange_info


		self.exchange_info = await self.submit_request(self.connection_manager.rest_get('/api/v3/exchangeInfo'), {'REQUEST_WEIGHT': 10, 'RAW_REQUESTS': 1})
		self.limits = []
		times = {'SECOND': 1, 'MINUTE': 60, 'DAY': 24 * 60 * 60}
		for limit in self.exchange_info['rateLimits']:
				self.limits.append((limit['rateLimitType'], times[limit['interval']] * limit['intervalNum'], limit['limit'])) 
			
		for symbol in self.exchange_info['symbols']:
			pair = symbol['symbol']
			self.volume_filters[pair] = {}
			for volume_filter in symbol['filters']:
				if volume_filter['filterType'] == 'MIN_NOTIONAL':
					min_notional = float(volume_filter['minNotional'])	
					self.volume_filters[pair]['MIN_NOTIONAL'] = MinNotionalFilter(MinNotionalParameters(min_notional))
				if volume_filter['filterType'] == 'LOT_SIZE':
					min_size = float(volume_filter['minQty'])
					max_size = float(volume_filter['maxQty'])
					self.volume_filters[pair]['LOT_SIZE'] = MinMaxFilter(MinMaxParameters(min_size, max_size))
					
					precision = float(symbol['baseAssetPrecision'])
					tick_size = float(volume_filter['stepSize'])
					self.volume_renderers[pair] = FloatRenderer(precision, tick_size)
				
				if volume_filter['filterType'] == 'PRICE_FILTER':
					precision = float(symbol['quotePrecision'])
					tick_size = float(volume_filter['tickSize'])
					self.price_renderers[pair] = FloatRenderer(precision, tick_size)
		return self.exchange_info

	def parse_order_book_update(self, message):
		if 'stream' in message and 'depth' in message['stream']:
			symbol = message['stream'].split('@')[0]
			if symbol not in self.order_books:
				self.unhandled_order_book_updates[symbol].append(message['data'])
				return
			self.order_books[symbol].update(message['data'])
		else:
				to_subscribe = set(s.lower() for s in symbols if s.lower() not in self.order_books)
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

	async def unsubscribe_to_order_books(self, *symbols) -> None:
		to_unsubscribe = set(s.lower() for s in symbols if s.lower() in self.order_books)

		ws_request = {
			'method': 'UNSUBSCRIBE',
			'params': [s + '@depth@100ms' for s in to_unsubscribe]
		}

		await self.connection_manager.ws_send(ws_request)
		for s in to_unsubscribe:
			del self.order_books[s]

	async def get_depth_snapshots(self, *symbols):
		for symbol in symbols:
			params = {
				'symbol': symbol.upper(),
				'limit': 100
			}

			response = await self.submit_request(self.connection_manager.rest_get('/api/v3/depth', params=params), {'REQUEST_WEIGHT': 1, 'RAW_REQUESTS': 1})
			self.order_books[symbol.lower()] = OrderBook(response['lastUpdateId'], {'bids': response['bids'], 'asks': response['asks']})

	async def get_asset_dividend(self,limit, api, secret):
		params = {'limit': limit}
		return await self.signed_get('/sapi/v1/asset/assetDividend', api, secret, params = params, weights={'REQUEST_WEIGHT': 1, 'RAW_REQUESTS': 1})
	

	async def market_order(self, pair, side, base_volume, api_key, secret_key):
		#get the price
		unubscribe = False
		if pair.lower() not in self.order_books:
			await self.subscribe_to_order_books(pair)	
			unsibscribe = True

		if side == 'BUY':
			price = self.order_books[pair].market_buy_price(base_volume)
		elif side == 'SELL':
			price = self.order_books[pair].market_sell_price(base_volume)
		else:
			print('ORDER TYPE ERROR')
			#TODO: actually raise an exception
		

		volume = self.filter_volume(pair, base_volume, price)
		if volume == 0:
			return

		volume_str = self.render_volume(pair, volume)
		
		#send trade request
		params = {
			'symbol': pair.upper(),
			'side': side,
			'type': 'MARKET',
			'quantity': volume_str
		}

		response = await self.signed_post('/api/v3/order', api_key, secret_key, params=params)

		if unsubscribe:
			await self.unsubscribe_to_order_books(pair)

		return response


	async def market_order_quote_volume(self, pair, side, quote_volume, api_key, secret_key):
		if quote_volume < self.market_filters[pair.upper()]['MIN_NOTIONAL'].parameters.min_notional:
			return 0

		params = {
			'symbol': pair.upper(),
			'side': side,
			'type': 'MARKET',
			'quoteOrderQty': str(quote_volume)
		}

		return await self.signed_post('/api/v3/order', api_key, secret_key, params=params)

	async def limit_order(self, pair, side, price, base_volume, api_key, secret_key):
		volume = self.fliter_volume(pair,base_volume, price)
		if volume == 0:
			return
		volume_str = self.render_volume(pair, volume)
		pirice_str = self.render_price(pair, price)

		params = {
			'symbol': pair.upper(),
			'side': side,
			'type': 'LIMIT',	
			'timeInForce': 'GTC',
			'quantity': volume_str,
			'price': price_str 
		}
		
		return await self.signed_post('/api/v3/order', api_key, secret_key, params=params)
		



