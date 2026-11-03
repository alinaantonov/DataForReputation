"""Central run configuration. Dates are inclusive; no prompts or Drive mounts here."""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_OUTPUT_ROOT = Path('/content/drive/MyDrive/ColabNotebooks/DataForReputation')
SUPPORTED_SOURCES = ('gdelt', 'google_trends', 'youtube', 'sec_edgar', 'yahoo_finance')


@dataclass(frozen=True)
class ExtractionConfig:
    ticker: str
    start_date: str
    end_date: str
    sources: tuple[str, ...] = SUPPORTED_SOURCES
    output_root: Path = DEFAULT_OUTPUT_ROOT
    company_name_override: str | None = None

    # GDELT
    gdelt_aliases: tuple[str, ...] = ()
    gdelt_additional_terms: tuple[str, ...] = ()
    gdelt_source_country: str | None = None
    gdelt_source_language: str | None = None
    gdelt_include_ticker: bool = False
    gdelt_window_days: int = 1
    gdelt_max_records: int = 250
    gdelt_request_delay_seconds: float = 60.0

    # Google Trends
    trends_search_term: str | None = None
    trends_geo: str = 'US'             # '' for worldwide
    trends_max_retries: int = 3

    # YouTube credentials are supplied at runtime, NEVER written to manifest
    youtube_api_key: str | None = None
    youtube_search_query: str | None = None
    youtube_max_videos: int = 100
    youtube_max_comment_pages_per_video: int | None = 10  # None removes cap
    youtube_include_comment_text: bool = False  # explicit opt-in for raw text
    youtube_include_author_fields: bool = False

    # SEC EDGAR requires a descriptive user agent with real contact address
    sec_user_agent: str | None = None
    sec_forms: tuple[str, ...] = (
        '8-K', '8-K/A', '10-K', '10-K/A', '10-Q', '10-Q/A',
        'DEF 14A', 'S-1', 'S-1/A', 'SC 13D', 'SC 13D/A',
        'SC 13G', 'SC 13G/A',
    )
    sec_request_delay_seconds: float = 0.2

    # Research artifact save options
    save_parquet: bool = True

    def __post_init__(self):
        ticker = self.ticker.strip().upper()
        if not ticker or not all(c.isalnum() or c in '.-^' for c in ticker):
            raise ValueError('Ticker must contain letters/digits, period, dash or caret')
        object.__setattr__(self, 'ticker', ticker)
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except (ValueError, TypeError) as exc:
            raise ValueError('Dates must be valid YYYY-MM-DD strings') from exc
        if start > end:
            raise ValueError('start_date cannot be later than end_date')
        if not self.sources or len(set(self.sources)) != len(self.sources):
            raise ValueError('Select distinct source names (at least one)')
        unknown = set(self.sources) - set(SUPPORTED_SOURCES)
        if unknown:
            raise ValueError(f'Unknown sources: {sorted(unknown)}')
        if not 1 <= self.gdelt_max_records <= 250 or self.gdelt_window_days < 1:
            raise ValueError('GDELT records must be 1–250 and window_days >= 1')
        if self.gdelt_request_delay_seconds < 0 or self.sec_request_delay_seconds < 0:
            raise ValueError('Request delays cannot be negative')
        if self.trends_max_retries < 1 or self.youtube_max_videos < 1:
            raise ValueError('Trend retries and YouTube max videos must be positive')
        if self.youtube_max_comment_pages_per_video is not None and self.youtube_max_comment_pages_per_video < 1:
            raise ValueError('youtube_max_comment_pages_per_video must be >= 1 or None')
        object.__setattr__(self, 'output_root', Path(self.output_root))
