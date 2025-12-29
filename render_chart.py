import pandas as pd
import mplfinance as mpf
from datetime import datetime

def render_candles(symbol: str, candles: list, path: str):
    """
    candles: list of dicts with keys time, open, high, low, close, volume
    """
    if not candles:
        return  

    df = pd.DataFrame(candles)
    if df.empty:
        return

    df["Date"] = pd.to_datetime(df["time"], unit="ms")
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
    df['K'] = df['RSV'].ewm(span=3, adjust=False).mean()
    df['D'] = df['K'].ewm(span=3, adjust=False).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']

    df = df.dropna()
    if df.empty:
        return

    df = df.dropna(subset=['Open','High','Low','Close'])
    if df.empty:
        return

    q_low = df['Low'].quantile(0.01)
    q_high = df['High'].quantile(0.99)
    padding = (q_high - q_low) * 0.05
    y_limits = (q_low - padding, q_high + padding)


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
        gridstyle=':',
        y_on_right=True,
        rc={
            'text.color': 'white',
            'axes.labelcolor': 'white',
            'xtick.color': 'white',
            'ytick.color': 'white'
        }
    )


    ap = [
        mpf.make_addplot(df['K'], panel=1, color='lightblue', ylabel='KDJ'),
        mpf.make_addplot(df['D'], panel=1, color='orange'),
        mpf.make_addplot(df['J'], panel=1, color='purple')
    ]


    mpf.plot(
        df,
        type="candle",
        addplot=ap,
        style=custom_style,
        title=symbol,
        ylim=y_limits, 
        tight_layout=True, 
        scale_padding={'left': 0.05, 'right': 0.95, 'top': 0.95, 'bottom': 0.05},
        savefig=dict(fname=path, dpi=120, bbox_inches="tight")
    )