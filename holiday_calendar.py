"""
Supplier Holiday Calendar — fetches public holidays for a country/year via
the free Nager.Date API, with an offline sample fallback for a handful of
countries when the live API isn't reachable.

Built around a real use case: reselling K-beauty products means orders
cross two countries' holiday calendars (South Korea, where suppliers
ship from, and Egypt, where customs has to clear the package) — and it's
the *clusters* of consecutive holidays (Chuseok, Lunar New Year) that
actually cause shipping delays, not any single day off.
"""

import argparse
import json
from datetime import date, datetime, timedelta

import requests

NAGER_API = "https://date.nager.at/api/v3/PublicHolidays"

# Nager.Date's public-holiday date-shifting (like Lunar New Year, Eid) is
# recalculated by them every year from lunar/religious calendars, which
# this offline sample can't replicate — it exists purely as a fallback so
# the tool still works with no network, calibrated to a real past year
# (2025) rather than invented dates. A live lookup is what you'd actually
# want for a real shipment.
OFFLINE_SAMPLE_DATA = {
    ("EG", 2025): [
        {"date": "2025-01-07", "localName": "Coptic Christmas", "name": "Coptic Christmas Day"},
        {"date": "2025-01-25", "localName": "عيد الثورة", "name": "Revolution Day"},
        {"date": "2025-03-30", "localName": "عيد الفطر", "name": "Eid al-Fitr"},
        {"date": "2025-03-31", "localName": "عيد الفطر", "name": "Eid al-Fitr Holiday"},
        {"date": "2025-04-01", "localName": "عيد الفطر", "name": "Eid al-Fitr Holiday"},
        {"date": "2025-04-25", "localName": "عيد تحرير سيناء", "name": "Sinai Liberation Day"},
        {"date": "2025-05-01", "localName": "عيد العمال", "name": "Labour Day"},
        {"date": "2025-06-06", "localName": "عيد الأضحى", "name": "Eid al-Adha"},
        {"date": "2025-06-07", "localName": "عيد الأضحى", "name": "Eid al-Adha Holiday"},
        {"date": "2025-06-08", "localName": "عيد الأضحى", "name": "Eid al-Adha Holiday"},
        {"date": "2025-06-26", "localName": "رأس السنة الهجرية", "name": "Islamic New Year"},
        {"date": "2025-07-23", "localName": "عيد الثورة", "name": "Revolution Day"},
        {"date": "2025-09-04", "localName": "المولد النبوي", "name": "Prophet's Birthday"},
        {"date": "2025-10-06", "localName": "عيد القوات المسلحة", "name": "Armed Forces Day"},
    ],
    ("KR", 2025): [
        {"date": "2025-01-01", "localName": "신정", "name": "New Year's Day"},
        {"date": "2025-01-28", "localName": "설날", "name": "Lunar New Year's Eve"},
        {"date": "2025-01-29", "localName": "설날", "name": "Lunar New Year"},
        {"date": "2025-01-30", "localName": "설날", "name": "Day after Lunar New Year"},
        {"date": "2025-03-01", "localName": "삼일절", "name": "Independence Movement Day"},
        {"date": "2025-05-05", "localName": "어린이날", "name": "Children's Day"},
        {"date": "2025-05-06", "localName": "대체공휴일", "name": "Substitute Holiday"},
        {"date": "2025-06-06", "localName": "현충일", "name": "Memorial Day"},
        {"date": "2025-08-15", "localName": "광복절", "name": "Liberation Day"},
        {"date": "2025-10-03", "localName": "개천절", "name": "National Foundation Day"},
        {"date": "2025-10-05", "localName": "추석", "name": "Chuseok Eve"},
        {"date": "2025-10-06", "localName": "추석", "name": "Chuseok"},
        {"date": "2025-10-07", "localName": "추석", "name": "Day after Chuseok"},
        {"date": "2025-10-09", "localName": "한글날", "name": "Hangul Day"},
        {"date": "2025-12-25", "localName": "기독탄신일", "name": "Christmas Day"},
    ],
    ("US", 2025): [
        {"date": "2025-01-01", "localName": "New Year's Day", "name": "New Year's Day"},
        {"date": "2025-01-20", "localName": "Martin Luther King, Jr. Day", "name": "Martin Luther King, Jr. Day"},
        {"date": "2025-07-04", "localName": "Independence Day", "name": "Independence Day"},
        {"date": "2025-11-27", "localName": "Thanksgiving", "name": "Thanksgiving Day"},
        {"date": "2025-12-25", "localName": "Christmas Day", "name": "Christmas Day"},
    ],
}


def fetch_holidays_live(country_code, year, timeout=5):
    """Raises on any network problem — callers should catch
    requests.RequestException and fall back to offline sample data."""
    url = f"{NAGER_API}/{year}/{country_code}"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def get_holidays(country_code, year, timeout=5):
    """Returns (holidays, source_label, found). `found` is False only
    when we fell back to the offline sample and don't have data for this
    country/year combination — same "honest not-found" shape used by the
    weather dashboard project rather than silently returning []."""
    try:
        holidays = fetch_holidays_live(country_code, year, timeout=timeout)
        return holidays, "live", True
    except requests.RequestException:
        pass

    key = (country_code.upper(), year)
    if key in OFFLINE_SAMPLE_DATA:
        return OFFLINE_SAMPLE_DATA[key], "offline sample", True
    return [], "offline sample", False


def _parse_date(holiday):
    return datetime.strptime(holiday["date"], "%Y-%m-%d").date()


def cluster_consecutive_holidays(holidays, max_gap_days=1):
    """Groups holidays into windows where consecutive entries (like a
    3-day Chuseok listing) are treated as one closure period rather than
    three separate one-day events. A gap of `max_gap_days` or fewer
    between two holidays keeps them in the same cluster."""
    if not holidays:
        return []

    sorted_holidays = sorted(holidays, key=_parse_date)
    clusters = []
    current_cluster = [sorted_holidays[0]]

    for holiday in sorted_holidays[1:]:
        previous_date = _parse_date(current_cluster[-1])
        this_date = _parse_date(holiday)
        if (this_date - previous_date).days <= max_gap_days:
            current_cluster.append(holiday)
        else:
            clusters.append(current_cluster)
            current_cluster = [holiday]

    clusters.append(current_cluster)

    windows = []
    for cluster in clusters:
        start = _parse_date(cluster[0])
        end = _parse_date(cluster[-1])
        windows.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "length_days": (end - start).days + 1,
            "names": [h["name"] for h in cluster],
        })
    return windows


def find_shipping_risk_windows(supplier_holidays, buyer_holidays, min_window_days=2):
    """Flags supplier-side holiday clusters of `min_window_days` or more
    as shipping delay risks (factories/couriers often extend a break
    around multi-day holidays), and separately flags any buyer-side
    holiday that overlaps a supplier risk window (customs clearance
    would also be closed that day, compounding the delay)."""
    supplier_windows = cluster_consecutive_holidays(supplier_holidays)
    risk_windows = [w for w in supplier_windows if w["length_days"] >= min_window_days]

    buyer_dates = {_parse_date(h) for h in buyer_holidays}
    for window in risk_windows:
        start = date.fromisoformat(window["start"])
        end = date.fromisoformat(window["end"])
        overlapping_buyer_days = [
            d for d in buyer_dates
            if start <= d <= end
        ]
        window["buyer_side_overlap"] = sorted(d.isoformat() for d in overlapping_buyer_days)

    return risk_windows


def format_holiday_line(holiday):
    return f"{holiday['date']}  {holiday['name']}"


def format_risk_window(window):
    span = window["start"] if window["start"] == window["end"] else f"{window['start']} to {window['end']}"
    names = " + ".join(window["names"])
    line = f"{span} ({window['length_days']} day(s)): {names}"
    if window["buyer_side_overlap"]:
        line += f" — also a buyer-side holiday on: {', '.join(window['buyer_side_overlap'])}"
    return line


def main():
    parser = argparse.ArgumentParser(description="Supplier Holiday Calendar")
    parser.add_argument("--supplier", default="KR", help="Supplier country code (default: KR)")
    parser.add_argument("--buyer", default="EG", help="Buyer/receiving country code (default: EG)")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--min-window-days", type=int, default=2)
    args = parser.parse_args()

    supplier_holidays, supplier_source, supplier_found = get_holidays(args.supplier, args.year)
    buyer_holidays, buyer_source, buyer_found = get_holidays(args.buyer, args.year)

    print(f"=== {args.supplier} public holidays {args.year} ({supplier_source}) ===")
    if not supplier_found:
        print("  (no data available)")
    for holiday in sorted(supplier_holidays, key=_parse_date):
        print(f"  {format_holiday_line(holiday)}")

    print(f"\n=== {args.buyer} public holidays {args.year} ({buyer_source}) ===")
    if not buyer_found:
        print("  (no data available)")
    for holiday in sorted(buyer_holidays, key=_parse_date):
        print(f"  {format_holiday_line(holiday)}")

    print(f"\n=== Shipping delay risk windows (supplier closures >= {args.min_window_days} days) ===")
    risk_windows = find_shipping_risk_windows(
        supplier_holidays, buyer_holidays, min_window_days=args.min_window_days
    )
    if not risk_windows:
        print("  None found.")
    for window in risk_windows:
        print(f"  {format_risk_window(window)}")


if __name__ == "__main__":
    main()
