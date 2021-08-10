import sys
sys.path.append('./')
sys.path.append('../')

from binancebots import binance
import asyncio

import keys

async def main():
	manager = binance.connectionManager('https://api.binance.com/api', 'wss://stream.binance.com:9443/stream')
	await manager.ws_connect()
	#await manager.ws_send({'method': 'SUBSCRIBE', 'params': ['btcusdt@depth@100ms']})
	#await manager.rest_get('/v3/exchangeInfo')
	print(await manager.rest_signed_get(keys.API, keys.SECRET, '/v3/account'))
	await manager.close()

if __name__=='__main__':
	asyncio.run(main())
