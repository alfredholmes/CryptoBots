import asyncio, time, hashlib, hmac, urllib, json
from abc import ABC, abstractmethod
from .connections import ConnectionManager
from contextlib import suppress
import httpx
from .orderbooks import OrderBook
from .book_ticker import BookTicker
from .exchanges import Exchange, Fill, Position, SpotMarket, Order, FutureMarket, OrderPlacementError, OrderClosed


class BinanceFutures(Exchange):
    rest_endpoint = 'https://fapi.binance.com'
    ws_endpoint = 'wss://fstream.binance.com/stream'

    def __init__(self):
        self.user_ping_tasks = {}        
        super().__init__()

    async def connect(self):
        """
            Method to get exchange market data and create websocket refresh task

        """
        try:
            exchange_info = (await self.connection_manager.rest_get('/fapi/v1/exchangeInfo'))
            self.rate_limits = exchange_info['rateLimits']
            trading_markets = exchange_info['symbols']
            for market_meta in trading_markets:
                if market_meta['status'] != 'TRADING':
                    continue

                if market_meta['quoteAsset'] != 'USDT' or market_meta['contractType'] != 'PERPETUAL' or market_meta['underlyingType'] != 'COIN':
                    continue
                market = FutureMarket(market_meta['baseAsset'], market_meta['symbol'], (market_meta['baseAsset'], 'PERP'))
                 
                market.enabled = True 
                market.base_asset_precision = int(market_meta['baseAssetPrecision'])
                market.quote_precision = int(market_meta['quotePrecision'])
                market.price_precision = int(market_meta['pricePrecision'])
                for data_filter in market_meta['filters']:
                    if data_filter['filterType'] == 'PRICE_FILTER':
                        market.price_increment  = float(data_filter['tickSize'])

                    if data_filter['filterType'] == 'LOT_SIZE':
                        market.size_increment = float(data_filter['stepSize'])
                        market.min_provide_size = float(data_filter['minQty'])        
                    if data_filter['filterType'] == 'MIN_NOTIONAL':
                        market.min_quote_volume = float(data_filter['notional'])
                self.markets[(market.underlying, 'PERP')] = market
                
        except:
            raise
        self.parse_task = asyncio.create_task(self.ws_parse())
        for market in self.markets.values():
            self.market_names[market.name] = market.pair

    async def subscribe_to_prices(self):
        prices = await self.connection_manager.rest_get('/fapi/v1/ticker/bookTicker')
        for ticker in prices:
            data = {
                'bid_price': float(ticker['bidPrice']),
                'bid_volume': float(ticker['bidQty']),
                'ask_price': float(ticker['askPrice']),
                'ask_volume': float(ticker['askQty']),
                'time': int(ticker['time'])
            }
            if ticker['symbol'] in self.market_names:
                self.markets[self.market_names[ticker['symbol']]].ticker = BookTicker(data) 
        
        ws_req = {'method': 'SUBSCRIBE', 'params': ['!bookTicker']}
        await self.connection_manager.ws_send(ws_req)

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
        depth = await self.connection_manager.rest_get(f'/fapi/v1/depth', params={'symbol': self.markets[market].name, 'limit':100})
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
        await self.connection_manager.rest_get('/fapi/v1/ping') 
        return True

    async def get_account_positions(self, api_key, secret_key):
        position_risk = await self.signed_get('/fapi/v2/positionRisk', api_key, secret_key)
        positions = []
        for position in position_risk:
            market = self.markets[self.market_names[position['symbol']]] 
            side = -1 if float(position['positionAmt']) < 0 else 1
            volume = abs(float(position['positionAmt']))
            entry_price = float(position['entryPrice'])
            poitions.append(Position(market, side, volume, entry_price, margin_requirement))
        

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
                elif stream == '!bookTicker' and message['data']['s'] in self.market_names:
                    if self.markets[self.market_names[message['data']['s']]].ticker.time <  int(message['data']['E']):
                        self.markets[self.market_names[message['data']['s']]].ticker.bid_price =  float(message['data']['b']) 
                        self.markets[self.market_names[message['data']['s']]].ticker.bid_volume = float(message['data']['B']) 
                        self.markets[self.market_names[message['data']['s']]].ticker.ask_price = float(message['data']['a']) 
                        self.markets[self.market_names[message['data']['s']]].ticker.ask_volume = float(message['data']['A']) 
                
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
        if message['e'] == 'ORDER_TRADE_UPDATE': 
            message = message['o']
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
            print('order volume in parse', volume, price, status)
            order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
            await self.user_updates.put({'type': 'order_update', 'order': order})

            if message['x'] == 'TRADE':
                fill_id = int(message['t'])  
                time = int(message['T'])
                volume = float(message['l'])
                price = float(message['L'])
                if 'N' in message:
                    fees = {message['N']: float(message['n'])}
                fill = Fill(fill_id, order_id, time, market, side, volume, price, fees)
                await self.user_updates.put({'type': 'fill_update', 'fill': fill})

        elif message['e'] == 'ACCOUNT_UPDATE':
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
        params, headers = BinanceFutures.sign_params(api_key, secret_key, params=params, headers=headers)
        return await self.connection_manager.rest_get(endpoint, params=params, headers=headers)

    async def signed_post(self, endpoint, api_key, secret_key, **kwargs):   
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = {} if 'params' not in kwargs else kwargs['params']
        params, headers = BinanceFutures.sign_params(api_key, secret_key, params=params, headers=headers)
        return await self.connection_manager.rest_post(endpoint, params=params, headers=headers)

    async def signed_delete(self, endpoint, api_key, secret_key, **kwargs):
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = {} if 'params' not in kwargs else kwargs['params']
        params, headers = BinanceFutures.sign_params(api_key, secret_key, params=params, headers=headers)
        return await self.connection_manager.rest_delete(endpoint, params=params, headers=headers)

    async def signed_put(self, endpoint, api_key, secret_key, **kwargs):
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = {} if 'params' not in kwargs else kwargs['params']
        params, headers = BinanceFutures.sign_params(api_key, secret_key, params=params, headers=headers)
        return await self.connection_manager.rest_put(endpoint, params=params, headers=headers)
        
    
    async def subscribe_to_user_data(self, api_key, secret_key):
        #key = (await self.signed_post('/api/v3/userDataStream', api_key, secret_key))['listenKey']
        key = (await self.connection_manager.rest_post('/fapi/v1/listenKey', headers={'X-MBX-APIKEY':api_key}))['listenKey']
        self.user_key = key
        self.user_api = api_key
        ws_request = {'method': 'SUBSCRIBE', 'params': [key]}
        await self.connection_manager.ws_send(ws_request)    
        self.user_ping_tasks[key] = asyncio.create_task(self.user_ping(api_key, key))

    async def user_ping(self, api_key, listen_key):
        await asyncio.sleep(30 * 60)
        while True:
            params = {'listenKey': listen_key}
            await self.connection_manager.rest_put('/fapi/v1/listenKey',params=params, headers={'X-MBX-APIKEY': api_key}) 
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
            response = await self.signed_post('/fapi/v1/order', api_key, secret_key, params=params)
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


    async def limit_order(self, api_key, secret_key,  market, side, price, volume, **kwargs):
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
        for k, v in kwargs.items():
            params[k] = v
        try:
            response = await self.signed_post('/fapi/v1/order', api_key, secret_key, params=params)
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
        print('order volume in order', volume, price, status)
        order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
        await self.user_updates.put({'type': 'order_update', 'order': order})

    

        
    async def cancel_order(self, api_key, secret_key, order_id, market):
        params = {
            'symbol': market.name,
            'orderId': order_id
        }
        response = await self.signed_delete("/fapi/v1/order", api_key, secret_key, params=params)                   
        
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

    
        






    async def get_fills(self, api_key, secret_key, order_id, market):
        params = {
            'symbol': market.name,
            'orderId': order_id
        }
        response = await self.signed_get(f'/fapi/v1/trades', api_key, secret_key, params=params)
        for fill in response:
            market = self.markets[self.market_names[fill['symbol']]]
            if order_id != int(fill['orderId']):
                continue            
            fill_id = int(fill['id'])
            side = 'buy' if fill['isBuyer'] else 'sell'
            volume = float(fill['qty'])
            price = float(fill['price'])
            time = int(fill['time'])
            fees = {fill['commissionAsset']: float(fill['comission'])}

            fill = Fill(fill_id, order_id, time, market, side, volume, price, fees)
            await self.user_updates.put({'type': 'fill_update', 'fill': fill})
            


    async def get_account_balances(self, api_key, secret_key):
        coins = (await self.signed_get('/fapi/v2/balance', api_key, secret_key))
        balance = {coin['asset']: float(coin['balance']) for coin in coins}
        available = {coin['asset']: float(coin['availableBalance']) for coin in coins}

        return {a: v for a, v in balance.items() if v > 0}, {a: v for a, v in available.items() if v > 0}

    async def set_account_leverage(self, api_key, secret_key, rate):
        pass

    async def get_account_info(self, api_key, secret_key):
        account_info = await self.signed_get('/fapi/v2/account', api_key, secret_key)
        positions = []
        for position in account_info['positions']:
            if float(position['positionAmt']) == 0:
                continue
            market = self.markets[self.market_names[position['symbol']]] 
            side = -1 if float(position['positionAmt']) < 0 else 1 
            volume = abs(float(position['positionAmt']))
            entry_price = float(position['entryPrice'])
            margin_requirement = float(position['initialMargin'])

            positions.append(Position( market, side, volume, entry_price, margin_requirement))

        leverage = min(int(b['leverage']) for b in account_info['positions'])
            
        return {
                'positions': positions,
                'leverage': leverage,
                'free_collateral': float(account_info['availableBalance'])
        }

    async def get_positions(self, api_key, secret_key): 
        account_info = await self.signed_get('/fapi/v2/account', api_key, secret_key)
        positions = []
        for position in account_info['positions']:
            if float(position['positionAmt']) == 0:
                continue
            market = self.markets[self.market_names[position['symbol']]] 
            side = -1 if float(position['positionAmt']) < 0 else 1 
            volume = abs(float(position['positionAmt']))
            entry_price = float(position['entryPrice'])
            margin_requirement = float(position['initialMargin'])

            positions.append(Position( market, side, volume, entry_price, margin_requirement))
            positions[-1].pnl = float(position['unrealizedProfit'])
        return positions

    async def get_open_orders(self, api_key, secret_key):
        response = (await self.signed_get('/fapi/v1/openOrders', api_key, secret_key))
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
    
    async def get_candles(self, market, start_time, end_time, resolution=60, limit=1500):   
        limit = 1000
        resolutions = {60: '1m', 300: '5m'}
        request_data = {
            'symbol': self.markets[market].name,
            'interval': resolutions[resolution],
            'startTime': int(start_time * 1000),
            'endTime': int(end_time * 1000),
            'limit': limit
        }
        market = self.markets[market].name
        response = await self.connection_manager.rest_get('/fapi/v1/klines', params=request_data)
        return [{h: float(v) for h, v in zip(['time', 'open', 'high', 'low', 'close', 'base_volume', 'close_time', 'volume', 'n_trades', 'taker_buy', 'taker_sell'], r[:11]) } for r in response] 

