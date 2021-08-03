#Script to get usd price candles
MARKETS = ['BTC','ETH','BNB','XRP','DOGE','ADA','DOT','UNI','BCH','LTC','LINK','VET','XLM','SOL','FIL','THETA','TRX','XMR','NEO','LUNA','CAKE','EOS','IOTA','KLAY','AAVE','FTT','CRO','BTT','ATOM','XTZ','ETC','MKR','MATIC','AVAX','ALGO','COMP','RUNE','KSM','DASH','EGLD','XEM','CHZ','ZEC','HOT','DCR','HBAR','DGB','LEO','STX','WAVES','ZIL','MANA','ENJ','SNX','NEAR','NEXO','FTM','GRT','SC','BAT','TFUEL','SUSHI','YFI','BTG','ICX','UMA','RVN','ONT','QTUM','ONE','CEL','ZRX','HNT','ZEN','CHSB','OKB','ANKR','BNT','CELO','RSR','NANO','IOST','XVS','REV','OMG','DENT','FLOW','AR','REN', 'VGX']


MARKETS = ['BTC','ETH','BNB','ADA','XRP','DOGE','DOT','UNI','BCH','LINK','LTC','SOL','MATIC','XLM','ETC','THETA','VET','ICP','FIL','TRX','LUNA','XMR','AAVE','EOS','CAKE','FTT','CRO','GRT','NEO','AMP','MKR','ATOM','LEO','ALGO','IOTA','BSV','XTZ','KLAY','SHIB','AXS','AVAX','COMP','DCR','HBAR','QNT','BIT','KSM','WAVES','TFUEL','DASH','EGLD','XEM','CHZ','RUNE','CEL','STX','ZEC','HNT','MANA','YFI','ENJ','OKB','SNX','FLOW','SUSHI','HOT','NEXO','NEAR','BAT','TEL','ZIL','XDC','PAX','BTG','SC','ONE','BNT','KCS','CELO','QTUM','CHSB','DGB','ONT','ZRX','ANKR','ICX','ZEN','MDX','CRV','FTM','OMG']
import sys
sys.path.append("./")
import asyncio
from binancebots.marketmeta import get_trading_markets 

import datetime

import numpy as np

async def get_trading_routes(bases, quote):
	markets = await get_trading_markets()
	all_bases = set(markets.keys())
	#all_quotes = set([quote for quote, status in markets.values()])
	all_quotes = set()
	for value in markets.values():
		for quote, status in value:
			if status == 'TRADING':
				all_quotes.add(quote)
	
	nodes = list(all_quotes.union(all_bases))
	edges = []
	available = []
	for m in MARKETS:
		if m in markets:
			for quote, status in markets[m]:
				if quote == 'USDT':
					available.append(m)
	print(available)
	print(len(available))
async def main():
	routes = await get_trading_routes(['STEEM'], 'USDT')

if __name__=='__main__':
	asyncio.run(main())
