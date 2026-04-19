import aiohttp
import logging
from config import Config

logger = logging.getLogger(__name__)

DEEZER_CHART = "https://api.deezer.com/chart/0/tracks?limit=10"
DEEZER_SEARCH = "https://api.deezer.com/search?q={query}&limit=5"
YT_TRENDING = (
    "https://www.googleapis.com/youtube/v3/videos"
    "?part=snippet,contentDetails&chart=mostPopular"
    "&videoCategoryId=10&maxResults=10&key={key}"
)


async def _get(url: str) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error(f"HTTP GET error ({url[:60]}): {e}")
    return {}


async def get_trending_music() -> list[dict]:
    """Deezer world chart — top 10 tracks (free, no auth)."""
    data = await _get(DEEZER_CHART)
    tracks = data.get("data", [])
    result = []
    for t in tracks[:10]:
        dur = t.get("duration", 0)
        result.append({
            "title":    t.get("title", ""),
            "artist":   t.get("artist", {}).get("name", ""),
            "duration": f"{dur // 60}:{dur % 60:02d}" if dur else "–",
            "preview":  t.get("preview", ""),
            "cover":    t.get("album", {}).get("cover_medium", ""),
            "deezer_id": str(t.get("id", "")),
        })
    return result


async def get_trending_videos() -> list[dict]:
    """YouTube trending music videos (requires YOUTUBE_API_KEY)."""
    if not Config.YOUTUBE_API_KEY:
        return []
    data = await _get(YT_TRENDING.format(key=Config.YOUTUBE_API_KEY))
    items = data.get("items", [])
    result = []
    for item in items[:10]:
        snip = item.get("snippet", {})
        result.append({
            "title":     snip.get("title", ""),
            "channel":   snip.get("channelTitle", ""),
            "video_id":  item.get("id", ""),
            "thumbnail": snip.get("thumbnails", {}).get("medium", {}).get("url", ""),
        })
    return result


async def search_deezer(query: str) -> list[dict]:
    """Deezer musiqa qidirish — boyroq metadata, bepul."""
    url = DEEZER_SEARCH.format(query=query.replace(" ", "+"))
    data = await _get(url)
    result = []
    for t in data.get("data", [])[:5]:
        dur = t.get("duration", 0)
        result.append({
            "title":    t.get("title", ""),
            "artist":   t.get("artist", {}).get("name", ""),
            "album":    t.get("album", {}).get("title", ""),
            "duration": f"{dur // 60}:{dur % 60:02d}" if dur else "–",
            "preview":  t.get("preview", ""),
            "cover":    t.get("album", {}).get("cover_medium", ""),
            "deezer_id": str(t.get("id", "")),
        })
    return result
