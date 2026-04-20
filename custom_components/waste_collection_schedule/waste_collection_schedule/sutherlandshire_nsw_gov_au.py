import re
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta

from waste_collection_schedule import Collection  # type: ignore[attr-defined]

TITLE = "Sutherland Shire Council"
DESCRIPTION = "Source for Sutherland Shire Council, NSW, Australia"
URL = "https://www.sutherlandshire.nsw.gov.au"
TEST_CASES = {
    "195 Washington Drive, BONNET BAY": {
        "suburb": "BONNET BAY",
        "street": "Washington Drive",
        "house_number": "195",
    },
}

# The council's waste information booklet form
_PAGE_URL = (
    "https://www.sutherlandshire.nsw.gov.au"
    "/living-here/waste-and-recycling/waste-information-booklet"
)
_PDF_BASE = "https://www.sutherlandshire.nsw.gov.au"

# Map day names to weekday numbers (Monday=0 ... Sunday=6)
_WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

# Zone -> which fortnight is "Week A" for recycling/greenwaste.
# Week A = the fortnight that starts on or after 2024-01-01 (Monday).
# Zone 1 = Week A starts 2024-01-01, Zone 2 = Week A starts 2024-01-08.
# Extend as more zones are confirmed by users.
_ZONE_OFFSETS = {
    "1": 0,  # Zone 1: recycling on Week A
    "2": 7,  # Zone 2: recycling offset by 1 week vs Zone 1
}

# Reference Monday for zone offset calculations
_REFERENCE_MONDAY = date(2024, 1, 1)

ICON_MAP = {
    "Garbage": "mdi:trash-can",
    "Recycling": "mdi:recycle",
    "Garden Waste": "mdi:leaf",
}


def _next_weekday(from_date: date, weekday: int) -> date:
    """Return the next occurrence of `weekday` on or after `from_date`."""
    days_ahead = weekday - from_date.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return from_date + timedelta(days=days_ahead)


def _collection_dates(
    weekday: int,
    zone: str,
    start: date,
    end: date,
):
    """
    Yield (date, waste_type) tuples for all collections between start and end.

    - Garbage: every week on `weekday`
    - Recycling & Garden Waste: alternate fortnights on `weekday`
      (Garden Waste is the opposite fortnight to Recycling)
    """
    zone_offset = _ZONE_OFFSETS.get(zone, 0)

    # First occurrence of the weekday on or after start
    cur = _next_weekday(start, weekday)

    while cur <= end:
        yield cur, "Garbage"

        # Determine which fortnight this date is in relative to the reference
        delta_days = (cur - _REFERENCE_MONDAY).days + zone_offset
        fortnight = (delta_days // 7) % 2  # 0 = recycling week, 1 = garden week

        if fortnight == 0:
            yield cur, "Recycling"
        else:
            yield cur, "Garden Waste"

        cur += timedelta(weeks=1)


def _get_hidden_fields(soup: BeautifulSoup) -> dict:
    """Extract all hidden input fields from the page."""
    return {
        inp["name"]: inp.get("value", "")
        for inp in soup.find_all("input", type="hidden")
        if inp.get("name")
    }


def _parse_update_panel(text: str) -> BeautifulSoup:
    """
    Parse the UpdatePanel async response.

    ASP.NET UpdatePanel responses look like:
      1|#||4|LENGTH|updatePanel|ID|HTML_CONTENT
    Extract the HTML_CONTENT and return a BeautifulSoup.
    """
    # Try to find the HTML block after the last pipe-separated header
    parts = text.split("|")
    if len(parts) >= 8 and parts[4].isdigit():
        # Standard UpdatePanel format: length is parts[4], content follows
        try:
            length = int(parts[4])
            # The content starts after "1|#||4|LEN|updatePanel|ID|"
            prefix = "|".join(parts[:7]) + "|"
            content = text[len(prefix) : len(prefix) + length]
            return BeautifulSoup(content, "html.parser")
        except (ValueError, IndexError):
            pass
    # Fallback: parse the whole response
    return BeautifulSoup(text, "html.parser")


class Source:
    def __init__(self, suburb: str, street: str, house_number: str):
        self._suburb = suburb.upper().strip()
        self._street = street.strip()
        self._house_number = str(house_number).strip()

    def fetch(self) -> list[Collection]:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": _PAGE_URL,
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        # ------------------------------------------------------------------ #
        # Step 1: GET the initial page to obtain ASP.NET hidden fields        #
        # ------------------------------------------------------------------ #
        resp = session.get(_PAGE_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        hidden = _get_hidden_fields(soup)

        # Detect the control prefix (usually "ctl03")
        suburb_sel = soup.find(
            "select", id=lambda x: x and x.endswith("_ddlSuburb")
        )
        if not suburb_sel:
            raise ValueError(
                "Could not find suburb dropdown on the Sutherland Shire page. "
                "The page layout may have changed."
            )
        # id="ctl03_ddlSuburb"  -> prefix="ctl03",  name prefix="ctl03$"
        ctrl_id = suburb_sel["id"].rsplit("_", 1)[0]  # "ctl03"
        ctrl_name = suburb_sel["name"].rsplit("$", 1)[0]  # "ctl03"

        def post_update(event_target: str, extra: dict) -> BeautifulSoup:
            payload = {
                **hidden,
                "__EVENTTARGET": event_target,
                "__EVENTARGUMENT": "",
                "__ASYNCPOST": "true",
                f"{ctrl_name}$ddlSuburb": self._suburb,
                f"{ctrl_name}$ddlStreet": self._street,
                f"{ctrl_name}$ddlHouseNumber": self._house_number,
                **extra,
            }
            r = session.post(
                _PAGE_URL,
                data=payload,
                headers={"X-MicrosoftAjax": "Delta=true"},
                timeout=30,
            )
            r.raise_for_status()
            # Refresh hidden fields from response (UpdatePanel sends them back)
            panel_soup = _parse_update_panel(r.text)
            for inp in panel_soup.find_all("input", type="hidden"):
                if inp.get("name"):
                    hidden[inp["name"]] = inp.get("value", "")
            return panel_soup

        # ------------------------------------------------------------------ #
        # Step 2: Select suburb (triggers street list refresh)                #
        # ------------------------------------------------------------------ #
        post_update(
            f"{ctrl_name}$ddlSuburb",
            {f"{ctrl_name}$ddlSuburb": self._suburb},
        )

        # ------------------------------------------------------------------ #
        # Step 3: Select street (triggers house number list refresh)          #
        # ------------------------------------------------------------------ #
        post_update(
            f"{ctrl_name}$ddlStreet",
            {
                f"{ctrl_name}$ddlSuburb": self._suburb,
                f"{ctrl_name}$ddlStreet": self._street,
            },
        )

        # ------------------------------------------------------------------ #
        # Step 4: Submit form with house number                               #
        # ------------------------------------------------------------------ #
        result_soup = post_update(
            "",  # blank EVENTTARGET for button submit
            {
                f"{ctrl_name}$ddlSuburb": self._suburb,
                f"{ctrl_name}$ddlStreet": self._street,
                f"{ctrl_name}$ddlHouseNumber": self._house_number,
                f"{ctrl_name}$btnSubmit": "Submit",
            },
        )

        # ------------------------------------------------------------------ #
        # Step 5: Parse result text and PDF link                              #
        # ------------------------------------------------------------------ #
        result_div = result_soup.find(class_="query-result")
        if not result_div:
            # Try full page fallback
            resp2 = session.post(
                _PAGE_URL,
                data={
                    **hidden,
                    "__EVENTTARGET": "",
                    "__EVENTARGUMENT": "",
                    f"{ctrl_name}$ddlSuburb": self._suburb,
                    f"{ctrl_name}$ddlStreet": self._street,
                    f"{ctrl_name}$ddlHouseNumber": self._house_number,
                    f"{ctrl_name}$btnSubmit": "Submit",
                },
                timeout=30,
            )
            resp2.raise_for_status()
            result_soup = BeautifulSoup(resp2.text, "html.parser")
            result_div = result_soup.find(class_="query-result")

        if not result_div:
            raise ValueError(
                f"No collection result found for {self._house_number} "
                f"{self._street}, {self._suburb}. "
                "Check that your suburb, street and house number are correct."
            )

        result_text = result_div.get_text(" ", strip=True)

        # Extract collection day
        day_match = re.search(
            r"\bis\s+(\w+),\s+recycling", result_text, re.IGNORECASE
        )
        if not day_match:
            raise ValueError(
                f"Could not parse collection day from: '{result_text}'"
            )
        day_name = day_match.group(1).lower()
        weekday = _WEEKDAY_MAP.get(day_name)
        if weekday is None:
            raise ValueError(f"Unknown day name: '{day_name}'")

        # Extract zone from PDF link
        pdf_link = result_soup.find("a", class_="pdf-link")
        zone = None
        if pdf_link and pdf_link.get("href"):
            import urllib.parse
            href = urllib.parse.unquote(pdf_link["href"])
            zone_match = re.search(r"Zone\s*(\d+)", href, re.IGNORECASE)
            if zone_match:
                zone = zone_match.group(1)

        if zone is None:
            # Default to Zone 1 if we can't determine it
            zone = "1"

        # ------------------------------------------------------------------ #
        # Step 6: Generate collection dates for ~1 year                      #
        # ------------------------------------------------------------------ #
        today = date.today()
        end_date = today + timedelta(days=365)

        collections = []
        for collection_date, waste_type in _collection_dates(
            weekday, zone, today, end_date
        ):
            collections.append(
                Collection(
                    date=collection_date,
                    t=waste_type,
                    icon=ICON_MAP.get(waste_type, "mdi:trash-can"),
                )
            )

        return collections
