"""Ghanaian calendar context: public holidays, festive and school seasons, weather seasons.

Used to suggest *possible* reasons for a change in sales ("the previous period included the
Christmas season"). It is never treated as proof. Holidays can be moved by executive
instrument and Eid dates follow the moon, so dates outside the table below are approximate.

Sources: Ministry of the Interior statutory holiday lists (mint.gov.gh) and the Public
Holidays and Commemorative Days (Amendment) Act, 2025. Review this table every year.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Event:
    name: str
    start: date
    end: date
    kind: str  # "holiday" | "festive" | "school" | "weather" | "religious"
    note: str = ""


# Fixed-date statutory holidays (Amendment Act, 2025). Observed dates can shift to a Friday/Monday.
_FIXED = (
    ((1, 1), "New Year's Day"),
    ((1, 7), "Constitution Day"),
    ((3, 6), "Independence Day"),
    ((5, 1), "May Day"),
    ((7, 1), "Republic Day"),
    ((9, 21), "Founder's Day"),
    ((12, 25), "Christmas Day"),
    ((12, 26), "Boxing Day"),
)

# Moon-based dates (approximate; confirm against the official list each year).
_LUNAR = {
    2024: {"ramadan": date(2024, 3, 11), "eid_fitr": date(2024, 4, 10), "eid_adha": date(2024, 6, 16)},
    2025: {"ramadan": date(2025, 3, 1), "eid_fitr": date(2025, 3, 30), "eid_adha": date(2025, 6, 6)},
    2026: {"ramadan": date(2026, 2, 18), "eid_fitr": date(2026, 3, 20), "eid_adha": date(2026, 5, 27)},
    2027: {"ramadan": date(2027, 2, 8), "eid_fitr": date(2027, 3, 10), "eid_adha": date(2027, 5, 17)},
}


def easter(year: int) -> date:
    """Western Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _first_friday_of_december(year: int) -> date:
    day = date(year, 12, 1)
    return day + timedelta(days=(4 - day.weekday()) % 7)


def events_for_year(year: int) -> list[Event]:
    events = [Event(name, date(year, month, day), date(year, month, day), "holiday") for (month, day), name in _FIXED]
    sunday = easter(year)
    events.append(Event("Easter (Good Friday to Easter Monday)", sunday - timedelta(days=2), sunday + timedelta(days=1), "holiday"))
    events.append(Event("Farmers' Day", _first_friday_of_december(year), _first_friday_of_december(year), "holiday"))
    events.append(Event("Christmas and New Year season", date(year, 12, 1), date(year + 1, 1, 6), "festive", "Peak shopping for food, drinks, clothing and gifts."))
    events.append(Event("Back to school (January)", date(year, 1, 5), date(year, 1, 20), "school", "Approximate. Uniforms, books, provisions and fees."))
    events.append(Event("Back to school (May)", date(year, 4, 28), date(year, 5, 12), "school", "Approximate."))
    events.append(Event("Back to school (September)", date(year, 9, 1), date(year, 9, 20), "school", "Approximate."))
    events.append(Event("Major rainy season (south)", date(year, 4, 1), date(year, 7, 15), "weather", "Approximate. Can reduce market footfall and raise produce prices."))
    events.append(Event("Minor rainy season (south)", date(year, 9, 1), date(year, 11, 15), "weather", "Approximate."))
    events.append(Event("Harmattan", date(year, 12, 1), date(year + 1, 2, 15), "weather", "Approximate. Dry, dusty months."))
    lunar = _LUNAR.get(year)
    if lunar:
        events.append(Event("Ramadan", lunar["ramadan"], lunar["eid_fitr"] - timedelta(days=1), "religious", "Approximate dates."))
        events.append(Event("Eid al-Fitr", lunar["eid_fitr"], lunar["eid_fitr"], "holiday", "Approximate date."))
        events.append(Event("Eid al-Adha", lunar["eid_adha"], lunar["eid_adha"], "holiday", "Approximate date."))
    return events


def events_between(start: date, end: date) -> list[Event]:
    """Events that overlap the inclusive window, longest-running first."""
    found = {
        event
        for year in range(start.year - 1, end.year + 1)
        for event in events_for_year(year)
        if event.start <= end and event.end >= start
    }
    return sorted(found, key=lambda event: (event.start, event.name))


def notable_difference(current: tuple[date, date], previous: tuple[date, date]) -> list[tuple[str, Event]]:
    """Festive, school and religious seasons in one window but not the other.

    Returns ("previous", event) for seasons only the previous window had, and ("current", event)
    for seasons only the current window has. Single-day holidays and weather are left out: they
    rarely explain a whole-period change.
    """
    kinds = {"festive", "school", "religious"}
    now = {event.name: event for event in events_between(*current) if event.kind in kinds}
    before = {event.name: event for event in events_between(*previous) if event.kind in kinds}
    return [("previous", before[name]) for name in sorted(before.keys() - now.keys())] + [
        ("current", now[name]) for name in sorted(now.keys() - before.keys())
    ]
