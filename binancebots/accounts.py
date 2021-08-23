from .exchanges import Exchange


class Account:
	'''Account class to manage orders and store basic data'''
	def __init__(self, api, secret, exchange: Exchange):
		self.api_key = api
		self.secret_key = secret
		self.exchange = exchange
		
	

	async def get_balance(self):

		account = await self.exchange.get_account_balance(self.api_key, self.secret_key)

		self.balance = {asset['asset']: float(asset['free']) + float(asset['locked']) for asset in account['balances'] if float(asset['free']) + float(asset['locked']) != 0}
		self.free_spot_balance = {asset['asset']: float(asset['free']) for asset in account['balances'] if float(asset['free']) != 0}
		
	async def get_open_orders(self):
		pass



class BinanceAccount(Account):
	async def get_dividend_record(self, limit = 20):
		return await self.exchange.get_asset_dividend(limit, self.api_key, self.secret_key)

class FuturesAccount(Account):
	pass


