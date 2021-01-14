import asyncio
import websockets
import json


async def main():
	uri = "wss://stream.binance.com:9443"
	async with websockets.connect(uri) as websocket:
		data = {
					"method": "SUBSCRIBE",
					"params": ["btcusdt@aggTrade"],
					"id": 1
			}
		await websocket.send(json.dumps(data))
		response = await websocket.recv()
		print(response)


if __name__ == '__main__':
	asyncio.run(main())