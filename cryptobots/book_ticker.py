import asyncio
from contextlib import suppress

class BookTicker:
    def __init__(self, initial_best_prices):
        self.time = initial_best_prices['time']
        self.bid_price = initial_best_prices['bid_price']
        self.bid_volume = initial_best_prices['bid_volume']
        self.ask_price = initial_best_prices['ask_price']
        self.ask_volume = initial_best_prices['ask_volume']


    def mid_price(self):
        return (self.bid_price + self.ask_price) / 2



