"""Composition identities from catalogue metadata, independent of recording artists."""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

WorkKey = tuple[str, str, str]
CatalogueAliases = dict[WorkKey, WorkKey]

_INSTRUMENTS = (
    r"double bass|cor anglais|harpsichord|percussion|saxophone|trombone"
    r"|piano|violin|cello|viola|clarinet|flute|oboe|horn|trumpet|tuba|bassoon|harp"
    r"|guitar|organ|recorder"
)
_KIND = (
    rf"concert(?:o|os|i)\s+for\s+(?:{_INSTRUMENTS})"
    rf"|(?:(?:{_INSTRUMENTS})\s+)?concert(?:o|os|i)"
    r"|sinfoni(?:a|as)|symphon(?:y|ies)"
    rf"|(?:(?:{_INSTRUMENTS})\s+)?sonatas?"
    r"|(?:string\s+)?quartets?|(?:piano\s+)?trios?|suites?"
)
_CATALOGUE = r"\b(op|bwv|k|kv|d|hwv|rv)\.?\s*(\d+(?:\s*/\s*\d+)?)"
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9}
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_EDITION_WORDS = frozenset(
    {
        "deluxe",
        "edition",
        "expanded",
        "remaster",
        "remastered",
        "anniversary",
        "bonus",
        "live",
        "version",
        "special",
        "collector",
        "limited",
        "highlights",
        "excerpts",
    }
)


@dataclass(frozen=True, slots=True)
class WorkSignature:
    """One recognised work in a release title, independent of recording artist."""

    composer: str
    kind: str
    label: str
    composer_label: str
    identifiers: frozenset[str] = frozenset()
    phrase: str = ""


def _normalize(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold()) if char.isalnum()
    )


def _kind(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"sinfoni(?:a|as)", "symphony", text)
    text = re.sub(r"symphon(?:y|ies)", "symphony", text)
    text = re.sub(r"concert(?:o|os|i)", "concerto", text)
    text = re.sub(r"concerto for (\w+)", r"\1 concerto", text)
    return re.sub(r"s\b", "", text)


def work_keys(
    text: str,
    composer: str = "",
    kind: str = "",
    aliases: CatalogueAliases | None = None,
) -> set[WorkKey]:
    keys: set[WorkKey] = set()
    for section in re.split(r";|\s+/\s+", text):
        match = re.search(rf"\b({_KIND})\b", section, re.IGNORECASE)
        if match:
            prefix = section[: match.start()].strip(" :,-")
            prefix = re.sub(r"^\d+\s*[.:-]?\s*", "", prefix)
            section_composer = (
                _normalize(prefix.split(":", 1)[0].split()[-1]) if prefix else composer
            )
            section_kind = _kind(match[1])
            if section_kind in {"concerto", "sonata", "quartet", "trio"} and kind.endswith(
                section_kind
            ):
                section_kind = kind
            suffix = section[match.end() :]
        else:
            section_composer, section_kind, suffix = composer, kind, section
        if not section_composer or not section_kind:
            continue
        numbers = (
            re.match(
                r"\s*(?:nos?\.?\s*|numbers?\s*|#\s*)?(\d+(?:\s*(?:&|and|,|/|[-–])\s*(?:no\.?\s*)?\d+)*)",
                suffix,
                re.IGNORECASE,
            )
            if match
            else None
        )
        values: list[int] = []
        if numbers:
            values = [int(value) for value in re.findall(r"\d+", numbers[1])]
            if re.search(r"[-–]", numbers[1]) and len(values) == 2:
                if 0 < values[0] <= values[1] <= 100:
                    values = list(range(values[0], values[1] + 1))
        numbered = {
            (section_composer, section_kind, str(number)) for number in values if number > 0
        }
        catalogue = {
            (section_composer, section_kind, _normalize(label.replace("kv", "k") + value))
            for label, value in re.findall(_CATALOGUE, suffix.casefold())
        }
        if aliases is not None and len(numbered) == 1:
            if any(key in aliases and aliases[key] not in numbered for key in catalogue):
                continue
            for key in catalogue:
                aliases.setdefault(key, next(iter(numbered)))
        keys.update(numbered or {(aliases or {}).get(key, key) for key in catalogue})
    return keys


def _identifiers(suffix: str, kind: str) -> set[str]:
    """Work numbers and catalogue numbers that follow a recognised work name."""
    suffix = suffix.strip()
    identifiers: set[str] = set()
    numbers = re.match(
        r"(?:nos?\.?\s*|numbers?\s*|#\s*)?"
        r"(\d+(?:\s*(?:&|and|,|/|[-\u2013])\s*(?:no\.?\s*)?\d+)*)",
        suffix,
        re.IGNORECASE,
    )
    if numbers:
        values = [int(value) for value in re.findall(r"\d+", numbers[1])]
        if re.search(r"[-\u2013]", numbers[1]) and len(values) == 2:
            start, end = values
            if 0 < start <= end <= 100:
                values = list(range(start, end + 1))
        identifiers.update(str(value) for value in values if value > 0)
    elif kind == "symphony":
        roman = re.match(r"(?:nos?\.?\s*|numbers?\s*|#\s*)?([ivx]+)\b", suffix.casefold())
        if roman and roman[1] in _ROMAN:
            identifiers.add(str(_ROMAN[roman[1]]))
    for label, value in re.findall(_CATALOGUE, suffix.casefold()):
        identifiers.add(_normalize(label.replace("kv", "k") + value))
    return identifiers


def _composer(head: str) -> tuple[str, str]:
    """Normalized surname and display name from a release credit heading."""
    words = head.split(":")[0].replace(",", " ").split()
    if not words:
        return "", ""
    if len(_normalize(words[-1])) <= 2 and len(words) > 1:
        return _normalize(words[0]), words[0]
    return _normalize(words[-1]), words[-1]


def _named_signature(section: str, inherited: str) -> WorkSignature | None:
    """Signature for a colon-separated work without a catalogue-style work name."""
    head, separator, tail = section.partition(":")
    if not separator:
        return None
    composer, composer_label = _composer(head)
    phrase = _normalize(tail)
    words = re.findall(r"[^\W\d_]+", tail.casefold())
    if not composer or len(phrase) < 5 or not words:
        return None
    if all(word in _EDITION_WORDS for word in words):
        return None
    return WorkSignature(composer, "", composer_label, composer_label, frozenset(), phrase)


def work_signatures(text: str) -> list[WorkSignature]:
    """Recognised works in a release or request, with the credited composer."""
    signatures: list[WorkSignature] = []
    inherited = ""
    for section in re.split(r";|\s+/\s+", text):
        section = section.strip()
        if not section:
            continue
        matches = list(re.finditer(rf"\b({_KIND})\b", section, re.IGNORECASE))
        if not matches:
            named = _named_signature(section, inherited)
            if named is not None:
                signatures.append(named)
                inherited = named.composer
            continue
        head = section[: matches[0].start()].strip(" :-,")
        composer_label = inherited
        composer = inherited
        if head:
            composer, composer_label = _composer(head)
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
            suffix = section[match.end() : end]
            label = " ".join(match[1].split())
            signatures.append(
                WorkSignature(
                    composer,
                    _kind(label),
                    label,
                    composer_label,
                    frozenset(_identifiers(suffix, _kind(label))),
                )
            )
        if composer:
            inherited = composer
    return signatures


def _composers_agree(left: str, right: str) -> bool:
    if not left:
        return True
    if not right:
        return False
    return left == right or SequenceMatcher(None, left, right).ratio() >= 0.85


def signature_matches(request: WorkSignature, title: str, artist: str = "") -> bool:
    """Whether a release title contains the requested work."""
    normalized_title = _normalize(title)
    credited = normalized_title + _normalize(artist)
    if not request.kind:
        return (
            bool(request.composer)
            and request.composer in credited
            and bool(request.phrase)
            and request.phrase in normalized_title
        )
    candidates = work_signatures(title)
    composer_seen = bool(
        request.composer
        and (
            request.composer in credited
            or any(_composers_agree(request.composer, item.composer) for item in candidates)
        )
    )
    if request.composer and not composer_seen:
        return False
    for candidate in candidates:
        if request.kind != candidate.kind:
            continue
        if not _composers_agree(request.composer, candidate.composer):
            continue
        if request.identifiers and candidate.identifiers:
            numeric_requested = {item for item in request.identifiers if item.isdigit()}
            numeric_found = {item for item in candidate.identifiers if item.isdigit()}
            if len(numeric_requested) > 1:
                if numeric_requested <= numeric_found:
                    return True
                continue
            if request.identifiers & candidate.identifiers:
                return True
            continue
        if request.identifiers:
            # Numberless titles cannot confirm a specific numbered work, except for
            # sets named by quantity ("Five Sinfonias").
            if _quantity(title) == len(request.identifiers):
                return True
            continue
        return True
    return False


def _quantity(text: str) -> int:
    for word in re.findall(r"[^\W\d_]+", text.casefold()):
        if word in _NUMBER_WORDS:
            return _NUMBER_WORDS[word]
        if word.isdigit() and int(word) <= 100:
            return int(word)
    return 0


def work_query(signature: WorkSignature, reverse: bool = False) -> str:
    """Short unpunctuated query for the work, e.g. "Rautavaara Symphony No. 8"."""
    if not signature.kind or not signature.composer_label or not signature.label:
        return ""
    label = re.sub(r"ies$", "y", signature.label)
    label = re.sub(r"(?<=[^s])s$", "", label)
    numeric = [identifier for identifier in signature.identifiers if identifier.isdigit()]
    if len(signature.identifiers) == 1 and len(numeric) == 1:
        label += f" No. {numeric[0]}"
    # Surnames rank better than full names, and Tidal weights leading tokens heavily.
    composer = signature.composer_label.split()[-1]
    return f"{label} {composer}" if reverse else f"{composer} {label}"


_ORDINALS = (
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
    r"|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th"
)
_QUANTITIES = r"\d+|one|two|three|four|five|six|seven|eight|nine|ten"
_WORK_NOUNS = (
    r"symphon\w*|concert\w*|sonat\w*|quartet\w*|trio\w*|suite\w*|opera\w*|ballet\w*"
    r"|oratorio\w*|requiem\w*|mass\w*|cantata\w*|prelude\w*|etude\w*|nocturne\w*"
    r"|waltz\w*|polonaise\w*|mazurka\w*|rhapsod\w*|overture\w*|fugue\w*"
)


def wants_work_set(prompt: str) -> bool:
    """True when the request enumerates a set of works, not a single named work."""
    return bool(
        re.search(
            r"\b(?:all|both|complete|entire|every)\b"
            rf"|\b(?:{_ORDINALS})\s+(?:{_QUANTITIES})\b"
            rf"|\b(?:{_QUANTITIES})\s+(?:{_WORK_NOUNS})\b"
            r"|\b\d+\s*[-\u2013]\s*\d+"
            r"|\b\d+\s*(?:&|and|,)\s*\d+",
            prompt,
            re.IGNORECASE,
        )
    )


def wants_multiple_recordings(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(?:different|multiple|several|compare|various)\b.{0,50}"
            r"\b(?:recordings|interpretations|performances|versions)\b",
            prompt,
            re.IGNORECASE,
        )
    )
