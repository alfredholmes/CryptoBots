from .exchanges import Exchange


class Account:
	'''Account class to manage orders and store basic data'''
	def __init__(self, api, secret, exchange: Exchange):
		self.api_key = api
		self.secret_key = secret
		self.exchange = exchange
		self.balance = None
	

	async def get_balance(self):

		account = await self.exchange.get_account_balance(self.api_key, self.secret_key)

		self.balance = {asset['asset']: float(asset['free']) + float(asset['locked']) for asset in account['balances'] if float(asset['free']) + float(asset['locked']) != 0}
		self.free_spot_balance = {asset['asset']: float(asset['free']) for asset in account['balances'] if float(asset['free']) != 0}
		
	async def get_open_orders(self):
		pass

	async def market_order(self, base, quote, side, **kwargs):
		if 'quote_volume' not in kwargs and 'volume' not in kwargs:
			print('ERROR: missing required argument')
			#TODO: proper exception
			return
		if 'volume' in kwargs:
			base_change, quote_change, commission = await self.exchange.market_order(base + quote, side, kwargs['volume'], self.api_key, self.secret_key)
		else:
			base_change, quote_change, commission =  await self.exchange.market_order_quote_volume(base + quote, side, kwargs['quote_volume'], self.api_key, self.secret_key)
	
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


