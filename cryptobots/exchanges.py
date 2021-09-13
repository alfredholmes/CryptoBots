from abc import ABC, abstractmethod
import asyncio 
from .connections import ConnectionManager
from .orderbooks import OrderBook
from .accounts import Order
import asyncio, json, datetime, hashlib, hmac, urllib, httpx, websockets, time, urllib.parse

import numpy as np


class Exchange(ABC):
	
	def __init__(self, connection_manager: ConnectionManager):
		'''Initalize an exchange object'''
		self.connection_manager = connection_manager
		self.request_queue = asyncio.Queue()
		self.user_update_queue = asyncio.Queue()
		self.limits = []
		self.sent_requests = {}
		self.send_requests_task = asyncio.create_task(self.send_requests())
		self.ws_parse_task = asyncio.create_task(self.ws_parse())
		self.order_books = {}
		self.unhandled_order_book_updates = {}
		self.trading_symbols = {} #dict to store trading pairs, e.g. {'BTCUSDT': ('BTC', 'USD'), 'ETHBTC': ('ETH', 'BTC') }
		self.trading_markets = []

		self.volume_filters = {}
		self.volume_renderers = {}
		self.quote_volume_renderers = {}

		self.price_renderers = {}
		self.exchange_info = None
	
		self.request_wait_lock = asyncio.Lock()	
		self.exchange_info_lock = asyncio.Lock()
		self.subscribe_to_order_book_lock = asyncio.Lock()
	def close(self):
		'''Cancel the objects asyncio tasks'''
		self.send_requests_task.cancel()
		self.ws_parse_task.cancel()

	async def send_requests(self):
		'''Method to send requests once they have been added to the request queue and the request won't go over the request limits'''
		while True:
			try:
				send_request, weights = await self.request_queue.get()
				await self.wait_to_send_request(weights)
				send_request.set()
			except Exception as e:
				print('Error in Exchange.send_request: ', e)
				
			


	async def wait_to_send_request(self, weights: dict):
		'''Waits for the required time to be able to send a request with the given weight'''
		async with self.request_wait_lock:
			for weight_type, requests in self.sent_requests.items():
				for limit_type, interval, limit in self.limits:
					if limit_type != weight_type or limit_type not in weights:
						continue
					now = time.time()
					relevant_requests = [req for req in requests if now - req[0] < interval]
					spent = sum(weight for request_time, weight in relevant_requests)	
					if spent + weights[limit_type] < limit:
						continue
					total_spent = 0
					for request_time, spent in reversed(relevant_requests):
						total_spent += spent
						if total_spent + weights[limit_type] >= limit:
							await asyncio.sleep(interval - (now - request_time))
							break	
			for weight_type, value in weights.items():
				if weight_type not in self.sent_requests:
					self.sent_requests[weight_type] = []
				self.sent_requests[weight_type].append((time.time(), value))



	async def submit_request(self, request, weights: dict = {}): 
		'''Submits a request to the queue and waits for the response'''
		send_request = asyncio.Event()
		await self.request_queue.put((send_request, weights))
		await send_request.wait()
		return await request
	

	@abstractmethod
	async def ws_parse(self):
		'''Gets new responses from the websocket connections and sends parses them'''


	@abstractmethod
	def parse_order_book_update(self, message):
		'''Updates the orderbooks with the message from the order book websockets'''

	
	@abstractmethod
	async def get_exchange_info(self):
		'''Gets the exchange info from the api to populate data'''

	@abstractmethod
	async def get_account_balance(self, api_key, secret_key) -> dict:
		'''Gets the account balance of the accout with the given api_key'''

	@abstractmethod
	async def subscribe_to_user_data(self, api_key, secret_key) -> None:
		'''Subscribes to the user websocket connection'''

	async def market_buy_price(base, quote, **kwargs):
		if (base, quote) not in self.order_books:
			await self.subscribe_to_order_books((base, quote))
		if 'volume' in kwargs:
			return self.order_books[(base, quote)].market_buy_price(kwargs['volume'])
		if 'quote_volume' in kwargs:
			return self.order_books[(base, quote)].market_buy_price_quote_volume(kwargs['quote_volume'])
		else:
			return self.order_books[(base, quote)].market_buy_price()
	
	async def market_sell_price(base, quote, **kwargs):
		if (base, quote) not in self.order_books:
			await self.subscribe_to_order_books((base, quote))
		if 'volume' in kwargs:
			return self.order_books[(base, quote)].market_sell_price(kwargs['volume'])
		if 'quote_volume' in kwargs:
			return self.order_books[(base, quote)].market_sell_price_quote_volume(kwargs['volume'])
		else:
			return self.order_books[(base, quote)].market_sell_price()


	@abstractmethod
	async def subscribe_to_order_books(self, *currencies) -> None:
		'''Start listening to orderbooks'''
	
	@abstractmethod
	async def market_order(self, base: str, quote: str, side: str, base_volume: float) -> dict:
		'''Places a market order. Side is either BUY or SELL'''

	@abstractmethod
	async def market_order_quote_volume(self, base: str, quote: str, side: str, quote_volume: float) -> dict:
		'''Places a market order but with the given quote volume'''
	@abstractmethod
	async def limit_order(self, base: str, quote: str, side: str, price: float, base_volume: float) -> dict: 
		'''Places a limit order, similar to market_order'''
	

	@abstractmethod
	async def filter_volume(self, pair: str, base_volume: float) -> float:
		'''Returns a valid trading volume close to the requested'''


	def filter_volume(self, pair: str, base_volume: float, price: float) -> float:
		'''Returns a valid trading volume close to the requested'''
		for volume_filter in self.volume_filters[pair.upper()].values():
			base_volume = volume_filter.filter(base_volume, price)

		return base_volume
	
	def render_volume(self, pair: str, base_volume: float) -> str:
		'''Renders the tradding volume as a string to be sent in the request'''
		return self.volume_renderers[pair.upper()].render(base_volume)
	
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
			return volume

class MinMaxParameters(VolumeFilterParameters):
	def __init__(self, min_volume, max_volume):
		self.min_volume = min_volume
		self.max_volume = max_volume

class MinMaxFilter(VolumeFilter):
	def filter(self, volume: float, price: float) -> float:
		if volume < self.parameters.min_volume:
			return 0
		if volume > self.parameters.max_volume:
			return self.parameters.max_volume
		return volume


class FloatRenderer:
	def __init__(self, precision, tick_size = None, return_float = False):
		self.precision = int(precision)
		self.tick_size = tick_size
		self.return_float = return_float

	def render(self, value: float):
		if self.return_float:
			return int(value / self.tick_size) * self.tick_size
		if self.tick_size is None:
			return ('{0:.' + str(self.precision) + 'f}').format(value)
		n_ticks = int(value / self.tick_size)
		return ('{0:.' + str(self.precision) + 'f}').format(n_ticks * self.tick_size)

class BinanceSpot(Exchange):
	def sign_params(secret_key: str, params: dict = None):
		if params is None:
			params = {}
		timestamp = int(time.time() * 1000)
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
		async with self.exchange_info_lock:
			if self.exchange_info is not None and cache:
				return self.exchange_info
		
			self.exchange_info = await self.submit_request(self.connection_manager.rest_get('/api/v3/exchangeInfo'), {'REQUEST_WEIGHT': 10, 'RAW_REQUESTS': 1})
		
		self.limits = []
		times = {'SECOND': 1, 'MINUTE': 60, 'DAY': 24 * 60 * 60}
		for limit in self.exchange_info['rateLimits']:
				self.limits.append((limit['rateLimitType'], times[limit['interval']] * limit['intervalNum'], limit['limit'])) 
		
		for symbol in self.exchange_info['symbols']:
			if (symbol['baseAsset'], symbol['quoteAsset']) in self.trading_markets:
				continue
			pair = (symbol['baseAsset'], symbol['quoteAsset'])
			
			self.volume_filters[pair] = {}

			if symbol['status'] == 'TRADING':
					self.trading_markets.append((symbol['baseAsset'], symbol['quoteAsset']))
			
			quote_precision = int(symbol['quoteAssetPrecision'])
			self.quote_volume_renderers[pair] = FloatRenderer(int(symbol['quoteAssetPrecision']))
			
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
	async def ws_parse(self):
		while True:
			message = await self.connection_manager.ws_q.get()
			if 'result' in message:
				self.connection_manager.ws_q.task_done()
				continue
			self.parse_order_book_update(message)
			self.connection_manager.ws_q.task_done()
	
	def parse_order_book_update(self, message):
		if 'stream' in message and 'depth' in message['stream']:
			symbol = message['stream'].split('@')[0]
			if self.trading_symbols[symbol] not in self.order_books:
				self.unhandled_order_book_updates[self.trading_symbols[symbol]].append(message['data'])
				return
			self.order_books[self.trading_symbols[symbol]].update(message['data']['u'], message['data']['b'], message['data']['a'])
		else:
			print('Unhandled book update', message)

	async def subscribe_to_order_books(self, *symbols):
		to_subscribe = set(s for s in symbols if s not in self.order_books)
		for s in to_subscribe:
			self.unhandled_order_book_updates[s] = []
			self.trading_symbols[(s[0] + s[1]).lower()] = s

		ws_request = {
			'method': 'SUBSCRIBE',
			'params': [(b + q).lower() + '@depth@100ms' for b, q in to_subscribe]
		}
		await self.connection_manager.ws_send(ws_request)
		await asyncio.gather(*(self.get_depth_snapshots(s) for s in to_subscribe))
		
		for s in to_subscribe:
			for update in self.unhandled_order_book_updates[s]:
				self.order_books[s].update(update['u'], update['b'], update['a'])
			del self.unhandled_order_book_updates[s]

	async def unsubscribe_to_order_books(self, *symbols) -> None:
		to_unsubscribe = set(s for s in symbols if s in self.order_books)

		ws_request = {
			'method': 'UNSUBSCRIBE',
			'params': [(b + q).lower() + '@depth@100ms' for b,q in to_unsubscribe]
		}

		await self.connection_manager.ws_send(ws_request)
		for s in to_unsubscribe:
			del self.order_books[s]

	async def subscribe_to_user_data(self, api, secret):
		pass
	async def get_depth_snapshots(self, *symbols):
		for symbol in symbols:
			params = {
				'symbol': symbol[0].upper() + symbol[1].upper(),
				'limit': 100
			}

			response = await self.submit_request(self.connection_manager.rest_get('/api/v3/depth', params=params), {'REQUEST_WEIGHT': 1, 'RAW_REQUESTS': 1})
			self.order_books[symbol] = OrderBook(response['lastUpdateId'], response['bids'],response['asks'])

	async def get_asset_dividend(self,limit, api, secret):
		params = {'limit': limit}
		return await self.signed_get('/sapi/v1/asset/assetDividend', api, secret, params = params, weights={'REQUEST_WEIGHT': 1, 'RAW_REQUESTS': 1})
	

	async def market_order(self, base, quote, side, base_volume, api_key, secret_key):
		#get the price
		unsubscribe = False
		if (base, quote) not in self.order_books:
			await self.subscribe_to_order_books((base, quote))	
			unsibscribe = True
		
		side = side.upper()
		if side == 'BUY':
			price = self.order_books[(base, quote)].market_buy_price(base_volume)
		elif side == 'SELL':
			price = self.order_books[(base, quote)].market_sell_price(base_volume)
		else:
			print('ORDER TYPE ERROR')
			raise Exception('Unrecognised order side')	

		volume = self.filter_volume((base, quote), base_volume, price)
		
		if volume == 0:
			return

		volume_str = self.render_volume((base, quote), volume)
		
		#send trade request
		params = {
			'symbol': (base + quote).upper(),
			'side': side,
			'type': 'MARKET',
			'quantity': volume_str
		}

		response = await self.signed_post('/api/v3/order', api_key, secret_key, params=params, weights = {'ORDERS': 1, 'RAW_REQUESTS': 1})

		if unsubscribe:
			await self.unsubscribe_to_order_books((base, quote))

		base_change = 0
		quote_change = 0
		commission  = {}
		if response['status'] == 'FILLED':
			for fill in response['fills']:
				if side == 'BUY':
					base_change += float(fill['qty'])
					quote_change -= float(fill['qty']) * float(fill['price'])
				elif side == 'SELL':
					base_change -= float(fill['qty'])
					quote_change += float(fill['qty']) * float(fill['price'])
				if fill['commissionAsset'] not in commission:
					commission[fill['commissionAsset']] = 0
				commission[fill['commissionAsset']] += float(fill['commission'])

		return base_change, quote_change, commission


	async def market_order_quote_volume(self, base, quote, side, quote_volume, api_key, secret_key):
		if quote_volume < self.volume_filters[(base, quote)]['MIN_NOTIONAL'].parameters.min_notional:
			return 0

		params = {
			'symbol': (base + quote).upper(),
			'side': side,
			'type': 'MARKET',
			'quoteOrderQty': self.quote_volume_renderers[(base, quote)].render(quote_volume)
		}

		response = await self.signed_post('/api/v3/order', api_key, secret_key, params=params, weights = {'ORDERS': 1, 'RAW_REQUESTS': 1})
		base_change = 0
		quote_change = 0
		commission  = {}
		if response['status'] == 'FILLED':
			for fill in response['fills']:
				if side == 'BUY':
					base_change += float(fill['qty'])
					quote_change -= float(fill['qty']) * float(fill['price'])
				elif side == 'SELL':
					base_change -= float(fill['qty'])
					quote_change += float(fill['qty']) * float(fill['price'])
				if fill['commissionAsset'] not in commission:
					commission[fill['commissionAsset']] = 0
				commission[fill['commissionAsset']] += float(fill['commission'])
		return base_change, quote_change, commission

	async def limit_order(self, base, quote, side, price, base_volume, api_key, secret_key):
		volume = self.fliter_volume(base, quote,base_volume, price)
		if volume == 0:
			return
		volume_str = self.render_volume(pair, volume)
		pirice_str = self.render_price(pair, price)

		params = {
			'symbol': (base + quote).upper(),
			'side': side,
			'type': 'LIMIT',	
			'timeInForce': 'GTC',
			'quantity': volume_str,
			'price': price_str 
		}
		
		return await self.signed_post('/api/v3/order', api_key, secret_key, params=params, weights={'ORDERS': 1, 'RAW_REQUESTS': 1})
		


	async def get_account_balance(self, api_key, secret_key):
		account =  await self.signed_get('/api/v3/account', api_key, secret_key, weights = {'REQUEST_WEIGHT': 10, 'RAW_REQUESTS': 1})
		return {asset['asset']: float(asset['free']) + float(asset['locked']) for asset in account['balances'] if float(asset['free']) + float(asset['locked']) != 0}


class FTXSpot(Exchange):
	def __init__(self, connection_manager: ConnectionManager):
		self.ws_authenticated = False
		self.ws_authentication_response = asyncio.Event()
		self.ws_ping_task = asyncio.create_task(self.ws_ping())
		super().__init__(connection_manager)
	
	async def ws_ping(self):
		while self.connection_manager.open:
			data = {'op': 'ping'}
			await self.connection_manager.ws_send(data)
			await asyncio.sleep(15 * 60)

	def sign_headers(headers, api_key: str, secret_key: str, method: str, url: str, params: dict = None, subaccount = None ):
		ts = int(time.time() * 1000)	
		payload = str(ts) + method.upper() +  url	
		if params is not None:
			payload += json.dumps(params)
		headers['FTX-KEY'] = api_key
		headers['FTX-SIGN'] = hmac.new(secret_key.encode(), payload.encode(), 'sha256').hexdigest()
		headers['FTX-TS'] = str(ts)
		if subaccount is not None:
			headers['FTX-SUBACCOUNT'] = urllib.parse.quote(subaccount)

		
	async def signed_get(self, endpoint: str, api_key: str, secret_key: str, **kwargs):
		headers = {} if 'headers' not in kwargs else kwargs['headers']
		params = None if 'params' not in kwargs else kwargs['params']
		if 'subaccount' not in kwargs:	
			FTXSpot.sign_headers(headers, api_key, secret_key, 'GET', endpoint, params)	
		else:
			FTXSpot.sign_headers(headers, api_key, secret_key, 'GET', endpoint, params, kwargs['subaccount'])	
		
		return await self.submit_request(self.connection_manager.rest_get(endpoint, params=params, headers=headers), {'REQUEST': 1})
	
	async def signed_post(self, endpoint: str, api_key: str, secret_key: str, **kwargs):
		headers = {} if 'headers' not in kwargs else kwargs['headers']
		params = None if 'params' not in kwargs else kwargs['params']
			
		if 'subaccount' not in kwargs:	
			FTXSpot.sign_headers(headers, api_key, secret_key, 'POST', endpoint, params)	
		else:	
			FTXSpot.sign_headers(headers, api_key, secret_key, 'POST', endpoint, params, kwargs['subaccount'])
		if params is not None:
			none_keys = []
		return await self.submit_request(self.connection_manager.rest_post(endpoint, params=params, headers=headers), {'REQUEST': 1})

	async def get_exchange_info(self, cache: bool = True):

		self.limits.append(('REQUEST', 0.2, 3)) 
		self.limits.append(('REQUEST', 1, 3))
		
		async with self.exchange_info_lock: 
			if self.exchange_info is not None and cache:
				return self.exchange_info

			markets = (await self.submit_request(self.connection_manager.rest_get('/api/markets')))['result']
			self.exchange_info = markets
		for market in markets:
			if market['baseCurrency'] is None or not market['enabled']:
				continue
			base = market['baseCurrency']
			quote = market['quoteCurrency']
			self.trading_markets.append((base, quote))
			min_order = market['minProvideSize'] 
			max_order = np.inf
			price_tick = market['priceIncrement']
			size_tick = market['sizeIncrement']

			self.volume_filters[(base, quote)] = {'LOT_SIZE': MinMaxFilter(MinMaxParameters(min_order, max_order)), 'MIN_NOTIONAL': MinNotionalFilter(MinNotionalParameters(0))}

			self.volume_renderers[(base,quote)] = FloatRenderer(8, size_tick, True)
			self.price_renderers[(base,quote)] = FloatRenderer(8, price_tick, True)
		return self.exchange_info
	async def ws_parse(self):
		while True:
			try:
				message = await self.connection_manager.ws_q.get()
				if message['type'] == 'error':
					print('WS ERROR:', message)
					self.connection_manager.ws_q.task_done()
					raise Exception(message)
				elif message['type'] == 'update':
					if message['channel'] == 'orderbook':
						self.parse_order_book_update(message)
						self.connection_manager.ws_q.task_done()	
					if message['channel'] == 'orders':
						message_data = message['data']
						order_update = {
							'type': 'UPDATE',
							'id': message_data['id'],
							'size': message_data['size'],
							'price': message_data['price'], 
							'status': message_data['status'].upper(),
							'filled_size': message_data['filledSize']
						}
						await self.user_update_queue.put(order_update)
					if message['channel'] == 'fills':
						message_data = message['data']
						order_update = {
							'type': 'FILL',
							'id': message_data['orderId'],
							'fees': {message_data['feeCurrency']: message_data['fee']},
							'price': message_data['price'],
							'volume': message_data['size']
						}
						await self.user_update_queue.put(order_update)
				elif 'channel' in message and message['channel'] == 'orderbook' and message['type'] == 'partial':
					self.parse_order_book_update(message)
				elif message['type'] == 'subscribed' and (message['channel'] == 'orders' or message['channel'] == 'fills'):
					self.ws_authenticated = True
					self.ws_authentication_response.set()
				
				elif message['type'] == 'subscribed':
					self.connection_manager.ws_q.task_done()
				elif message['type'] == 'pong':
					pass
				else:
					print('Unhandled ws message', message)
			except Exception as e:
				print('Error in FTXSpot.ws_parse', e)


	def parse_order_book_update(self, message):
		if message['type'] == 'partial':
			self.order_books[self.trading_symbols[message['market']]] = OrderBook(message['data']['time'],  message['data']['bids'], message['data']['asks'])
			for update in self.unhandled_order_book_updates[self.trading_symbols[message['market']]]:
				self.order_books[self.trading_symbols[message['market']]].update(*update)
			del self.unhandled_order_book_updates[self.trading_symbols[message['market']]]
		elif message['type'] == 'update':
			if self.trading_symbols[message['market']] not in self.order_books:
				self.unhandled_order_book_updates[self.trading_symbols[message['market']]].append((message['data']['time'], message['data']['bids'], message['data']['asks']))
			self.order_books[self.trading_symbols[message['market']]].update(message['data']['time'], message['data']['bids'], message['data']['asks'])



	async def subscribe_to_order_books(self, *symbols):
		async with self.subscribe_to_order_book_lock:
			to_subscribe = set([s for s in symbols if s not in self.order_books])
			for b, q in to_subscribe:
				self.trading_symbols[b + '/' + q] = (b, q)
				self.unhandled_order_book_updates[(b, q)] = []
			ws_requests = [{'op': 'subscribe', 'channel': 'orderbook', 'market': b + '/' + q} for b, q in to_subscribe]		
			await asyncio.gather(*[self.connection_manager.ws_send(req) for req in ws_requests])
			while len(self.unhandled_order_book_updates) > 0:
				await asyncio.sleep(0.1)


	async def unsubscribe_to_order_books(self, *symbols):
		to_unsubscribe = set([s for s in symbols is s in self.order_books])
		ws_request = [{'op': 'unsubscribe', 'channel': 'orderbook', 'market': b +'/' + q} for b, q, in to_subscribe]
		await asyncio.gather(*[self.connection_manager.ws_send(req) for req in ws_requests])
		await asyncio.sleep(0.1) #Waits for the server to recive the request before deleting, should replace with response handling
		for s in to_unsubscribe:
			del self.order_books[s]
		
	async def get_depth_snapshots(sef, *symbols):
		pass

	async def market_order(self, base, quote, side, base_volume, api_key, secret_key, subaccount = None):
		for volume_filter in self.volume_filters[(base, quote)].values():
			base_volume = volume_filter.filter(base_volume, self.order_books[(base, quote)].market_buy_price(base_volume))
		base_volume = self.volume_renderers[(base, quote)].render(base_volume)

		request = {
			'market': base + '/' + quote,
			'side': side.lower(),
			'price': None,
			'type': 'market',
			'size': float(base_volume)
		}
		try:
			response = await self.signed_post('/api/orders', api_key, secret_key, params=request, subaccount=subaccount)
		except Exception as e:
			print('Exception in FTX.market_order', e)
			return
		if 'success' not in response or not response['success']:
			raise Execption('Order placement failed' + str(response))
		else:
			order_info = response['result']
			return Order(order_info['id'], *self.trading_symbols[order_info['market']], order_info['side'].upper(), order_info['size'])	
				
		

	async def market_order_quote_volume(self, base, quote, side, quote_volume, api_key, secret_key, subaccount = None):
		subscribe = (base, quote) not in self.order_books
		if subscribe:
			await self.subscribe_to_order_books((base, quote))
		if side.upper() == 'BUY':
			base_volume = quote_volume / self.order_books[(base, quote)].market_buy_price_quote_volume(quote_volume)	
		elif side.upper() == 'SELL':
			base_volume = quote_volume / self.order_books[(base, quote)].market_sell_price_quote_volume(quote_volume)
		return await self.market_order(base, quote, side, base_volume, api_key, secret_key, subaccount)


	async def limit_order(self, base, quote, side, price, base_volume, api_key, secret_key, subaccount = None):
		subscribe = (base, quote) not in self.order_books
		if subscribe:
			await self.subscribe_to_order_books((base, quote))
		for volume_filter in self.volume_filters[(base, quote)].values():
			base_volume = volume_filter.filter(base_volume, self.order_books[(base, quote)].market_buy_price(base_volume))
		price = float(self.price_renderers[(base, quote)].render(price))
		
		base_volume = self.volume_renderers[(base, quote)].render(base_volume)

		request = {
			'market': base + '/' + quote,
			'side': side.lower(),
			'price': price,
			'type': 'limit',
			'size': float(base_volume)
		}
		response = await self.signed_post('/api/orders', api_key, secret_key, params=request, subaccount=subaccount)
		if 'success' not in response or not response['success']:
			raise Execption('Order placement failed' + str(response))
		else:
			order_info = response['result']
			return Order(order_info['id'], *self.trading_symbols[order_info['market']], order_info['side'].upper(), order_info['size'])	

	async def get_account_balance(self, api_key, secret_key, subaccount = None):
		coins = (await self.signed_get('/api/wallet/balances', api_key, secret_key, subaccount=subaccount))['result']
		return {coin['coin']: coin['total'] for coin in coins}
		
	async def subscribe_to_user_data(self, api_key, secret_key, subaccount = None):
		ts = int(time.time() * 1000)
		payload = str(ts) + 'websocket_login'
		signature = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
		if not self.ws_authenticated:
			request_body = {
				'args': {
					'key': api_key,
					'sign': signature,
					'time': ts
				},
				'op': 'login'
			}	
			if subaccount is not None:
				request_body['args']['subaccount'] = urllib.parse.quote(subaccount) 
			self.ws_authentication_response = asyncio.Event()
			await self.connection_manager.ws_send(request_body)
			#subscribe to the order data
			request_body = {
				'op': 'subscribe',
				'channel': 'orders'
			}
			await self.connection_manager.ws_send(request_body)
			await self.ws_authentication_response.wait()
			request_body = {
				'op': 'subscribe',
				'channel': 'fills'
			}
			await self.connection_manager.ws_send(request_body)
			if self.ws_authenticated:
				return self.user_update_queue
			else:
				raise Exception('Failed to subscribe to orders stream')
		else:
			return self.user_update_queue
	async def get_candles(self, quote, base, start_time, end_time, resolution=15):
		possible_resolutions = [15, 60, 300, 900, 3600, 14400] + [(i + 1) * 86400 for i in range(30)]
		if resolution not in possible_resolutions:
			differences = [abs(res-resolution) for res in possible_resolutions]
			resolution = possible_resolutions[differences.index(min(differences))]
		limit = 1500
		times = [(start_time + i * limit, start_time + (i + 1) * limit * resolution - 1) for i in range(int((end_time - start_time) / (limit * resolution)))]
		candles = []
		for start_time, end_time in times:
			request_data = {
				'resolution': resolution,
				'start_time': start_time,
				'end_time': end_time
			}
			market = urllib.parse.quote(quote.upper() + '/'  + base.upper())
			response = await self.submit_request(self.connection_manager.rest_get('/api/markets/' + market + '/candles', params=request_data)) 
			for candle in response['result']:
				candles.append([int(candle['time'] / 1000), float(candle['open']), float(candle['close']), float(candle['high']), float(candle['low'])])	
		return candles
