# Binance Bots
Asynchronous Bot Framework for Binance Cryptocurrency Exchange. As the Binance APIs are quite simple, the framework interfaces with these directly to remain lightweight and avoid security issues.


### Current Features
- Asynchronous order book management
- Basic Spot Account Interaction


### To do:
- Account management and trading
- Simple custom trading logic extensions
- Listen to aggregated trade streams to get more up to date order book information
- Interaction with flexible savings 

### Running
	$ git clone https://github.com/alfredholmes/BinanceBots
	$ cd BinanceBots
	$ pip3 install -r requirements.txt
	$ python3 examples/ticker.py btcusdt ethusdt

To run the other examples that read account information, create the file `keys.py` which just assignes your binance api and secret keys to the variables `api` and `seceret`. For example, after setting up an API key on Binance, run

	$ echo 'API = "your api key"' >> keys.py
	$ echo 'SECRET' = "your secret key" >> keys.py

and then run

	$ python3 examples/spotaccount.py

to get the live spot data for the account.

### Advice for writing and running a BinanceBot bot

1. Create a new binance account or sub account to avoid any unnecessary complication. If you'd like to support the project and recive a 10% discount on fees, consider signing up with this [referal link](https://www.binance.com/en/register?ref=DJK8PVAG).
2. A good way to design your bot is for the script you write to only complete one task and manage running the bot with the operating system. In this way you do not need to have loops running forever in your code, making bugs much easier to find and fix and any errors will hopefully be limited to one instance of the bot running. If the bot crashes then it will be executed again by the OS in the future, rather than crashing and never running again. Any state data you need to save can be pickled or serialized in any way you prefer - see `examples/mamr.py` for an example of this.


### Example Trading Bot - Automatic portfolio balancing
This is an example of how to set up automatic spot account balancing with the BinanceBot framework. In this guide we set up a simple script that connects to the binance websockets API to track the prices of various currencies and trades when the portfolio is sufficiently different from the target portfolio. The final script can be found at `examples/rebalance.py`

1. Import the required files - in this script we will use the `OrderBookManager` and `SpotAccount` classes also make sure you've set up the `keys.py` file as described above. We import `sys` so that the script can be saved in the `examples` folder and executed from the root of the cloned repository. We'll also need `asyncio` to manage the asynchronous tasks. So we'll add the following to `examples/rebalance.py`

```python
import sys
sys.path.append("./")
import keys
from binancebots.accounts import SpotAccount
import asyncio
```

2. For the main loop we need to get the current account balances, so we'll create a `SpotAccount` instance to track the account balances and prices. Let's implement this first. We'll write a simple main function and call it with `asyncio` in the standard way.

```python
async def main():
	acc = account(keys.API, keys.SECRET)

	await acc.get_account_data()
	print(acc.spot_balances)

	await acc.close()

if __name__ == '__main__':
	asyncio.run(main())	
```
if we run the script you will see a print out of your spot account balance. `SpotAccount` does not track 0 balances so if you have not deposited to Binance you will get an empty dictionary. The function `SpotAccount.get_account_data` pulls the available spot market meta-data from the Binance API and gets the current account information, which contains the account balances.

	$ python3 examples/rebalance.py
	{'USDT': 120.30743}
  
3. Now we'll call the `SpotAccount.weighted_portfolio` function to get the relative values of the portfolio and decide if the portfolio is far enough away from the desired portfolio to bother rebalancing: we'll say that a portfolio needs rebalancing if at least 10% of the portfolio is in the wrong asset. Before calling the `SpotAccount.weighted_portfolio` we need to use the websocket API to listen to the relevant orderbooks so that the bot can access real time market data. The new main function looks like this.

```python
async def main():
	acc = SpotAccount(keys.API, keys.SECRET)
	await acc.get_account_data()

	weighted_portfolio = await acc.weighted_portfolio(['USDT', 'BTC', 'ETH'])
	print(weighted_portfolio)

	await acc.close()
```
and running this gives the following output

	$ python3 examples/rebalance.py
	{'USDT': 1.0, 'BTC': 0.0, 'ETH': 0.0}


4. Next we'll construct a target portfolio and get the account to trade into that portfolio using the `SpotAccount.trade_to_portfolio`function
### Example Trading Bot - Third party trading logic!

