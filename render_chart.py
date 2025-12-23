import pandas as pd
import mplfinance as mpf
from datetime import datetime

def render_candles(symbol: str, candles: list, path: str):
    """
    candles: list of dicts with keys t,o,h,l,c,v
    """

    df = pd.DataFrame(candles)
    df["Date"] = pd.to_datetime(df["time"], unit="ms")
    df.set_index("Date", inplace=True)

    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    })

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

    mpf.plot(
        df,
        type="candle",
        volume=True,
        style=custom_style,
        title=symbol,
        savefig=dict(fname=path, dpi=120, bbox_inches="tight")
    )
