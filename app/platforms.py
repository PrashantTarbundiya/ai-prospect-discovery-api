"""Registry of supported public profile routes and Google discovery scopes."""
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .schemas import Link


@dataclass(frozen=True)
class Platform:
    name: str
    hosts: tuple[str, ...]
    path_pattern: str
    search_scope: str


HANDLE = r"[A-Za-z0-9_][A-Za-z0-9._-]{0,99}"
PLATFORMS = (
    Platform("LinkedIn", ("linkedin.com",), r"/(?:in|company)/[\w%-]+", "site:linkedin.com"),
    Platform("X", ("x.com", "twitter.com"), r"/[A-Za-z0-9_]{1,15}", "site:x.com"),
    Platform("YouTube", ("youtube.com",), r"/(?:@[\w.%-]+|channel/UC[\w-]{22}|(?:user|c)/[\w.%-]+)", "site:youtube.com"),
    Platform("Instagram", ("instagram.com",), "/" + HANDLE, "site:instagram.com"),
    Platform("Facebook", ("facebook.com",), "/" + HANDLE, "site:facebook.com"),
    Platform("Threads", ("threads.com", "threads.net"), "/@" + HANDLE, "(site:threads.com OR site:threads.net)"),
)
RESERVED = set("about account accounts ads business channel channels communities contact developers directory discover events explore feed friends gaming groups hashtag help home i intent jobs legal live login logout marketplace messages notifications pages people photo photos pin policy policies posts privacy profile.php public reels results search settings share shorts signin signup status stories terms trending watch videos web".split())
WEBSITE_DENY = ("google.com", "google.co.uk", "google.co.in", "bing.com", "yahoo.com", "duckduckgo.com",
                "wa.me", "whatsapp.com", "youtu.be", "wikipedia.org", "reddit.com", "pinterest.com", "tiktok.com")


def profile_link(raw: str) -> Link | None:
    try:
        url = urlsplit(raw)
        host = (url.hostname or "").lower()
        if url.scheme not in ("https", "http") or url.username or url.password or url.port not in (None, 80, 443):
            return None
        if any(c.isspace() or c in "\\<>" for c in raw) or not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,63}", host):
            return None
        if host.endswith((".local", ".internal", ".localhost")):
            return None
    except ValueError:
        return None
    host = host.removeprefix("www.")
    path = url.path.rstrip("/")
    for spec in PLATFORMS:
        if not any(host == h or host.endswith("." + h) for h in spec.hosts):
            continue
        if host not in spec.hosts and not (spec.name == "Facebook" and host == "m.facebook.com") and not (
                spec.name == "LinkedIn" and re.fullmatch(r"[a-z]{2}\.linkedin\.com", host)):
            return None
        canonical_host = spec.hosts[0]
        if spec.name == "Facebook" and path == "/profile.php":
            ids = parse_qs(url.query).get("id", [])
            if len(ids) == 1 and re.fullmatch(r"[1-9]\d{4,20}", ids[0]):
                return Link(platform=spec.name, link=f"https://facebook.com/profile.php?id={ids[0]}")
            return None
        if path.lstrip("/").casefold() in RESERVED or not re.fullmatch(spec.path_pattern, path):
            return None
        if spec.name in {"Instagram", "X", "Facebook", "Threads"}:
            path = path.lower()
        return Link(platform=spec.name, link=f"https://{canonical_host}{path}")
    if any(host == h or host.endswith("." + h) for h in WEBSITE_DENY) or re.search(r"(?:^|\.)google\.", host):
        return None
    if url.query and any(not key.startswith("utm_") for key in parse_qs(url.query, keep_blank_values=True)):
        return None
    if path.lower() not in ("", "/about", "/about-us", "/about-me", "/contact", "/contact-us"):
        return None
    return Link(platform="Google", link=f"{url.scheme}://{url.hostname}{path}")
