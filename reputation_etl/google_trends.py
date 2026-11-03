"""Google Trends extraction adapted from user's GoogleTrends notebook.

No Google Drive or input() calls. Google Trends values are normalized (0–100)
within the selected query; cadence depends on the requested timeframe.
"""
import time
from datetime import datetime, timezone

import pandas as pd


def get_google_trends(
    *, ticker: str, company_name: str, search_term: str,
    start_date: str, end_date: str, geo: str = 'US', max_retries: int = 3,
) -> pd.DataFrame:
    from pytrends.request import TrendReq

    timeframe = f'{start_date} {end_date}'
    last_error = None
    for attempt in range(max_retries):
        try:
            client = TrendReq(hl='en-US', tz=300, timeout=(10, 25))
            client.build_payload(
                kw_list=[search_term], cat=0,
                timeframe=timeframe, geo=geo, gprop='',
            )
            df = client.interest_over_time()
            if df.empty:
                # No data is a valid outcome, distinct from a transient HTTP error.
                return pd.DataFrame(columns=[
                    'date', 'ticker', 'company_name', 'search_term',
                    'trend_interest', 'is_partial', 'geo', 'source',
                    'retrieved_at_utc',
                ])
            break
        except Exception as exc:
            last_error = exc
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f'Google Trends failed after {max_retries} attempts: {exc}'
                ) from exc
            time.sleep(5 * (2 ** attempt))
    else:
        raise RuntimeError(f'Google Trends failed: {last_error}')

    df = df.reset_index().rename(columns={
        search_term: 'trend_interest',
        'isPartial': 'is_partial',
    })
    df['ticker'] = ticker
    df['company_name'] = company_name
    df['search_term'] = search_term
    df['geo'] = geo or 'WORLD'
    df['source'] = 'Google Trends'
    df['retrieved_at_utc'] = datetime.now(timezone.utc).isoformat()
    ordered = [
        'date', 'ticker', 'company_name', 'search_term', 'trend_interest',
        'is_partial', 'geo', 'source', 'retrieved_at_utc',
    ]
    return df[[c for c in ordered if c in df.columns]]
