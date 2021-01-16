import asyncio
import json
import datetime

import hashlib, hmac, urllib

class account:
	def __init__(self, httpx_client, api, secret, order_book_manager, endpoint='https://api.binance.com/api/v3/'):
		self.httpx_client = httpx_client
		self.api_key = api
		self.secret_key = secret
		self.order_book_manager = order_book_manager
		self.endpoint = endpoint
		self.exchange_data = None
		self.market_filters = {}
	

	async def get_account_data(self):
		if self.exchange_data is None:
			await self.get_exchange_data()

		await self.get_account_balance()



	async def get_exchange_data(self):
		response = await self.httpx_client.get(self.endpoint + 'exchangeInfo')
		self.exchange_data = json.loads(response.text)
		

		#the following code is perhaps inefficient as it loops through the symbols quite a lot
		#get a list of all the currencies
		base_assets = set(symbol['baseAsset'] for symbol in self.exchange_data['symbols'])
		quote_assets = set(symbol['quoteAsset'] for symbol in self.exchange_data['symbols'])
		
		self.tradable_assets = base_assets.union(quote_assets)

		

		for symbol_data in self.exchange_data['symbols']:
			
			symbol = symbol_data['symbol']
			self.market_filters[symbol] = {'precision': int(symbol_data['baseAssetPrecision']), 'precision_quote': int(symbol_data['quoteAssetPrecision'])}
			for f in symbol_data['filters']:
				if f['filterType'] == 'LOT_SIZE':
					self.market_filters[symbol]['min_order'] = float(f['minQty'])
					self.market_filters[symbol]['max_order'] = float(f['maxQty'])
					self.market_filters[symbol]['step_size'] = float(f['stepSize'])
				elif f['filterType'] == 'MIN_NOTIONAL':
					self.market_filters[symbol]['min_order_quote'] = float(f['minNotional'])


	async def get_account_balance(self):
		ts = int(datetime.datetime.now().timestamp() * 1000)
		params = {
			'timestamp': str(ts)
		}

		headers = {
			'X-MBX-APIKEY': self.api_key
		}

		params['signature'] = self.generate_signature(params)

		response = await self.httpx_client.get(self.endpoint + 'account', headers=headers, params=params)
		account = json.loads(response.text)


		self.spot_balances = {asset['asset']: float(asset['free']) for asset in account['balances'] if float(asset['free']) != 0}



	def generate_signature(self, params):
		return hmac.new(self.secret_key.encode('utf-8'), urllib.parse.urlencode(params).encode('utf-8'), hashlib.sha256).hexdigest()		
