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
		self.fills = {}
		self.fill_event = asyncio.Event()
		self.close_event = asyncio.Event()
		
		self.reported_fill = None
	
	def update(self, update_type, data):	
		balance_changes = {self.quote: 0, self.base: 0}
		if update_type == 'FILL':
			if data['trade_id'] in self.fills:
				return balance_changes
			volume_modifyer = 1 if self.side == 'BUY' else -1
			self.remaining_volume -= data['volume']
			print('Order', self.id, self.base, self.quote, ' fill, remaining volume: ', self.remaining_volume) 
			balance_changes[self.base] += volume_modifyer * data['volume']
			balance_changes[self.quote] -= volume_modifyer * data['volume'] * data['price']	
			for currency, fee in data['fees'].items():
				if currency not in self.total_fees:
					self.total_fees[currency] = 0
				if currency not in balance_changes:
					balance_changes[currency] = 0
				self.total_fees[currency] += fee
				balance_changes[currency] -= fee
				self.fills[data['trade_id']] = dict(balance_changes)	

			if self.remaining_volume < 10**-5 or (self.reported_fill is not None and self.reported_fill - 10**-5 <= self.volume - self.remaining_volume):
				self.open = False
				self.completed = True
				self.fill_event.set()
			
		
		if update_type == 'UPDATE':
			if data['status'] == 'CLOSED':
				self.open = False
				self.close_event.set()
				self.reported_fill = data['filled_size']
				if self.reported_fill - 10**-5 <= self.volume - self.remaining_volume:
					self.fill_event.set()
				if self.reported_fill == 0.0:
					print('Order canceled by exchange, no reason given')
		return balance_changes



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
		self.unhandled_order_updates = {}
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
	
	def remove_closed_orders(self):
		to_delete = []
		for order_id, order in self.orders.items():
			if not order.open:
				to_delete.append(order_id)
		for order_id in to_delete:
			del self.orders[order_id]
	async def get_open_orders(self):
		pass	
		
	
	async def parse_order_updates(self):
		try:
			while True and self.exchange.connection_manager.open:
				if self.balance is None:
					await self.get_balance()

				order_update = await self.order_update_queue.get()
				if order_update['id'] not in self.orders:
					if order_update['id'] not in self.unhandled_order_updates:
						self.unhandled_order_updates[order_update['id']] = []
					self.unhandled_order_updates[order_update['id']].append(order_update)
				else:
					balance_changes = self.orders[order_update['id']].update(order_update['type'], order_update)
					for currency, change in balance_changes.items():
						if currency not in self.balance:
						#It might be the case that the account balance api call only gets non zero balances
							self.balance[currency] = 0
						self.balance[currency] += change
				self.order_update_queue.task_done()
		except Exception as e:
			print('Error in Account.parse_order_updates():', e)
	
	def add_order(self, order):
		if order.id in self.unhandled_order_updates:
			for update in self.unhandled_order_updates[order.id]:
				order.update(update['type'], update)
		self.orders[order.id] = order
	
	async def refresh_fills(self, start_time):
		fills =  await self.exchange.get_order_fills(start_time, self.api_key, self.secret_key)
		for fill in fills:
			if fill['id'] not in self.orders:
				print('Error in account class, orders out of sync!')
				#need to update orders
			elif fill['trade_id'] not in self.orders[fill['id']]:
				self.orders[fill['id']].update('FILL', fill)
			

					
	
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
	def __init__(self, api, secret, exchange, subaccount = None, connection_manager = None):
		self.subaccount = subaccount
		super().__init__(api, secret, exchange)
		if connection_manager is not None:
			self.connection_manager = connection_manager
		
	async def market_order(self, base, quote, side, **kwargs):
		if 'exchange' in kwargs:
			exchange = kwargs['exchange']
		else:
			exchange = self.exchange 
		if 'quote_volume' not in kwargs and 'volume' not in kwargs:
			print('ERROR: missing required argument')
			#TODO: proper exception
			return
		if 'volume' in kwargs:
			order = await exchange.market_order(base, quote, side, kwargs['volume'], self.api_key, self.secret_key, self.subaccount)
		else:
			order =  await exchange.market_order_quote_volume(base, quote, side, kwargs['quote_volume'], self.api_key, self.secret_key, self.subaccount)
		if order is None:
			#failed to place order...
			return
		self.add_order(order)
		return order
			
	async def limit_order(self, base, quote, side, price, volume, **kwargs):
		if 'exchange' in kwargs: 
			exchange = kwargs['exchange']
		else:
			exchange = self.exchange
		response = await exchange.limit_order(base, quote, 'SELL', price, volume, self.api_key, self.secret_key, self.subaccount)
		self.add_order(response)
		return response
	
	async def get_balance(self):
		if self.balance is None:
			self.balance = await self.exchange.get_account_balance(self.api_key, self.secret_key, self.subaccount)
		

	async def subscribe_to_user_data(self):
		await self.get_balance()
		await self.exchange.subscribe_to_user_data(self.api_key, self.secret_key, self.subaccount)	
