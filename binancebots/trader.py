import asyncio

from .accounts import Account, SpotAccount, FuturesAccount

from .orderbooks import OrderBookManager

import numpy as np

class Trader:
	def __init__(self, account: Account, order_book_manager: OrderBookManager, assets: list[str], quotes: list[str]):
		'''Construct a Trader instance, assets are the assets that the trader can trade, while quotes are the quote markets to look at for each asset (if they exist)'''
		self.account = account
		self.connection_manager = account.connection_manager
		self.order_book_manager = order_book_manager
		self.assets = assets
		self.quotes = quotes



	async def get_trading_markets(self):
		'''Gets a list of currently trading symbols'''
		print('getting data')
		exchange_info = await self.connection_manager.rest_get('/v3/exchangeInfo', weight=10)
		print('got data')
		self.trading_markets = []
		self.market_filters = {}
		for symbol in exchange_info['symbols']:
			if symbol['status'] == 'TRADING' and symbol['baseAsset'] in self.assets and symbol['quoteAsset'] in self.quotes:
				self.market_filters[symbol['symbol']] = symbol['filters']
				self.trading_markets.append((symbol['baseAsset'], symbol['quoteAsset']))
	
	async def subscribe_to_order_books(self, symbols: list[str] = []):
		'''Subscribe to the orderbooks of symbols. If no parameter is passed then subscribe to all trading orderbooks'''
		if len(symbols) == 0:
			symbols = self.trading_markets

		print(len(symbols))
		await self.order_book_manager.subscribe_to_depths(*[(base + quote).lower() for base, quote in symbols])


	def weighted_portfolio(self, assets: list[str] = []):
		'''Calculate the weighted portfolio of assets the account by calculating the value in BTC. If assets is None calculate the weighted portfolio of the account'''
		base = 'BTC'
		if len(assets) == 0:
			assets = self.account.balances
		total_base = np.zeros(len(assets))
		for i, asset in enumerate(assets):
			amount = 0
			price = 1
			if asset in self.account.balances:
				#calculate BTC price...
				amount = self.account.balances[asset]
				if asset != base:
					if (asset, base) in self.trading_markets:
						price = self.order_book_manager.books[(asset + base).lower()].mid_price()
					elif (base, asset) in self.trading_markets:
						price = 1 / self.order_book_manager.books[(base + asset).lower()].mid_price()
					else:
						prices = []
						for middle_asset in self.account.balances:
							if (middle_asset, base) in self.trading_markets and (asset, middle_asset) in self.trading_markets:
								prices.append(self.order_book_manager.books[(asset + middle_asset).lower()].mid_price() * self.order_book_manager.books[(middle_asset + base).lower()].mid_price())
							if (base, middle_asset) in self.trading_markets and (asset, middle_asset) in self.trading_markets:
								prices.append(self.order_book_manager.books[(asset + middle_asset).lower()].mid_price() * 1 / self.order_book_manager.books[(base + middle_asset).lower()].mid_price())
							if (middle_asset, base) in self.trading_markets and ( middle_asset, asset) in self.trading_markets:
								prices.append(1 / self.order_book_manager.books[( middle_asset + asset).lower()].mid_price() *self.order_book_manager.books[(middle_asset + base).lower()].mid_price())
							if (base, middle_asset) in self.trading_markets and (middle_asset, asset) in self.trading_markets:
								prices.append(1 / self.order_book_manager.books[(middle_asset + asset).lower()].mid_price() * 1 / self.order_book_manager.books[(base+ middle_asset).lower()].mid_price())
						price = np.mean(prices)
			total_base[i] = amount * price	
			 
		weighted_portfolio = total_base / np.sum(total_base)
		return {a: weighted_portfolio[i] for i, a in enumerate(assets)}

	def trade_to_portfolio(self, portfolio: dict):
		'''Trade to rebalance the accounts portfolio to the portfolio parameter. Any currencies not added to the portfolio dict will be ignored.'''
		pass




class SpotTrader(Trader):
	pass

class MarginTrader(Trader):
	pass


class FuturesTrader(Trader):
	pass
