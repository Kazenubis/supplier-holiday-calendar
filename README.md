# Supplier Holiday Calendar

Built for a real problem in running a K-beauty resale business: orders
cross two countries' holiday calendars — South Korea, where suppliers
ship from, and Egypt, where the package clears customs — and it's the
*clusters* of consecutive holidays (Chuseok, Lunar New Year) that
actually cause multi-day shipping delays, not any single day off.

This pulls public holidays for any country/year from the free
[Nager.Date API](https://date.nager.at/), falls back to an offline
sample for a few countries when the network isn't available, clusters
consecutive holidays into single closure windows, and flags any
supplier-side window long enough to be a real shipping risk.

Real output for Korea (supplier) vs. Egypt (buyer), 2025 — running
offline here, since this environment has no network access, so it's
using the bundled sample data:

```
=== KR public holidays 2025 (offline sample) ===
  2025-01-01  New Year's Day
  2025-01-28  Lunar New Year's Eve
  2025-01-29  Lunar New Year
  2025-01-30  Day after Lunar New Year
  ...
  2025-10-05  Chuseok Eve
  2025-10-06  Chuseok
  2025-10-07  Day after Chuseok
  ...

=== EG public holidays 2025 (offline sample) ===
  2025-01-07  Coptic Christmas Day
  ...
  2025-10-06  Armed Forces Day

=== Shipping delay risk windows (supplier closures >= 2 days) ===
  2025-01-28 to 2025-01-30 (3 day(s)): Lunar New Year's Eve + Lunar New Year + Day after Lunar New Year
  2025-05-05 to 2025-05-06 (2 day(s)): Children's Day + Substitute Holiday
  2025-10-05 to 2025-10-07 (3 day(s)): Chuseok Eve + Chuseok + Day after Chuseok — also a buyer-side holiday on: 2025-10-06
```

That last line is exactly the kind of thing this tool is for: Korea's
Chuseok break overlaps Egypt's Armed Forces Day, so a package already
delayed by the supplier's 3-day closure would *also* hit a closed
customs office on delivery — a compounding delay that's easy to miss
scanning two holiday calendars separately.

## Features

- Live fetch from the Nager.Date public holiday API for any
  ISO country code + year, with an offline sample fallback (Egypt,
  South Korea, United States) when the network is unreachable
- Clusters consecutive-day holidays (e.g. a 3-day Chuseok listing) into
  a single closure window instead of treating them as unrelated single
  days
- Flags supplier-side closure windows at or above a configurable length
  as shipping delay risks, and separately reports when a buyer-side
  holiday overlaps that window
- CLI supports any `--supplier`/`--buyer` country code pair and
  `--year`, defaulting to the KR → EG case this was built for

## Tech Stack

Python 3 · `requests`

## Getting Started

```bash
git clone https://github.com/Kazenubis/supplier-holiday-calendar.git
cd supplier-holiday-calendar
pip install -r requirements.txt
python3 holiday_calendar.py --supplier KR --buyer EG --year 2025
```

Try a different pair:

```bash
python3 holiday_calendar.py --supplier US --buyer EG --year 2025 --min-window-days 1
```

Run the tests:

```bash
python3 -m unittest test_holiday_calendar.py -v
```

## What I Learned

Holiday-shifted, culturally-observed multi-day breaks (Lunar New Year,
Chuseok, Eid) aren't well represented as a flat list of individual
dates for this use case — a naive version of this tool would print
"Jan 28, Jan 29, Jan 30 are all holidays" and leave it to the reader to
notice those three lines are really one 3-day closure. Clustering
consecutive dates into a single window before doing the risk analysis
is what actually makes the output useful for planning around: "expect
a 3-day closure starting Jan 28" is something I can act on; three
separate single-day flags aren't.

The offline sample data also can't fully replicate what the live API
does — Islamic-calendar holidays like Eid shift by about 10-11 days
every year, so a hardcoded sample is only ever correct for the specific
year it was captured against. That's disclosed directly in the code
rather than left implicit, since presenting stale fallback dates as if
they were current would defeat the point of the tool.
