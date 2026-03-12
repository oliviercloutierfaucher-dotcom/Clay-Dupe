"""Email pattern detection, learning, and candidate generation."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data.database import Database
    from quality.verification import EmailVerifier


# ---------------------------------------------------------------------------
# Nickname mappings (40+ entries)
# ---------------------------------------------------------------------------

NICKNAMES: dict[str, list[str]] = {
    "bob": ["robert"],
    "rob": ["robert"],
    "bobby": ["robert"],
    "robbie": ["robert"],
    "bill": ["william"],
    "will": ["william"],
    "willy": ["william"],
    "billy": ["william"],
    "liam": ["william"],
    "mike": ["michael"],
    "mikey": ["michael"],
    "jim": ["james"],
    "jimmy": ["james"],
    "jamie": ["james"],
    "joe": ["joseph"],
    "joey": ["joseph"],
    "dick": ["richard"],
    "rick": ["richard"],
    "rich": ["richard"],
    "ricky": ["richard"],
    "dave": ["david"],
    "davy": ["david"],
    "dan": ["daniel"],
    "danny": ["daniel"],
    "tom": ["thomas"],
    "tommy": ["thomas"],
    "tony": ["anthony"],
    "steve": ["steven", "stephen"],
    "steph": ["stephanie", "stephen"],
    "chris": ["christopher", "christine", "christina"],
    "matt": ["matthew"],
    "matty": ["matthew"],
    "pat": ["patrick", "patricia"],
    "patty": ["patricia"],
    "paddy": ["patrick"],
    "nick": ["nicholas"],
    "nicky": ["nicholas"],
    "alex": ["alexander", "alexandra"],
    "al": ["albert", "alan", "alexander"],
    "ed": ["edward", "edwin"],
    "eddie": ["edward"],
    "ted": ["theodore", "edward"],
    "teddy": ["theodore"],
    "andy": ["andrew"],
    "drew": ["andrew"],
    "charlie": ["charles"],
    "chuck": ["charles"],
    "ben": ["benjamin"],
    "benny": ["benjamin"],
    "sam": ["samuel", "samantha"],
    "sammy": ["samuel"],
    "jack": ["john", "jackson"],
    "johnny": ["john"],
    "jon": ["jonathan"],
    "kate": ["katherine", "catherine"],
    "kathy": ["katherine", "catherine"],
    "katie": ["katherine", "catherine"],
    "beth": ["elizabeth", "bethany"],
    "liz": ["elizabeth"],
    "lizzy": ["elizabeth"],
    "betty": ["elizabeth"],
    "jenny": ["jennifer"],
    "jen": ["jennifer"],
    "sue": ["susan", "suzanne"],
    "susie": ["susan"],
    "meg": ["megan", "margaret"],
    "peggy": ["margaret"],
    "maggie": ["margaret"],
    "margie": ["margaret"],
    "barb": ["barbara"],
    "debbie": ["deborah"],
    "deb": ["deborah"],
    "becky": ["rebecca"],
    "vicky": ["victoria"],
    "vic": ["victor", "victoria"],
    "larry": ["lawrence"],
    "jerry": ["gerald", "jerome"],
    "harry": ["harold", "henry"],
    "hank": ["henry"],
    "frank": ["franklin", "francis"],
    "fred": ["frederick"],
    "freddy": ["frederick"],
    "pete": ["peter"],
    "greg": ["gregory"],
    "jeff": ["jeffrey"],
    "phil": ["philip"],
    "ray": ["raymond"],
    "ron": ["ronald"],
    "ronnie": ["ronald"],
    "doug": ["douglas"],
    "ken": ["kenneth"],
    "kenny": ["kenneth"],
    "wes": ["wesley"],
    "walt": ["walter"],
    "abe": ["abraham"],
    "stu": ["stuart"],
    "nate": ["nathan", "nathaniel"],
    "leo": ["leonard", "leonardo"],
}

# Reverse lookup: formal name -> list of nicknames
FORMAL_TO_NICKNAMES: dict[str, list[str]] = {}
for _nick, _formals in NICKNAMES.items():
    for _formal in _formals:
        FORMAL_TO_NICKNAMES.setdefault(_formal, []).append(_nick)


# ---------------------------------------------------------------------------
# Pattern templates ordered by B2B frequency
# ---------------------------------------------------------------------------

PATTERN_TEMPLATES: list[str] = [
    "{first}.{last}",       # ~45%
    "{f}{last}",            # ~15%
    "{first}{last}",        # ~10%
    "{first}",              # ~8%
    "{f}.{last}",           # ~7%
    "{last}.{first}",       # ~5%
    "{first}_{last}",       # ~3%
    "{last}{f}",            # ~2%
    "{last}",               # ~1%
    "{first}-{last}",       # <1%
    "{last}_{first}",       # <1%
]

PATTERN_FREQUENCY: dict[str, float] = {
    "{first}.{last}":  0.45,
    "{f}{last}":       0.15,
    "{first}{last}":   0.10,
    "{first}":         0.08,
    "{f}.{last}":      0.07,
    "{last}.{first}":  0.05,
    "{first}_{last}":  0.03,
    "{last}{f}":       0.02,
    "{last}":          0.01,
    "{first}-{last}":  0.005,
    "{last}_{first}":  0.005,
}


# ---------------------------------------------------------------------------
# Suffix patterns to strip from names
# ---------------------------------------------------------------------------

_SUFFIX_RE = re.compile(
    r",?\s+(?:Jr\.?|Sr\.?|III|II|IV|V|PhD\.?|Ph\.D\.?|MD\.?|M\.D\.?|Esq\.?|CPA|MBA|DDS|DO|JD|DVM|RN)$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def normalize_ascii(text: str) -> str:
    """NFKD decomposition + strip combining marks + lowercase.

    Examples:
        Jose -> jose, Garcia -> garcia, Muller -> muller, Nono -> nono
    """
    # Decompose into base characters + combining marks
    nfkd = unicodedata.normalize("NFKD", text)
    # Keep only non-combining characters (category != Mn)
    stripped = "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")
    return stripped.lower()


def parse_name(first_name: str, last_name: str) -> dict:
    """Handle edge cases and return name variants.

    - Strip suffixes: Jr, Sr, III, II, IV, PhD, MD, etc.
    - Handle hyphens: Watson-Jones -> variants [watsonjones, watson, jones]
    - Handle single chars: just use as-is for initial
    - Build nickname variants from NICKNAMES/FORMAL_TO_NICKNAMES

    Returns:
        {
            "first": str (normalized),
            "last": str (normalized),
            "f": str (first initial),
            "first_variants": list[str] (includes nicknames),
            "last_variants": list[str] (includes hyphen variants),
        }
    """
    # Strip suffixes
    first_clean = _SUFFIX_RE.sub("", first_name.strip())
    last_clean = _SUFFIX_RE.sub("", last_name.strip())

    # Normalize to ASCII lowercase
    first = normalize_ascii(first_clean)
    last = normalize_ascii(last_clean)

    # Strip any remaining non-alpha characters (except hyphens handled below)
    first = re.sub(r"[^a-z-]", "", first)
    last = re.sub(r"[^a-z-]", "", last)

    # First initial
    f = first[0] if first else ""

    # --- First name variants ---
    first_variants: list[str] = [first] if first else []

    # Nickname -> formal lookups
    if first in NICKNAMES:
        for formal in NICKNAMES[first]:
            if formal not in first_variants:
                first_variants.append(formal)

    # Formal -> nickname lookups
    if first in FORMAL_TO_NICKNAMES:
        for nick in FORMAL_TO_NICKNAMES[first]:
            if nick not in first_variants:
                first_variants.append(nick)

    # --- Last name variants ---
    last_variants: list[str] = [last] if last else []

    if "-" in last:
        # e.g. watson-jones -> [watson-jones, watsonjones, watson, jones]
        joined = last.replace("-", "")
        parts = last.split("-")
        for variant in [joined] + parts:
            if variant and variant not in last_variants:
                last_variants.append(variant)

    return {
        "first": first,
        "last": last,
        "f": f,
        "first_variants": first_variants,
        "last_variants": last_variants,
    }


def _expand_pattern(template: str, name_info: dict) -> list[str]:
    """Expand a pattern template with name variants.

    For example, ``{first}.{last}`` with first="john", last="doe" yields
    ``["john.doe"]``.  When nickname variants exist for first="bob" the
    result would be ``["bob.doe", "robert.doe"]``.

    Returns a deduplicated list of local-part strings.
    """
    results: list[str] = []

    first_variants = name_info.get("first_variants", [name_info["first"]])
    last_variants = name_info.get("last_variants", [name_info["last"]])

    for fv in first_variants:
        for lv in last_variants:
            # Build per-variant name_info with correct initial
            fv_initial = fv[0] if fv else ""
            try:
                local = template.format(
                    first=fv,
                    last=lv,
                    f=fv_initial,
                )
            except (KeyError, IndexError):
                continue

            if local and local not in results:
                results.append(local)

    return results


def detect_pattern(email: str, first_name: str, last_name: str) -> Optional[str]:
    """Given a known email + person name, reverse-engineer the pattern template.

    Steps:
        1. Normalize names (lowercase, strip accents).
        2. Extract local part (before @).
        3. For each pattern template, expand it with name parts and check match.
        4. Also try nickname variants (bob -> robert, etc.).
        5. Return matching template string or ``None``.
    """
    if not email or "@" not in email:
        return None

    local_part = email.split("@")[0].lower()
    name_info = parse_name(first_name, last_name)

    for template in PATTERN_TEMPLATES:
        expansions = _expand_pattern(template, name_info)
        if local_part in expansions:
            return template

    return None


def compute_confidence(pattern_counts: dict[str, int]) -> dict[str, float]:
    """Bayesian confidence from observation counts.

    Formula: ``confidence = 1 - (1 / (1 + count))^2``

    Returns ``{pattern: confidence}`` for each pattern.
    """
    result: dict[str, float] = {}
    for pattern, count in pattern_counts.items():
        result[pattern] = 1.0 - (1.0 / (1 + count)) ** 2
    return result


def generate_candidates(
    first_name: str,
    last_name: str,
    domain: str,
    known_patterns: dict[str, float],
) -> list[dict]:
    """Generate email candidates from known domain patterns.

    Filters to patterns with confidence >= 0.5.  For each pattern, expand
    with name parts and build full email addresses.

    Returns ``[{email, pattern, confidence, is_primary}, ...]`` sorted by
    confidence descending.  ``is_primary`` is ``True`` only for the highest
    confidence candidate.
    """
    name_info = parse_name(first_name, last_name)
    candidates: list[dict] = []

    for pattern, confidence in known_patterns.items():
        if confidence < 0.5:
            continue
        expansions = _expand_pattern(pattern, name_info)
        if expansions:
            # Use the first (primary) expansion for the candidate
            email = f"{expansions[0]}@{domain}"
            candidates.append({
                "email": email,
                "pattern": pattern,
                "confidence": confidence,
                "is_primary": False,
            })

    # Sort by confidence descending
    candidates.sort(key=lambda c: c["confidence"], reverse=True)

    # Mark highest confidence as primary
    if candidates:
        candidates[0]["is_primary"] = True

    return candidates


def generate_fallback_candidates(
    first_name: str,
    last_name: str,
    domain: str,
) -> list[dict]:
    """When no domain patterns are known, use global frequency distribution.

    Generates top 5 most common patterns.  Confidence is
    ``frequency * 0.5`` (halved since we are guessing).

    Returns same format as :func:`generate_candidates`.
    """
    name_info = parse_name(first_name, last_name)

    # Sort templates by frequency descending and take top 5
    sorted_templates = sorted(
        PATTERN_FREQUENCY.items(), key=lambda kv: kv[1], reverse=True
    )[:5]

    candidates: list[dict] = []
    for template, frequency in sorted_templates:
        expansions = _expand_pattern(template, name_info)
        if expansions:
            email = f"{expansions[0]}@{domain}"
            confidence = frequency * 0.5
            candidates.append({
                "email": email,
                "pattern": template,
                "confidence": confidence,
                "is_primary": False,
            })

    # Already sorted by frequency (== confidence order), mark primary
    if candidates:
        candidates[0]["is_primary"] = True

    return candidates


# ---------------------------------------------------------------------------
# PatternEngine class
# ---------------------------------------------------------------------------

class PatternEngine:
    """Learns email patterns from successful lookups and generates candidates
    for future lookups at the same domain, potentially avoiding paid API calls
    entirely.
    """

    def __init__(self, db: Database, verifier: EmailVerifier):
        self.db = db
        self.verifier = verifier

    async def try_pattern_match(
        self,
        first_name: str,
        last_name: str,
        domain: str,
    ) -> Optional[str]:
        """Try to find an email via pattern detection + SMTP verification. FREE.

        Steps:
            1. Get known patterns for domain from DB.
            2. Compute confidence for each pattern.
            3. If best confidence >= 0.80 and sample_count >= 2: generate
               candidates.
            4. Check catch-all status (DB cache first, fall back to verifier).
            5. If not catch-all: SMTP verify top candidates.
            6. If catch-all + confidence >= 0.90: return best candidate
               unverified.
            7. Return email if found, ``None`` otherwise.
        """
        # Step 1: Retrieve known patterns from DB
        domain_patterns = await self.db.get_domain_patterns(domain)
        if not domain_patterns:
            # No known patterns — try fallback using global frequency
            return await self._try_fallback(first_name, last_name, domain)

        # Step 2: Build counts and compute confidence
        pattern_counts: dict[str, int] = {}
        sample_counts: dict[str, int] = {}
        for row in domain_patterns:
            pattern = row["pattern"]
            pattern_counts[pattern] = row.get("sample_count", 1)
            sample_counts[pattern] = row.get("sample_count", 1)

        confidences = compute_confidence(pattern_counts)

        # Step 3: Check if best confidence meets threshold
        if not confidences:
            return None

        best_pattern = max(confidences, key=confidences.get)
        best_confidence = confidences[best_pattern]
        best_sample_count = sample_counts.get(best_pattern, 0)

        if best_confidence < 0.80 or best_sample_count < 2:
            return None

        # Generate candidates from confident patterns
        candidates = generate_candidates(first_name, last_name, domain, confidences)
        if not candidates:
            return None

        # Step 4: Check catch-all status
        is_catch_all = await self.db.get_catch_all_status(domain)
        if is_catch_all is None:
            # Fall back to verifier detection
            is_catch_all = await self.verifier.detect_catch_all(domain)
            if is_catch_all is not None:
                await self.db.set_catch_all_status(domain, is_catch_all)

        # Step 5 & 6: Verify or return based on catch-all status
        if not is_catch_all:
            # Not a catch-all domain -- SMTP verify top candidates
            for candidate in candidates:
                verification = await self.verifier.verify(candidate["email"])
                if verification.get("valid"):
                    return candidate["email"]
            # None of the candidates verified
            return None
        else:
            # Catch-all domain -- can't verify via SMTP
            if best_confidence >= 0.90:
                # High enough confidence to return unverified
                return candidates[0]["email"]
            # Confidence too low for unverified guess on catch-all
            return None

    async def _try_fallback(
        self,
        first_name: str,
        last_name: str,
        domain: str,
    ) -> Optional[str]:
        """Fallback when no domain-specific patterns exist.

        Uses global frequency distribution to generate guesses.
        Only proceeds if the best candidate confidence >= 0.40.
        For non-catch-all domains, verifies via SMTP before returning.
        """
        candidates = generate_fallback_candidates(first_name, last_name, domain)
        if not candidates or candidates[0]["confidence"] < 0.40:
            return None

        # Check catch-all status
        is_catch_all = await self.db.get_catch_all_status(domain)
        if is_catch_all is None:
            is_catch_all = await self.verifier.detect_catch_all(domain)
            if is_catch_all is not None:
                await self.db.set_catch_all_status(domain, is_catch_all)

        if not is_catch_all:
            # Not catch-all — SMTP verify the best candidate
            for candidate in candidates:
                if candidate["confidence"] < 0.40:
                    break
                verification = await self.verifier.verify(candidate["email"])
                if verification.get("valid"):
                    return candidate["email"]
            return None

        # Catch-all — can't verify, return None (confidence too low for unverified guess)
        return None

    async def learn_pattern(
        self,
        email: str,
        first_name: str,
        last_name: str,
        domain: str,
    ) -> None:
        """After a successful lookup, learn the pattern.

        1. Call :func:`detect_pattern` to determine which template matches.
        2. If a pattern is found, store in DB via ``db.record_pattern``.
        """
        pattern = detect_pattern(email, first_name, last_name)
        if pattern is None:
            return

        # Compute a simple confidence from the pattern's known frequency
        # as a starting point; the DB will track sample_count for Bayesian
        # confidence on subsequent lookups.
        base_confidence = PATTERN_FREQUENCY.get(pattern, 0.01)
        await self.db.record_pattern(domain, pattern, email, base_confidence)
