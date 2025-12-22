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

    mpf.plot(
        df,
        type="candle",
        volume=True,
        style="yahoo",
        title=symbol,
        savefig=dict(fname=path, dpi=120, bbox_inches="tight")
    )
