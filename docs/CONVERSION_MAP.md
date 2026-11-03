# Source notebook to `.py` conversion map

| Uploaded notebook | Reusable functions preserved/adapted | New module | Centralized / changed functionality |
|---|---|---|---|
| `GDELTData.ipynb` / earlier `GDELTData (1).ipynb` | `build_company_query`, date windows, retries, article extraction | `reputation_etl/gdelt.py` | Company lookup once, API cap/failure log, CSV/Parquet saving in pipeline |
| `GoogleTrends.ipynb` | `get_google_trends` | `reputation_etl/google_trends.py` | Removes unmount/remount + directory deletion, shares parameters and filenames |
| `YouTubeData.ipynb` | `search_youtube_videos`, `get_video_statistics`, `extract_video_comments` | `reputation_etl/youtube.py` | Secrets not embedded, video and page logs, comment text/author opt-in, no source-level Drive mount |
| `SecEdgarData.ipynb` | `sec_get_json`, `get_company_cik`, filtering, event/disclosure table | `reputation_etl/sec_edgar.py` | SEC User-Agent from Colab Secrets; fetches historical index chunks as well as recent |
| `YahooFinanceDataforTicker.ipynb` | `download_stock_dataset`, daily returns/ranges/volatility, company metadata | `reputation_etl/yahoo_finance.py` | Fixes end-date exclusivity; output CSV/Parquet and metadata tables centrally |
| `SyncWithGithub.ipynb` | Git clone, staging, commit, push and preflight size checks | `tools/sync_code_to_github.py` plus `notebooks/02_Sync_Code_to_GitHub.ipynb` | Selective code-only publishing, dry run, secret scanning, remote conflict checks |
| Earlier `00_Run_All_Extractors.ipynb` | Shared config and run orchestration | `reputation_etl/config.py`, `pipeline.py` + updated notebook | All five data sources available, one Drive mount, per-source status logs |

**Not a literal notebook-to-script export:** Colab commands (`!pip`, `drive.mount`, `input`, `display`, downloads, ad hoc tests) are deliberately not included inside reusable extraction modules. They are part of the notebook or omitted where no longer needed.

**Security handling:** Uploaded `YouTubeData.ipynb` contains hard-coded API-key-like values in markdown, so source notebooks are not redistributed in this ZIP. The SEC User-Agent is moved to runtime configuration rather than hard-coded. Rotate/revoke leaked credentials and check previously pushed Git history.
