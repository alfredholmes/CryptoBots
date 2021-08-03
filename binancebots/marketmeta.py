import asyncio

import websockets, httpx
import json


async def get_spot_markets(httpx_client=None, endpoint='https://api.binance.com/api/v3/'):
	close_connection = False
	if httpx_client is None:
		httpx_client = httpx.AsyncClient()
		close_connection = True
		
	response = await httpx_client.get(endpoint + 'exchangeInfo') 
	await httpx_client.aclose()
	data = json.loads(response.text)
	markets = {}
	for symbol in data['symbols']:
		if symbol['baseAsset'] == 'DEFI':
			print(symbol)
		if symbol['baseAsset'] in markets:
			markets[symbol['baseAsset']].append([symbol['quoteAsset'], symbol['status']])
		else:		
			markets[symbol['baseAsset']] = [[symbol['quoteAsset'], symbol['status']]]
	return markets

async def get_futures_markets(httpx_client=None, endpoint='https://fapi.binance.com/fapi/v1/'):
	return await get_spot_markets(httpx_client, endpoint)

if __name__=='__main__':
	asyncio.run(get_trading_markets())
