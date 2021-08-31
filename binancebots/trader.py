import asyncio
import time

from .accounts import Account 
from .exchanges import Exchange, BinanceSpot

import numpy as np


class TradingSale:
	def __init__(self, sell_asset: str, buy_asset: str, quote_asset: str, trading_fee, order_book, min_order, max_order, min_notional):
		self.sell_asset = sell_asset
		self.buy_asset = buy_asset
		self.quote_asset = quote_asset
		self.order_book = order_book
		self.min_order = min_order
		self.max_order = max_order
		self.min_notional = min_notional

		if quote_asset != sell_asset and quote_asset != buy_asset:
			print('Error, the quote asset is neither the buy nor sell asset')
	
	def min_market_order(self) -> float:
		'''Calculates the minimum volume (in sell asset) for a market order'''		
		if self.quote_asset == self.sell_asset:
			#calculate quote volume of min order
			min_order_price = self.order_book.market_sell_price(self.min_order)
			min_order_quote_volume = self.min_order * min_order_price
			return max(self.min_notional, min_order_quote_volume)
		else:
			#calculate volume of min notional
			min_notional_price = self.order_book.market_buy_price_quote_volume(self.min_notional)
			min_notional_volume = self.min_notional / min_notional_price
			return max(min_notional_volume, self.min_order)

			

	def market_order_price(self, side: str, volume: float) -> float:
		'''Calculates the volume aquired of buy_asset when volume of sell_asset is sold'''
		if quote_asset == sell_asset:
			return volume / self.order_book.market_buy_price_quote_volume(volume) 
		else:
			return volume * self.order_book.market_sell_price(volume)

		

class Trader:
	def __init__(self, account: Account, exchange: Exchange, assets: list, quotes: list, trading_fee = 0):
		'''Construct a Trader instance, assets are the assets that the trader can trade, while quotes are the quote markets to look at for each asset (if they exist)'''
		self.account = account
		self.exchange = exchange
		self.assets = assets
		self.quotes = quotes
			
		self.trading_fee = trading_fee
		self.sales = {}


	async def get_trading_markets(self):
		'''Gets a list of currently trading symbols'''
		exchange_info = await self.exchange.get_exchange_info()
		self.trading_markets = []
		for base, quote in self.exchange.trading_markets:
			if base in self.assets and quote in self.quotes:
				self.trading_markets.append((base, quote))
		
		await self.exchange.subscribe_to_order_books(*[base + quote for base, quote in self.trading_markets])
		
		for base, quote in self.trading_markets:
			if base not in self.sales:
				self.sales[base] = []
			if quote not in self.sales:
				self.sales[quote] = []
		
			min_max_params = self.exchange.volume_filters[base + quote]['LOT_SIZE'].parameters	
			min_notional_params = self.exchange.volume_filters[base + quote]['MIN_NOTIONAL'].parameters
			self.sales[base].append(TradingSale(base, quote, quote, self.trading_fee, self.exchange.order_books[(base + quote).lower()], min_max_params.min_volume, min_max_params.max_volume, min_notional_params.min_notional)) 
			self.sales[quote].append(TradingSale(quote, base, quote, self.trading_fee, self.exchange.order_books[(base + quote).lower()], min_max_params.min_volume, min_max_params.max_volume, min_notional_params.min_notional)) 


	
	async def subscribe_to_order_books(self, symbols: list = None):
		'''Subscribe to the orderbooks of symbols. If no parameter is passed then subscribe to all trading orderbooks'''
		if symbols is None:
			symbols = self.trading_markets

		await self.exchange.subscribe_to_order_books(*[(base + quote).lower() for base, quote in symbols])

	def prices(self, assets: list = None, base='USDT'):
		'''Calculate the prices of an asset with respect to the base. The trading pairs need not exist'''
		if assets is None:
			assets = self.account.balance
		assets = [asset for asset in assets]
		asset_prices = np.zeros(len(assets))
		for i, asset in enumerate(assets):
			amount = 0
			price = 1
			if asset in self.account.balance:
				amount = self.account.balance[asset]
				if asset != base:
					if (asset, base) in self.trading_markets:
						price = self.exchange.order_books[(asset + base).lower()].mid_price()
					elif (base, asset) in self.trading_markets:
						price = 1 / self.exchange.order_books[(base + asset).lower()].mid_price()
					else:
						prices = []
						for middle_asset in self.account.balance:
							if (middle_asset, base) in self.trading_markets and (asset, middle_asset) in self.trading_markets:
								prices.append(self.exchange.order_books[(asset + middle_asset).lower()].mid_price() * self.exchange.order_books[(middle_asset + base).lower()].mid_price())
							if (base, middle_asset) in self.trading_markets and (asset, middle_asset) in self.trading_markets:
								prices.append(self.exchange.order_books[(asset + middle_asset).lower()].mid_price() * 1 / self.exchange.order_books[(base + middle_asset).lower()].mid_price())
							if (middle_asset, base) in self.trading_markets and ( middle_asset, asset) in self.trading_markets:
								prices.append(1 / self.exchange.order_books[( middle_asset + asset).lower()].mid_price() *self.exchange.order_books[(middle_asset + base).lower()].mid_price())
							if (base, middle_asset) in self.trading_markets and (middle_asset, asset) in self.trading_markets:
								prices.append(1 / self.exchange.order_books[(middle_asset + asset).lower()].mid_price() * 1 / self.exchange.order_books[(base+ middle_asset).lower()].mid_price())
						if len(prices) != 0:
							price = np.mean(prices)
						else:
							print('Trading error, no route!')
			asset_prices[i] = price	 
		return {a: asset_prices[i] for i, a in enumerate(assets)}
	


	def portfolio_values(self, assets: list = None, base = 'USDT'):
		if assets is None:
			assets = self.account.balance
		prices = self.prices(assets, base)
		return {asset: self.account.balance[asset] * prices[asset] if asset in self.account.balance else 0 for asset in assets}
	
	def weighted_portfolio(self, assets: list = None, base='USDT'):
		base_values = self.portfolio_values(assets, base)
		total = sum(base_values.values())
		return {asset: value / total for asset, value in base_values.items()}

	async def trade_to_portfolio_market(self, portfolio: dict, quote='USDT', trading_fee=0.1 / 100):
		'''Trade to rebalance the accounts portfolio to the portfolio parameter. 

		args:
		- portolio: Dict of the portfolio {asset: proportion}. Any currencies not added to the portfolio dict will be ignored, to trade out of an asset {asset: 0} needs to be in the dict.
		- base: currency to calculate the portfolio weights in'''

		assets = [asset for asset in portfolio]
		prices = self.prices(assets, quote)
		quote_values = self.portfolio_values(assets, quote)
		total_value = sum(quote_values.values())	
		current_weighted_portfolio = np.array([quote_values[asset] / total_value for asset in assets])
		target_portfolio = np.array([portfolio[asset] for asset in assets])
		


		target_portfolio /= np.sum(target_portfolio)
		
		sells = -np.min([target_portfolio - current_weighted_portfolio, np.zeros(target_portfolio.size)], axis=0)
		
		sell_actual = np.array([self.account.balance[asset] if asset in self.account.balance else 0 for asset in assets]) * sells / (current_weighted_portfolio + 10**-16)
		sell_assets = [(i, asset) for i, asset in enumerate(assets) if sells[i] > 0]

		total_sells = np.sum(sells)
		sell_orders = []


		for i, asset in sell_assets:	
			volume = sell_actual[i] 
			if volume < min([s.min_market_order() for s in self.sales[asset]]):
				sells[i] = 0
			elif (asset, quote) in self.trading_markets:
				sell_orders.append((asset, volume))	
		
		#execute trades
		responses = await asyncio.gather(*[self.account.market_order(base, quote, 'SELL', volume=volume) for base, volume in sell_orders])
		
		quote_values = self.portfolio_values(assets, quote)
		total_value = sum(quote_values.values())
		
		buys = np.max([target_portfolio - current_weighted_portfolio, np.zeros(target_portfolio.size)], axis=0)
		buy_assets = [(i, asset) for i, asset in enumerate(assets) if buys[i] > 0]
		buys *= np.sum(sells) / total_sells #TODO: replace with actual aquired sales	
		
		buy_orders = []
		total_sold = 0
		available_quote = self.account.balance[quote]

		
		for i, asset in buy_assets:
			quote_volume = buys[i] * total_value
			if total_sold + quote_volume > available_quote:
				quote_volume = available_quote - total_sold
			
			if (asset, quote) in self.trading_markets:
				for s in self.sales[quote]:
					if s.buy_asset == asset:
						sale = s
				if quote_volume < sale.min_market_order():
					buys[i] = 0
				else:
					buy_orders.append((asset, quote_volume))	
					total_sold += quote_volume

		responses = await asyncio.gather(*[self.account.market_order(asset, quote, 'BUY', quote_volume=quote_volume) for asset, quote_volume in buy_orders])
	
		
		

class SpotTrader(Trader):
	pass

class MarginTrader(Trader):
	pass


class FuturesTrader(Trader):
	pass
