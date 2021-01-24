import sys
sys.path.append("./")
import keys
from binancebots.orderbooks import OrderBookManager
from binancebots.accounts import SpotAccount

import asyncio



async def main():
	acc = SpotAccount(keys.API, keys.SECRET)
	await acc.get_account_data()

	target_portfolio = {'BTC': 0.0, 'ETH': 0.0, 'USDT': 0.0, 'STEEM': 1.0, 'BNB':  0.0}


	weighted = await acc.weighted_portfolio(target_portfolio)
	print('Initial portfolio: ', weighted)

	diff = sum([abs(target_portfolio[s] - weighted[s]) for s in target_portfolio])

	if diff > 0.1:
		print('Performing rebalance')
		await acc.trade_to_portfolio(target_portfolio)
	else:
		print('Portfolio difference of ', diff, 'too low to trade')
	

	weighted = await acc.weighted_portfolio()
	print('Final portfolio: ', weighted)

	await acc.close()
	

if __name__ == '__main__':
	asyncio.run(main())