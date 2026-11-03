"""Offline tests with fake response objects; NO live API calls."""
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from reputation_etl import ExtractionConfig, run_pipeline
from reputation_etl.gdelt import build_company_query, create_date_windows
from reputation_etl.yahoo_finance import download_stock_dataset
from reputation_etl.sec_edgar import filter_filings_by_date, create_sec_event_dataset, get_filings
from reputation_etl.youtube import extract_video_comments, search_youtube_videos
from reputation_etl.pipeline import SourceResult
from tools.notebook_to_py import convert_notebook
from tools.sync_code_to_github import audit_code_files


def config(tmp_path, **kwargs):
    return ExtractionConfig(ticker='AAPL', start_date='2026-10-01',
                            end_date='2026-10-07', output_root=tmp_path, **kwargs)


def test_config_dates_and_bad_source(tmp_path):
    with pytest.raises(ValueError):
        ExtractionConfig('AAPL', '2026-10-08', '2026-10-07', output_root=tmp_path)
    with pytest.raises(ValueError):
        config(tmp_path, sources=('invalid',))
    assert config(tmp_path, sources=('gdelt',)).ticker == 'AAPL'


def test_gdelt_query_windows():
    q = build_company_query('AAPL', 'Apple Inc.', aliases=['Apple'], include_ticker=False)
    assert 'Apple' in q and '"AAPL"' not in q
    w = create_date_windows('2026-10-01', '2026-10-03', window_days=1)
    assert len(w) == 3
    assert w[-1][1].strftime('%Y-%m-%d %H:%M:%S') == '2026-10-03 23:59:59'


def test_yahoo_inclusive_end_date(monkeypatch):
    import sys
    dates = pd.to_datetime(['2026-10-01', '2026-10-02'])
    fake = pd.DataFrame({'Open': [10,11], 'High': [12,13], 'Low': [9,10],
                         'Close': [11,12], 'Volume': [100,200]}, index=dates)
    fake.index.name='Date'
    download = Mock(return_value=fake)
    module = SimpleNamespace(download=download, Ticker=lambda t: SimpleNamespace(info={'longName': 'Apple Inc.'}))
    monkeypatch.setitem(sys.modules, 'yfinance', module)
    data, metadata = download_stock_dataset('AAPL', '2026-10-01', '2026-10-02')
    assert download.call_args.kwargs['end'] == '2026-10-03'
    assert list(data['Ticker']) == ['AAPL', 'AAPL']
    assert 'Daily_Return' in data and metadata['Company_Name']=='Apple Inc.'


def test_sec_filters_and_forms():
    df=pd.DataFrame([{'filingDate': '2026-10-01', 'form': '8-K', 'accessionNumber': '0001-02-03', 'primaryDocument': 'x.htm'},
                     {'filingDate': '2026-10-12', 'form': '10-Q', 'accessionNumber': '0003-04-05', 'primaryDocument': 'y.htm'}])
    selected=filter_filings_by_date(df, '2026-10-01', '2026-10-07')
    assert len(selected)==1
    event=create_sec_event_dataset(selected, 'AAPL', 'Apple Inc.', '0000320193')
    assert 'https://www.sec.gov/Archives/edgar/data/320193/00010203/x.htm' in event['filing_url'].iloc[0]


def test_sec_historical_files(monkeypatch):
    import reputation_etl.sec_edgar as sec
    called=[]
    def fake_get(url, ua, delay):
        called.append(url)
        if url.endswith('CIK0000320193.json'):
            return {'name': 'Apple Inc.', 'filings': {'recent': {
                    'filingDate':['2026-10-02'], 'accessionNumber':['1'], 'form':['8-K']},
                    'files':[{'name':'CIK0000320193-submissions-001.json', 'filingFrom':'2025-01-01', 'filingTo':'2026-10-07'},
                             {'name':'older.json','filingFrom':'2020-01-01','filingTo':'2021-01-01'}]}}
        return {'filingDate':['2026-10-01'], 'accessionNumber':['2'], 'form':['10-K']}
    monkeypatch.setattr(sec,'sec_get_json',fake_get)
    records,meta=get_filings('0000320193','2026-10-01','2026-10-07','research name contact@university.edu')
    assert len(records)==2 and len(called)==2
    assert meta['historical_file_failures']==0


class VideosClient:
    def __init__(self):
        self.requests=[]
    def search(self): return self
    def list(self,**kwargs): self.requests.append(kwargs); return self
    def execute(self): return {'items': [{'id': {'videoId':'abc'}, 'snippet': {'title':'Apple', 'publishedAt':'2026-10-01T10:00:00Z'}}]}


def test_youtube_video_search_dates():
    client=VideosClient()
    videos, truncated=search_youtube_videos(client,'"Apple" AAPL',pd.Timestamp('2026-10-01',tz='UTC'),pd.Timestamp('2026-10-08',tz='UTC'),max_videos=5)
    assert videos.iloc[0]['video_id']=='abc' and not truncated
    assert client.requests[0]['publishedBefore']=='2026-10-08T00:00:00Z'


class CommentClient:
    def commentThreads(self): return self
    def list(self,**kwargs): return self
    def execute(self):
        return {'items': [{'id':'thread1', 'snippet': {
            'totalReplyCount':2, 'topLevelComment': {'id':'comment1', 'snippet': {
                'publishedAt':'2026-10-02T10:00:00Z', 'textDisplay':'hello Apple',
                'likeCount':3,'authorDisplayName':'User','authorChannelId':{'value':'author1'}}}}}]}


def test_youtube_hides_pii_by_default(monkeypatch):
    import sys, types
    errors_module = types.ModuleType('googleapiclient.errors')
    errors_module.HttpError = type('HttpError', (Exception,), {})
    parent_module = types.ModuleType('googleapiclient')
    monkeypatch.setitem(sys.modules, 'googleapiclient', parent_module)
    monkeypatch.setitem(sys.modules, 'googleapiclient.errors', errors_module)
    result, log=extract_video_comments(CommentClient(),{'video_id':'abc'},'Apple Inc.','AAPL',
                                     pd.Timestamp('2026-10-01',tz='UTC'),pd.Timestamp('2026-10-08',tz='UTC'),'Apple', 10,False,False)
    assert len(result)==1
    assert result[0]['comment_text'] is None and result[0]['author_display_name'] is None
    assert result[0]['comment_engagement']==5 and result[0]['comment_length']==11
    assert log['pages_fetched']==1


def test_pipeline_independent_sources_and_manifest(tmp_path, monkeypatch):
    import reputation_etl.pipeline as p
    monkeypatch.setattr(p, 'resolve_company', lambda ticker, override: {'ticker':ticker,'company_name':'Apple Inc.'})
    good = lambda c, company: SourceResult(pd.DataFrame([{'date':'2026-10-01','value':1}]),
                 notes=['test note'], metadata={'coverage':'sample'})
    def bad(c, company): raise RuntimeError('simulated failure')
    monkeypatch.setitem(p.RUNNERS, 'gdelt', good)
    monkeypatch.setitem(p.RUNNERS, 'google_trends', bad)
    c=config(tmp_path, sources=('gdelt','google_trends'),youtube_api_key='dummy-key',sec_user_agent='Research contact@university.edu',save_parquet=False)
    summary, folder=run_pipeline(c)
    assert list(summary['status']) == ['success','failed']
    assert (folder/'gdelt.csv').exists()
    manifest=json.loads((folder/'manifest.json').read_text())
    text=(folder/'manifest.json').read_text()
    assert 'dummy-key' not in text and 'contact@university.edu' not in text
    assert manifest['sources']['gdelt']['files']['data']['csv_sha256']
    assert manifest['sources']['google_trends']['error'].endswith('simulated failure')


def test_notebook_converter_comments_magics(tmp_path):
    source=tmp_path/'source.ipynb';out=tmp_path/'draft.py'
    source.write_text(json.dumps({'cells':[{'cell_type':'code','source':['!pip install xyz']},
                                          {'cell_type':'code','source':['def fn():\n','    return 1']}] }))
    convert_notebook(source,out)
    assert '# !pip install xyz' in out.read_text() and 'def fn():' in out.read_text()


def test_sync_audit_rejects_keys(tmp_path):
    (tmp_path/'reputation_etl').mkdir()
    p=tmp_path/'reputation_etl'/'test.py'
    p.write_text('token = "AIza'+'A'*35+'"')
    with pytest.raises(ValueError, match='potential embedded credential'):
        audit_code_files(tmp_path)
    p.write_text('def f(): return 42')
    assert p in audit_code_files(tmp_path)
