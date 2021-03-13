import sys
sys.path.append("./")
import keys
from binancebots.accounts import SpotAccount

import asyncio



async def main():
	#create SpotAccount object to manage the account
	acc = SpotAccount(keys.API, keys.SECRET)
	

	#Create a portfolio dict, values don't need to add up to 1 and any currencies not included in the dictionary will not be traded 
	target_portfolio = {'BTC': 0/3, 'ETH': 0/3, 'USDT': 0/3, 'STEEM': 0, 'BNB':  3/3}

	#this gets the weighted portfolio of the binance account
	weighted = await acc.weighted_portfolio(target_portfolio)
	print('Initial portfolio: ', weighted)


	#logic to decide whether or not to trade; if 10% of the funds are in the wrong place
	diff = sum([abs(target_portfolio[s] - weighted[s]) for s in target_portfolio])

	if diff > 0.1:
		print('Performing rebalance')
		await acc.trade_to_portfolio(target_portfolio)
	else:
		print('Portfolio difference of ', diff, 'too low to trade')
	
	#once complete, print out the new portfolio
	weighted = await acc.weighted_portfolio()
	print('Final portfolio: ', weighted)

	await acc.close()
	

if __name__ == '__main__':
	asyncio.run(main())
