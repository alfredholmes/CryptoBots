'''Module to manage connections to the Binance APIs'''
import asyncio, json, datetime, hashlib, hmac, urllib, httpx, websockets
from contextlib import suppress

class ConnectionManager:
    '''Manage connections to the Binance APIs'''
    def __init__(self, base_endpoint: str, ws_uri: str = None):
        self.base_endpoint = base_endpoint
        self.ws_uri = ws_uri
        self.open = True
        self.subscribed_to_ws_stream = False

        self.httpx_client = None 
        self.ws_id = 0
        self.ws_requests = {}
        self.ws_q = asyncio.Queue()

        self.rest_requests = []
        self.rest_request_limits = {} #{'timeperiod': number}
        

    async def connect(self): 
        if self.ws_uri is not None:
            self.ws_client = await websockets.connect(self.ws_uri, ssl=True, compression=None)
            self.ws_listener = asyncio.create_task(self.ws_listen())
            self.subscribed_to_ws_stream = True
        self.httpx_client = httpx.AsyncClient()
        self.open = True


    async def close(self):
        '''Close the open connections'''
        self.open = False
        await self.httpx_client.aclose()
        if self.subscribed_to_ws_stream:
            await self.ws_client.close()
            await self.ws_listener
        self.subscribed_to_ws_stream = False
    
    async def check_connection(self, timeout = 5):
        try:
            if self.subscribed_to_ws_stream:
                await asyncio.wait_for(asyncio.gather(self.rest_get(''), self.ws_client.ping()), timeout)
            else:
                await asyncio.wait_for(self.rest_get(''), timeout)
            return True
        except Exception as e:
            print('ws check connection exception', e)
            raise
            

    async def ws_listen(self):
        '''Listen to incoming ws messages and adds the data to the processing queue'''
        try:
            async for message in self.ws_client:
                await self.ws_q.put(json.loads(message))
        except Exception as e:
            print('Error in Connection.ws_listen', e)
            #raise e
        finally:
            self.open = False

    async def ws_send(self, data: dict):
        '''Send data to the websocket server'''
        data['id'] = self.ws_id
            
        self.ws_requests[self.ws_id] = {'data': data, 'response': None}
        try:
            await self.ws_client.send(json.dumps(data))
        except Exception as e:
            self.subscribed_to_ws_stream = False
            raise e
            
        self.ws_id += 1
        return data['id']




    async def rest_get(self, endpoint: str, **kwargs):
        '''Send a get request to the rest api and returns the response. Raises httpx.HTTPStatusError if the respons status is not 200'''
        params = {} if 'params' not in kwargs else kwargs['params']
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        response =  await self.httpx_client.get(self.base_endpoint + endpoint, headers=headers, params=params) 
        
        try:
            response.raise_for_status()
        except Exception as e:
            print(datetime.datetime.now())
            print(e, response.text)
            raise e
        if endpoint != '':
            return json.loads(response.text)
    

    async def rest_post(self, endpoint: str, **kwargs): 
        '''Send a post request signed using api and secret keys provided, any key errors will raise an httpx.HTTPStatusError exception'''
        params = None if 'params' not in kwargs else kwargs['params']
        headers = None if 'headers' not in kwargs else kwargs['headers']
        
        response =  await self.httpx_client.post(self.base_endpoint + endpoint, params=params, headers = headers)   
        response.request.read()
        try:
            response.raise_for_status()
        except Exception as e:
            print(datetime.datetime.now())
            print(e, response.text, response.request.content)

            raise e


        return json.loads(response.text)

    async def rest_put(self, endpoint, **kwargs):
        params = {} if 'params' not in kwargs else kwargs['params']
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        
        response =  await self.httpx_client.put(self.base_endpoint + endpoint, data=params, headers = headers)   
        response.request.read()
        try:
            response.raise_for_status()
        except Exception as e:
            print(datetime.datetime.now())
            print(e, response.text, response.request.content)

            raise e


        return json.loads(response.text)


    async def rest_delete(self, endpoint: str, **kwargs):
        headers = kwargs['headers'] if 'headers' in kwargs else {}
        params = kwargs['params'] if 'params' in kwargs else {}
        response = await self.httpx_client.delete(self.base_endpoint + endpoint, params=params,headers=headers)
        try:
            response.raise_for_status()
        except Exception as e:
            print(response.text)
            e.response = json.loads(response.text)
            print(datetime.datetime.now())
            print(e.response)
            raise e

        return json.loads(response.text)
