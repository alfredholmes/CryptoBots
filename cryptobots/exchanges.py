import asyncio, time, hashlib, hmac, urllib, json
from abc import ABC, abstractmethod
from .connections import ConnectionManager
from contextlib import suppress
import httpx
from .orderbooks import OrderBook

class OrderPlacementError(Exception):
    """
        Exception raised when orders fail
    """
class OrderClosed(Exception):
    """
        Exception raised when Cancellations fail since already queued
    """
    def __init__(self, order_id):
        self.id = order_id
        super().__init__(f"Order {order_id} already queued for cancellation")
        
 

class Fill:
    def __init__(self, fill_id, order_id, time, market, side, volume, price, fees):
        self.id = fill_id
        self.order_id = order_id
        self.time = time
        self.market = market
        self.side = side
        self.volume = volume
        self.price = price
        self.fees = fees


class Trade:
    def __init__(self, time, price, volume, side):
        self.time = time
        self.price = price
        self.volume = volume
        self.buy = side #True if maker is buyer

class Order:
    def __init__(self, order_id, market, side, volume, price = None, order_type = 'unknown', status='new', filled_volume = 0):
        self.id = order_id
        self.market = market
        self.side = side
        self.volume = volume
        self.remaining_volume = volume
        self.order_type = order_type
        self.status = status
        self.filled_volume = filled_volume
        self.price = price
        self.type = order_type 
        self.balance_mod = {}
        self.fills = {}
        self.recorded_fills = 0
    
    def __str__(self):
        return f"Order {self.id}, {self.side} on {self.market.name}, {self.volume} at {self.price}"

class SpotMarket:
    """
        Holds basic spot market info
    """
    def __init__(self, base, quote, name):
        self.base = base
        self.quote = quote
        self.pair = (base, quote)
        self.name = name
        self.type = 'spot'


class FutureMarket:
    """
        Holds basic future market info
    """
    def __init__(self, underlying, name, pair = None):
        self.underlying = underlying
        self.name = name
        self.type = 'future'
        if pair is None:
            self.pair = (underlying, self.name.split('-')[-1])
        else:
            self.pair = pair

    

class Position:
    def __init__(self, market, side, volume, entry_price, margin_requirement):
        self.market = market
        self.side = side
        self.volume = volume
        self.entry_price = entry_price
        self.margin_requirement = margin_requirement
        

class Exchange(ABC):
    """
        Wrapper for exchange API calls

    """

    @property
    @abstractmethod
    def rest_endpoint():
        pass

    @property
    @abstractmethod
    def ws_endpoint():
        pass
    

    def __init__(self):
        self.connection_manager = ConnectionManager(self.rest_endpoint, self.ws_endpoint) 
        self.markets = {}
        self.order_books = {}
        self.order_book_queues = {}
        self.trade_queues = {}
        self.market_names = {}
        self.user_updates = asyncio.Queue()
        self.connection_lock = asyncio.Lock()

    @abstractmethod
    async def connect(self):
        pass

    @abstractmethod
    async def subscribe_to_order_books(self, *markets):
        pass    

    async def __aenter__(self):
        await self.connection_manager.connect()
        await self.connect()
        return self


    async def __aexit__(self, *details):
        await asyncio.wait_for(self.close(*details), 60)

    async def close(self, *details):
        #unsubscribe from order books 

        await self.unsubscribe_from_order_books(*self.order_books)
        #end tasks
        self.parse_task.cancel()
        
        with suppress(asyncio.CancelledError):
            await self.parse_task
            
        
        await self.connection_manager.close()
        
        
