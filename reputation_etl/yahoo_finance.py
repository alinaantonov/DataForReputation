"""Yahoo Finance daily OHLCV and derived measures, adapted from user's notebook.

Important: yfinance's `end` parameter is EXCLUSIVE; this module adds a day
so the user-facing end date remains inclusive. Daily bars ≠ hourly signals.
"""
from datetime import date, timedelta
import numpy as np
import pandas as pd


def download_stock_dataset(ticker: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, dict]:
    import yfinance as yf

    if date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise ValueError('start date must not exceed end date')
    end_exclusive = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
    data = yf.download(
        tickers=ticker, start=start_date, end=end_exclusive,
        interval='1d', auto_adjust=False, actions=True,
        progress=False, threads=False,
    )
    if data is None or data.empty:
        return pd.DataFrame(columns=['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']), {
            'Ticker': ticker, 'Company_Name': None, 'note': 'No trading bars returned',
        }
    if isinstance(data.columns, pd.MultiIndex):
        # Most yfinance versions use (Price, Ticker) for one ticker.
        if ticker in data.columns.get_level_values(-1):
            data = data.xs(ticker, level=-1, axis=1)
        else:
            data.columns = data.columns.get_level_values(0)
    data = data.reset_index()
    data.columns = [str(column).strip().replace(' ', '_') for column in data.columns]
    if 'Date' not in data.columns and 'Datetime' in data.columns:
        data = data.rename(columns={'Datetime': 'Date'})
    if 'Date' not in data.columns:
        raise ValueError('Expected Date column in yfinance output')
    data.insert(1, 'Ticker', ticker)
    required = {'Close', 'High', 'Low', 'Open', 'Volume'}
    if not required.issubset(data.columns):
        raise ValueError(f'yfinance output missing {sorted(required - set(data.columns))}')
    for name in required:
        data[name] = pd.to_numeric(data[name], errors='coerce')
    data['Daily_Price_Change'] = data['Close'].diff()
    data['Daily_Return'] = data['Close'].pct_change()
    data['Log_Return'] = np.log(data['Close'] / data['Close'].shift(1))
    data['Daily_Range'] = data['High'] - data['Low']
    data['Daily_Range_Percent'] = data['Daily_Range'].div(data['Open']).mul(100)
    data['Moving_Average_7_Day'] = data['Close'].rolling(7).mean()
    data['Moving_Average_30_Day'] = data['Close'].rolling(30).mean()
    data['Volatility_30_Day'] = data['Daily_Return'].rolling(30).std()
    data['Annualized_Volatility_30_Day'] = data['Volatility_30_Day'] * np.sqrt(252)
    data['Volume_Change_Percent'] = data['Volume'].pct_change() * 100

    metadata = {'Ticker': ticker, 'Company_Name': None, 'Exchange': None,
                'Currency': None, 'Sector': None, 'Industry': None,
                'Country': None, 'Website': None}
    try:
        info = yf.Ticker(ticker).info
        if isinstance(info, dict):
            for k, field in [('Company_Name', 'longName'), ('Exchange', 'exchange'),
                             ('Currency', 'currency'), ('Sector', 'sector'),
                             ('Industry', 'industry'), ('Country', 'country'),
                             ('Website', 'website')]:
                metadata[k] = info.get(field)
    except Exception as exc:
        metadata['metadata_warning'] = f'{type(exc).__name__}: company.info unavailable'
    return data, metadata
