import asyncio, time, hashlib, hmac, urllib, json
from abc import ABC, abstractmethod
from .connections import ConnectionManager
from contextlib import suppress
import httpx
from .orderbooks import OrderBook
from .exchanges import Exchange, Fill, Position, SpotMarket, Order, FutureMarket, OrderPlacementError, OrderClosed


class Binance(Exchange):
    rest_endpoint = 'https://api.binance.com'
    ws_endpoint = 'wss://stream.binance.com:9443/stream'

    def __init__(self):
        self.user_ping_tasks = {}
        
        super().__init__()

    async def connect(self):
        """
            Method to get exchange market data and create websocket refresh task

        """
        try:
            exchange_info = (await self.connection_manager.rest_get('/api/v3/exchangeInfo'))
            self.rate_limits = exchange_info['rateLimits']
            trading_markets = exchange_info['symbols']
            for market_meta in trading_markets:
                if market_meta['status'] != 'TRADING':
                    continue
                market = SpotMarket(market_meta['baseAsset'], market_meta['quoteAsset'], market_meta['symbol'])
                
                market.enabled = True 
                market.base_asset_precision = int(market_meta['baseAssetPrecision'])
                market.quote_precision = int(market_meta['quotePrecision'])
                market.price_precision = int(market_meta['quotePrecision'])
                for data_filter in market_meta['filters']:
                    if data_filter['filterType'] == 'PRICE_FILTER':
                        market.price_increment  = float(data_filter['tickSize'])

                    if data_filter['filterType'] == 'LOT_SIZE':
                        market.size_increment = float(data_filter['stepSize'])
                        market.min_provide_size = float(data_filter['minQty'])        
                    if data_filter['filterType'] == 'NOTIONAL':
                        market.min_quote_volume = float(data_filter['minNotional'])
                self.markets[(market.base, market.quote)] = market
        except:
            raise
        self.parse_task = asyncio.create_task(self.ws_parse())
        for market in self.markets.values():
            if market.type == 'spot':
                self.market_names[market.name] = (market.base, market.quote)


    async def close(self, *details):
        for ping_task in self.user_ping_tasks.values():
            ping_task.cancel()
        
        with suppress(asyncio.CancelledError):
            for ping_task in self.user_ping_tasks.values():
                await ping_task
        
        await super().close()

    #Market Data methods
    async def reconnect(self):
        await self.unsubscribe_from_order_books(*self.order_books)
        await self.connection_manager.close()

        self.markets = {}
        self.order_books = {}
        self.order_book_queues = {}
        self.market_names = {}

        self.parse_task.cancel()

        for ping_task in self.user_ping_tasks.values():
            ping_task.cancel()
            

        with suppress(asyncio.CancelledError):
            await self.parse_task
            for ping_task in self.user_ping_tasks.values():
                await ping_task


        await self.connection_manager.connect()
        await self.connect()

    def connected(self) -> bool:
        return self.connection_manager.open
        


    async def subscribe_to_order_books(self, *markets):
        """
            Subscibe to the orderbooks of markets
                markets: tuple of (base, quote), eg (BTC, USDT), BTC, ETH)
        """
        async with self.connection_lock:
            to_subscribe = set(market for market in markets if market not in self.order_book_queues)  
            if len(to_subscribe) == 0:
                return
            requests = []
            for market in to_subscribe:
                if market not in self.markets:
                    raise Exception('Invalid Market ' + str(market) + ' not listed on exchange. Maybe exchange.connect() not been executed')
                order_book_queue = asyncio.Queue()
                self.order_book_queues[market] = order_book_queue
                self.order_books[market] = OrderBook(order_book_queue)
            ws_request = {'method': 'SUBSCRIBE', 'params':  [f'{self.markets[market].name.lower()}@depth@100ms' for market in to_subscribe]} 
            
            await self.connection_manager.ws_send(ws_request)
            await asyncio.gather(*[self.get_order_book_snapshot(market) for market in to_subscribe])
            await asyncio.gather(*[self.order_books[market].initialised_event.wait() for market in to_subscribe])

    async def get_order_book_snapshot(self, market):
        depth = await self.connection_manager.rest_get(f'/api/v3/depth', params={'symbol': self.markets[market].name, 'limit':100})
        update = {'initial': True, 'bids': [[float(b), float(a)] for b, a in depth['bids']], 'asks': [[float(a), float(v)] for a, v in depth['asks']], 'time': int(depth['lastUpdateId'])} 
        await self.order_book_queues[market].put(update)
    
    async def unsubscribe_from_order_books(self, *markets):
        """
            Unsubscribe from markets order books
        """
        async with self.connection_lock:
            ws_requests = [{'method': 'UNSUBSCRIBE', 'params': ['f{self.markets[market].name}@depth@100ms' for market in markets]}]
            try:
                await asyncio.wait_for(asyncio.gather(*[self.connection_manager.ws_send(req) for req in ws_requests]), 1)
            except Exception as e:
                print(e)
            try: 
                await asyncio.gather(*[self.order_books[market].close() for market in markets]) 
            except Exception as e:
                print(e)
            for market in markets:
                del self.order_books[market]
    
    def check_order_books(self):
        return sum(book.ftx_checksum() for book in self.order_books.values()) == len(self.order_books)  

    async def check_connection(self):
        return await self.connection_manager.check_connection()  


    async def ws_parse(self):
        """
            Parse incomming websocket information
        """
        while True:
            #get message from queue
            try:
                message = await self.connection_manager.ws_q.get()
                if 'result' in message and message['result'] is None:
                    continue
                stream = message['stream']
                if 'depth' in stream:
                    await self.parse_order_book_message(message['data'])
                elif stream in self.user_ping_tasks:
                    await self.parse_user_update(message['data'])
            except Exception as e:
                print('Error in ws parse', e)
                print(message)
                raise e

    async def parse_order_book_message(self, message):
        message_data = {'time': message['u'], 'bids': [[float(b), float(v)] for b, v in message['b']], 'asks': [[float(a), float(v)] for a, v in message['a']]} 
        await self.order_book_queues[self.market_names[message['s']]].put(message_data)

    async def parse_user_update(self, message):
        if message['e'] == 'executionReport': 
            order_id = int(message['i'])
            market = self.markets[self.market_names[message['s']]]
            side = message['S'].lower()
            volume = float(message['q'])
            try:
                price = float(message['p']) 
            except TypeError:
                price = None
            order_type = message['o'].lower()
            status = message['X'].lower()
            if status == 'partially_filled':
                status = 'open'
            if status == 'canceled' or status == 'filled' or status == 'rejected':
                status = 'closed'
            filled_volume = float(message['z']) 
            order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
            await self.user_updates.put({'type': 'order_update', 'order': order})

            if message['x'] == 'TRADE':
                fill_id = int(message['t'])  
                time = int(message['E'])
                volume = float(message['l'])
                price = float(message['L'])
                if message['N'] is not None:
                    fees = {message['N']: float(message['n'])}
                fill = Fill(fill_id, order_id, time, market, side, volume, price, fees)
                await self.user_updates.put({'type': 'fill_update', 'fill': fill})

        elif message['e'] == 'outboundAccountPosition':
            pass
            #balance update from trade
        elif message['e'] == 'balanceUpdate':
            pass
            #balance update from deposit etc
        else:
            print('Unrecognised order type')


    #Account Methods

    def sign_params(api_key, secret_key, **kwargs):
        params = {} if 'params' not in kwargs else kwargs['params']
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        ts = int(time.time() * 1000)
        params['timestamp'] = ts
        params['signature'] = hmac.new(secret_key.encode('utf-8'), urllib.parse.urlencode(params).encode('utf-8'), hashlib.sha256).hexdigest()

        headers['X-MBX-APIKEY'] = api_key
        return params, headers

    async def signed_get(self, endpoint, api_key, secret_key, **kwargs):
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = {} if 'params' not in kwargs else kwargs['params']
        timestamp = int(time.time() * 1000)
        params, headers = Binance.sign_params(api_key, secret_key, params=params, headers=headers)
        return await self.connection_manager.rest_get(endpoint, params=params, headers=headers)

    async def signed_post(self, endpoint, api_key, secret_key, **kwargs):   
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = {} if 'params' not in kwargs else kwargs['params']
        params, headers = Binance.sign_params(api_key, secret_key, params=params, headers=headers)
        return await self.connection_manager.rest_post(endpoint, params=params, headers=headers)

    async def signed_delete(self, endpoint, api_key, secret_key, **kwargs):
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = {} if 'params' not in kwargs else kwargs['params']
        params, headers = Binance.sign_params(api_key, secret_key, params=params, headers=headers)
        return await self.connection_manager.rest_delete(endpoint, params=params, headers=headers)

    async def signed_put(self, endpoint, api_key, secret_key, **kwargs):
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = {} if 'params' not in kwargs else kwargs['params']
        params, headers = Binance.sign_params(api_key, secret_key, params=params, headers=headers)
        return await self.connection_manager.rest_put(endpoint, params=params, headers=headers)
        
    
    async def subscribe_to_user_data(self, api_key, secret_key):
        #key = (await self.signed_post('/api/v3/userDataStream', api_key, secret_key))['listenKey']
        key = (await self.connection_manager.rest_post('/api/v3/userDataStream', headers={'X-MBX-APIKEY':api_key}))['listenKey']
        self.user_key = key
        self.user_api = api_key
        ws_request = {'method': 'SUBSCRIBE', 'params': [key]}
        await self.connection_manager.ws_send(ws_request)    
        self.user_ping_tasks[key] = asyncio.create_task(self.user_ping(api_key, key))

    async def user_ping(self, api_key, listen_key):
        await asyncio.sleep(30 * 60)
        while True:
            params = {'listenKey': listen_key}
            await self.connection_manager.rest_put('/api/v3/userDataStream',params=params, headers={'X-MBX-APIKEY': api_key}) 
            await asyncio.sleep(30 * 60)


    async def market_order(self, api_key, secret_key, market, side, volume):
        if volume < self.markets[market].min_provide_size:
            raise ValueError(f"Volume {volume} below minimum for market {self.markets[market].name}")
        params = {
            'symbol': self.markets[market].name,
            'side': side.upper(),
            'type': 'MARKET',
            'quantity': ('{0:.' + str(self.markets[market].base_asset_precision) +'f}').format(volume),
        }

        try:
            response = await self.signed_post('/api/v3/order', api_key, secret_key, params=params)
        except:
            raise OrderPlacementError('Failed to place order')
        
        order_id =  int(response['orderId']) 
        status =  response['status'].lower() 
        filled_volume = float(response['executedQty']) 
        market = self.markets[market] 
        side =  response['side'].lower() 
        price =  float(response['price']) 
        if price == 0:
            price = None
        order_type =  response['type'].lower()
        volume =  float(response['origQty']) 
        order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
        await self.user_updates.put({'type': 'order_update', 'order': order})


    async def limit_order(self, api_key, secret_key,  market, side, price, volume):
        if volume < self.markets[market].min_provide_size:
            raise ValueError(f"Volume {volume} below minimum {self.markets[market].min_provide_size} for market {self.markets[market].name}")
        params = {
            'symbol': self.markets[market].name,
            'side': side.upper(),
            'type': 'LIMIT',
            'price': ('{0:.' + str(self.markets[market].price_precision) +'f}').format(price),
            'quantity': ('{0:.' + str(self.markets[market].base_asset_precision) +'f}').format(volume),
            'timeInForce': 'GTC'
        }
        try:
            response = await self.signed_post('/api/v3/order', api_key, secret_key, params=params)
        except:
            raise OrderPlacementError('Failed to place order')
        
        order_id =  int(response['orderId']) 
        status =  response['status'].lower() 
        if status == 'partially_filled':
            status = 'open'
        if status == 'canceled' or status == 'filled' or status == 'rejected':
            status = 'closed'
        filled_volume = float(response['executedQty']) 
        market = self.markets[market] 
        side =  response['side'].lower() 
        price =  float(response['price']) 
        if price == 0:
            price = None
        order_type =  response['type'].lower()
        volume =  float(response['origQty']) 
        order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
        await self.user_updates.put({'type': 'order_update', 'order': order})

    
    async def dust(self, api_key, secret_key, assets):
        assets = ','.join([a for a in assets if a != 'BNB'])
        if len(assets) == 0:
            return
        await self.signed_post('/sapi/v1/asset/dust', api_key, secret_key, params={'asset': assets})

        
    async def cancel_order(self, api_key, secret_key, order_id, market):
        params = {
            'symbol': market.name,
            'orderId': order_id
        }
        response = await self.signed_delete("/api/v3/order", api_key, secret_key, params=params)                   
        
        order_id =  response['orderId'] 
        status =  response['status'].lower() 
        if status == 'canceled':
            status = 'closed'
        filled_volume = float(response['executedQty']) 
        market = market 
        side =  response['side'].lower() 
        price =  float(response['price']) 
        if price == 0:
            price = None
        order_type =  response['type'].lower()
        volume =  float(response['origQty']) 
        order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
        await self.user_updates.put({'type': 'order_update', 'order': order})

    
        




    async def get_order(self, api_key, secret_key, order_id):
        response = await self.signed_get(f"/api/orders/{order_id}", api_key, secret_key) 
        order_id =  response['result']['id'] 
        status =  response['result']['status'] 
        filled_volume = response['result']['filledSize'] 
        market = self.markets[self.market_names[response['result']['market']]] 
        side =  response['result']['side'] 
        price =  response['result']['price'] 
        order_type =  response['result']['type'] 
        volume =  response['result']['size']
                  
        order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
        await self.user_updates.put({'type': 'order_update', 'order': Order})


    async def get_fills(self, api_key, secret_key, order_id, market):
        params = {
            'symbol': market.name,
            'orderId': order_id
        }
        response = await self.signed_get(f'/api/v3/myTrades', api_key, secret_key, params=params)
        for fill in response:
            market = self.markets[self.market_names[fill['symbol']]]
            order_id = int(fill['orderId'])
            fill_id = int(fill['id'])
            side = 'buy' if fill['isBuyer'] else 'sell'
            volume = float(fill['qty'])
            price = float(fill['price'])
            time = int(fill['time'])
            fees = {fill['commissionAsset']: float(fill['comission'])}

            fill = Fill(fill_id, order_id, time, market, side, volume, price, fees)
            await self.user_updates.put({'type': 'fill_update', 'fill': fill})
            

    async def get_positions(self, api_key, secret_key):
        return []

    async def get_account_balances(self, api_key, secret_key):
        coins = (await self.signed_get('/api/v3/account', api_key, secret_key))['balances']
        free = {coin['asset']: float(coin['free']) for coin in coins}
        locked = {coin['asset']: float(coin['locked']) for coin in coins}

        balance, available =  {a: v + locked[a] for a, v in free.items()}, free
        return {a: v for a, v in balance.items() if v > 0}, {a: v for a, v in available.items() if v > 0}

    async def set_account_leverage(self, api_key, secret_key, rate):
        pass

    async def get_account_info(self, api_key, secret_key):
        return {
                'positions': [],
                'leverage': 0,
                'free_collateral': 0,
                'maker_fee': 0,
                'taker_fee': 0
        } 

    

    async def get_open_orders(self, api_key, secret_key):
        response = (await self.signed_get('/api/v3/openOrders', api_key, secret_key))
        for order in response:
            order_id = int(order['orderId']) 
            status = order['status'].lower() 
            if status == 'partially_filled':
                status = 'open'
            if status == 'canceled' or status == 'filled' or status == 'rejected':
                status = 'closed'
            filled_volume = float(order['executedQty']) 
            market = self.markets[self.market_names[order['symbol']]] 
            side =  order['side'].lower() 
            price =  float(order['price']) 
            order_type =  order['type'].lower() 
            volume =  float(order['origQty'])
                  
            order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
            await self.user_updates.put({'type': 'order_update', 'order': order})
    
    async def get_candles(self, market, start_time, end_time, resolution=60):   
        limit = 1000
        resolutions = {60: '1m', 300: '5m'}
        request_data = {
            'symbol': self.markets[market].name,
            'interval': resolutions[resolution],
            'startTime': int(start_time * 1000),
            'endTime': int(end_time * 1000),
            'limit': 1000
        }
        market = self.markets[market].name
        response = await self.connection_manager.rest_get('/api/v3/klines', params=request_data)
        return [{h: float(v) for h, v in zip(['time', 'open', 'high', 'low', 'close', 'base_volume', 'close_time', 'volume', 'n_trades', 'taker_buy', 'taker_sell'], r[:11]) } for r in response] 

