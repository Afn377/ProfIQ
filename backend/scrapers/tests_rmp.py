import unittest
from unittest.mock import patch

from scrapers.rmp import teacher_gid_from_legacy


class TeacherGidTests(unittest.TestCase):
    def test_encodes_known_id(self):
        # base64("Teacher-12345")
        self.assertEqual(teacher_gid_from_legacy(12345), "VGVhY2hlci0xMjM0NQ==")

    def test_accepts_string_ids(self):
        self.assertEqual(teacher_gid_from_legacy("12345"), teacher_gid_from_legacy(12345))

    def test_different_ids_give_different_gids(self):
        self.assertNotEqual(teacher_gid_from_legacy(1), teacher_gid_from_legacy(2))


class ThrottleTests(unittest.TestCase):
    def test_first_call_does_not_sleep(self):
        from scrapers.base import Throttle
        with patch("scrapers.base.time.sleep") as sleep:
            Throttle(1.0).wait()
        sleep.assert_not_called()

    def test_second_call_sleeps_for_the_remaining_gap(self):
        from scrapers.base import Throttle
        # Pretend 0.3s passed between the two calls; a 1.0s throttle must sleep 0.7s.
        with patch("scrapers.base.time.monotonic", side_effect=[100.0, 100.3, 100.3]), \
             patch("scrapers.base.time.sleep") as sleep:
            t = Throttle(1.0)
            t.wait()
            t.wait()
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args[0][0], 0.7)

    def test_no_sleep_if_gap_already_elapsed(self):
        from scrapers.base import Throttle
        with patch("scrapers.base.time.monotonic", side_effect=[100.0, 105.0, 105.0]), \
             patch("scrapers.base.time.sleep") as sleep:
            t = Throttle(1.0)
            t.wait()
            t.wait()
        sleep.assert_not_called()


def _resp(status, payload=None):
    """A fake requests.Response with just what the client reads."""
    from unittest.mock import MagicMock
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    if status >= 400:
        import requests
        r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    else:
        r.raise_for_status.return_value = None
    return r


class RMPClientRetryTests(unittest.TestCase):
    def test_retries_transient_503_then_succeeds(self):
        from scrapers.rmp import RMPClient
        responses = [_resp(503), _resp(503), _resp(200, {"data": {"ok": 1}})]
        with patch("scrapers.rmp.requests.Session.post", side_effect=responses), \
             patch("time.sleep"):
            client = RMPClient(throttle_seconds=0)
            self.assertEqual(client._post("q", {}), {"ok": 1})

    def test_does_not_retry_404(self):
        from scrapers.rmp import RMPClient
        import requests
        post = patch("scrapers.rmp.requests.Session.post", side_effect=[_resp(404)]).start()
        self.addCleanup(patch.stopall)
        patch("scrapers.base.time.sleep").start()
        client = RMPClient(throttle_seconds=0)
        with self.assertRaises(requests.HTTPError):
            client._post("q", {})
        self.assertEqual(post.call_count, 1)

    def test_backoff_doubles_each_retry(self):
        from scrapers.rmp import RMPClient
        responses = [_resp(503), _resp(503), _resp(503), _resp(200, {"data": {}})]
        with patch("scrapers.rmp.requests.Session.post", side_effect=responses), \
             patch("time.sleep") as sleep:
            RMPClient(throttle_seconds=0)._post("q", {})
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.5, 1.0, 2.0])

    def test_gives_up_after_max_retries(self):
        from scrapers.rmp import RMPClient
        import requests
        responses = [_resp(503)] * 5
        with patch("scrapers.rmp.requests.Session.post", side_effect=responses) as post, \
             patch("time.sleep"):
            with self.assertRaises(requests.HTTPError):
                RMPClient(throttle_seconds=0, max_retries=4)._post("q", {})
        self.assertEqual(post.call_count, 5)


class IterRatingsTests(unittest.TestCase):
    def _page(self, ids, has_next, cursor):
        return {"node": {"ratings": {
            "edges": [{"node": {"legacyId": i, "comment": f"review {i}"}} for i in ids],
            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        }}}

    def test_follows_cursor_across_pages(self):
        from scrapers.rmp import RMPClient
        pages = [self._page([1, 2], True, "c1"), self._page([3], False, None)]
        with patch.object(RMPClient, "_post", side_effect=pages) as post:
            got = [r["legacyId"] for r in RMPClient().iter_ratings("gid")]
        self.assertEqual(got, [1, 2, 3])
        # second call must carry the cursor from the first page
        self.assertEqual(post.call_args_list[1].args[1]["cursor"], "c1")

    def test_max_reviews_stops_early(self):
        from scrapers.rmp import RMPClient
        pages = [self._page([1, 2, 3], True, "c1")]
        with patch.object(RMPClient, "_post", side_effect=pages):
            got = list(RMPClient().iter_ratings("gid", max_reviews=2))
        self.assertEqual(len(got), 2)
