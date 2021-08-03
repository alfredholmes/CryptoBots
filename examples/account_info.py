import sys
sys.path.append("./")
import keys
from binancebots.accounts import SpotAccount

import asyncio


async def main():

	acc = SpotAccount(keys.API, keys.SECRET)
	await acc.get_account_balance()
	await acc.close()

if __name__=='__main__':
	asyncio.run(main())
