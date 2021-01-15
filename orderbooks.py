import asyncio
import websockets
import ssl
import json
import pathlib



class WebsocketManager:
	async def connect(self):
		uri = "wss://stream.binance.com:9443/ws"
		self.client = await websockets.client.connect(uri, ssl=True)
		self.id = 0

		self.to_process = asyncio.Queue()
		asyncio.create_task(self.parse())


	async def listen_to_book(self, symbol):
		self.id += 1
		data = {
			"method": "SUBSCRIBE",
			"params": [symbol + '@depth5'],
			"id": self.id 
		}

		await self.client.send(json.dumps(data))
		#TODO: Handle response

	async def parse(self):
		async for message in self.client:
			

	async def close_connection(self):
		await self.client.close()



async def main():

	socket = WebsocketManager()

	await socket.connect()
	
	await socket.listen_to_book('btcusdt')

	await asyncio.sleep(10)

	await socket.close_connection()		



if __name__ == '__main__':
	asyncio.run(main())