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

1. Create a new binance account or sub account to avoid any unnecessary complication. If you'd like to support the project and recive a 10% discount on fees, consider signing up with this [referal link]{https://www.binance.com/en/register?ref=DJK8PVAG}.
2. A good way to design your bot is for the script you write to only complete one task and manage running the bot with the operating system. In this way you do not need to have loops running forever in your code, making bugs much easier to find and fix and any errors will hopefully be limited to one instance of the bot running. If the bot crashes then it will be executed again by the OS in the future, rather than crashing and never running again. Any state data you need to save can be pickled or serialized in any way you prefer - see `examples/mamr.py` for an example of this.


### Example Trading Bot - Automatic portfolio balancing
This is an example of how to set up automatic spot account balancing with the BinanceBot framework. In this guide we set up a simple script that connects to the binance websockets API to track the prices of various currencies and trades when the portfolio is sufficiently different from the target portfolio. The final script can be found at `examples/rebalance.py`

### Example Trading Bot - Third party trading logic

