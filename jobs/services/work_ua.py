"""
Work.ua vacancy parser.

As a library:
    from work_ua import WorkUaParser
    parser = WorkUaParser()
    data = parser.parse_vacancy("https://www.work.ua/jobs/12345/")

As a CLI:
    python work_ua.py <url>                  # print JSON to console
    python work_ua.py <url> -o vacancy.json  # save JSON to file (UTF-8)
"""

import re
import logging
from dataclasses import dataclass, field, asdict

import requests
from bs4 import BeautifulSoup, NavigableString

logger = logging.getLogger(__name__)


class WorkUaParseError(Exception):
    """Raised when the parser cannot extract required data."""


@dataclass
class VacancyData:
    """Parsed vacancy data — plain Python object, not a Django model."""
    source_url: str
    title: str
    company_name: str
    company_url: str = ""
    location: str = ""
    hr_name: str = ""
    phone: str = ""
    salary_text: str = ""
    skills: list[str] = field(default_factory=list)
    description_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class WorkUaParser:
    BASE_URL = "https://www.work.ua"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "uk,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/webp,*/*;q=0.8"
        ),
    }
    TIMEOUT = 15

    def parse_vacancy(self, url: str) -> VacancyData:
        """Fetch and parse a single Work.ua vacancy page."""
        html = self._fetch(url)
        soup = BeautifulSoup(html, "lxml")

        return VacancyData(
            source_url=url,
            title=self._parse_title(soup),
            company_name=self._parse_company_name(soup),
            company_url=self._parse_company_url(soup),
            location=self._parse_location(soup),
            hr_name=self._parse_hr_name(soup),
            phone=self._parse_phone(soup),
            salary_text=self._parse_salary(soup),
            skills=self._parse_skills(soup),
            description_text=self._parse_description_text(soup),
        )

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> str:
        try:
            response = requests.get(url, headers=self.HEADERS,
                                    timeout=self.TIMEOUT)
        except requests.RequestException as e:
            raise WorkUaParseError(f"Network error: {e}") from e

        if response.status_code == 404:
            raise WorkUaParseError(
                "Vacancy not found (probably closed or removed)")
        if response.status_code != 200:
            raise WorkUaParseError(
                f"Unexpected HTTP status: {response.status_code}")

        return response.text

    # ------------------------------------------------------------------
    # Field parsers — each isolated, returns "" or [] on failure
    # ------------------------------------------------------------------

    def _parse_title(self, soup: BeautifulSoup) -> str:
        """h1#h1-name. May contain <span class="highlight-result"> highlights."""
        h1 = soup.select_one("h1#h1-name")
        if not h1:
            raise WorkUaParseError("Vacancy title (h1#h1-name) not found")
        return h1.get_text(strip=True)

    def _parse_company_name(self, soup: BeautifulSoup) -> str:
        """Company name is in <span class="strong-500"> inside the company link."""
        span = soup.select_one('a[href^="/jobs/by-company/"] span.strong-500')
        if not span:
            return ""
        return span.get_text(strip=True)

    def _parse_company_url(self, soup: BeautifulSoup) -> str:
        link = soup.select_one('a[href^="/jobs/by-company/"]')
        if not link:
            return ""
        href = link.get("href", "")
        return f"{self.BASE_URL}{href}" if href.startswith("/") else href

    def _parse_location(self, soup: BeautifulSoup) -> str:
        """
        Tricky: address text is a direct text child of <li>,
        siblings include nested spans ("2.3 км від центру", "На мапі")
        which we need to ignore.
        """
        marker = soup.select_one("li span.glyphicon-map-marker")
        if not marker:
            return ""

        li = marker.find_parent("li")
        if not li:
            return ""

        parts = []
        for child in li.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    parts.append(text)

        location = " ".join(parts).strip()
        return re.sub(r"\s+", " ", location).strip().rstrip(".")

    def _parse_hr_name(self, soup: BeautifulSoup) -> str:
        """Name is in span.mr-sm next to phone glyphicon."""
        phone_marker = soup.select_one("li span.glyphicon-phone")
        if not phone_marker:
            return ""

        li = phone_marker.find_parent("li")
        if not li:
            return ""

        name_span = li.select_one("span.mr-sm")
        return name_span.get_text(strip=True) if name_span else ""

    def _parse_phone(self, soup: BeautifulSoup) -> str:
        """Phone is in href='tel:...' attribute, even when button is hidden."""
        link = soup.select_one('a.js-get-phone[href^="tel:"]')
        if not link:
            return ""
        href = link.get("href", "")
        return href.replace("tel:", "").strip()

    def _parse_salary(self, soup: BeautifulSoup) -> str:
        """
        Salary block uses glyphicon-hryvnia-fill icon.
        Returns the raw salary string as shown on the site, e.g.:
            "20 000 – 30 000 грн", "від 25 000 грн", "за домовленістю"
        Returns "" if no salary block is present.
        """
        marker = soup.select_one("li span.glyphicon-hryvnia-fill")
        if not marker:
            return ""

        li = marker.find_parent("li")
        if not li:
            return ""

        value_span = li.select_one("span.strong-500")
        if not value_span:
            return ""

        raw_text = value_span.get_text(strip=True)

        # Remove invisible formatting characters (e.g., zero-width spaces)
        clean_text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', raw_text)

        # Replace any sequence of whitespace characters (including NNBSP, THSP, NBSP)
        # with a single standard space
        clean_text = re.sub(r'\s+', ' ', clean_text)

        return clean_text.strip()

    def _parse_skills(self, soup: BeautifulSoup) -> list[str]:
        """Skill tags: ul > li.label-skill > span.ellipsis."""
        skills = []
        for li in soup.select("li.label-skill"):
            span = li.select_one("span.ellipsis")
            if span:
                text = span.get_text(strip=True)
                if text:
                    skills.append(text)
        return skills

    def _parse_description_text(self, soup: BeautifulSoup) -> str:
        """Plain-text version of description, full length."""
        block = soup.select_one("div#job-description")
        if not block:
            return ""
        return block.get_text("\n", strip=True)


# ----------------------------------------------------------------------
# CLI entry point — runs only when this file is executed directly,
# does NOT run on `from work_ua import WorkUaParser`
# ----------------------------------------------------------------------

def _main():
    import sys
    import json
    import argparse

    arg_parser = argparse.ArgumentParser(
        description="Parse a Work.ua vacancy.")
    arg_parser.add_argument("url", help="Work.ua vacancy URL")
    arg_parser.add_argument(
        "-o", "--output",
        help="Save JSON to this file (UTF-8). If omitted, prints to console.",
    )
    args = arg_parser.parse_args()

    parser = WorkUaParser()
    try:
        data = parser.parse_vacancy(args.url)
    except WorkUaParseError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)

    json_text = json.dumps(data.to_dict(), ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_text)
        print(f"Saved to {args.output}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
        print(json_text)


if __name__ == "__main__":
    _main()
