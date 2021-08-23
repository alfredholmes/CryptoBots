import asyncio

from .accounts import Account 
from .exchanges import Exchange, BinanceSpot

import numpy as np


class TradingRoute:
	def __init__(sell_asset, buy_asset, path, order_books, trading_fee = 0):
		self.sell_asset = sell_asset
		self.buy_asset = buy_asset
		self.path = path
		self.order_books = order_books
		self.trading_fee = 0


	def cheapest_sale(self) -> (float, float):
		'''Calculates the most efficient movement of sell_asset into buy_asset returns the volumes sold and bought'''
		asset_volume = None
		current_asset = self.sell_asset
		rolling_prices = 1
		for (base, quote), order_book in zip(self.path, self.order_books):
			if base == current_asset:
				#sell the base
				price = sorted(order_book.bids.keys(), reverse=True)[0]
				max_volume = order_books.bids[price]
				if asset_volume is None:
					asset_volume = max_volume
				else:
					volume = min(max_volume, volume)
			else:
				#buy the base
				price = sorted(order_book.asks.keys())[0]
				max_volume = order_book.asks[price] * price
				if asswt_volume is None:
					asset_volume = max_volume
				else:
					volume = min(max_volume)


			volume *= (1 - self.trading_fee) / rolling_price
	
	def calculate_cost(self, volume):
		'''Calculates the total cost of moving assets along this path'''


class Trader:
	def __init__(self, account: Account, exchange: Exchange, assets: list, quotes: list):
		'''Construct a Trader instance, assets are the assets that the trader can trade, while quotes are the quote markets to look at for each asset (if they exist)'''
		self.account = account
		self.exchange = exchange
		self.assets = assets
		self.quotes = quotes
			
		self.trading_routes = {}


	async def get_trading_markets(self):
		'''Gets a list of currently trading symbols'''
		exchange_info = await self.exchange.get_exchange_info()
		self.trading_markets = []
		for symbol in exchange_info['symbols']:
			if symbol['status'] == 'TRADING' and symbol['baseAsset'] in self.assets and symbol['quoteAsset'] in self.quotes:
				self.market_filters[symbol['symbol']] = symbol['filters']
				for filter in symbol['filters']:
					pass
				self.trading_markets.append((symbol['baseAsset'], symbol['quoteAsset']))
		

		for i, (base_1, quote_1) in enumerate(self.trading_markets:
			if base_1 not in self.trading_routes:
				self.trading_routes[base_1] = {}
			if quote_1 not in self.trading_routes:
				self.trading_routes[quote_1] = {}
			if quote_1 not in self.trading_routes[base_1]:
				self.trading_routes[base_1][quote_1] = []
			self.trading_routes[base_1][quote_1].append((base_1, quote_1))
			self.trading_routes[quote_1][base_1].append((base_1, quote_1))

			for base_2, quote_2 in self.trading_markets[i+1:]:
				if base_2 == base_1:
					if quote_2 not in self.trading_routes:
						self.trading_routes[quote_2] = {}
					if quote_1 not in self.trading_routes[quote_2]:
						self.trading_routes[quote_2][quote_1] = []
					if quote_2 not in self.trading_routes[quote_1]:
						self.trading_routes[quote_1][quote_2] = []

					self.trading_routes[quote_1][quote_2].append(((base_1, quote_1), (base_2, quote_2)))
					self.trading_routes[quote_2][quote_1].append(((base_2, quote_2), (base_1, quote_1)))
					
				if base_2 == quote_1:
					if quote_2 not in self.trading_routes:
						self.trading_routes[quote_2] = {}
					if base_1 not in self.trading_routes[quote_2]:
						self.trading_routes[quote_2][base_1] = []
					if quote_2 not in self.trading_routes[base_1]:
						self.trading_routes[base_1][quote_2] = []

					self.trading_routes[base_1][quote_2].append(((base_1, quote_1), (base_2, quote_2)))
					self.trading_routes[quote_2][base_1].append(((base_2, quote_2), (base_1, quote_1)))

				if quote_2 == base_1:
					if base_2 not in self.trading_routes:
						self.trading_routes[base_2] = {}
					if quote_1 not in self.trading_routes[base_2]:
						self.trading_routes[base_2][quote_1] = []
					if base_2 not in self.trading_routes[quote_1]:
						self.trading_routes[quote_1][base_2] = []

					self.trading_routes[quote_1][base_2].append(((base_1, quote_1), (base_2, quote_2)))
					self.trading_routes[base_2][quote_1].append(((base_2, quote_2), (base_1, quote_1)))

				if quote_2 == quote_1:
					if base_2 not in self.trading_routes:
						self.trading_routes[base_2] = {}
					if base_1 not in self.trading_routes[base_2]:
						self.trading_routes[base_2][base_1] = []
					if base_2 not in self.trading_routes[base_1]:
						self.trading_routes[base_1][base_2] = []

					self.trading_routes[base_1][base_2].append(((base_1, quote_1), (base_2, quote_2)))
					self.trading_routes[base_2][base_1].append(((base_2, quote_2), (base_1, quote_1)))

	
	async def subscribe_to_order_books(self, symbols: list = None):
		'''Subscribe to the orderbooks of symbols. If no parameter is passed then subscribe to all trading orderbooks'''
		if symbols is None:
			symbols = self.trading_markets

		print(len(symbols))
		await self.exchange.subscribe_to_order_books(*[(base + quote).lower() for base, quote in symbols])

	def portfolio_values(self, assets: list = None, base='USDT'):
		'''Calculate the weighted portfolio of assets the account by calculating the value in BTC. If assets is None calculate the weighted portfolio of the account'''
		if assets is None:
			assets = self.account.balance
		total_base = np.zeros(len(assets))
		for i, asset in enumerate(assets):
			amount = 0
			price = 1
			if asset in self.account.balance:
				#calculate BTC price...
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
						price = np.mean(prices)
			total_base[i] = amount * price	
			if np.isnan(total_base[i]):
				print('Warning: asset volume is nan', asset, prices)
			 
		return {a: total_base[i] for i, a in enumerate(assets)}

	
	def weighted_portfolio(self, assets: list = None, base='USDT'):
		base_values = self.portfolio_values(assets, base)
		total = sum(base_values.values())
		return {asset: value / total for asset, value in base_values.items()}

	def trade_to_portfolio_market(self, portfolio: dict, base='USDT', trading_fee=0.1 / 100):
		'''Trade to rebalance the accounts portfolio to the portfolio parameter. 

		args:
		- portolio: Dict of the portfolio {asset: proportion}. Any currencies not added to the portfolio dict will be ignored, to trade out of an asset {asset: 0} needs to be in the dict.
		- base: currency to calculate the portfolio weights in'''

		assets = [asset for asset in portfolio]
		base_values = self.portfolio_values(assets)
		total_value = sum(base_values.values())	

		current_weighted_portfolio = np.array(current_portfolio[asset] / total_value for asset in assets)
		target_portfolio = np.array(portfolio[asset] for asset in assets)
		


		target_portfolio /= np.sum(target_portfolio)
		
		buys = np.max([target_portfolio - current_weighted_portfolio, np.zeros(target_portfolio.size)], axis=0)
		sells = -np.max([target_portfolio - current_weighted_portfolio, np.zeros(target_portfolio.size)], axis=0)
		
		sell_actual = np.array(self.account.balance[asset] if asset in self.account.balance else 0 for asset in assets ) * sells / current_weighted_portfolio

		buy_assets = [asset for i, asset in enumerate(assets) if buys[i] > 0]	
		sell_assets = [asset for i, asset in enumerate(assets) if sells[i] > 0]

		routes = []
		for buy_asset in buy_assets:
			for sell_asset in sell_assets:
				routes.extend(self.trading_routes[buy_asset][sell_asset])	
			
					



class SpotTrader(Trader):
	pass

class MarginTrader(Trader):
	pass


class FuturesTrader(Trader):
	pass
