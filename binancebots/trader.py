import asyncio

from .accounts import Account 
from .exchanges import Exchange, BinanceSpot

import numpy as np

class Trader:
	def __init__(self, account: Account, exchange: Exchange, assets: list[str], quotes: list[str]):
		'''Construct a Trader instance, assets are the assets that the trader can trade, while quotes are the quote markets to look at for each asset (if they exist)'''
		self.account = account
		self.exchange = exchange
		self.assets = assets
		self.quotes = quotes



	async def get_trading_markets(self):
		'''Gets a list of currently trading symbols'''
		exchange_info = await self.exchange.get_exchange_info()
		self.trading_markets = []
		self.market_filters = {}
		for symbol in exchange_info['symbols']:
			if symbol['status'] == 'TRADING' and symbol['baseAsset'] in self.assets and symbol['quoteAsset'] in self.quotes:
				self.market_filters[symbol['symbol']] = symbol['filters']
				for filter in symbol['filters']:
					pass
				self.trading_markets.append((symbol['baseAsset'], symbol['quoteAsset']))
	
	async def subscribe_to_order_books(self, symbols: list[str] = []):
		'''Subscribe to the orderbooks of symbols. If no parameter is passed then subscribe to all trading orderbooks'''
		if len(symbols) == 0:
			symbols = self.trading_markets

		print(len(symbols))
		await self.exchange.subscribe_to_order_books(*[(base + quote).lower() for base, quote in symbols])

	def portfolio_values(self, assets: list[str] = None, base='USDT'):
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

	
	def weighted_portfolio(self, assets: list[str] = None, base='USDT'):
		base_values = self.portfolio_values(assets, base)
		total = sum(base_values.values())
		return {asset: value / total for asset, value in base_values.items()}

	def trade_to_portfolio(self, portfolio: dict, base='USDT', reducefees=False, trading_fee=0.075 / 100):
		'''Trade to rebalance the accounts portfolio to the portfolio parameter. 

		args:
		- portolio: Dict of the portfolio {asset: proportion}. Any currencies not added to the portfolio dict will be ignored, to trade out of an asset {asset: 0} needs to be in the dict.
		- base: currency to calculate the portfolio weights in. Assumes BNB is in the portfolio'''

		assets = [asset for asset in portfolio]
		base_values = self.portfolio_values(assets)
		total_value = sum(base_values.values())

		

		current_weighted_portfolio = np.array(current_portfolio[asset] / total_value for asset in assets)
		target_portfolio = np.array(portfolio[asset] for asset in assets)
		


		target_portfolio /= np.sum(target_portfolio)
		
		buys = np.max([target_portfolio - current_weighted_portfolio, np.zeros(target_portfolio.size)], axis=0)
		sells = -np.max([target_portfolio - current_weighted_portfolio, np.zeros(target_portfolio.size)], axis=0)
		
		sell_actual = np.array(self.account.balance[asset] if asset in self.account.balance else 0 for asset in assets ) * sells / current_weighted_portfolio

		
		trading_volume = np.sum(np.abs(target_portfolio - np.portfolio)) * total_value 
		if reducefees:
			total_fee = trading_volume * fee
			
		
			if base == 'BNB':
				bnb_price = 1
				bnb_to_buy = total_fee
			else:
				bnb_price = self.orderbooks.books[('bnb' + base).lower()].buy_price()
				bnb_to_buy = total_fee / bnb_price 

			#find the assets to buy BNB with
			bnb_assets = [asset for asset in assets if (asset, 'BNB') in self.trading_markets and current_weighted_portfolio[asset] * bnb_to_buy > self.market_filters[asset + 'BNB']]
			bnb_asset_weight = sum(current_weighted_portfolio[asset] for asset in bnb_assets)
			bnb_orders = {}
			

			for asset in bnb_assets:
				bnb_amount = bnb_to_buy * current_weighed_portfolio[asset] / bnb_asset_weight	
				bnb_orders[asset] =  bnb_amount

			# Buy BNB	
		
		





class SpotTrader(Trader):
	pass

class MarginTrader(Trader):
	pass


class FuturesTrader(Trader):
	pass
