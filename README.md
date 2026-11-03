# Corporate Reputation Dissertation — Python Extraction Framework (v2)

**Five modules, one control notebook, one Drive mount, one company/date configuration.**

This framework adapts the attached `GDELTData.ipynb`, `GoogleTrends.ipynb`, `YouTubeData.ipynb`, `SecEdgarData.ipynb`, and `YahooFinanceDataforTicker.ipynb`, along with the earlier ETL starter and `SyncWithGithub.ipynb`. It is a modular rewrite of their data extraction functions, **not a byte-for-byte conversion**. Source notebooks were **not** copied into this distribution because the uploaded YouTube notebook contains API-key-like strings in Markdown cells. Rotate those keys immediately if still valid.

## Quick start in Google Colab

1. Unzip the archive. Copy the contents of `Reputation_Python_Framework_v2/` into Google Drive at **`MyDrive/ColabNotebooks/DataForReputation/`** (merge carefully; do not delete earlier datasets).
2. In Google Drive, open **`notebooks/00_Run_All_Extractors.ipynb`** using Colab.
3. Run the **Mount Drive** and **Install packages** cells in order. Mount happens **once**, in this main notebook.
4. In Colab's left sidebar, open the **Secrets** tab (key icon) and enter **`YOUTUBE_API_KEY`** (your current, rotated key). Allow notebook access. Also enter **`SEC_USER_AGENT`**, e.g. `Research Name your-real-email@example.edu`; it must be an actual identity/contact, not the example string. You do **not** enter secrets directly into a notebook or Python file.
5. Edit the central configuration: `TICKER`, `START_DATE`, `END_DATE`, `COMPANY_NAME_OVERRIDE`, and `SOURCES`. Example `SOURCES = ('gdelt','google_trends','youtube','sec_edgar','yahoo_finance')`.
6. Run the extraction cell. Inspect `run_summary.csv`, `manifest.json`, `gdelt_request_log.csv`, `sec_edgar_historical_file_log.csv`, and `youtube_comment_request_log.csv` as relevant. A source failure does not stop the others.

If you lack a YouTube key or SEC User-Agent, remove those source names temporarily, or accept a failed status for that source and rerun once configured.

### Central settings

```python
config = ExtractionConfig(
    ticker='AAPL', start_date='2026-10-01', end_date='2026-10-07',
    sources=('gdelt', 'google_trends', 'youtube', 'sec_edgar', 'yahoo_finance'),
    output_root=PROJECT_ROOT,
    company_name_override='Apple Inc.',
    gdelt_aliases=('Apple',),
    gdelt_window_days=1,
    trends_geo='US',
    youtube_api_key=get_secret('YOUTUBE_API_KEY'),
    sec_user_agent=get_secret('SEC_USER_AGENT'),
)
summary, folder = run_pipeline(config)
```

The dates are **inclusive** throughout. `yfinance` receives the next day as its exclusive end bound. No data module mounts Drive, performs `input()`, or saves to fixed paths. `run_pipeline` is responsible for output directories.

## Folder organization

```text
DataForReputation/
├── notebooks/
│   ├── 00_Run_All_Extractors.ipynb       # one run of all chosen sources
│   └── 02_Sync_Code_to_GitHub.ipynb      # separate code-only GitHub publish
├── reputation_etl/
│   ├── __init__.py
│   ├── config.py                        # central parameters + validation
│   ├── company.py                       # one ticker -> name resolution
│   ├── pipeline.py                      # coordination, logging, outputs
│   ├── gdelt.py
│   ├── google_trends.py
│   ├── youtube.py
│   ├── sec_edgar.py
│   └── yahoo_finance.py
├── tools/
│   ├── notebook_to_py.py                # educational, manual-review converter
│   └── sync_code_to_github.py           # code-only publisher
├── tests/
├── docs/
├── README.md
├── requirements.txt
├── .gitignore
└── runs/                               # created automatically, NEVER to GitHub
    └── AAPL/2026-10-01_to_2026-10-07/<run-id>/
        ├── gdelt.csv                  # if source selected
        ├── google_trends.csv
        ├── youtube.csv
        ├── youtube_videos.csv
        ├── sec_edgar.csv
        ├── yahoo_finance.csv
        ├── *_request_log.csv
        ├── run_summary.csv
        └── manifest.json
```

Data are stored in date/ticker/run-specific folders. Source CSVs may have corresponding `.parquet` files. `manifest.json` records configured parameters (with sensitive fields masked), source statuses, file checksums, output counts, and timestamps. No automatic hourly merge is performed; this is **Data Acquisition Layer 1**.

## `.ipynb` versus `.py` and conversion

- **`.ipynb`** is an interactive *control notebook*: Drive setup, selected parameters, execution, review of output. Save to Drive; optionally publish sanitized notebooks on GitHub.
- **`.py`** is a reusable Python *module*: importable functions, not a sequence of interactive cells.
- Your original notebooks each mixed install/mount/input/query/export in one file. To convert them safely, I **refactored** their functions into `reputation_etl/*.py`, moved input to the control notebook, and moved saving and status recording to `pipeline.py`. See `docs/CONVERSION_MAP.md` for exact mapping.
- For a new notebook, optional inspection tool: `python tools/notebook_to_py.py old.ipynb draft.py`. It comments out Colab/magic cells. **This is not automatic production-ready conversion**; remove global execution, secrets, Drive mount and prompts manually before importing.

## Working with GitHub

Colab is where you run code, Drive holds working datasets, and GitHub tracks reproducible research code. Do **not** mirror the entire `DataForReputation` folder. To sync:

1. Create GitHub repository (e.g., `corporate-reputation-early-warning`).
2. Store a limited-scope token in Colab Secrets as `GITHUB_TOKEN`, with notebook access enabled. **Never** type tokens into notebooks. Rotate any previously exposed tokens.
3. Open `notebooks/02_Sync_Code_to_GitHub.ipynb` in Colab; mount Drive and review exactly which files it would publish.
4. Enter `GITHUB_REPO='YOUR_USERNAME/YOUR_REPO'`. Run with `DRY_RUN=True` to preview. `dry_run` still clones remote code for comparison; it does **not** push.
5. Resolve reported conflicts before pushing. For a first push into a repo with existing target files, you may choose `ALLOW_INITIAL_OVERWRITE=True` **after reviewing the preview**. Subsequent edits made independently in GitHub will be treated as conflicts, based on the last successfully published file hashes.
6. Set `DRY_RUN=False` and rerun to commit selected code files. The publisher excludes `runs/`, data, `.csv`, original unreviewed notebooks, and credentials. It runs a basic secret scan; it is **not** a guarantee that all possible sensitive data are identified. Review every change.

GitHub push protection may reject commits containing exposed tokens, even after they are deleted from the latest file. You may need to revoke the credentials and clean the affected Git history separately. **Do not bypass push protection.**

## Research-methodology warnings

- **GDELT:** DOC ArticleList has a per-request 250-record cap and limited historical access; use smaller windows or GDELT bulk/BigQuery for historical events. Flag failures and saturated windows.
- **Google Trends:** `pytrends` is unofficial/archived, data are query-normalized and not guaranteed hourly. Do not compare independent runs' indexes as absolute counts.
- **YouTube:** video selection is based on *video publish date*; top-level comments are then filtered by *comment publish date*. Replies and comments on older videos are excluded. Page limits, quotas, disabled comments, and search relevance may bias results. **Default stores no raw comment text or author identifiers**; enable `youtube_include_comment_text=True` only when compliant with applicable terms, approvals, and a documented retention/deletion procedure. Counts and comment lengths are still captured. Revisit source-selection design for your dissertation's longitudinal research. YouTube may need renewed authorization before broad collection.
- **SEC EDGAR:** retrieves recent and overlapping historical filing indexes. Only chosen forms are included. Form date and acceptance time are *disclosure evidence*, not verified reputational-event time or labels. SEC requires a genuine descriptive User-Agent; respect request limits.
- **Yahoo Finance:** daily prices, end date is handled inclusively, includes return/range/rolling volatility features. Data are **not** 6–24-hour predictors by themselves and should not be used as crisis labels. The first 30 trading days lack rolling estimates without pre-window history. Check licensing and an institutional alternative for publication-grade research.
- **No temporal leakage:** preserve native timestamps and evidence provenance, then create leakage-safe hourly features in a **separate feature-engineering stage**. This framework does not perform that stage or validate the outcome labels.

## Testing

Offline smoke tests run without live APIs:

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
```

A passing offline test **does not** establish live YouTube/SEC/GDELT/Trends/Yahoo availability. Start with a small date range and check status logs; API quotas and credentials apply.
