import asyncio, math
from contextlib import suppress
from abc import ABC, abstractmethod
from httpx import HTTPStatusError

from .exchanges import Position, OrderClosed
from .exchanges import Order, Fill

import logging
from logging.handlers import TimedRotatingFileHandler

class RequestError(Exception):
    """
        Exception raised when account request fails
    """





class SpotAccount:
    order_limit = 6
    def __init__(self, keys, exchange, collateral_asset, name=None, timeout=10):
        self.exchange = exchange
        self.keys = keys
        self.orders = {}
        self.positions = {}
        self.open_orders = {}
        self.unhandled_fills = {}
        self.name = name
        self.collateral_asset = collateral_asset

        self.update_task = asyncio.create_task(self.parse_updates())
        self.fill_event = asyncio.Event()
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.logger.setLevel(logging.DEBUG)
        if name is None:
            ch = logging.StreamHandler()
        else:
            ch = TimedRotatingFileHandler(f"logs/accounts.{name}.log", backupCount = 5)
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        self.running = True




    async def __aenter__(self):
        await self.get_account_data()
        return self 
        

    async def __aexit__(self, *details): 
        self.update_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.update_task 


    async def parse_updates(self):
        while self.running:
            try:
                update = await asyncio.wait_for(self.exchange.user_updates.get(), 5 * 60)
            except asyncio.TimeoutError:
                self.logger.debug('5 minutes since update, refreshing account')
                try:
                    await self.get_account_balance()
                    await self.get_account_positions()
                    await self.get_open_orders()
                except Exception:
                    pass
                continue

            self.logger.debug(f'number of open orders {len(self.open_orders)}')
            try:
                await self.parse_update(update)
            except Exception:
                self.logger.exception('Failed to update')
                self.logger.debug('Refreshing orders')
                await self.get_open_orders()
               
                for order_id in self.open_orders:
                    await self.get_fills(order_id)

    async def parse_update(self, update):
        
        if update['type'] == 'order_update':
            order = update['order']
            if order.id not in self.orders:
                self.new_order(order)
                self.orders[order.id] = order 
                if order.status == 'new' or order.status == 'open':
                    self.logger.debug('new order')
                    self.open_orders[order.id] = order
                    
                if order.id in self.unhandled_fills:
                    for unhandled in self.unhandled_fills[order.id]:
                        if self.exchange[unhandled.market].type == 'spot':
                            self.apply_spot_fill_update(unhandled)
                        else:
                            self.apply_future_fill_update(unhandled)
                    del self.unhandled_fills[order.id]
            else:
                self.apply_order_update(update['order'])
        elif update['type'] == 'fill_update':
            self.fill_event.set()
            self.fill_event.clear()
            fill = update['fill']
            if fill.order_id in self.orders and fill.id not in self.orders[fill.order_id].fills:
                if fill.market.type == 'spot':
                    self.apply_spot_fill_update(fill)
                elif fill.market.type == 'future':
                    self.apply_future_fill_update(fill)
            else:
                if fill.order_id not in self.unhandled_fills:
                    self.unhandled_fills[fill.order_id] = []
                self.unhandled_fills[fill.order_id].append(fill)
    
    async def dust(self, base_asset, prices):
        assets = []
        for asset, v in self.balance.items():
            if v == 0 or (asset, base_asset) not in self.exchange.markets:
                continue
            if v < self.exchange.markets[(asset, base_asset)].min_provide_size:
                assets.append(asset)
            elif asset in prices and v * prices[asset] < self.exchange.markets[(asset, base_asset)].min_quote_volume:
                assets.append(asset)
        if len(assets) > 0:
             self.logger.info(f'Dusting {assets}')
             await self.exchange.dust(*self.keys, assets)

    async def convert_small_balance_to_usd(self):
        for asset, v in self.balance.items():
            if asset == 'USD':
                continue
            if v > 0 and v < self.exchange.markets[(asset, 'USD')].min_provide_size:
                try:
                    await self.convert_to_usd(asset)
                except Exception:
                    self.logger.exception('Error converting to USD')
                await asyncio.sleep(0.4)

    async def convert_to_usd(self, asset):
        quote, price, time = await self.exchange.get_convert_quote(*self.keys, asset, 'USD', self.balance[asset])
        await self.exchange.accept_convert_quote(*self.keys, quote)

    def apply_order_update(self, new_order):
        current_order = self.orders[new_order.id] 
        self.logger.debug(f"Order update, {new_order.id}")        
        current_order.status = new_order.status
        if new_order.status == 'closed':   
            current_order.filled_volume = new_order.filled_volume
            current_order.volume = new_order.filled_volume
            if current_order.id in self.open_orders and current_order.recorded_fills == current_order.filled_volume:
                del self.open_orders[current_order.id]
            self.new_order(current_order)
        elif new_order.status != 'requested_cancellation':
            current_order.status = new_order.status
            current_order.filled_volume = new_order.filled_volume 
            self.new_order(current_order) 

    

    def apply_future_fill_update(self, fill):
        for asset, fee in fill.fees.items():
            self.balance[asset] -= fee
        try:
            self.free_collateral -= fill.fees[self.collateral_asset]
        except KeyError:
            pass
        
        if fill.market.pair not in self.positions:
            side = -1 if fill.side == 'sell' else 1
            self.positions[fill.market.pair] = Position(fill.market,  side,  fill.volume, fill.price, fill.price * fill.volume / self.leverage)
            self.free_collateral -= self.positions[fill.market.pair].margin_requirement
        else:
            original_position = self.positions[fill.market.pair]
            
            signed_fill_volume = -fill.volume if fill.side == 'sell' else fill.volume
            
            new_volume = original_position.volume * original_position.side + signed_fill_volume 
            
            if original_position.side * signed_fill_volume < 0:
                #reducing position
                self.balance[self.collateral_asset] += original_position.side * (fill.price - original_position.entry_price) * fill.volume
                if new_volume * original_position.side < 0:
                    side = -original_position.side
                    margin_requirement = fill.volume * fill.price / self.leverage
                    entry_price = fill.price
                else:
                    side = original_position.side
                    margin_requirement = original_position.margin_requirement * abs(new_volume) / original_position.volume 
                    entry_price = original_position.entry_price
            else:
                #increasing position
                new_volume = original_position.volume + fill.volume
                side = original_position.side
                margin_requirement = original_position.margin_requirement + fill.volume * fill.price / self.leverage
                entry_price = fill.volume / abs(new_volume) * fill.price + (original_position.volume) / abs(new_volume) * original_position.entry_price  

                
            self.free_collateral -= original_position.margin_requirement - margin_requirement 
            self.positions[fill.market.pair] = Position(fill.market, side, abs(new_volume), entry_price, margin_requirement) 

            if new_volume == 0:
                del self.positions[fill.market.pair]
        
        order = self.orders[fill.order_id]
        order.fills[fill.id] = fill
        order.recorded_fills += fill.volume
        order.remaining_volume = order.volume - order.recorded_fills
        if order.remaining_volume <= 0 and order.id in self.open_orders:
            del self.open_orders[order.id]
        self.new_order(self.orders[fill.order_id])

             

            
           
            


    def apply_spot_fill_update(self, fill):
        order = None
        self.logger.debug(f"Fill update received {fill}")
        if fill.order_id in self.orders:
                order = self.orders[fill.order_id]
                order.fills[fill.id] = fill
                order.recorded_fills += fill.volume
                order.remaining_volume = order.volume - order.recorded_fills
                if fill.order_id in self.open_orders and order.remaining_volume == 0:
                    self.logger.info(f"Order {fill.order_id} fully filled")
                    del self.open_orders[fill.order_id]
        else:
                self.logger.warning(f"Fill recived for order {fill.order_id} not tracked")
                
        side = fill.side
        market = fill.market.pair
        changes = {}
        volume_modifyer = -1 if side == 'sell' else 1

        changes = {market[0]: volume_modifyer * fill.volume, market[1]: -volume_modifyer * fill.volume * fill.price} 
        for currency, fee in fill.fees.items():
            if currency not in changes:
                changes[currency] = 0
            changes[currency] -= fee
        
        for currency, change in changes.items():    
            if currency not in self.balance:
                self.balance[currency] = 0 
            if currency not in self.available:
                self.available[currency] = 0

            self.available[currency] += change
            self.balance[currency] += change

            if order is not None and order.type == 'limit':
                if change < 0:
                    self.available[currency] -= change 
        self.logger.debug(self.balance)

    def new_order(self, order):
        if order.type == 'limit':
            if order.side == 'buy' and order.market.type == 'spot':
                #quote asset no longer available
                order.balance_mod[order.market.quote] = -(order.volume - order.recorded_fills) * order.price         
            elif order.side == 'sell' and order.market.type == 'spot': 
                #base asset no longer avail 
                order.balance_mod[order.market.base] = -(order.volume - order.recorded_fills)

            if order.market.type == 'future':
                #if we already have a position in the future
                if order.market in self.positions:
                    position = self.positions[order.market.pair]
                    #let position_volume be the signed volume of the position
                    position_volume = position.side * position.volume
                else:
                    position_volume = 0

            
                side = -1 if order.side == 'sell' else 1
                required_collateral = position_volume - (order.volume - order.remaining_volume) * side
                if abs(required_collateral) > abs(position_volume):
                    #increasing position
                    self.free_collateral -= (order.volume - order.remaining_volume) * order.price / self.leverage
                
            
    def available(self):
        """
            Return the available account balance
        """
        available = dict(self.balance)
        for order in self.open_orders:
            for asset, modification in order.balance_mod:
               available[asset] += modification
                


    async def get_account_data(self):
        await self.get_account_info()
        await self.get_account_balance()
        await self.get_account_positions()
        
        await self.exchange.subscribe_to_user_data(*self.keys)
        await self.get_open_orders()


    def add_positions(self, positions):
        for position in positions:
            if position.volume != 0:
                self.positions[position.market.pair] = position

    async def get_account_positions(self):
        self.positions = {}
        positions = await self.exchange.get_positions(*self.keys)
        self.add_positions(positions)
        pnl = 0 
        for position in self.positions.values():
            pnl += position.pnl

        if self.collateral_asset in self.balance:
            self.balance[self.collateral_asset] -= pnl
        
    

    async def get_account_balance(self):
        self.balance, self.available = await self.exchange.get_account_balances(*self.keys)
        await self.get_account_positions()

    async def get_account_info(self):
        account_info = await self.exchange.get_account_info(*self.keys)
        #self.add_positions(account_info['positions'])
        self.leverage = account_info['leverage']
        self.free_collateral = account_info['free_collateral']
        #self.maker_fee = account_info['maker_fee']
        #self.taker_fee = account_info['taker_fee']
    
    async def get_open_orders(self): 
        self.orders = {}
        self.open_orders = {}
        await self.exchange.get_open_orders(*self.keys)
        await self.get_account_balance()

    async def get_fills(self, order_id = None):
        if order_id is None:
            market = None
        else:
            market = self.orders[order_id].market
        await self.exchange.get_fills(*self.keys, order_id, market)
          
    async def cancel_order(self, order_id):
        self.logger.debug(f"cancelling order {order_id} with status {self.orders[order_id].status}")
        if self.orders[order_id].status != 'requested_cancellation' and self.orders[order_id].status != 'closed':
            try:
                await self.exchange.cancel_order(*self.keys, order_id, self.orders[order_id].market)
            except OrderClosed:
                if order_id in self.open_orders:
                    del self.open_orders[order_id]
            self.orders[order_id].status = 'requested_cancellation' 
        elif self.orders[order_id].status == 'requested_cancellation':
            await self.get_fills(order_id)
           

    async def cancel_all_orders(self):
        await self.exchange.cancel_all_orders(*self.keys)


    async def set_leverage(self, leverage: int):
        await self.exchange.set_account_leverage(*self.keys, leverage)
        self.leverage = leverage
    

    async def market_order(self, market, side, volume):
        await self.exchange.market_order(*self.keys, market, side, volume)

    async def limit_order(self, market, side, price, volume, **kwargs):

        if side == 'buy': 
            price = math.floor(price / self.exchange.markets[market].price_increment) * self.exchange.markets[market].price_increment + 10 ** -14
            volume = math.floor(volume / self.exchange.markets[market].size_increment) * self.exchange.markets[market].size_increment
        elif side == 'sell':
            price = math.ceil(price / self.exchange.markets[market].price_increment) * self.exchange.markets[market].price_increment - 10 ** -14
            volume = math.floor(volume / self.exchange.markets[market].size_increment) * self.exchange.markets[market].size_increment

        
        await self.exchange.limit_order(*self.keys, market, side, price, volume, **kwargs)

