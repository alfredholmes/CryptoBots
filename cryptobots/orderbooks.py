import asyncio
from contextlib import suppress
import binascii


class OrderBook:
    """
        Handle basic order book operations and computations
    """
    def __init__(self,  update_queue):
        self.update_queue = update_queue
        self.unhandled_updates = []
        self.initialised = False
        self.initialised_event = asyncio.Event()
        self.previous_time = 0
        self.update_parser = asyncio.create_task(self.parse_updates())  
        self.update_event = asyncio.Event()
        self.subscribed = True
        self.correct = False
        self.checksum = 0

    async def close(self):
        self.subscribed = False
        self.update_parser.cancel()
        with suppress(asyncio.CancelledError):
            await self.update_parser

    def mid_price(self):
        if not self.initialised:
            raise Exception('Orderbook not initialised')
        return (max(self.bids) + min(self.asks)) / 2

    def sell_price(self):
        """
            Get the current best market sell price - the current highest bid

        """
        return sorted(self.bids, reverse=True)[0]

    def buy_price(self):
        """
            Gives the current best market buy price - the lowest ask

        """
        return sorted(self.asks)[0]


    def ftx_checksum(self, n=100):
        s = ''
        
        for bid, ask in zip(sorted(self.bids, reverse=True)[:100], sorted(self.asks)[:100]):
            s += f'{bid}:{self.bids[bid]}:{ask}:{self.asks[ask]}:'
        if len(self.bids) < len(self.asks): 
            for ask in sorted(self.asks)[len(self.bids):100]:
                s += f'{ask}:{self.asks[ask]}:'
        if len(self.asks) < len(self.bids):
            for bid in sorted(self.bids, reverse=True)[len(self.asks):100]:
                s += f'{bid}:{self.bids[bid]}:'

        s = s[:-1]
        return binascii.crc32(s.encode('utf-8')) == self.checksum



    async def parse_updates(self):
        while self.subscribed:
            update = await self.update_queue.get()
            if 'checksum' in update:
                self.checksum = update['checksum']
            if 'unsubscribed' in update:
                self.subscribed = False
                self.update_queue.task_done()
                break
            self.update_event.set()
            self.update_event.clear()
            if update['time'] < self.previous_time:
                self.update_queue.task_done()
                continue
            if not self.initialised:
                if 'initial' in update:
                    self.bids = {price: volume for price, volume in update['bids']}
                    self.asks = {price: volume for price, volume in update['asks']} 
                    self.unhandled_updates = [u for u in self.unhandled_updates if u['time'] > update['time']]
                    self.previous_time = update['time']
                    self.initialised = True
                    self.initialised_event.set()
                    for update in self.unhandled_updates:
                        for bid, volume in update['bids']:
                            self.bids[bid] = volume 
                            if volume == 0:
                                del self.bids[bid]
                        for ask, volume in update['asks']:
                            self.asks[ask] = volume
                            if volume == 0:
                                del self.asks[ask]

                    self.unhandled_updates = []
                    
                else:
                    self.unhandled_updates.append(update)
            else:
                for bid, volume in update['bids']:
                    self.bids[bid] = volume
                    if volume == 0:
                        del self.bids[bid]
                for ask, volume in update['asks']:
                    self.asks[ask] = volume
                    if volume == 0:
                        del self.asks[ask]

            self.update_queue.task_done()


class OrderBookManager:
    """
        Handle collections of orderbooks
    """
