import time
from collections import defaultdict

_search_log: dict[int, list[float]] = defaultdict(list)
_download_log: dict[int, list[float]] = defaultdict(list)

SEARCH_LIMIT = 4
SEARCH_WINDOW = 10.0

DOWNLOAD_LIMIT = 2
DOWNLOAD_WINDOW = 30.0


def _check(log: dict, user_id: int, limit: int, window: float) -> tuple[bool, int]:
    now = time.time()
    log[user_id] = [t for t in log[user_id] if now - t < window]
    if len(log[user_id]) >= limit:
        wait = int(window - (now - log[user_id][0])) + 1
        return False, wait
    log[user_id].append(now)
    return True, 0


def check_search(user_id: int) -> tuple[bool, int]:
    return _check(_search_log, user_id, SEARCH_LIMIT, SEARCH_WINDOW)


def check_download(user_id: int) -> tuple[bool, int]:
    return _check(_download_log, user_id, DOWNLOAD_LIMIT, DOWNLOAD_WINDOW)
