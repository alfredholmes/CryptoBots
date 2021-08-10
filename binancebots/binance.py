'''Module to manage connections to the Binance APIs'''
import asyncio, json, datetime, hashlib, hmac, urllib, httpx, websockets

class ConnectionManager:
	'''Manage connections to the Binance APIs'''
	def __init__(self, base_endpoint: str, ws_uri: str):
		self.base_endpoint = base_endpoint
		self.ws_uri = ws_uri

		self.subscribed_to_ws_stream = False

		self.httpx_client = httpx.AsyncClient()
		self.ws_id = 0
		self.ws_requests = {}
		self.ws_q = asyncio.Queue()

		self.rest_requests = []
		self.rest_request_limits = {} #{'timeperiod': number}
		self.request_queue = asyncio.Queue()

	async def __aenter__(self):
		self.rest_request_sender = asyncio.create_task(self.send_requests())
		await self.get_request_limits()
		return self

	async def __aexit__(self, exc_type, exc_value, traceback):
		self.rest_request_sender.cancel()
		await self.httpx_client.aclose()
		if self.subscribed_to_ws_stream:
			await self.ws_client.close()
			await self.ws_listener
	
	async def send_requests(self):
		'''Waits for requests to be passed to request_queue and sends them once the rates are free'''
		while True:
			weight, request_submitted = await self.request_queue.get() 
			await self.wait_for_request_limit(weight)
			self.rest_requests.append([datetime.datetime.now().timestamp(), weight])
			request_submitted.set()

	async def submit_request(self, task, weight):
		'''Add request task to the request queue'''
		request_submitted = asyncio.Event()
		await self.request_queue.put((weight, request_submitted))
		await request_submitted.wait()
		return await task

	async def get_request_limits(self):
		rate_limits = (await self.rest_get('/v3/exchangeInfo', weight=10))['rateLimits']
		intervals = {
			'SECOND': 1,
			'MINUTE': 60,
			'HOUR': 60 * 60,
			'DAY': 60 * 60 * 24	
		}

		for request_data in rate_limits:
			if request_data['rateLimitType'] == 'REQUEST_WEIGHT':
				self.rest_request_limits[intervals[request_data['interval']] * request_data['intervalNum']] = request_data['limit']
		self.max_request_interval = max(self.rest_request_limits)

	async def wait_for_request_limit(self, required_weight: int):
		'''Wait asynchronusly to be allowed to post a request'''
		wait_time = 0
		#delete the irrelevant weights
		i = 0
		for i, (time, weight) in enumerate(self.rest_requests):
			if time > datetime.datetime.now().timestamp() - self.max_request_interval:
				break
		self.rest_requests = self.rest_requests[i:]

		for interval, limit in self.rest_request_limits.items():	
			start_time = datetime.datetime.now().timestamp() - interval	
			relevant_requests = self.rest_requests[sum([1 for time, weight in self.rest_requests if time > start_time]):]
			if sum(weight for time, weight in relevant_requests) > limit:
				reclaimed_weight = 0
				for time, weight in relevant_requests:
					reclaimed_weight += weight
					if reclaimed_weight >= required_weight:
						break
				print('Waiting for ', time - datetime.datetime.now().timestamp + interval, ' to send next request')
				await asyncio.sleep(datetime.datetime.now().timestamp + interval)
					
						



	async def ws_connect(self):
		'''Subscribe to the websocket stream and creates a task to asynchronusly listen to the incoming messages'''
		self.ws_client = await websockets.connect(self.ws_uri, ssl=True)
		self.ws_listener = asyncio.create_task(self.ws_listen())
		self.subscribed_to_ws_stream = True



	async def ws_listen(self):
		'''Listen to incoming ws messages and adds the data to the processing queue'''
		async for message in self.ws_client:
			message = json.loads(message)
			if 'result' in message:
				
				self.ws_requests[message['id']]['response'] = message['result']

			else:
				await self.ws_q.put(message)

	async def ws_send(self, data: dict):
		'''Send data to the websocket server'''
		data['id'] = self.ws_id
		
		self.ws_requests[self.ws_id] = {'data': data, 'response': None}
		await self.ws_client.send(json.dumps(data))
		self.ws_id += 1


	async def close(self):
		'''Close the open connections'''
		await self.httpx_client.aclose()
		if self.subscribed_to_ws_stream:
			self.ws_listener.cancel()
			await self.ws_client.close()


	async def rest_get(self, endpoint: str, **kwargs):
		'''Send a get request to the rest api and returns the response. Raises httpx.HTTPStatusError if the respons status is not 200'''
		params = {} if 'params' not in kwargs else kwargs['params']
		headers = {} if 'headers' not in kwargs else kwargs['headers']
		weight = 10 if 'weight' not in kwargs else kwargs['weight']
		response =  await self.submit_request(self.httpx_client.get(self.base_endpoint + endpoint, headers=headers, params=params), weight) 
		response.raise_for_status()
		return json.loads(response.text)
	
	def sign_params(secret_key, params={}):
		'''Creates a cryptographic signature of the parameters using the secret key, as required by Binance when sending account requests'''
		timestamp = int(datetime.datetime.now().timestamp() * 1000)	
		params['timestamp'] = str(timestamp)
		params['signature'] = hmac.new(secret_key.encode('utf-8'), urllib.parse.urlencode(params).encode('utf-8'), hashlib.sha256).hexdigest()
		return params


	async def rest_signed_get(self, endpoint: str, api_key, secret_key, **kwargs):	
		'''Send a get request signed using api and secret keys provided, any key errors will raise an httpx.HTTPStatusError exception'''
		params = {} if 'params' not in kwargs else kwargs['params']
		headers = {} if 'headers' not in kwargs else kwargs['headers']
		weight = 10 if 'weight' not in kwargs else kwargs['weight']

		return await self.rest_signed(self.httpx_client.get, api_key, secret_key, endpoint, headers, params, weight)	

	async def rest_signed_post(self, endpoint: str, api_key, secret_key,**kwargs):	
		'''Send a post request signed using api and secret keys provided, any key errors will raise an httpx.HTTPStatusError exception'''
		params = {} if 'params' not in kwargs else kwargs['params']
		headers = {} if 'headers' not in kwargs else kwargs['headers']
		weight = 10 if 'weight' not in kwargs else kwargs['weight']
		return await self.rest_signed(self.httpx_client.post, api_key, secret_key, endpoint, headers, params, weight)	


	async def rest_signed(self, method,api_key, secret_key, endpoint: str, headers: dict, params: dict, weight):
		'''Send a request (using the supplied method) signed using api and secret keys provided, any key errors will raise an httpx.HTTPStatusError exception'''
		params = ConnectionManager.sign_params(secret_key, params)
		headers = {'X-MBX-APIKEY': api_key}
		
		response = await self.submit_request(method(self.base_endpoint + endpoint, headers = headers, params = params), weight)
		response.raise_for_status()
		return json.loads(response.text)

	
