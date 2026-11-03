"""YouTube top-level comment extraction adapted from user's YouTubeData notebook.

Search video publication dates first, THEN filter comments by their timestamps.
This does not capture comments on older videos. Data API quotas, pagination,
public-content availability and platform retention rules apply.
"""
from datetime import datetime, timedelta, timezone
import pandas as pd

VIDEO_COLUMNS = ['video_id', 'video_title', 'video_description',
                 'video_published_at', 'channel_id', 'channel_title',
                 'view_count', 'like_count', 'video_comment_count']
COMMENT_COLUMNS = [
    'company', 'ticker', 'date', 'video_id', 'video_url', 'video_title',
    'channel_title', 'video_published_at', 'video_view_count', 'video_like_count',
    'video_comment_count', 'comment_thread_id', 'comment_id',
    'comment_published_at', 'comment_updated_at', 'comment_text',
    'comment_like_count', 'reply_count', 'comment_engagement', 'comment_length',
    'author_display_name', 'author_channel_id', 'search_query',
    'research_start_date', 'research_end_date', 'extraction_timestamp_utc',
]


def search_youtube_videos(client, query: str, start_dt: pd.Timestamp,
                          end_exclusive: pd.Timestamp, max_videos: int = 100):
    videos, page_token = [], None
    while len(videos) < max_videos:
        response = client.search().list(
            part='snippet', q=query, type='video', order='date',
            publishedAfter=start_dt.isoformat().replace('+00:00', 'Z'),
            publishedBefore=end_exclusive.isoformat().replace('+00:00', 'Z'),
            maxResults=min(50, max_videos-len(videos)),
            pageToken=page_token,
        ).execute()
        for item in response.get('items', []):
            snippet = item.get('snippet', {})
            vid = item.get('id', {}).get('videoId')
            if not vid:
                continue
            videos.append({'video_id': vid, 'video_title': snippet.get('title'),
                           'video_description': snippet.get('description'),
                           'video_published_at': snippet.get('publishedAt'),
                           'channel_id': snippet.get('channelId'),
                           'channel_title': snippet.get('channelTitle')})
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return pd.DataFrame(videos).reindex(columns=VIDEO_COLUMNS[:6]), bool(page_token)


def get_video_statistics(client, video_ids: list[str]) -> pd.DataFrame:
    rows = []
    for offset in range(0, len(video_ids), 50):
        result = client.videos().list(part='statistics', id=','.join(video_ids[offset:offset+50])).execute()
        for item in result.get('items', []):
            stats = item.get('statistics', {})
            rows.append({'video_id': item.get('id'),
                         'view_count': int(stats.get('viewCount', 0)),
                         'like_count': int(stats.get('likeCount', 0)),
                         'video_comment_count': int(stats.get('commentCount', 0))})
    return pd.DataFrame(rows, columns=VIDEO_COLUMNS[6:] + ['video_id'])


def extract_video_comments(client, video: dict, company: str, ticker: str,
                           start_dt: pd.Timestamp, end_exclusive: pd.Timestamp,
                           query: str, max_pages: int | None = 10,
                           include_text: bool = False,
                           include_author_fields: bool = False):
    from googleapiclient.errors import HttpError

    rows, token, pages = [], None, 0
    truncated, unavailable = False, None
    while True:
        try:
            response = client.commentThreads().list(
                part='snippet', videoId=video['video_id'], maxResults=100,
                order='time', textFormat='plainText', pageToken=token,
            ).execute()
        except HttpError as exc:
            status = getattr(exc.resp, 'status', None)
            content = str(exc).lower()
            # quota or authentication errors must fail the whole source; silently
            # marking them "comments disabled" would bias research results.
            if status in (429, 500, 502, 503, 504) or 'quota' in content or 'rate limit' in content:
                raise
            # A disabled-comment or removed-video response is a meaningful
            # per-video gap. Other 400/403 errors may indicate API access
            # problems; fail the source rather than hide them.
            disabled = ('commentsdisabled' in content or 'comments are disabled' in content)
            inaccessible = status == 404 or 'videonotfound' in content
            if disabled or inaccessible:
                unavailable = f'HTTP {status}: disabled comments or inaccessible video'
                break
            raise
        pages += 1
        for item in response.get('items', []):
            snippet = item.get('snippet', {}).get('topLevelComment', {}).get('snippet', {})
            when = pd.to_datetime(snippet.get('publishedAt'), errors='coerce', utc=True)
            if pd.isna(when) or not (start_dt <= when < end_exclusive):
                continue
            text = str(snippet.get('textDisplay') or '').strip()
            if not text:
                continue
            author_id = (snippet.get('authorChannelId') or {}).get('value')
            likes = int(snippet.get('likeCount', 0))
            replies = int(item.get('snippet', {}).get('totalReplyCount', 0))
            row = {
                'company': company, 'ticker': ticker, 'date': str(when.date()),
                'video_id': video['video_id'],
                'video_url': 'https://www.youtube.com/watch?v=' + video['video_id'],
                'video_title': video.get('video_title'), 'channel_title': video.get('channel_title'),
                'video_published_at': video.get('video_published_at'),
                'video_view_count': video.get('view_count'),
                'video_like_count': video.get('like_count'),
                'video_comment_count': video.get('video_comment_count'),
                'comment_thread_id': item.get('id'),
                'comment_id': item.get('snippet', {}).get('topLevelComment', {}).get('id'),
                'comment_published_at': when,
                'comment_updated_at': snippet.get('updatedAt'),
                'comment_text': text if include_text else None,
                'comment_like_count': likes, 'reply_count': replies,
                'comment_engagement': likes + replies, 'comment_length': len(text),
                'author_display_name': snippet.get('authorDisplayName') if include_author_fields else None,
                'author_channel_id': author_id if include_author_fields else None,
                'search_query': query,
            }
            rows.append(row)
        token = response.get('nextPageToken')
        if not token:
            break
        if max_pages is not None and pages >= max_pages:
            truncated = True
            break
    return rows, {'video_id': video['video_id'], 'pages_fetched': pages,
                  'comments_collected': len(rows), 'page_limit_reached': truncated,
                  'unavailable_reason': unavailable or ''}


def extract_youtube_dataset(*, ticker: str, company_name: str, start_date: str,
                            end_date: str, api_key: str, search_query: str | None = None,
                            max_videos: int = 100, max_comment_pages_per_video: int | None = 10,
                            include_comment_text: bool = False,
                            include_author_fields: bool = False):
    from googleapiclient.discovery import build

    if not api_key:
        raise ValueError('Missing YouTube API key; add YOUTUBE_API_KEY to Colab Secrets')
    start = pd.Timestamp(start_date, tz='UTC')
    end_exclusive = pd.Timestamp(end_date, tz='UTC') + pd.Timedelta(days=1)
    query = search_query or f'"{company_name}" {ticker}'
    client = build('youtube', 'v3', developerKey=api_key, cache_discovery=False)
    videos, search_truncated = search_youtube_videos(client, query, start, end_exclusive, max_videos)
    if not videos.empty:
        stats = get_video_statistics(client, videos['video_id'].tolist())
        videos = videos.merge(stats, how='left', on='video_id', validate='one_to_one')
    videos = videos.reindex(columns=VIDEO_COLUMNS)
    all_comments, logs = [], []
    for video in videos.to_dict('records'):
        rows, info = extract_video_comments(
            client, video, company_name, ticker, start, end_exclusive, query,
            max_pages=max_comment_pages_per_video,
            include_text=include_comment_text, include_author_fields=include_author_fields,
        )
        all_comments.extend(rows)
        logs.append(info)
    comments = pd.DataFrame(all_comments, columns=COMMENT_COLUMNS)
    if not comments.empty:
        comments['research_start_date'] = start_date
        comments['research_end_date'] = end_date
        comments['extraction_timestamp_utc'] = datetime.now(timezone.utc).isoformat()
        comments = comments.drop_duplicates(subset=['comment_id']).reset_index(drop=True)
    logs_df = pd.DataFrame(logs, columns=['video_id', 'pages_fetched', 'comments_collected',
                                          'page_limit_reached', 'unavailable_reason'])
    meta = {'search_query': query, 'max_videos': max_videos,
            'video_selection_reached_cap': search_truncated,
            'comment_pages_truncated': int(logs_df.get('page_limit_reached', pd.Series(dtype=bool)).sum()),
            'videos_with_unavailable_comments': int(logs_df.get('unavailable_reason', pd.Series(dtype=str)).fillna('').ne('').sum()),
            'include_comment_text': include_comment_text,
            'include_author_fields': include_author_fields,
            'raw_text_policy_notice': 'Review YouTube API terms; limit retention and access to comment text/identifiers.'}
    return comments, videos, logs_df, meta
