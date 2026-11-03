"""GDELT DOC article extraction adapted from user's GDELTData notebook.

Returns both a DataFrame and coverage metadata; does not mount Drive or prompt.
"""
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

GDELT_DOC_ENDPOINT = 'https://api.gdeltproject.org/api/v2/doc/doc'


def clean_company_name(company_name: str) -> str: 
    pattern = (
        r',?\s+(incorporated|inc\.?|corporation|corp\.?|company|co\.?|'
        r'limited|ltd\.?|plc|holdings?|group|sa|ag|nv)\.?$'
    )
    return re.sub(pattern, '', company_name.strip(), flags=re.IGNORECASE).strip(' ,.-')


def build_company_query(
    ticker: str, company_name: str,
    aliases: Optional[list[str]] = None,
    additional_terms: Optional[list[str]] = None,
    include_ticker: bool = False,
) -> str:
    """Use quoted company-name variants; ticker alone is often ambiguous."""
    aliases = aliases or []
    additional_terms = additional_terms or []
    unique_names = []
    seen = set()
    for name in [company_name, clean_company_name(company_name), *aliases]:
        if name and name.strip().casefold() not in seen:
            seen.add(name.strip().casefold())
            unique_names.append(name.strip())
    if include_ticker:
        unique_names.append(ticker.upper())
    if not unique_names:
        raise ValueError('Missing company name for GDELT query')
    quote = lambda s: '"' + s.replace('"', '\\"') + '"'
    parts = [quote(x) for x in unique_names]
    query = parts[0] if len(parts) == 1 else '(' + ' OR '.join(parts) + ')'
    terms = [quote(x.strip()) for x in additional_terms if x and x.strip()]
    if terms:
        topic_query = terms[0] if len(terms) == 1 else '(' + ' OR '.join(terms) + ')'
        query = f'{query} AND {topic_query}'
    return query


def create_date_windows(start_date: str, end_date: str, window_days: int = 7):
    """Inclusive user dates become full-day, nonoverlapping UTC API windows."""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    windows = []
    while start <= end:
        stop = min(start + pd.Timedelta(days=window_days) - pd.Timedelta(seconds=1), end)
        windows.append((start, stop))
        start = stop + pd.Timedelta(seconds=1)
    return windows


def request_gdelt_json(params: dict, max_retries: int = 4, timeout: int = 60) -> dict:
    headers = {'User-Agent': 'Academic-GDELT-Company-Research/1.0 (Python requests; research)'}
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.get(
                GDELT_DOC_ENDPOINT, params=params, headers=headers, timeout=timeout,
            )
            #####
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = RuntimeError(f'HTTP {response.status_code} from GDELT')
            else:
                response.raise_for_status()
                return response.json() if response.text.strip() else {}
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    raise RuntimeError(f'GDELT request failed after {max_retries} attempts: {last_error}')


def get_gdelt_company_articles(
    *,
    ticker: str,
    company_name: str,
    start_date: str,
    end_date: str,
    aliases: Optional[list[str]] = None,
    additional_terms: Optional[list[str]] = None,
    source_country: Optional[str] = "United States",
    source_language: Optional[str] = "English",
    include_ticker_in_query: bool = False,
    window_days: int = 1,  # Set default window size to 1 day to stay safely under 250 records
    max_records_per_window: int = 250,
    request_delay: float = 60.0,
) -> tuple[pd.DataFrame, dict]:

    """Download articles across split chronological windows to bypass the 250-record limit."""
    
    query = build_company_query(
        ticker, company_name, aliases, additional_terms, include_ticker_in_query,
    )
    
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    
    # Generate chronological date chunks
    date_intervals = pd.date_range(start=start_dt, end=end_dt, freq=f"{window_days}D")
    
    all_articles = []
    request_logs = []
    failed_windows = 0
    capped_windows = 0
    
    for i in range(len(date_intervals)):
        chunk_start = date_intervals[i]
        # Ensure chunk end doesn't overshoot the overall end_date
        chunk_end = min(chunk_start + timedelta(days=window_days), end_dt)
        
        # GDELT format expects YYYYMMDDHHMMSS
        start_str = chunk_start.strftime("%Y%m%d000000")
        end_str = chunk_end.strftime("%Y%m%d235959")
        
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": max_records_per_window,
            "startdatetime": start_str,
            "enddatetime": end_str,
            "format": "json"
        }
        
        if source_country:
            params["query"] += f" sourcecountry:{source_country.upper()}"
        if source_language:
            params["query"] += f" sourcelang:{source_language}"
            
        try:
            data = request_gdelt_json(params)
            articles = data.get("articles", [])
            
            if len(articles) >= max_records_per_window:
                capped_windows += 1
                
            if articles:
                df_chunk = pd.DataFrame(articles)
                all_articles.append(df_chunk)
                
            request_logs.append({
                "window_start": chunk_start.strftime("%Y-%m-%d"),
                "window_end": chunk_end.strftime("%Y-%m-%d"),
                "status": "success",
                "records_returned": len(articles)
            })
            
        except Exception as e:
            failed_windows += 1
            request_logs.append({
                "window_start": chunk_start.strftime("%Y-%m-%d"),
                "window_end": chunk_end.strftime("%Y-%m-%d"),
                "status": "failed",
                "error": str(e)
            })
            
        time.sleep(request_delay)
        
    # Combine all windows together and drop duplicate articles by URL if any overlap
    if all_articles:
        combined_df = pd.concat(all_articles, ignore_index=True)
        if "url" in combined_df.columns:
            combined_df = combined_df.drop_duplicates(subset=["url"])
    # --- STRICT POST-PROCESSING FILTER ---
        if "sourcecountry" in combined_df.columns:
            combined_df = combined_df[combined_df["sourcecountry"].str.lower() == "united states"]
        if "language" in combined_df.columns:
            combined_df = combined_df[combined_df["language"].str.lower() == "english"]
        # ------------------------------------        
    else:
        combined_df = pd.DataFrame()
        
    log_df = pd.DataFrame(request_logs)
    
    metadata = {
        "failed_windows": failed_windows,
        "capped_windows": capped_windows,
        "total_rows": len(combined_df)
    }
    
    return combined_df, metadata