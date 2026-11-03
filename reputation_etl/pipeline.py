"""Independent source runners, auditable output, and failure isolation.

Every run creates a new directory, rather than overwriting old research data.
Each source gets the same normalized ticker, company name, and inclusive dates.
"""
import hashlib
import json
import platform
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Callable

import pandas as pd

from .company import resolve_company
from .config import ExtractionConfig
from .gdelt import clean_company_name, get_gdelt_company_articles
from .google_trends import get_google_trends
from .youtube import extract_youtube_dataset
from .sec_edgar import extract_sec_filings
from .yahoo_finance import download_stock_dataset


@dataclass
class SourceResult:
    data: pd.DataFrame
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    incomplete: bool = False


def _gdelt(c: ExtractionConfig, company: dict) -> SourceResult:
    data, meta = get_gdelt_company_articles(
        ticker=c.ticker, company_name=company['company_name'],
        start_date=c.start_date, end_date=c.end_date,
        aliases=list(c.gdelt_aliases), additional_terms=list(c.gdelt_additional_terms),
        source_country=c.gdelt_source_country, source_language=c.gdelt_source_language,
        include_ticker_in_query=c.gdelt_include_ticker,
        window_days=c.gdelt_window_days, max_records_per_window=c.gdelt_max_records,
        request_delay=c.gdelt_request_delay_seconds,
    )
    failed, capped = meta['failed_window_count'], meta['potentially_truncated_window_count']
    notes = ['GDELT DOC ArticleList is capped at 250 articles per request and has limited historical access; '
             'capped windows or unavailable periods do not imply no articles exist.']
    if failed:
        notes.append(f'{failed} failed GDELT time window(s); see request log.')
    if capped:
        notes.append(f'{capped} capped GDELT time window(s); use smaller windows or bulk/BigQuery.')
    return SourceResult(data, tables={'request_log': meta['request_log']}, notes=notes,
                        metadata={k: v for k, v in meta.items() if k != 'request_log'},
                        incomplete=bool(failed or capped))


def _trends(c: ExtractionConfig, company: dict) -> SourceResult:
    term = c.trends_search_term or clean_company_name(company['company_name'])
    data = get_google_trends(ticker=c.ticker, company_name=company['company_name'],
                             search_term=term, start_date=c.start_date,
                             end_date=c.end_date, geo=c.trends_geo,
                             max_retries=c.trends_max_retries)
    return SourceResult(data, notes=[
        'Google Trends values are normalized within the request; do not compare uncalibrated runs.',
        'Output observation cadence is determined by the requested historical range, not guaranteed hourly.',
        'pytrends is an unofficial archived client; access may fail or change.',
    ], metadata={'term': term, 'geo': c.trends_geo or 'WORLD'})


def _youtube(c: ExtractionConfig, company: dict) -> SourceResult:
    data, videos, log, meta = extract_youtube_dataset(
        ticker=c.ticker, company_name=company['company_name'],
        start_date=c.start_date, end_date=c.end_date,
        api_key=c.youtube_api_key or '', search_query=c.youtube_search_query,
        max_videos=c.youtube_max_videos,
        max_comment_pages_per_video=c.youtube_max_comment_pages_per_video,
        include_comment_text=c.youtube_include_comment_text,
        include_author_fields=c.youtube_include_author_fields,
    )
    incomplete = bool(meta['video_selection_reached_cap'] or meta['comment_pages_truncated']
                      or meta['videos_with_unavailable_comments'])
    return SourceResult(data, tables={'videos': videos, 'comment_request_log': log},
        notes=['Search selects videos PUBLISHED within the date range, then comments on those videos '
               'PUBLISHED within the range; older videos are excluded.',
               'Only top-level comments are retrieved, not replies; public comments may be unavailable.',
               'YouTube search and comment paging are quota-constrained; partial coverage is flagged.',
               'Video statistics are collected at extraction time, not historical engagement snapshots.',
               'Review YouTube API retention/deletion and research approval requirements before retaining raw content.'],
        metadata=meta, incomplete=incomplete)


def _sec(c: ExtractionConfig, company: dict) -> SourceResult:
    events, meta = extract_sec_filings(
        ticker=c.ticker, company_name=company['company_name'], start_date=c.start_date,
        end_date=c.end_date, user_agent=c.sec_user_agent or '', forms=c.sec_forms,
        request_delay=c.sec_request_delay_seconds,
    )
    log = meta.pop('extra_file_log')
    return SourceResult(events, tables={'historical_file_log': log}, metadata=meta,
        incomplete=bool(meta['historical_file_failures']),
        notes=['SEC filings are independent corroborating disclosure records, NOT validated incident labels.',
               'FilingDate is date-level; acceptanceDateTime can be more precise when available.',
               'SEC submission history is composed of recent AND older index files.'])


def _yahoo(c: ExtractionConfig, company: dict) -> SourceResult:
    data, meta = download_stock_dataset(c.ticker, c.start_date, c.end_date)
    return SourceResult(data, tables={'company_metadata': pd.DataFrame([meta])},
        notes=['yfinance end parameter converted to inclusive end date.',
               'Daily stock bars are not hourly prediction signals; market data are external corroboration.',
               'Rolling 7/30-trading-day variables are NaN near the start unless prior warm-up history is fetched.',
               'yfinance is unofficial; verify data license and replace with licensed research data if needed.'],
        metadata={'bar_interval': '1d', 'raw_adjusted': False})


RUNNERS = {'gdelt': _gdelt, 'google_trends': _trends, 'youtube': _youtube,
           'sec_edgar': _sec, 'yahoo_finance': _yahoo}


def _safe_config(c: ExtractionConfig) -> dict:
    result = asdict(c)
    result['output_root'] = str(c.output_root)
    # Never store API tokens or identifying SEC contact details in a shared manifest.
    result['youtube_api_key'] = '[REDACTED]' if c.youtube_api_key else '[NOT SET]'
    result['sec_user_agent'] = '[PROVIDED]' if c.sec_user_agent else '[NOT SET]'
    result['sources'] = list(c.sources)
    return result


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def _error(exc, c: ExtractionConfig) -> str:
    result = f'{type(exc).__name__}: {exc}'
    for sensitive in [c.youtube_api_key, c.sec_user_agent]:
        if sensitive:
            result = result.replace(sensitive, '[REDACTED]')
    result = re.sub(r'AIza[A-Za-z0-9_-]{30,}', '[REDACTED_KEY]', result)
    return result[:800]


def _pkg_version(pkg: str):
    try:
        return version(pkg)
    except PackageNotFoundError:
        return None


def _save(df: pd.DataFrame, dest: Path, parquet=True) -> dict:
    path = dest.with_suffix('.csv')
    df.to_csv(path, index=False, encoding='utf-8-sig')
    dig = hashlib.sha256(path.read_bytes()).hexdigest()
    files = {'csv': path.name, 'csv_sha256': dig}
    if parquet and len(df.columns):
        try:
            df.to_parquet(dest.with_suffix('.parquet'), index=False)
            files['parquet'] = dest.with_suffix('.parquet').name
        except (ImportError, ValueError, TypeError, OSError) as exc:
            files['parquet_warning'] = f'{type(exc).__name__}: {exc}'
    return files


def run_pipeline(c: ExtractionConfig,
                 extra_extractors: dict[str, Callable] | None = None) -> tuple[pd.DataFrame, Path]:
    """Continue other sources if an individual source fails; never silently overwrite runs."""
    runners = dict(RUNNERS)
    runners.update(extra_extractors or {})
    missing = set(c.sources) - set(runners)
    if missing:
        raise ValueError(f'No extractor registered for {sorted(missing)}')
    now = datetime.now(timezone.utc)
    run_id = now.strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
    out = (c.output_root / 'runs' / c.ticker.replace('^', '_') /
           f'{c.start_date}_to_{c.end_date}' / run_id)
    out.mkdir(parents=True, exist_ok=False)
    manifest_path = out / 'manifest.json'
    manifest = {
        'run_id': run_id, 'started_at_utc': now.isoformat(),
        'finished_at_utc': None, 'config': _safe_config(c), 'company': None,
        'environment': {'python': platform.python_version(), 'pandas': pd.__version__,
                        'yfinance': _pkg_version('yfinance'),
                        'pytrends': _pkg_version('pytrends'),
                        'google-api-python-client': _pkg_version('google-api-python-client')},
        'sources': {},
    }
    def write_manifest():
        manifest_path.write_text(json.dumps(_jsonable(manifest), indent=2, ensure_ascii=False), encoding='utf-8')

    try:
        company = resolve_company(c.ticker, c.company_name_override)
        manifest['company'] = company
    except Exception as exc:
        manifest['setup_error'] = _error(exc, c)
        manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        write_manifest()
        raise
    write_manifest()
    print(f"Company: {c.ticker} — {company['company_name']}")
    rows = []
    for source in c.sources:
        started = datetime.now(timezone.utc)
        item = {'status': 'failed', 'rows': 0, 'files': {}, 'notes': [], 'error': '', 'metadata': {}}
        print(f'\nRunning {source} ...')
        try:
            output = runners[source](c, company)
            if isinstance(output, pd.DataFrame):
                output = SourceResult(output)
            if not isinstance(output, SourceResult) or not isinstance(output.data, pd.DataFrame):
                raise TypeError('Extractor must return SourceResult with DataFrame data')
            item['rows'] = len(output.data)
            item['notes'] = output.notes
            item['metadata'] = output.metadata
            item['files']['data'] = _save(output.data, out / source, c.save_parquet)
            for name, table in output.tables.items():
                if not isinstance(table, pd.DataFrame):
                    raise TypeError(f'{source}.{name} is not a DataFrame')
                safe = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
                item['files'][safe] = _save(table, out / f'{source}_{safe}', c.save_parquet)
            item['status'] = 'partial' if output.incomplete else ('empty' if output.data.empty else 'success')
        except Exception as exc:
            item['error'] = _error(exc, c)
        item['duration_seconds'] = round((datetime.now(timezone.utc) - started).total_seconds(), 2)
        manifest['sources'][source] = item
        rows.append({'source': source, 'status': item['status'], 'rows': item['rows'],
                     'error': item['error'], 'notes': ' | '.join(item['notes'])})
        print(f"{source}: {item['status']} — {item['rows']} rows" + (f"; {item['error']}" if item['error'] else ''))
        write_manifest()
    summary = pd.DataFrame(rows)
    summary.to_csv(out / 'run_summary.csv', index=False)
    manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    write_manifest()
    print(f'\nOutputs: {out}')
    return summary, out
