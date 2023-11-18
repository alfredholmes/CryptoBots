# Cryptocurrency Trading Bot Framework
Asynchronous Bot Framework for Binance cryptocurrency exchange, potentially more will be added in the future (there used to be support for ftx...). As the APIs are quite simple, the framework interfaces with these directly to remain lightweight and avoid security issues.


### Current Features
- Support for Binance
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
	
### Example scripts

### examples/ticker.py 

Example showing live prices calculated from the midpoint of the orderbook on binance. Pass the markets in the form `BTC-USDT ` as a command line arguments. For example running

    $ python examples/ticker.py BTC-USDT ETH-USDT
    
lists the USDT prices of ETH and BTC every second for 10 seconds.

### examples/orderbook.py 

Example showing live prices orderbooks on binance. Much the same as `ticker.py` but prints the orderbook. Pass the markets in the form `BTC-USDT ` as a command line arguments. For example running

    $ python examples/orderbook.py BTC-USDT ETH-USDT
    
lists the USDT orderbooks of BTC and ETH every second for 10 seconds.


### examples/binance_account.py






### Design Advice

Write programs that only run for a short amount of time, and then schedule running using the OS. This means that any errors that occur don't result in the application not working at future time


