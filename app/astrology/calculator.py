from __future__ import annotations

from datetime import date

ZODIAC_RANGES = [
    ((1, 20), (2, 18), "Aquarius"),
    ((2, 19), (3, 20), "Pisces"),
    ((3, 21), (4, 19), "Aries"),
    ((4, 20), (5, 20), "Taurus"),
    ((5, 21), (6, 20), "Gemini"),
    ((6, 21), (7, 22), "Cancer"),
    ((7, 23), (8, 22), "Leo"),
    ((8, 23), (9, 22), "Virgo"),
    ((9, 23), (10, 22), "Libra"),
    ((10, 23), (11, 21), "Scorpio"),
    ((11, 22), (12, 21), "Sagittarius"),
    ((12, 22), (12, 31), "Capricorn"),
    ((1, 1), (1, 19), "Capricorn"),
]


def compute_zodiac(dob: date | None) -> str | None:
    if dob is None:
        return None
    month, day = dob.month, dob.day
    for (sm, sd), (em, ed), sign in ZODIAC_RANGES:
        if (month, day) >= (sm, sd) and (month, day) <= (em, ed):
            return sign
    return None
