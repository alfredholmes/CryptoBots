'''Binance Account

Script to demonstrate binance account interaction, script calculates the value of the spot account in BTC and USDT 

Author: 
    Alfred Holmes

'''


import asyncio

import sys
sys.path.append("./")


from cryptobots.connections import ConnectionManager
from cryptobots import Binance
from cryptobots.accounts import SpotAccount as Account
import keys
import datetime

from contextlib import AsyncExitStack



async def main():

    async with Binance() as exchange, AsyncExitStack() as exit_stack: 

        account = await exit_stack.enter_async_context(Account([keys.API, keys.SECRET], exchange, "USDT"))
        await account.get_account_balance() 
        print(account.balance)


        print('closing connections...')

if __name__=='__main__':
    asyncio.run(main())
