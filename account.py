import asyncio
import json

class account:
	def __init__(self, httpx_client, api, secret, order_book_manager, endpoint='https://api.binance.com/api/v3/'):
		self.httpx_client = httpx_client
		self.api_key = api
		self.secret_key = secret
		self.order_book_manager = order_book_manager
		self.endpoint = endpoint
		self.exchange_data = None
	

	async def get_account_data(self):
		if self.exchange_data is None:
			await self.get_exchange_data()


	async def get_exchange_data(self):
		response = await self.httpx_client.get(self.endpoint + 'exchangeInfo')
		self.exchange_data = json.loads(response.text)
		self.currencies = set

		self.markets = set(symbol for symbol in self.exchange_data['symbols'])



