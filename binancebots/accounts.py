from .exchanges import Exchange
import asyncio

class Account:
	'''Account class to manage orders and store basic data'''
	def __init__(self, api, secret, exchange: Exchange):
		self.api_key = api
		self.secret_key = secret
		self.exchange = exchange
		self.balance = None
		self.order_update_queue = exchange.user_update_queue
		asyncio.create_task(self.parse_order_updates)	

	async def get_balance(self):

		self.balance = await self.exchange.get_account_balance(self.api_key, self.secret_key) 
		
	async def get_open_orders(self):
		pass
	
	async def parse_order_updates(self):
		while True:
			order = await self.order_update_queue.get()
			self.order_update_queue.task_done()

	async def market_order(self, base, quote, side, **kwargs):
		if 'quote_volume' not in kwargs and 'volume' not in kwargs:
			print('ERROR: missing required argument')
			#TODO: proper exception
			return
		if 'volume' in kwargs:
			base_change, quote_change, commission = await self.exchange.market_order(base, quote, side, kwargs['volume'], self.api_key, self.secret_key)
		else:
			base_change, quote_change, commission =  await self.exchange.market_order_quote_volume(base, quote, side, kwargs['quote_volume'], self.api_key, self.secret_key)
	
		if self.balance is None:
			await self.get_balance()

		else:
			self.balance[base] += base_change
			self.balance[quote] += quote_change
			for asset, fee in commission.items():
				self.balance[asset] -= fee


class BinanceAccount(Account):
	async def get_dividend_record(self, limit = 20):
		return await self.exchange.get_asset_dividend(limit, self.api_key, self.secret_key)

	async def get_account_websocket_key(self):
		response = await self.exchange.connection_manager.signed_get()
		return 
	
class FuturesAccount(Account):
	pass


