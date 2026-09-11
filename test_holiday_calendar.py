"""
Tests for the Supplier Holiday Calendar — offline fallback, holiday
clustering, and shipping-risk-window detection.
"""

import sys
import types
import unittest

import holiday_calendar as hc


class FakeRequestException(Exception):
    pass


def install_fake_requests(get_fn):
    """Dual-patch: inject a fake `requests` module into sys.modules AND
    reassign the already-imported holiday_calendar module's own bound
    `requests` name (a sys.modules swap alone doesn't affect a name that
    was already bound by `import requests` at module load time)."""
    fake_requests = types.ModuleType("requests")
    fake_requests.get = get_fn
    fake_requests.RequestException = FakeRequestException
    sys.modules["requests"] = fake_requests
    hc.requests = fake_requests
    return fake_requests


class TestOfflineFallback(unittest.TestCase):
    def setUp(self):
        self._real_requests = hc.requests

    def tearDown(self):
        hc.requests = self._real_requests
        sys.modules["requests"] = self._real_requests

    def test_connection_failure_falls_back_to_offline_sample(self):
        def broken_get(*args, **kwargs):
            raise FakeRequestException("connection refused")

        install_fake_requests(broken_get)

        holidays, source, found = hc.get_holidays("KR", 2025)

        self.assertEqual(source, "offline sample")
        self.assertTrue(found)
        self.assertGreater(len(holidays), 0)

    def test_offline_sample_for_unknown_country_year_reports_not_found(self):
        def broken_get(*args, **kwargs):
            raise FakeRequestException("connection refused")

        install_fake_requests(broken_get)

        holidays, source, found = hc.get_holidays("ZZ", 1999)

        self.assertEqual(holidays, [])
        self.assertFalse(found)

    def test_offline_sample_has_data_for_three_different_countries(self):
        def broken_get(*args, **kwargs):
            raise FakeRequestException("connection refused")

        install_fake_requests(broken_get)

        for country in ["EG", "KR", "US"]:
            holidays, source, found = hc.get_holidays(country, 2025)
            self.assertTrue(found, f"expected offline data for {country}")
            self.assertGreater(len(holidays), 0)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeRequestException(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class TestLivePath(unittest.TestCase):
    def setUp(self):
        self._real_requests = hc.requests

    def tearDown(self):
        hc.requests = self._real_requests
        sys.modules["requests"] = self._real_requests

    def test_live_fetch_is_used_when_available(self):
        live_payload = [
            {"date": "2026-01-01", "localName": "New Year", "name": "New Year's Day"},
        ]

        def fake_get(url, timeout=5):
            self.assertIn("2026", url)
            self.assertIn("KR", url)
            return FakeResponse(live_payload)

        install_fake_requests(fake_get)

        holidays, source, found = hc.get_holidays("KR", 2026)

        self.assertEqual(source, "live")
        self.assertTrue(found)
        self.assertEqual(holidays, live_payload)


class TestClustering(unittest.TestCase):
    def test_single_holiday_is_its_own_window(self):
        holidays = [{"date": "2025-05-01", "name": "Labour Day"}]
        windows = hc.cluster_consecutive_holidays(holidays)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["length_days"], 1)

    def test_consecutive_holidays_form_one_window(self):
        holidays = [
            {"date": "2025-10-05", "name": "Chuseok Eve"},
            {"date": "2025-10-06", "name": "Chuseok"},
            {"date": "2025-10-07", "name": "Day after Chuseok"},
        ]
        windows = hc.cluster_consecutive_holidays(holidays)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["start"], "2025-10-05")
        self.assertEqual(windows[0]["end"], "2025-10-07")
        self.assertEqual(windows[0]["length_days"], 3)

    def test_holidays_far_apart_form_separate_windows(self):
        holidays = [
            {"date": "2025-01-01", "name": "New Year"},
            {"date": "2025-08-15", "name": "Liberation Day"},
        ]
        windows = hc.cluster_consecutive_holidays(holidays)
        self.assertEqual(len(windows), 2)

    def test_empty_holiday_list_produces_no_windows(self):
        self.assertEqual(hc.cluster_consecutive_holidays([]), [])

    def test_clustering_is_order_independent(self):
        holidays = [
            {"date": "2025-10-07", "name": "Day after Chuseok"},
            {"date": "2025-10-05", "name": "Chuseok Eve"},
            {"date": "2025-10-06", "name": "Chuseok"},
        ]
        windows = hc.cluster_consecutive_holidays(holidays)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["names"], ["Chuseok Eve", "Chuseok", "Day after Chuseok"])


class TestShippingRiskWindows(unittest.TestCase):
    def test_short_single_day_holiday_is_not_a_risk(self):
        supplier_holidays = [{"date": "2025-05-05", "name": "Children's Day"}]
        risk_windows = hc.find_shipping_risk_windows(supplier_holidays, [], min_window_days=2)
        self.assertEqual(risk_windows, [])

    def test_multi_day_cluster_is_flagged_as_risk(self):
        supplier_holidays = [
            {"date": "2025-10-05", "name": "Chuseok Eve"},
            {"date": "2025-10-06", "name": "Chuseok"},
            {"date": "2025-10-07", "name": "Day after Chuseok"},
        ]
        risk_windows = hc.find_shipping_risk_windows(supplier_holidays, [], min_window_days=2)
        self.assertEqual(len(risk_windows), 1)
        self.assertEqual(risk_windows[0]["length_days"], 3)

    def test_buyer_side_overlap_is_reported(self):
        supplier_holidays = [
            {"date": "2025-10-05", "name": "Chuseok Eve"},
            {"date": "2025-10-06", "name": "Chuseok"},
            {"date": "2025-10-07", "name": "Day after Chuseok"},
        ]
        buyer_holidays = [{"date": "2025-10-06", "name": "Some Overlapping Holiday"}]
        risk_windows = hc.find_shipping_risk_windows(supplier_holidays, buyer_holidays, min_window_days=2)
        self.assertEqual(risk_windows[0]["buyer_side_overlap"], ["2025-10-06"])

    def test_no_buyer_overlap_gives_empty_list_not_missing_key(self):
        supplier_holidays = [
            {"date": "2025-01-28", "name": "Lunar New Year's Eve"},
            {"date": "2025-01-29", "name": "Lunar New Year"},
        ]
        risk_windows = hc.find_shipping_risk_windows(supplier_holidays, [], min_window_days=2)
        self.assertEqual(risk_windows[0]["buyer_side_overlap"], [])

    def test_real_offline_kr_data_flags_lunar_new_year_and_chuseok(self):
        kr_holidays = hc.OFFLINE_SAMPLE_DATA[("KR", 2025)]
        eg_holidays = hc.OFFLINE_SAMPLE_DATA[("EG", 2025)]

        risk_windows = hc.find_shipping_risk_windows(kr_holidays, eg_holidays, min_window_days=2)

        flagged_starts = {w["start"] for w in risk_windows}
        self.assertIn("2025-01-28", flagged_starts)  # Lunar New Year cluster
        self.assertIn("2025-10-05", flagged_starts)  # Chuseok cluster


if __name__ == "__main__":
    unittest.main()
