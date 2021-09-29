import asyncio
import time

import httpx

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
	def __init__(self, account: Account, exchange: Exchange, assets: list, quotes: list,trading_fee = 0):
		'''Construct a Trader instance, assets are the assets that the trader can trade, while quotes are the quote markets to look at for each asset (if they exist)'''
		self.account = account
		self.exchange = exchange
		self.assets = assets
		self.quotes = quotes
		self.trading_fee = trading_fee
		self.sales = {}


	async def get_trading_markets(self, min_24h_volume = 0):
		'''Gets a list of currently trading symbols'''
		exchange_info = await self.exchange.get_exchange_info()
		self.trading_markets = []
		for base, quote in self.exchange.trading_markets:
			if base in self.assets and quote in self.quotes and self.exchange.daily_volumes[(base, quote)] > min_24h_volume:
				self.trading_markets.append((base, quote))
		
		await self.exchange.subscribe_to_order_books(*[m for m in self.trading_markets])
		
		for base, quote in self.trading_markets:
			if base not in self.sales:
				self.sales[base] = []
			if quote not in self.sales:
				self.sales[quote] = []
		
			min_max_params = self.exchange.volume_filters[(base, quote)]['LOT_SIZE'].parameters	
			min_notional_params = self.exchange.volume_filters[(base, quote)]['MIN_NOTIONAL'].parameters
			self.sales[base].append(TradingSale(base, quote, quote, self.trading_fee, self.exchange.order_books[(base, quote)], min_max_params.min_volume, min_max_params.max_volume, min_notional_params.min_notional)) 
			self.sales[quote].append(TradingSale(quote, base, quote, self.trading_fee, self.exchange.order_books[(base, quote)], min_max_params.min_volume, min_max_params.max_volume, min_notional_params.min_notional)) 


	
	async def subscribe_to_order_books(self, symbols: list = None):
		'''Subscribe to the orderbooks of symbols. If no parameter is passed then subscribe to all trading orderbooks'''
		if symbols is None:
			symbols = self.trading_markets

		await self.exchange.subscribe_to_order_books([(base, quote) for base, quote in symbols])

	def prices(self, assets: list = None, quote='BTC'):
		'''Calculate the prices of an asset with respect to the quote. The trading pairs need not exist'''
		if assets is None:
			assets = self.account.balance
		assets = [asset for asset in assets]
		asset_prices = np.zeros(len(assets))
		for i, asset in enumerate(assets):
			amount = 0
			price = 0 if asset != quote else 1.0
			if asset != quote:
				if (asset, quote) in self.trading_markets:
					price = self.exchange.order_books[(asset, quote)].mid_price()
				elif (quote, asset) in self.trading_markets:
					price = 1 / self.exchange.order_books[(quote, asset)].mid_price()
				else:
					prices = []
					for middle_asset in self.account.balance:
						if (middle_asset, quote) in self.trading_markets and (asset, middle_asset) in self.trading_markets:
							prices.append(self.exchange.order_books[(asset, middle_asset)].mid_price() * self.exchange.order_books[(middle_asset,quote)].mid_price())
						if (quote, middle_asset) in self.trading_markets and (asset, middle_asset) in self.trading_markets:
							prices.append(self.exchange.order_books[(asset,middle_asset)].mid_price() * 1 / self.exchange.order_books[(quote, middle_asset)].mid_price())
						if (middle_asset, quote) in self.trading_markets and ( middle_asset, asset) in self.trading_markets:
							prices.append(1 / self.exchange.order_books[( middle_asset, asset)].mid_price() *self.exchange.order_books[(middle_asset,quote)].mid_price())
						if (quote, middle_asset) in self.trading_markets and (middle_asset, asset) in self.trading_markets:
							prices.append(1 / self.exchange.order_books[(middle_asset, asset)].mid_price() * 1 / self.exchange.order_books[(quote,middle_asset)].mid_price())
					if len(prices) != 0:
						price = np.mean(prices)
					else:
						print('Trading error, no route!', asset, quote)
			asset_prices[i] = price	 
		return {a: asset_prices[i] for i, a in enumerate(assets)}
	


	def portfolio_values(self, portfolio: dict = None, base = 'BTC'):
		if portfolio is None:
			portfolio = self.account.balance
		prices = self.prices(portfolio, base)
		return {asset: portfolio[asset] * prices[asset] for asset in portfolio}
	
	def weighted_portfolio(self, assets: list = None, base='BTC'):
		base_values = self.portfolio_values(assets, base)
		total = sum(base_values.values())
		return {asset: value / total for asset, value in base_values.items()}

	async def trade_to_portfolio_market(self, target_portfolio: dict, quote='BTC', initial_portfolio: dict = None):
		assets = [asset for asset in target_portfolio]
		prices = self.prices(assets, quote)
		weighted_portfolio = {asset: value * prices[asset] for asset, value in target_portfolio.items()}
		return await self.trade_to_portfolio_weighted_market(target_portfolio, quote, initial_portfolio)

	def process_portfolios(self, target_portfolio, quote, initial_portfolio):
		
		assets = [asset for asset in target_portfolio]
		prices = self.prices(assets, quote)
		if initial_portfolio is None:
			portfolio = {asset: self.account.balance[asset] if asset in self.account.balance else 0.0 for asset in assets}
		else:
			portfolio = {asset: initial_portfolio[asset] if asset in self.portfolio else 0.0 for asset in assets}
		
		quote_values = self.portfolio_values(portfolio, quote)
		total_value = sum(quote_values.values())	
		current_weighted_portfolio = np.array([quote_values[asset] / total_value for asset in assets])
		target_portfolio = np.array([target_portfolio[asset] for asset in assets])
		initial_value = total_value 
		if initial_value == 0.0:
			return {asset: 0.0 for asset in assets}
		target_portfolio /= np.sum(target_portfolio)
		
		return assets, prices, portfolio, target_portfolio, current_weighted_portfolio

	def calculate_sell_orders(self, assets,quote, target_portfolio, current_weighted_portfolio, portfolio):
		sells = -np.min([target_portfolio - current_weighted_portfolio, np.zeros(target_portfolio.size)], axis=0)
		sell_actual = np.zeros(len(assets))
		for i, asset in enumerate(assets):
			if current_weighted_portfolio[i] > 0:
				sell_actual[i] = portfolio[asset] * sells[i] / current_weighted_portfolio[i]
		sell_assets = [(i, asset) for i, asset in enumerate(assets) if sells[i] > 0]
		
		sell_orders = []

		for i, asset in sell_assets:	
			volume = sell_actual[i]
			if volume < min([s.min_market_order() for s in self.sales[asset]]):
				sells[i] = 0
				print(asset, 'sale ', volume, 'below min order')
			elif (asset, quote) in self.trading_markets:
				sell_orders.append((asset, volume))	
		
		return sell_orders


	def calculate_buy_orders(self, assets, quote, target_portfolio, current_weighted_portfolio, total_value):	
		buys = np.max([target_portfolio - current_weighted_portfolio, np.zeros(target_portfolio.size)], axis=0)
		buy_assets = [(i, asset) for i, asset in enumerate(assets) if buys[i] > 0]
		buy_orders = []
		minimum_orders = []
		total_sold = 0
		for i, asset in buy_assets:
			if asset == quote:
				continue
			quote_volume = buys[i] * total_value
			
			if (asset, quote) in self.trading_markets:
				for s in self.sales[quote]:
					if s.buy_asset == asset:
						sale = s
				min_market_order = sale.min_market_order()
				if quote_volume < min_market_order:
					buys[i] = 0
				else:
					buy_orders.append((asset, quote_volume))	
					total_sold += quote_volume
					minimum_orders.append((asset, min_market_order))


		return buy_orders, minimum_orders
			

	async def trade_to_portfolio_weighted_market(self, target_portfolio: dict, quote='BTC', initial_portfolio: dict = None):
		'''Trade to rebalance the accounts portfolio to the portfolio parameter. 

		args:
		- portolio: Dict of the portfolio {asset: proportion}. Any currencies not added to the portfolio dict will be ignored, to trade out of an asset {asset: 0} needs to be in the dict.
		- base: currency to calculate the portfolio weights in
		- initial_portfolio - the assets which will be traded to be in the proportions of the target portfolio'''
		assets, prices, portfolio, target_portfolio, current_weighted_portfolio = self.process_portfolios(target_portfolio, quote, initial_portfolio)
		sell_orders = self.calculate_sell_orders(assets, quote, target_portfolio, current_weighted_portfolio, portfolio)	
		#execute trades
		print('Selling to USD...')
		orders = await asyncio.gather(*[self.account.market_order(base, quote, 'SELL', volume=volume, exchange=self.exchange) for base, volume in sell_orders])
		print('Waiting for orders to fill!')
		await asyncio.gather(*[order.fill_event.wait() for order in orders if order is not None])	
		for i, order in enumerate(orders):
			if order is None:
				print('Warning, failed to place sell order', sell_orders[i])
				continue
			for changes in order.fills.values():
				for asset, change in changes.items():
					if asset not in portfolio:
						portfolio[asset] = 0.0
					portfolio[asset] += change
		print('Done!')

		quote_values = self.portfolio_values(portfolio, quote)
		total_value = sum(quote_values.values())
	
		buy_orders, min_orders = self.calculate_buy_orders(assets, quote, target_portfolio, current_weighted_portfolio, total_value)
		
		total_quote_volume = portfolio[quote]
		spent_volume = 0
		to_delete = []
		for i in range(len(buy_orders)):
			if buy_orders[i][1] + spent_volume < total_quote_volume:
				spent_volume += buy_orders[i][1]
			elif spent_volume < total_quote_volume and total_quote_volume - spent_volume > min_orders[i]:
				buy_orders[i] = (buy_ordes[i][0], total_quote_volume - spent_volume)
				spent_volume += total_quote_volume - spent_volume
			else:
				to_delete.append(i)	
			
		for i in reversed(to_delete):
			del buy_orders[i]	

		print('Buying ...')
		orders = await asyncio.gather(*[self.account.market_order(asset, quote, 'BUY', quote_volume=quote_volume, exchange=self.exchange) for asset, quote_volume in buy_orders])
		print('Waiting for orders to fill...')	
		await asyncio.gather(*[order.fill_event.wait() for order in orders if order is not None])	
		for i, order in enumerate(orders):
			if order is None:
				print('Warning, failed to place sell order', buy_orders[i])
				continue
			for changes in order.fills.values():
				for asset, change in changes.items():
					if asset not in portfolio:
						portfolio[asset] = 0.0
		print('Done!')

		print('Done trading!')

		return {asset: round(new_balance, 8) for asset, new_balance in portfolio.items()}

	async def limit_trade(self, base, quote, side, fill_queue = None, timeout=10, max_slippage=0.01, **kwargs):
		'''
			Places a limit order for timout seconds and tries to keep the order in the middle of the order book
		'''
		mid_price = self.prices([base], quote)[base]
		if 'volume' in kwargs:
			volume = kwargs['volume']
		elif 'quote_volume' in kwargs:
			volume = kwargs['quote_volume'] / mid_price
		target_volume = volume
		start_price = mid_price
		
		min_volume = self.exchange.volume_filters[(base, quote)]['LOT_SIZE'].parameters.min_volume

		if side == 'BUY' and target_volume * mid_price > self.account.balance[quote]:
			volume = self.account.balance[quote] / mid_price
		elif side == 'SELL' and target_volume > self.account.balance[base]:
			volume = self.account.balance[base]
		try:
			if fill_queue is not None:
				print('Placing limit order', base, quote, side, mid_price, volume)
				order = await self.account.limit_order(base, quote, side, mid_price, volume, fill_queue=fill_queue, exchange=self.exchange)
			else:
				order = await self.account.limit_order(base, quote, side, mid_price, volume, exchange=self.exchange)
		except httpx.HTTPStatusError:
			print('Error placing order')
			return
		
		start_time = time.time()
		await asyncio.sleep(1)
		#wait to see if the order fills, if not
		while order.open:
			if time.time() - start_time > timeout:
				break
			mid_price = self.prices([base], quote)[base]
			if side == 'SELL' and mid_price < start_price * (1 - max_slippage):
				mid_price = mid_price * (1 - max_slippage)
			if side == 'BUY' and mid_price > start_price / (1 - max_slippage):
				mid_price = start_price / (1 - max_slippage)
		
			try:
				if order.remaining_volume > min_volume:
					await self.account.change_order(order, price=mid_price)
			except httpx.HTTPStatusError:
				print('Error trying to update order')
				break
			await asyncio.sleep(1)
	
		if order.open:
			try:
				await self.account.cancel_order(order)
				await asyncio.wait_for(order.close_event.wait(), timeout)
			except asyncio.TimeoutError:
				print('Order cencellation timeout error', order.id, order.base, order.quote, order.price)
			except httpx.HTTPStatusError:
				print('Order cancellation status error')


	async def create_sell_order_tasks(self, orders, quote, complete_event, fill_queue):
		tasks = []
		for base, volume in orders:
			tasks.append(asyncio.create_task(self.limit_trade(base, quote, 'SELL', fill_queue, volume=volume)))
		try:	
			await asyncio.wait_for(asyncio.gather(*tasks), 15)
		except asyncio.TimeoutError:
			print('Timeout Error in sell order tasks')
		complete_event.set()
	
	async def trade_to_portfolio(self, target_portfolio: dict, quote='BTC', initial_portfolio: dict = None):
		assets = [asset for asset in target_portfolio]
		prices = self.prices(assets, quote)
		weighted_portfolio = {asset: value * prices[asset] for asset, value in target_portfolio.items()}
		return await self.trade_to_portfolio_weighted_limit(target_portfolio, quote, initial_portfolio)

	async def trade_to_portfolio_weighted_limit(self, target_portfolio: dict, quote='BTC', initial_portfolio: dict = None):
		await self.account.cancel_all_orders()
		assets, prices, portfolio, target_portfolio, current_weighted_portfolio = self.process_portfolios(target_portfolio, quote, initial_portfolio)
		sell_orders = self.calculate_sell_orders(assets, quote, target_portfolio, current_weighted_portfolio, portfolio)
		fill_queue = asyncio.Queue()
		complete = asyncio.Event()
		placed_sell_orders = []
		sell_task = asyncio.create_task(self.create_sell_order_tasks(sell_orders, quote, complete, fill_queue))	
		
		quote_values = self.portfolio_values(portfolio, quote)
		total_value = sum(quote_values.values())
		buy_orders, min_orders = self.calculate_buy_orders(assets, quote, target_portfolio, current_weighted_portfolio, total_value)
		
		total_volume = sum(volume for asset, volume in buy_orders)
		volume_weights = [volume / total_volume for asset, volume in buy_orders]
		print(volume_weights)
			
		tasks = []
		print(portfolio[quote], current_weighted_portfolio[assets.index(quote)])
		quote_index = assets.index(quote)
		to_buy = portfolio[quote] * (current_weighted_portfolio[quote_index] - target_portfolio[quote_index]) / current_weighted_portfolio[quote_index] if portfolio[quote] > 0 else 0.0
		
		orders = [[asset, volume_weights[i] * to_buy] for i, (asset, volume) in enumerate(buy_orders) if volume_weights[i] * to_buy  > min_orders[i][1]]
		for base, quote_volume in orders:
			tasks.append(asyncio.create_task(self.limit_trade(base, quote, 'BUY', quote_volume=quote_volume)))
		to_buy -= sum(volume for asset, volume in orders)
		while not complete.is_set():
			try:
				fill_event = await asyncio.wait_for(fill_queue.get(), 0.1)	
				to_buy += fill_event['volume'] * fill_event['price']		
				to_buy -= fill_event['fees'][quote] if quote in fill_event['fees'] else 0.0
				fill_queue.task_done()
			except asyncio.TimeoutError:
				pass
				
			orders = [[asset, volume_weights[i] * to_buy] for i, (asset, volume) in enumerate(buy_orders) if volume_weights[i] * to_buy > min_orders[i][1] ]
			to_buy -= sum(quote_volume for asset, quote_volume in orders)

			mid_prices = self.prices([asset for asset, volume in buy_orders], quote)
			for base, quote_volume in orders:
				print(base, quote_volume / mid_prices[base])
				tasks.append(asyncio.create_task(self.limit_trade(base, quote, 'BUY', quote_volume=quote_volume)))

			
		
		await asyncio.gather(*tasks, sell_task)

class SpotTrader(Trader):
	pass

class MarginTrader(Trader):
	pass


class FuturesTrader(Trader):
	pass
