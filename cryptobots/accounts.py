#from .exchanges import Exchange, FTXSpot
import asyncio


class Order:
	def __init__(self, order_id: str,  base: str, quote: str, side: str, volume: float):
		
		self.id = order_id
		self.base = base
		self.quote = quote
		self.side = side.upper()
		self.volume = volume
		self.remaining_volume = volume
		self.open = False
		self.completed = False	
		self.filled_volume = 0 #Total order volume (including fees)
		self.total_fees = {} #Fees paid, format {currency: fee}
		self.fills = []
	
	def update(self, update_type, data):	
		balance_changes = {self.quote: 0, self.base: 0}
		if update_type == 'FILL':
			volume_modifyer = 1 if self.side == 'BUY' else -1
			self.remaining_volume -= data['volume']
			self.fills.append((data['price'], data['volume']))	
			balance_changes[self.base] += volume_modifyer * data['volume']
			balance_changes[self.quote] -= volume_modifyer * data['volume'] * data['price']	
			for currency, fee in data['fees'].items():
				if currency not in self.total_fees:
					self.total_fees[currency] = 0
				if currency not in balance_changes:
					balance_changes[currency] = 0
				self.total_fees[currency] += fee
				balance_changes[currency] -= fee

			if self.remaining_volume <= 0:
				self.open = False
				self.completed = True
			
		
		if update_type == 'CANCEL':
			self.open = False
		return balance_changes

	def executed_price(self):
		if len(self.fills) == 0:
			return 0
		
		quote_value_exchanged = np.sum([price * volume for price, volume in self.fills]) 
		return quote_value_exchanged / np.sum([volume for price, volume in self.fills])


class LimitOrder(Order):
	pass

class MarketOrder(Order):
	pass
	
		
		
		

class Account:
	'''Account class to manage orders and store basic data'''
	def __init__(self, api, secret, exchange):
		self.api_key = api
		self.secret_key = secret
		self.exchange = exchange
		self.balance = None
		self.order_update_queue = exchange.user_update_queue
		self.parse_order_update_task = asyncio.create_task(self.parse_order_updates())	
		self.orders = {}

	async def get_balance(self):
		if self.balance is None:
			self.balance = await self.exchange.get_account_balance(self.api_key, self.secret_key) 
	
	def __str__(self):
		r = ''	
		for coin, balance in self.balance.items():
			if balance > 0:
				r += coin + '\t| ' + '{0:.4f}'.format(balance)
				r += '\n'

		return r 	
		
	async def get_open_orders(self):
		pass	
		
	
	async def parse_order_updates(self):
		while True and self.exchange.connection_manager.open:
			if self.balance is None:
				await self.get_balance()

			order_update = await self.order_update_queue.get()
			balance_changes = self.orders[order_update['id']].update(order_update['type'], order_update)
			for currency, change in balance_changes.items():
				if currency not in self.balance:
					#It might be the case that the account balance api call only gets non zero balances
					self.balance[currency] = 0
				self.balance[currency] += change
			self.order_update_queue.task_done()

	async def market_order(self, base, quote, side, **kwargs):
		if 'quote_volume' not in kwargs and 'volume' not in kwargs:
			print('ERROR: missing required argument')
			#TODO: proper exception
			return
		if 'volume' in kwargs:
			response = await self.exchange.market_order(base, quote, side, kwargs['volume'], self.api_key, self.secret_key)
		else:
			response =  await self.exchange.market_order_quote_volume(base, quote, side, kwargs['quote_volume'], self.api_key, self.secret_key)
	async def limit_order(self, base, quote, side, volume):
		response = await self.exchange.limit_order(base, quote, 'SELL', volume, self.api_key, self.secret_key)
	
class BinanceAccount(Account):
	async def get_dividend_record(self, limit = 20):
		return await self.exchange.get_asset_dividend(limit, self.api_key, self.secret_key)

	async def get_account_websocket_key(self):
		response = await self.exchange.connection_manager.signed_get()
	
class FuturesAccount(Account):
	pass

class FTXAccount(Account):
	def __init__(self, api, secret, exchange, subaccount = None):
		self.subaccount = subaccount
		super().__init__(api, secret, exchange)
		
	async def market_order(self, base, quote, side, **kwargs):
		if 'quote_volume' not in kwargs and 'volume' not in kwargs:
			print('ERROR: missing required argument')
			#TODO: proper exception
			return
		if 'volume' in kwargs:
			order = await self.exchange.market_order(base, quote, side, kwargs['volume'], self.api_key, self.secret_key, self.subaccount)
		else:
			order =  await self.exchange.market_order_quote_volume(base, quote, side, kwargs['quote_volume'], self.api_key, self.secret_key, self.subaccount)

		self.orders[order.id] = order
			
	async def limit_order(self, base, quote, side, price, volume):
		response = await self.exchange.limit_order(base, quote, 'SELL', price, volume, self.api_key, self.secret_key, self.subaccount)
		self.orders[response.id] = response
	
	async def get_balance(self):
		if self.balance is None:
			self.balance = await self.exchange.get_account_balance(self.api_key, self.secret_key, self.subaccount)
		

	async def subscribe_to_user_data(self):
		await self.get_balance()
		await self.exchange.subscribe_to_user_data(self.api_key, self.secret_key, self.subaccount)	
