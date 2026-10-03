"""
What a UI test run touched: the API requests the page sent and the pages the browser was on.

A RunTrace is filled during a run (collect() after every step) and saved once at its end. It must
never fail a run: everything here swallows its own errors and logs them.

The requests come from Chrome's performance log (BrowserAutomation.drain_network_log); the pages
from the address of the browser after each step. See migrations/20261003_run_traces.sql.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)

MAX_CALLS_PER_RUN = 500
MAX_PAGES_PER_RUN = 200

_ID_SEGMENT = re.compile(
    r'^(\d+'                                                              # 42
    r'|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'  # a UUID
    r'|[0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{26}'                               # a ULID
    r'|[0-9a-fA-F]{16,}'                                                  # a long hex id
    r'|(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{20,})$')  # a long mixed token


def page_of(url: str) -> Optional[str]:
    """
    The page of the application an address belongs to: host and path, ids replaced by {id}, no
    query. A hash route ("#/cart") is part of the page; a plain anchor ("#top") is not.
    None for an address that is not a page (about:blank, data:).
    """
    parts = urlsplit(url or '')
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        return None
    path = '/'.join('{id}' if _ID_SEGMENT.match(segment) else segment for segment in parts.path.split('/'))
    page = f"{parts.netloc}{path.rstrip('/') or '/'}"
    if parts.fragment.startswith('/') or parts.fragment.startswith('!/'):
        route = '/'.join('{id}' if _ID_SEGMENT.match(segment) else segment
                         for segment in parts.fragment.split('?')[0].split('/'))
        page += f"#{route}"
    return page


class RunTrace:
    def __init__(self):
        self.calls: Dict[Tuple[str, str, Optional[int]], int] = {}
        self.pages: List[Tuple[int, str, str]] = []  # step order, address, page

    def collect(self, browser, step_order: int):
        """Take what the browser did since the last call: its requests and the page it is on now."""
        try:
            for method, url, status in browser.drain_network_log():
                key = (method, url.split('?')[0].split('#')[0], status)
                if key in self.calls or len(self.calls) < MAX_CALLS_PER_RUN:
                    self.calls[key] = self.calls.get(key, 0) + 1
        except Exception as e:
            logger.debug(f"Run trace: requests not collected: {e}")
        try:
            url = browser.driver.current_url
            page = page_of(url)
            if page and (not self.pages or self.pages[-1][2] != page) and len(self.pages) < MAX_PAGES_PER_RUN:
                self.pages.append((step_order, url[:2000], page))
        except Exception as e:  # a native alert is open, the session is gone
            logger.debug(f"Run trace: page not collected: {e}")

    def save(self, test_run_id: int, test_case_id: int):
        if not self.calls and not self.pages:
            return
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    for (method, url, status), hits in self.calls.items():
                        cursor.execute("""
                            INSERT INTO test_run_api_calls (test_run_id, test_case_id, method, url, status, hits)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (test_run_id, test_case_id, method[:10], url[:2000], status, hits))
                    for step_order, url, page in self.pages:
                        cursor.execute("""
                            INSERT INTO test_run_pages (test_run_id, test_case_id, step_order, url, page)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (test_run_id, test_case_id, step_order, url, page))
                    conn.commit()
            logger.info(f"Run trace of run {test_run_id}: {len(self.calls)} requests, {len(self.pages)} pages")
        except Exception as e:
            logger.error(f"Run trace of run {test_run_id} not saved: {e}")
