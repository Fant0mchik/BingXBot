import requests

BASE_URL = "https://open-api.bingx.com"
CONTRACTS_URL = BASE_URL + "/openApi/swap/v2/quote/contracts"
TICKER_URL = BASE_URL + "/openApi/swap/v2/quote/ticker"


MAX_PRICE = 1.0
MIN_PRICE = 0.0001


def get_usdtm_symbols():
    r = requests.get(CONTRACTS_URL, timeout=10)
    data = r.json()

    if data.get("code") != 0:
        return set()

    return {
        c["symbol"]
        for c in data["data"]
        if c["symbol"].endswith("USDT")
    }


def get_prices():
    r = requests.get(TICKER_URL, timeout=10)
    data = r.json()

    if data.get("code") != 0:
        return {}

    prices = {}
    for t in data["data"]:
        prices[t["symbol"]] = float(t["lastPrice"])

    return prices


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
