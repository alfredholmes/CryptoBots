import asyncio, time, hashlib, hmac, urllib, json
from abc import ABC, abstractmethod
from .connections import ConnectionManager
from contextlib import suppress
import httpx
from .orderbooks import OrderBook
from .exchanges import Exchange, Fill, Position, SpotMarket, Order, FutureMarket, OrderPlacementError, OrderClosed


class FTX(Exchange):
    rest_endpoint = 'https://ftx.com'
    ws_endpoint = 'wss://ftx.com/ws/'
    
    async def connect(self):
        """
            Method to get exchange market data and create websocket refresh task

        """
        try:
            trading_markets = (await self.connection_manager.rest_get('/api/markets'))['result']
            for market_meta in trading_markets:
                if not market_meta['enabled']:
                    continue
                if market_meta['type'] == 'spot':
                    market = SpotMarket(market_meta['baseCurrency'], market_meta['quoteCurrency'], market_meta['name'])
                    self.markets[(market_meta['baseCurrency'], market_meta['quoteCurrency'])] = market
                elif market_meta['type'] == 'future':
                    market = FutureMarket(market_meta['underlying'], market_meta['name'])
                    self.markets[market_meta['underlying'], market_meta['name'].split('-')[-1]] = market
                market.enabled = market_meta['enabled'] 
                market.postOnly = market_meta['postOnly']
                market.price_increment = market_meta['priceIncrement']
                market.size_increment = market_meta['sizeIncrement']
                market.min_provide_size = market_meta['minProvideSize']
                market.underlying = market_meta['underlying']   
                market.restricted = market_meta['restricted']
                market.high_leverage_fee_exempt = market_meta['highLeverageFeeExempt']  
                market.daily_volume_usd = market_meta['volumeUsd24h']
        except:
            raise
        self.ping_task = asyncio.create_task(self.ws_ping())
        self.parse_task = asyncio.create_task(self.ws_parse())
        for market in self.markets.values():
            if market.type == 'spot':
                self.market_names[market.name] = (market.base, market.quote)
            else:
                self.market_names[market.name] = (market.underlying, market.name.split('-')[-1])
    async def close(self): 
        self.ping_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.ping_task
        super().close()

    #Market Data methods
    async def reconnect(self):
        await self.unsubscribe_from_order_books(*self.order_books)
        await self.connection_manager.close()

        self.markets = {}
        self.order_books = {}
        self.order_book_queues = {}
        self.market_names = {}

        self.ping_task.cancel()
        self.parse_task.cancel()

        with suppress(asyncio.CancelledError):
            await self.ping_task
            await self.parse_task


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
        
            requests = []
            for market in to_subscribe:
                if market not in self.markets:
                    raise Exception('Invalid Market ' + str(market) + ' not listed on exchange. Maybe exchange.connect() not been executed')
                order_book_queue = asyncio.Queue()
                self.order_book_queues[market] = order_book_queue
                self.order_books[market] = OrderBook(order_book_queue)
            ws_request = [{'op': 'subscribe', 'channel': 'orderbook', 'market': self.markets[market].name} for market in to_subscribe]  
            await asyncio.gather(*[self.connection_manager.ws_send(req) for req in ws_request])
            await asyncio.gather(*[self.order_books[market].initialised_event.wait() for market in to_subscribe])


    async def unsubscribe_from_order_books(self, *markets):
        """
            Unsubscribe from markets order books
        """
        async with self.connection_lock:
            ws_requests = [{'op': 'unsubscribe', 'channel': 'orderbook', 'market': self.markets[market].name} for market in markets]
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
                if message['type'] == 'error':
                    print('WS Error:')
                    raise Exception(message)    
                elif message['type'] == 'pong':
                    #ignore pongs
                    pass
                elif message['channel'] == 'orderbook':
                    await self.parse_order_book_message(message)
                elif message['channel'] == 'fills':
                    await self.parse_fill_message(message)
                elif message['channel'] == 'orders':
                    await self.parse_order_message(message)
                if self.connection_manager.open:
                    self.connection_manager.ws_q.task_done()
            except Exception as e:
                print('Error in ws parse', e)
                raise e

    async def parse_order_book_message(self, message):
        if message['type'] == 'subscribed':
            #TODO: add in subscription handling / error checking.
            return  
        if message['type'] == 'unsubscribed':
            message_data = ['unsubscribed']
            await self.order_book_queues[self.market_names[message['market']]].put(message_data)
            return
        message_data = {'time': message['data']['time'], 'bids': message['data']['bids'], 'asks': message['data']['asks'], 'checksum': message['data']['checksum']}
        if message['type'] == 'partial':
            message_data['initial'] = True
        await self.order_book_queues[self.market_names[message['market']]].put(message_data)

    async def parse_order_message(self, message):
        if message['type'] == 'subscribed':
            await self.user_updates.put({'type': 'order_subscription', 'success': True})
        else:
            order_id =  message['data']['id'] 
            status =  message['data']['status'] 
            filled_volume = message['data']['filledSize'] 
            market = self.markets[self.market_names[message['data']['market']]] 
            side =  message['data']['side'] 
            price =  message['data']['price'] 
            order_type =  message['data']['type'] 
            volume =  message['data']['size']
            
                  
            order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
            await self.user_updates.put({'type': 'order_update', 'order': order})

    async def parse_fill_message(self, message):
        if message['type'] == 'subscribed':     
            await self.user_updates.put({'type': 'fill_subscription', 'success': True})
        else:
            market = self.markets[self.market_names[message['data']['market']]]
            order_id = message['data']['orderId']
            fill_id = message['data']['tradeId']
            side = message['data']['side']
            volume = message['data']['size']
            price = message['data']['price']
            time = message['data']['time']
            fees = {message['data']['feeCurrency']: message['data']['fee']}

            fill = Fill(fill_id, order_id, time, market, side, volume, price, fees)
            await self.user_updates.put({'type': 'fill_update', 'fill': fill})

    def verify_order_book_checksum(bids, asks, checksum):
        #TODO: Implement
        pass

    async def ws_ping(self):
        while self.connection_manager.open:
            data = {'op': 'ping'}
            await self.connection_manager.ws_send(data)
            #send ping more than every 15 minutes to keep the connection alive
            await asyncio.sleep(15 * 60 - 30)

    #Account Methods

    def sign_headers(headers, api_key, secret_key, subaccount, method, url, params = None):
        ts = int(time.time() * 1000)
        payload = str(ts) + method.upper() + url
        if params is not None:
            payload += json.dumps(params)
        headers['FTX-KEY'] = api_key
        headers['FTX-SIGN'] = hmac.new(secret_key.encode(), payload.encode(), 'sha256').hexdigest()
        headers['FTX-TS'] = str(ts)
        if subaccount is not None:
            headers['FTX-SUBACCOUNT'] = urllib.parse.quote(subaccount)

    async def signed_get(self, endpoint, api_key, secret_key, subaccount, **kwargs):
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = None if 'params' not in kwargs else kwargs['params']
        FTX.sign_headers(headers, api_key, secret_key, subaccount, 'GET', endpoint)
        return await self.connection_manager.rest_get(endpoint, params=params, headers=headers)

    async def signed_post(self, endpoint, api_key, secret_key, subaccount, **kwargs):   
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = None if 'params' not in kwargs else kwargs['params']
        FTX.sign_headers(headers, api_key, secret_key, subaccount, 'POST', endpoint, params)
        return await self.connection_manager.rest_post(endpoint, params=params, headers=headers)

    async def signed_delete(self, endpoint, api_key, secret_key, subaccount, **kwargs):
        headers = {} if 'headers' not in kwargs else kwargs['headers']
        params = None if 'params' not in kwargs else kwargs['params']
        FTX.sign_headers(headers, api_key, secret_key, subaccount, 'DELETE', endpoint, params)
        return await self.connection_manager.rest_delete(endpoint, params=params, headers=headers)
        
    
    async def ws_login(self, api_key, secret_key, subaccount):
        ts = int(time.time() * 1000)
        payload = str(ts) + 'websocket_login'
        signature = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        body = {
            'args': {
                'key': api_key,
                'sign': signature,
                'time': ts
            },
            'op': 'login'
        }
        if subaccount is not None: 
            body['args']['subaccount'] =  urllib.parse.quote(subaccount)
        await self.connection_manager.ws_send(body)

    async def subscribe_to_orders(self, api_key, secret_key, subaccount):
        body = {
            'op': 'subscribe',
            'channel': 'orders'
        }
        await self.connection_manager.ws_send(body)


    async def subscribe_to_fills(self, api_key, secret_key, subaccount):
        body = {
            'op': 'subscribe',
            'channel': 'fills'
        }
        await self.connection_manager.ws_send(body)
    
    async def subscribe_to_user_data(self, api_key, secret_key, subaccount):
        await self.ws_login(api_key, secret_key, subaccount)
        await self.subscribe_to_orders(api_key, secret_key, subaccount)
        await self.subscribe_to_fills(api_key, secret_key, subaccount)

    async def market_order(self, api_key, secret_key, subaccount, market, side, volume):
        if volume < self.markets[market].min_provide_size:
            raise ValueError(f"Volume {volume} below minimum for market {self.markets[market].name}")
        params = {
            'market': self.markets[market].name,
            'side': side.lower(),
            'type': 'market',
            'size': round(volume, 10),
            'price': None
        }


        response = await self.signed_post('/api/orders', api_key, secret_key, subaccount, params=params)
        if not response['success']:
            raise OrderPlacementError('Failed to place order')
        
        order_id =  response['result']['id'] 
        status =  response['result']['status'] 
        filled_volume = response['result']['filledSize'] 
        market = self.markets[self.market_names[response['result']['market']]] 
        side =  response['result']['side'] 
        price =  response['result']['price'] 
        order_type =  response['result']['type'] 
        volume =  response['result']['size']
                  
        order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
        await self.user_updates.put({'type': 'order_update', 'order': order})


    async def limit_order(self, api_key, secret_key, subaccount, market, side, price, volume):
        if volume < self.markets[market].min_provide_size:
            raise ValueError(f"Volume {volume} below minimum {self.markets[market].min_provide_size} for market {self.markets[market].name}")
        params = {
            'market': self.markets[market].name,
            'side': side.lower(),
            'type': 'limit',
            'size': round(volume, 10) + 10 ** -14,
            'price': round(price, 10) + 10 ** -14
        }

        response = await self.signed_post('/api/orders', api_key, secret_key, subaccount, params=params)
        if not response['success']:
            raise OrderPlacementError("Failed to place order")
            return

        order_id =  response['result']['id'] 
        status =  response['result']['status'] 
        filled_volume = response['result']['filledSize'] 
        market = self.markets[self.market_names[response['result']['market']]] 
        side =  response['result']['side'] 
        price =  response['result']['price'] 
        order_type =  response['result']['type'] 
        volume =  response['result']['size']
                  
        order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
        await self.user_updates.put({'type': 'order_update', 'order': order})
    
    async def dust(self, api_key, secret_key, subaccount, conversions):
        pass

    async def get_convert_quote(self, api_key, secret_key, subaccount, from_coin, to_coin, volume): 
        params = {'fromCoin': from_coin, 'toCoin': to_coin, 'size': volume}
        quote_id = (await self.signed_post('/api/otc/quotes', api_key, secret_key, subaccount, params=params))['result']['quoteId']
        quote_details = (await self.signed_get(f'/api/otc/quotes/{quote_id}', api_key, secret_key, subaccount))['result']
     
        return quote_id, quote_details['price'], quote_details['expiry']

    async def accept_convert_quote(self, api_key, secret_key, subaccount, quote_id):
        await self.signed_post(f'/api/otc/quotes/{quote_id}/accept', api_key, secret_key, subaccount)
       


    async def cancel_order(self, api_key, secret_key, subaccount, order_id, market):
        try:
            response = await self.signed_delete(f"/api/orders/{order_id}", api_key, secret_key, subaccount)                   
        except httpx.HTTPStatusError as e: 
            response = e.response
            if response['error'] != "Order already closed" and response['error'] != 'Order already queued for cancellation':
                raise e 
            
            else:
                raise OrderClosed(order_id)


    async def cancel_all_orders(self, api_key, secret_key, subaccount):
        await self.signed_delete(f"/api/orders", api_key, secret_key, subaccount)             


    async def get_order(self, api_key, secret_key, subaccount, order_id):
        response = await self.signed_get(f"/api/orders/{order_id}", api_key, secret_key, subaccount)
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


    async def get_fills(self, api_key, secret_key, subaccount, order_id = None):
        response = await self.signed_get(f'/api/fills?orderId={order_id}', api_key, secret_key, subaccount)
        for fill in response['result']:
            market = self.markets[self.market_names[fill['market']]]
            order_id = fill['orderId']
            fill_id = fill['tradeId']
            side = fill['side']
            volume = fill['size']
            price = fill['price']
            time = fill['time']
            fees = {fill['feeCurrency']: fill['fee']}

            fill = Fill(fill_id, order_id, time, market, side, volume, price, fees)
            await self.user_updates.put({'type': 'fill_update', 'fill': fill})
            

    async def get_positions(self, api_key, secret_key, subaccount):
        position_response = (await self.signed_get('/api/positions', api_key, secret_key, subaccount))['result']
        positions = []
        for position in position_response:
            market = self.markets[self.market_names[position['future']]]
            side = -1 if position['side'] == 'sell' else 1
            if position['openSize'] == 0:
                continue
            margin_requirement = position['entryPrice'] * position['size'] * position['initialMarginRequirement']
            positions.append(Position(market, side, position['size'], position['entryPrice'], margin_requirement))
            positions[-1].pnl = position['unrealizedPnl']
        return positions

    async def get_account_balances(self, api_key, secret_key, subaccount):
        coins = (await self.signed_get('/api/wallet/balances', api_key, secret_key, subaccount))['result']
        return {coin['coin']: coin['total'] for coin in coins if coin['total'] > 0}, {coin['coin']: coin['availableWithoutBorrow'] for coin in coins if coin['availableWithoutBorrow'] > 0}

    async def set_account_leverage(self, api_key, secret_key, subaccount, rate):
        data = {'leverage': rate}
        await self.signed_post('/api/account/leverage', api_key, secret_key, subaccount, params=data)

    async def get_account_info(self, api_key, secret_key, subaccount):
        account_data = (await self.signed_get('/api/account', api_key, secret_key, subaccount))['result']
        positions = []
        for position_response in account_data['positions']:
            side = -1 if position_response['side'] == 'sell' else 1
            positions.append(Position(self.markets[self.market_names[position_response['future']]], side, position_response['size'], position_response['entryPrice'], position_response['initialMarginRequirement']))
        return {
                'positions': positions,
                'leverage': account_data['leverage'],
                'free_collateral': account_data['freeCollateral'],
                'maker_fee': account_data['makerFee'],
                'taker_fee': account_data['takerFee']
        } 

    

    async def get_open_orders(self, api_key, secret_key, subaccount):
        response = (await self.signed_get('/api/orders', api_key, secret_key, subaccount))['result']
        for order in response:
            order_id = order['id'] 
            status = order['status'] 
            filled_volume = order['filledSize'] 
            market = self.markets[self.market_names[order['market']]] 
            side =  order['side'] 
            price =  order['price'] 
            order_type =  order['type'] 
            volume =  order['size']
                  
            order = Order(order_id, market, side, volume, price, order_type, status, filled_volume)
            await self.user_updates.put({'type': 'order_update', 'order': order})
    
    async def get_candles(self, market, start_time, end_time, resolution=15):   
        limit = 1500
        request_data = {
            'resolution': resolution,
            'start_time': start_time,
            'end_time': end_time
        }
        market = self.markets[market].name
        response = await self.connection_manager.rest_get('/api/markets/' + market + '/candles', params=request_data)
        return response['result'] 

