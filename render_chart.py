import pandas as pd
import mplfinance as mpf
from datetime import datetime

def render_candles(symbol: str, candles: list, path: str):
    """
    candles: list of dicts with keys t,o,h,l,c,v
    """

    df = pd.DataFrame(candles)
    df["Date"] = pd.to_datetime(df["time"], unit="ms")  # Fixed: 't' instead of 'time'
    df.set_index("Date", inplace=True)

    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    })

    df['Lowest Low'] = df['Low'].rolling(window=14).min()
    df['Highest High'] = df['High'].rolling(window=14).max()
    df['RSV'] = (df['Close'] - df['Lowest Low']) / (df['Highest High'] - df['Lowest Low']) * 100
    df['K'] = df['RSV'].ewm(span=3).mean()  
    df['D'] = df['K'].ewm(span=3).mean() 
    df['J'] = 3 * df['K'] - 2 * df['D']

    custom_style = mpf.make_mpf_style(
        base_mpf_style='charles',
        marketcolors=mpf.make_marketcolors(
            up='green',
            down='red',
            edge='inherit',
            wick='inherit',
            volume='inherit'
        ),
        facecolor='black',
        figcolor='black',
        rc={'text.color': 'white', 'axes.labelcolor': 'white', 'xtick.color': 'white', 'ytick.color': 'white'}
    )

    ap = [
        mpf.make_addplot(df['K'], panel=1, color='lightblue'),  
        mpf.make_addplot(df['D'], panel=1, color='orange'),
        mpf.make_addplot(df['J'], panel=1, color='purple')
    ]

    mpf.plot(
        df,
        type="candle",
        addplot=ap,
        style=custom_style,
        title=symbol,
        savefig=dict(fname=path, dpi=120, bbox_inches="tight")
    )