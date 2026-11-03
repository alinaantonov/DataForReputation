"""SEC filing-index retrieval adapted from the supplied SecEdgarData notebook.

Loads the recent submissions PLUS matching older submission-index chunks. These
are filing dates/acceptance timestamps, not dates when an incident occurred.
"""
import time
from datetime import date
import pandas as pd
import requests

SEC_TICKER_URL = 'https://www.sec.gov/files/company_tickers.json'
SEC_SUBMISSIONS = 'https://data.sec.gov/submissions/'


def sec_get_json(url: str, user_agent: str, sleep_seconds: float = .2, session=None):
    if not user_agent or '@' not in user_agent:
        raise ValueError('SEC user_agent must identify your research and include a real contact email')
    http = session or requests
    response = http.get(url, headers={'User-Agent': user_agent, 'Accept-Encoding': 'gzip, deflate'}, timeout=45)
    response.raise_for_status()
    if sleep_seconds:
        time.sleep(sleep_seconds)
    return response.json()


def get_company_cik(ticker: str, user_agent: str, request_delay: float = .2) -> dict:
    catalog = sec_get_json(SEC_TICKER_URL, user_agent, request_delay)
    for candidate in catalog.values():
        if str(candidate.get('ticker', '')).upper() == ticker.upper():
            return {'ticker': candidate['ticker'], 'company': candidate['title'],
                    'cik': str(candidate['cik_str']).zfill(10)}
    raise ValueError(f'SEC ticker mapping not found for {ticker}')


def get_filings(cik: str, start_date: str, end_date: str, user_agent: str,
                request_delay: float = .2) -> tuple[pd.DataFrame, dict]:
    """Retrieve index chunks that overlap selected dates, recording failures."""
    meta = sec_get_json(f'{SEC_SUBMISSIONS}CIK{cik}.json', user_agent, request_delay)
    filing_data = meta.get('filings', {})
    frames = [pd.DataFrame(filing_data.get('recent', {}))]
    attempted = []
    for file in filing_data.get('files', []):
        try:
            start, end = date.fromisoformat(file['filingFrom']), date.fromisoformat(file['filingTo'])
        except (KeyError, ValueError):
            continue
        if start > date.fromisoformat(end_date) or end < date.fromisoformat(start_date):
            continue
        name = file['name']
        log = {'file': name, 'status': 'failed', 'rows': 0, 'error': ''}
        try:
            payload = sec_get_json(f'{SEC_SUBMISSIONS}{name}', user_agent, request_delay)
            frame = pd.DataFrame(payload)
            frames.append(frame)
            log.update(status='success', rows=len(frame))
        except (requests.RequestException, ValueError, KeyError) as exc:
            log['error'] = f'{type(exc).__name__}: {exc}'
        attempted.append(log)
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not data.empty and 'accessionNumber' in data:
        data = data.drop_duplicates(subset='accessionNumber')
    info = {'cik': cik, 'company_name_sec': meta.get('name'),
            'extra_file_log': pd.DataFrame(attempted,
                columns=['file', 'status', 'rows', 'error']),
            'historical_file_failures': sum(x['status'] == 'failed' for x in attempted),
            'historical_files_checked': len(attempted)}
    return data, info


def filter_filings_by_date(filings: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if 'filingDate' not in filings:
        return filings.iloc[0:0].copy()
    df = filings.copy()
    df['filingDate'] = pd.to_datetime(df['filingDate'], errors='coerce')
    return df.loc[df['filingDate'].between(pd.Timestamp(start_date), pd.Timestamp(end_date))].sort_values('filingDate').reset_index(drop=True)


def create_sec_event_dataset(filings: pd.DataFrame, ticker: str, company_name: str, cik: str) -> pd.DataFrame:
    """A table of *disclosure evidence*, not confirmed reputational events."""
    df = filings.copy()
    df['ticker'], df['company'], df['cik'] = ticker, company_name, cik
    df['source'], df['signal_layer'] = 'SEC_EDGAR', 'Governance'
    df['event_date'] = pd.to_datetime(df['filingDate']) if 'filingDate' in df else pd.NaT
    df['event_type'] = 'SEC_' + df['form'].astype(str) if 'form' in df else 'SEC_UNKNOWN'
    if 'accessionNumber' in df and 'primaryDocument' in df:
        accessions = df['accessionNumber'].astype(str).str.replace('-', '', regex=False)
        df['filing_url'] = ('https://www.sec.gov/Archives/edgar/data/' + str(int(cik)) + '/'
                             + accessions + '/' + df['primaryDocument'].astype(str))
    columns = ['ticker', 'company', 'cik', 'event_date', 'source', 'signal_layer',
               'event_type', 'form', 'items', 'accessionNumber', 'reportDate',
               'acceptanceDateTime', 'primaryDocument', 'primaryDocDescription',
               'isXBRL', 'isInlineXBRL', 'filing_url']
    for column in columns:
        if column not in df:
            df[column] = pd.Series(dtype='object')
    return df[columns]


def extract_sec_filings(ticker: str, company_name: str, start_date: str, end_date: str,
                        user_agent: str, forms: tuple[str, ...], request_delay: float = .2):
    company = get_company_cik(ticker, user_agent, request_delay)
    filings, info = get_filings(company['cik'], start_date, end_date, user_agent, request_delay)
    dated = filter_filings_by_date(filings, start_date, end_date)
    selected = dated[dated['form'].isin(forms)].copy() if 'form' in dated else dated.iloc[0:0].copy()
    events = create_sec_event_dataset(selected, ticker, company_name, company['cik'])
    info.update({'sec_company': company, 'filings_in_period': len(dated),
                 'selected_forms': list(forms), 'selected_filings': len(selected)})
    return events, info
