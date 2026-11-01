from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class WebsiteSafetyReport:
    url: str
    risk_level: str
    confidence: str
    findings: tuple[str, ...]
    summary: str


class WebsiteSafetyAnalyzer:
    """Local heuristic checks; this is not a reputation service or malware scan."""

    SHORTENERS = frozenset(
        {
            "bit.ly",
            "cutt.ly",
            "is.gd",
            "rb.gy",
            "t.co",
            "tinyurl.com",
            "trib.al",
            "ow.ly",
        }
    )
    OFFICIAL_BRANDS = {
        "amazon": "amazon.com",
        "apple": "apple.com",
        "facebook": "facebook.com",
        "github": "github.com",
        "google": "google.com",
        "instagram": "instagram.com",
        "microsoft": "microsoft.com",
        "openai": "openai.com",
        "paypal": "paypal.com",
    }

    @classmethod
    def analyze(cls, value: str) -> WebsiteSafetyReport:
        raw_url = str(value or "").strip()
        scheme_supplied = "://" in raw_url
        candidate = raw_url if "://" in raw_url else f"https://{raw_url}"
        findings: list[str] = []
        try:
            parts = urlsplit(candidate)
            host = (parts.hostname or "").rstrip(".").casefold()
            port = parts.port
        except ValueError:
            return cls._report(raw_url, ["The address is malformed; its destination could not be assessed."])

        if parts.scheme.casefold() not in {"http", "https"} or not host:
            return cls._report(raw_url, ["The address does not contain a supported website host."])
        if not scheme_supplied:
            findings.append("No scheme was supplied; HTTPS was assumed for this URL-only check.")
        if parts.username is not None or parts.password is not None:
            findings.append("The URL contains user information before the host, a common deception pattern.")
        if port is not None and port not in {80, 443}:
            findings.append("The URL uses a non-standard port.")
        if parts.scheme.casefold() == "http":
            findings.append("The address uses HTTP rather than encrypted HTTPS.")
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError:
            ascii_host = host
        if "xn--" in ascii_host:
            findings.append("The hostname contains an internationalized punycode label; verify the spelling carefully.")

        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            findings.append("The site is addressed by an IP number rather than a recognizable domain.")

        if host in cls.SHORTENERS:
            findings.append("This is a URL-shortening domain, so the final destination is obscured.")

        labels = set(re.split(r"[.-]", host))
        for brand, official_domain in cls.OFFICIAL_BRANDS.items():
            if brand in labels and not (host == official_domain or host.endswith(f".{official_domain}")):
                findings.append(
                    f"The hostname uses the name of {brand.title()} outside its official {official_domain} domain."
                )
                break

        if not findings:
            findings.append("No obvious URL-level warning signal was found by these limited local checks.")

        if any(
            "user information" in item
            or "punycode" in item
            or "uses the name" in item
            or "IP number" in item
            for item in findings
        ):
            risk_level = "elevated"
        elif any(
            "HTTP rather than" in item
            or "non-standard port" in item
            or "shortening domain" in item
            for item in findings
        ):
            risk_level = "caution"
        else:
            risk_level = "no_obvious_signals"

        return WebsiteSafetyReport(
            url=raw_url,
            risk_level=risk_level,
            confidence="limited",
            findings=tuple(findings),
            summary=(
                f"URL-level assessment: {risk_level.replace('_', ' ')}. "
                "This is a limited heuristic check, not a definitive safety verdict."
            ),
        )

    @staticmethod
    def _report(value: str, findings: list[str]) -> WebsiteSafetyReport:
        return WebsiteSafetyReport(
            url=value,
            risk_level="unknown",
            confidence="limited",
            findings=tuple(findings),
            summary=(
                "URL-level assessment: unknown. The address could not be assessed; "
                "this is not a definitive safety verdict."
            ),
        )
