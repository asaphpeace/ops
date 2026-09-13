"""Fetches and caches real new-feature entries from releasenotes.dataloy.com
— the public GitBook site's master-release "Synopsis" pages. Patch releases
(8.30.1, 8.30.2...) carry bug fixes only, confirmed live against the real
site; feature content lives specifically at master-release (MAJOR.MINOR)
boundaries, which is the right anchor for "did this version jump cross a
real feature shift."

Confirmed live before writing this parser: the container's outbound network
reaches this public site fine (a separate question from the earlier,
unrelated finding that customer-tenant DNS isn't reachable from this
sandbox — this is a public GitBook site, not a private tenant). Confirmed
the real markdown structure via a direct fetch of master-release-8.30's
page: a `{% tab title="Synopsis" %}` block containing `####`-heading
categories, each followed by a `<mark ...>**VMS-XXXXX — Title**</mark>`
line and a description paragraph.

The site's own index admits older versions "sometimes use inconsistent
directory structures" — _fetch_master_release_markdown() tries a small set
of real, confirmed URL shapes and treats every failure as skippable, never
fatal. A version is only fetched once, ever, and never re-fetched once it
has any cached rows — a published master release's content doesn't change
after the fact."""
import html
import logging
import re

import httpx
from sqlalchemy import select

from app.models.release_note_feature import ReleaseNoteFeature

logger = logging.getLogger(__name__)

# Both confirmed live this session — 8.30 uses the subdirectory form,
# 8.31 does not. Tried in order, first success wins.
_URL_CANDIDATES = [
    "https://releasenotes.dataloy.com/master-release-{v}/master-release-{v}.md",
    "https://releasenotes.dataloy.com/master-release-{v}.md",
]

_SYNOPSIS_BLOCK = re.compile(r'\{%\s*tab title="Synopsis"\s*%\}(.*?)\{%\s*endtab\s*%\}', re.DOTALL)
_HEADING = re.compile(r"^(#{3,4})\s+(.+)$", re.MULTILINE)

# Deliberately NOT anchored to the <mark> tag — confirmed live this varies
# by version (8.30 wraps the bold ticket+title in <mark>...</mark>, 8.24
# uses a plain bold bullet with no <mark> at all, 8.29 puts the bold
# ticket+title directly IN the #### heading itself with the category one
# level up at ###). The one consistent real signal across every version
# checked is the bold markdown itself: "**VMS-XXXXX — Title**". A single
# heading's body can also hold MORE THAN ONE feature (confirmed on 8.24 —
# multiple bullets under one "####" heading), so this is used with
# finditer(), not search().
_FEATURE_MARK = re.compile(r'\*\*\s*([A-Z]+-\d+)\s*[—–-]+\s*(.+?)\*\*', re.DOTALL)

# Fallback for a real, confirmed 5th layout (8.15): the ticket ID gets its
# OWN short bold span that closes right after the dash (often with nothing
# but an HTML space entity inside), and the real title lives in a
# SEPARATE, adjacent bold/mark span right after — e.g.
# "**VMS-20925 —&#x20;**<mark>**De-Bunkering Now Supported**</mark>".
# Used only when the primary match's own title text turns out empty.
_NEXT_BOLD_SPAN = re.compile(r'(?:<mark[^>]*>)?\s*\*\*(.+?)\*\*', re.DOTALL)


def _clean_markdown(text: str) -> str:
    """Strip the GitBook/markdown noise (bold markers, HTML entities, extra
    whitespace) down to plain, readable text — good enough for an Ollama
    prompt and a UI description, not a full markdown renderer. html.unescape()
    handles every numeric/named entity generically (confirmed live: GitBook
    uses at least &#x200B; and &#x20; — a real bug found by testing found
    the earlier ad hoc single-entity replace left &#x20; as a literal
    visible artifact in a stored title)."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("**", "").replace("*", "")
    text = html.unescape(text).replace("\\", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _resolve_title(raw_title: str, tail: str) -> str:
    """raw_title is the primary regex's own captured group; tail is the
    text immediately following the match, searched only when raw_title
    cleans to nothing real."""
    cleaned = _clean_markdown(raw_title)
    if cleaned:
        return cleaned
    fallback = _NEXT_BOLD_SPAN.search(tail[:300])
    return _clean_markdown(fallback.group(1)) if fallback else cleaned


def _parse_synopsis(markdown: str) -> list[dict]:
    """Walks every ### / #### heading in document order, tracking the most
    recent ### as the running category (8.29's shape) while also handling
    a #### heading that IS the category (8.30/8.24's shape). A heading
    whose own text carries a bold "TICKET — Title" is itself a feature
    (8.29); otherwise its body is scanned for one or more bold marks
    (8.30/8.24) under that heading as the category."""
    match = _SYNOPSIS_BLOCK.search(markdown)
    if not match:
        return []
    block = match.group(1)

    headings = list(_HEADING.finditer(block))
    features = []
    current_category: str | None = None

    for i, h in enumerate(headings):
        level, raw_heading = h.group(1), h.group(2)
        body_start = h.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(block)
        body = block[body_start:body_end]

        heading_feature = _FEATURE_MARK.search(raw_heading)
        if heading_feature:
            ticket_id = heading_feature.group(1)
            title = _resolve_title(heading_feature.group(2), raw_heading[heading_feature.end():] + body)
            features.append({
                "ticket_id": ticket_id, "title": title, "category": current_category,
                "description": _clean_markdown(body)[:600],
            })
            continue

        if len(level) == 3:
            current_category = _clean_markdown(raw_heading)
            continue

        category = _clean_markdown(raw_heading)
        matches = list(_FEATURE_MARK.finditer(body))
        for idx, feature_match in enumerate(matches):
            ticket_id = feature_match.group(1)
            # Description runs from the end of this feature's bold title to
            # the start of the NEXT feature under the same heading (if any)
            # — never bleeds into a sibling feature's own description.
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
            title = _resolve_title(feature_match.group(2), body[feature_match.end():end])
            description = _clean_markdown(body[feature_match.end():end])[:600]
            features.append({
                "ticket_id": ticket_id, "title": title, "category": category, "description": description,
            })
    return features


# CONFIRMED UNRELIABLE — DO NOT WIRE THIS BACK INTO refresh_release_notes_cache().
#
# GitBook's own documentation-query interface (llms.txt advertises it) looked
# like a promising fallback for versions the fast regex scraper can't parse:
# in two isolated single-version tests (8.30, 8.10) it returned clean,
# correctly-titled, correctly-scoped answers — 8.10 alone recovered 16 real
# features the regex parser missed entirely.
#
# But run across a real batch of ~20 versions in sequence, it produced
# genuine cross-version data contamination: three real features already
# confirmed (via direct page fetch) to belong to master-release-8.31 —
# VMS-24931, VMS-25144, VMS-25354 — came back attributed to FOUR different
# WRONG versions each (8.5, 8.11, 8.12, 8.16), none of them 8.31. 11 distinct
# features total showed this pattern. The `ask` endpoint does not reliably
# scope its answer to the one page/version in the URL — it appears to pull
# in content from elsewhere on the site, especially when queried repeatedly
# with the same prompt wording in a short window (likely a GitBook-side
# answer cache keyed loosely on the question text, not the full URL).
#
# All ~111 rows this produced were found and purged from
# release_note_features on 2026-09-04 after the contamination was caught by
# a downstream uniqueness-constraint failure (a lucky catch — the versions
# that only got ONE wrong feature, with no collision, would have looked
# completely clean and silently misattributed a real feature to the wrong
# release). Given this feeds "which version introduced this, does this
# customer need training on it," a wrong-but-confident answer is worse than
# an honest gap — versions the regex parser can't cover stay empty rather
# than risk this again. Left in the file, unwired, as a record of what was
# tried and why it was rejected — do not re-enable without a materially
# different validation approach (e.g. cross-checking every ask-sourced
# ticket_id against every OTHER cached version before trusting it).
_ASK_PROMPT = (
    "List every new feature in this release as a markdown bullet list. For each, "
    "bold the ticket ID, then a dash, then the feature title, then in parentheses "
    "the category. If there are no new features, output exactly: NONE"
)
_ASK_FEATURE_LINE = re.compile(
    r'\*\*\s*([A-Z]+)\s*-\s*(\d+)\s*\*\*\s*[-–—]\s*(.+?)\.?\s*\(([^)]+)\)', re.MULTILINE,
)


async def _fetch_via_ask(version: str) -> list[dict]:
    """DO NOT CALL — see the CONFIRMED UNRELIABLE note above this function's
    constants. Kept only as a record of what was tried."""
    for template in _URL_CANDIDATES:
        url = template.format(v=version)
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.get(url, params={"ask": _ASK_PROMPT})
            text = resp.text.strip()
            if resp.status_code != 200 or "# Page Not Found" in text or not text:
                continue
            if re.search(r"^\s*NONE\s*$", text, re.MULTILINE):
                return []
            features = []
            for m in _ASK_FEATURE_LINE.finditer(text):
                ticket_id = f"{m.group(1)}-{m.group(2)}"
                features.append({
                    "ticket_id": ticket_id, "title": _clean_markdown(m.group(3)),
                    "category": _clean_markdown(m.group(4)), "description": None,
                })
            if features:
                return features
        except httpx.HTTPError as exc:
            logger.info("ask-fallback fetch failed for %s: %s", url, exc)
    return []


async def _fetch_master_release_markdown(version: str) -> tuple[str, str] | None:
    """Returns (markdown, source_url) on success, None if every candidate
    URL failed — a real, expected outcome for older/inconsistent versions,
    not an error to surface loudly.

    GitBook returns a real, well-formed "Page Not Found" document with a
    200 status (confirmed live on 8.31's subdirectory form) — a bare
    status-code check silently accepts this as success. Every candidate
    is checked against that soft-404 signature before being trusted."""
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for template in _URL_CANDIDATES:
            url = template.format(v=version)
            try:
                resp = await client.get(url)
                text = resp.text.strip()
                if resp.status_code == 200 and text and "# Page Not Found" not in text:
                    return text, url
            except httpx.HTTPError as exc:
                logger.info("release notes fetch failed for %s: %s", url, exc)
    return None


def master_releases_between(from_version: str, to_version: str) -> list[str]:
    """Real master-release (MAJOR.MINOR) strings strictly after from_version
    up to and including to_version — e.g. "8.24" -> "8.30" yields
    8.25..8.30. Every real version seen this session stays within major
    version 8, so a flat minor-integer range is honest; a major-version
    change (e.g. 8.x -> 9.x) isn't handled and simply yields nothing rather
    than guessing a wrong range."""
    num = re.compile(r"\d+")

    def _major_minor(v: str) -> tuple[int, int] | None:
        parts = num.findall(v)
        return (int(parts[0]), int(parts[1])) if len(parts) >= 2 else None

    fm = _major_minor(from_version)
    tm = _major_minor(to_version)
    if not fm or not tm or fm[0] != tm[0] or fm >= tm:
        return []
    return [f"{fm[0]}.{minor}" for minor in range(fm[1] + 1, tm[1] + 1)]


async def refresh_release_notes_cache(db, versions: list[str]) -> dict:
    """Fetches only versions with zero cached rows — cheap and incremental
    on repeat calls. Returns real per-version outcomes so a caller (or the
    person clicking the button) can see exactly what worked, not just a
    bare success count."""
    already_cached = set(
        (await db.execute(select(ReleaseNoteFeature.version).distinct())).scalars().all()
    )
    to_fetch = [v for v in versions if v not in already_cached]

    fetched: list[str] = []
    empty: list[str] = []
    failed: list[str] = []

    for version in to_fetch:
        result = await _fetch_master_release_markdown(version)
        if result is None:
            failed.append(version)
            continue
        markdown, source_url = result
        features = _parse_synopsis(markdown)
        if not features:
            # Confirmed real gap in the regex parser (older/variant page
            # layouts) — NOT filled by a fallback. The obvious candidate
            # (GitBook's own "ask" query interface) was tried and rejected:
            # see the CONFIRMED UNRELIABLE note on _fetch_via_ask() above —
            # it produced real cross-version data contamination in testing.
            # An honest empty result here is safer than a confident wrong one.
            empty.append(version)
            continue
        for f in features:
            db.add(ReleaseNoteFeature(
                version=version, ticket_id=f["ticket_id"], title=f["title"],
                category=f["category"], description=f["description"], source_url=source_url,
            ))
        fetched.append(version)

    await db.commit()
    return {
        "already_cached": sorted(already_cached),
        "fetched": fetched, "empty": empty, "failed": failed,
    }
