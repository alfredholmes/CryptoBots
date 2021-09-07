# Cryptocurrenty Trading Bot Framework
Asynchronous Bot Framework for Binance and FTX Cryptocurrency Exchanges, potentially more will be added in the future. As the APIs are quite simple, the framework interfaces with these directly to remain lightweight and avoid security issues.


### Current Features
- Support for Binance and FTX
- Asynchronous order book management
- Basic Spot Account Interaction
- Account management and Basic useful trading

### To do:
- Binance orders websocket stream to allow limit order handling on biance


### Running
	$ git clone https://github.com/alfredholmes/CryptoBots
	$ cd CryptoBots
	$ pip3 install -r requirements.txt
	$ python3 examples/ticker.py BTC-USD BTC-ETH

To run the other examples that read account information, create the file `keys.py` which just assignes your binance api and secret keys to the variables `api` and `seceret`. For example, after setting up an API key on Binance, run

	$ echo 'API = "your api key"' >> keys.py
	$ echo 'SECRET' = "your secret key" >> keys.py

and then run

	$ python3 examples/balance.py

to get the live spot data for the account.

### Advice for writing and running a BinanceBot bot

1. Write programs that only run for a short amount of time, and then schedule running using the OS. This means that any errors are short lived.


