import requests
import logging

BASE_URL = "https://open-api.bingx.com"
CONTRACTS_URL = BASE_URL + "/openApi/swap/v2/quote/contracts"
TICKER_URL = BASE_URL + "/openApi/swap/v2/quote/ticker"


MAX_PRICE = 1.0
MIN_PRICE = 0.0001


def get_usdtm_symbols():
    try:
        r = requests.get(CONTRACTS_URL, timeout=10)
        r.raise_for_status()  # Викличе виняток для помилкових статусів
        
        if not r.text or not r.text.strip():
            logging.error(f"Empty response from {CONTRACTS_URL}")
            return set()
        
        data = r.json()

        if data.get("code") != 0:
            logging.warning(f"API returned error code: {data.get('code')}, msg: {data.get('msg')}")
            return set()

        return {
            c["symbol"]
            for c in data.get("data", [])
            if c.get("symbol", "").endswith("USDT")
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error in get_usdtm_symbols: {e}")
        return set()
    except ValueError as e:
        logging.error(f"JSON decode error in get_usdtm_symbols: {e}, response text: {r.text[:200]}")
        return set()
    except Exception as e:
        logging.error(f"Unexpected error in get_usdtm_symbols: {e}")
        return set()


def get_prices():
    try:
        r = requests.get(TICKER_URL, timeout=10)
        r.raise_for_status()  
        
        if not r.text or not r.text.strip():
            logging.error(f"Empty response from {TICKER_URL}")
            return {}
        
        data = r.json()

        if data.get("code") != 0:
            logging.warning(f"API returned error code: {data.get('code')}, msg: {data.get('msg')}")
            return {}

        prices = {}
        for t in data.get("data", []):
            symbol = t.get("symbol")
            last_price = t.get("lastPrice")
            if symbol and last_price:
                try:
                    prices[symbol] = float(last_price)
                except (ValueError, TypeError):
                    continue

        return prices
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error in get_prices: {e}")
        return {}
    except ValueError as e:
        logging.error(f"JSON decode error in get_prices: {e}, response text: {r.text[:200] if 'r' in locals() else 'N/A'}")
        return {}
    except Exception as e:
        logging.error(f"Unexpected error in get_prices: {e}")
        return {}


def get_filtered_symbols(min_price=MIN_PRICE, max_price=MAX_PRICE): #0.1 2.0
    symbols = get_usdtm_symbols()
    prices = get_prices()

    result = []

    for symbol in symbols:
        price = prices.get(symbol)
        if price is None:
            continue

        if min_price <= price <= max_price:
            result.append(symbol)

    return result


# if __name__ == "__main__":
#    items = get_filtered_symbols()
#    i = 0
#    for item in items:
#       i+=1
#       print(item)
#    print(f"--TOTAL:{i}--")
