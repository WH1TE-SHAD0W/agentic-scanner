"""Slovak/Czech rodné číslo (birth number) — encodes the birth date as
YYMMDD + a 4-digit serial we don't care about. Deriving age from it beats
asking a vision model to read/guess an age field off the scan."""

import re
from datetime import date

_DIGITS_RE = re.compile(r"\D")


def parse_birth_date(birth_number: str) -> date | None:
    if not birth_number:
        return None
    digits = _DIGITS_RE.sub("", birth_number)
    if len(digits) not in (9, 10):
        return None

    yy, mm, dd = int(digits[0:2]), int(digits[2:4]), int(digits[4:6])
    if mm > 50:  # women: month + 50
        mm -= 50
    if not (1 <= mm <= 12):
        return None

    if len(digits) == 9:
        year = 1900 + yy  # 9-digit format predates the 2000s
    else:
        this_century = 2000 + yy
        year = this_century if this_century <= date.today().year else 1900 + yy

    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def age_from_birth_number(birth_number: str, as_of: date | None = None) -> int | None:
    birth_date = parse_birth_date(birth_number)
    if birth_date is None:
        return None
    as_of = as_of or date.today()
    had_birthday = (as_of.month, as_of.day) >= (birth_date.month, birth_date.day)
    age = as_of.year - birth_date.year - (0 if had_birthday else 1)
    return age if age >= 0 else None
