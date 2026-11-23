"""Derive prospects from the indexed title and excerpt of a single identity page."""
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from email_validator import EmailNotValidError, validate_email

from .platforms import profile_link
from .schemas import Link, Prospect


def normalize(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def supports(text, phrase):
    term = normalize(phrase)
    if not term:
        return False
    for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text):
        if not re.search(r"\b(?:not|never|formerly|former|ex|outside|visiting|travel to)(?: an?| the| based in| from| in)? $", text[:match.start()]):
            return True
    return False


def identity(title):
    label = re.split(r"\s(?:[-–—|•·]|\bon\b\s+(?:X|Instagram|Threads|LinkedIn))\s*|\s*\(@", title, maxsplit=1, flags=re.I)[0]
    label = re.sub(r"\s+on\s+(?:YouTube|Facebook)$", "", label, flags=re.I).strip()
    if not (1 < len(label) <= 85) or not any(c.isalpha() for c in label):
        return None
    if normalize(label) in {"home", "about", "about us", "about me", "contact", "official website", "welcome"}:
        return None
    if len(label.split()) > 9 or re.search(r"https?://|[<>@#|?]|\b(?:top \d+|best of|sign in|log in|profiles|directory|contact us|search results)\b", label, re.I):
        return None
    return label


EMAIL = r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,63}"
PHONE = r"\+[1-9](?:[\d ()-]{5,22})\d"
WHATSAPP = r"https?://(?:wa\.me/[1-9]\d{6,14}|api\.whatsapp\.com/send\?phone=[1-9]\d{6,14})(?![\w/?&=])"
PUBLIC_CONTACT = re.compile(r"(?:(?:my|our|business|booking|work|public)\s+(?:contact|e-?mail|phone|mobile|whatsapp)|(?:contact|e-?mail|call|message|reach)\s+(?:me|us)|(?:enquiries|inquiries|bookings))\s*(?:(?:at|on|via)\s+)?[:=-]?\s*", re.I)
OWNED_LINK = re.compile(r"\b(?:my|our|official)\s+(?:LinkedIn|Instagram|X|Twitter|YouTube|Facebook|Threads)(?:\s+(?:profile|channel|page))?\s*[:=-]\s*(https?://[^\s<>]+)", re.I)


def published_contacts(snippet):
    found = []
    for cue in PUBLIC_CONTACT.finditer(snippet):
        after = snippet[cue.end():]
        if match := re.match(EMAIL, after):
            try:
                address = validate_email(match[0], check_deliverability=False).normalized
            except EmailNotValidError:
                continue
            found.append(Link(platform="Email", link="mailto:" + address))
        elif match := re.match(WHATSAPP, after, re.I):
            digits = re.search(r"\d+$", match[0])[0]
            found.append(Link(platform="WhatsApp", link="https://wa.me/" + digits))
        elif match := re.match(PHONE, after):
            digits = re.sub(r"\D", "", match[0])
            if 7 <= len(digits) <= 15 and len(set(digits)) > 1:
                found.append(Link(platform="Phone", link="tel:+" + digits))
    return found


@dataclass
class Candidate:
    prospect: Prospect
    primary: str
    references: set[str]


def name_key(name):
    # Normalize accents, honorifics and punctuation without accepting substring matches.
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch))
    plain = re.sub(r"^(?:(?:dr|prof|mr|mrs|ms)\.?\s+)+", "", plain, flags=re.I)
    return normalize(plain)


def named_profile(hit, query):
    primary = profile_link(hit.url)
    if not primary or (primary.platform == "LinkedIn" and "/company/" in primary.link):
        return None
    name = identity(hit.title)
    if not name:
        return None
    url = urlsplit(primary.link)
    handle = unquote(url.path.rstrip("/").rsplit("/", 1)[-1]).removeprefix("@")
    if query.startswith("@"):
        if primary.platform == "Google" or handle.casefold() != query[1:].casefold():
            return None
    elif name_key(name) != name_key(query):
        return None
    if re.search(r"\b(?:fan (?:page|account|club)|parody account|impersonation)\b", hit.title + " " + hit.snippet, re.I):
        return None
    if primary.platform == "Google":
        # A first-party homepage needs an ownership cue or a domain matching the person's name.
        domain_label = (url.hostname or "").removeprefix("www.").split(".")[0]
        if name_key(name).replace(" ", "") != domain_label.replace("-", "") and not re.search(
                r"\b(?:official (?:site|website)|my (?:site|website)|I am|I'm)\b", hit.title + " " + hit.snippet, re.I):
            return None
    candidate = from_profile(hit, primary, name, None)
    description = " ".join(hit.snippet.split())
    if description:
        candidate.prospect.description = description[:340]
    return candidate


def extract(hit, intent):
    primary = profile_link(hit.url)
    name = identity(hit.title)
    if not primary or not name:
        return None
    # Ignore title display names when testing the actual biography/role evidence.
    bio = normalize(hit.title[len(name):] + " " + hit.snippet)
    if not all(any(supports(bio, phrase) for phrase in group) for group in intent.requirements):
        return None
    is_company_route = "/company/" in primary.link and primary.platform == "LinkedIn"
    is_person_route = "/in/" in primary.link and primary.platform == "LinkedIn"
    if intent.target_type == "individual":
        if is_company_route or re.search(r"\b(?:inc|llc|ltd|agency|company|club|association|studios?|academy|foundation)\b", name, re.I):
            return None
        if not is_person_route and not re.search(r"\b(?:I(?:'m| am)|my|me|founder|owner|fan|player|enthusiast|coach|artist|creator)\b", hit.snippet, re.I):
            return None
    if intent.target_type == "business" and (is_person_route or not (
            is_company_route or re.search(r"\b(?:we|our|company|agency|shop|studio|restaurant|business|team)\b", name + " " + hit.snippet, re.I))):
        return None
    if primary.platform == "Google" and not re.search(r"\b(?:official|my|our|I am|I'm|we are)\b", hit.title + " " + hit.snippet, re.I):
        return None
    geo = intent.location
    place = geo.city or geo.state or geo.country
    location = None
    if place:
        # Use a spelling actually seen on the source. Do not append inferred countries.
        location = next((p for p in [place, *geo.aliases] if supports(bio, p)), None)
        if location is None:
            return None
    return from_profile(hit, primary, name, location)


def from_profile(hit, primary, name, location):
    links = [primary, *published_contacts(hit.snippet)]
    refs = set()
    for raw in OWNED_LINK.findall(hit.snippet):
        ref = profile_link(raw.rstrip(".,);]"))
        if ref and ref.platform != "Google":
            refs.add(ref.link)
    return Candidate(Prospect(name=name, location=location, social_link=links), primary.link, refs)


def consolidate(candidates):
    # Identity edges require an indexed canonical URL or a same-name explicit self-link.
    parents = list(range(len(candidates)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    by_url = {}
    for i, candidate in enumerate(candidates):
        if candidate.primary in by_url:
            parents[root(i)] = root(by_url[candidate.primary])
        else:
            by_url[candidate.primary] = i
    for i, candidate in enumerate(candidates):
        for url in candidate.references:
            j = by_url.get(url)
            if j is not None and normalize(candidate.prospect.name) == normalize(candidates[j].prospect.name):
                parents[root(i)] = root(j)
    groups = {}
    for i, candidate in enumerate(candidates):
        p = candidate.prospect
        group = groups.setdefault(root(i), Prospect(name=p.name, location=p.location, social_link=[]))
        if p.description and not group.description:
            group.description = p.description
        for link in p.social_link:
            if link not in group.social_link:
                group.social_link.append(link)
    return list(groups.values())
