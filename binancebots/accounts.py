class Account:
	'''Account class to manage orders and store basic data'''
	def __init__(self, api, secret, connection_manager):
		self.api_key = api
		self.secret_key = secret
		self.connection_manager = connection_manager
		
	

	async def get_account_balance(self):

		account = await self.connection_manager.rest_signed_get('/v3/account', self.api_key, self.secret_key, weight=10)

		self.balances = {asset['asset']: float(asset['free']) + float(asset['locked']) for asset in account['balances'] if float(asset['free']) + float(asset['locked']) != 0}
		self.free_spot_balances = {asset['asset']: float(asset['free']) for asset in account['balances'] if float(asset['free']) != 0}
		
	async def get_open_orders(self):
		pass



class SpotAccount(Account):
	pass

class FuturesAccount(Account):
	pass


