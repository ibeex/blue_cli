"""Composition identities from catalogue metadata, independent of recording artists."""

import re
import unicodedata

WorkKey = tuple[str, str, str]
CatalogueAliases = dict[WorkKey, WorkKey]

_KIND = (
    r"concert(?:o|os|i)\s+for\s+(?:piano|violin|cello|clarinet|flute|oboe|horn|trumpet)"
    r"|(?:(?:piano|violin|cello|clarinet|flute|oboe|horn|trumpet)\s+)?concert(?:o|os|i)"
    r"|symphon(?:y|ies)|(?:(?:piano|violin|cello)\s+)?sonatas?"
    r"|(?:string\s+)?quartets?|(?:piano\s+)?trios?|suites?"
)
_CATALOGUE = r"\b(op|bwv|k|kv|d|hwv|rv)\.?\s*(\d+(?:\s*/\s*\d+)?)"


def _normalize(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold()) if char.isalnum()
    )


def _kind(text: str) -> str:
    text = text.casefold()
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


def wants_multiple_recordings(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(?:different|multiple|several|compare|various)\b.{0,50}"
            r"\b(?:recordings|interpretations|performances|versions)\b",
            prompt,
            re.IGNORECASE,
        )
    )
