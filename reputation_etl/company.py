"""Resolve a ticker once per run, adapted from the uploaded GDELT notebook."""


def resolve_company(ticker: str, company_name_override: str | None = None) -> dict:
    ticker = ticker.strip().upper()
    if company_name_override and company_name_override.strip():
        return {
            'ticker': ticker,
            'company_name': company_name_override.strip(),
            'resolution_method': 'user_override',
        }

    import yfinance as yf

    search_error = None
    try:
        search = yf.Search(
            ticker, max_results=10, news_count=0,
            include_research=False, raise_errors=True,
        )
        # Important: do not silently select the first *nonmatching* ticker.
        match = next(
            (q for q in (search.quotes or [])
             if str(q.get('symbol', '')).upper() == ticker),
            None,
        )
        if match:
            name = match.get('longname') or match.get('shortname') or match.get('name')
            if name:
                return {
                    'ticker': ticker, 'company_name': name,
                    'short_name': match.get('shortname'),
                    'exchange': match.get('exchange'),
                    'quote_type': match.get('quoteType'),
                    'resolution_method': 'yfinance_search_exact_match',
                }
    except Exception as exc:
        search_error = exc

    # Fallback reflects the Google Trends notebook's original approach.
    try:
        details = yf.Ticker(ticker).get_info()
        name = details.get('longName') or details.get('shortName')
        if name and details.get('symbol', ticker).upper() == ticker:
            return {
                'ticker': ticker, 'company_name': name,
                'resolution_method': 'yfinance_ticker_info',
            }
    except Exception as exc:
        search_error = search_error or exc

    raise ValueError(
        f'Unable to resolve company for {ticker}. Set company_name_override '
        f'in ExtractionConfig to a verified company name. Underlying error: {search_error}'
    )
