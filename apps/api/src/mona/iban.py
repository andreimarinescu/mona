import hashlib
import hmac
import re
import unicodedata

IBAN_PATTERN = re.compile(r"\b[A-Z]{2}[0-9]{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b")
_LENGTHS = {"FR": 27, "RO": 24}


def normalize_iban(iban: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", iban.upper())


def is_valid_iban(iban: str) -> bool:
    """Country length (FR 27, RO 24, others 15–34) and the ISO 13616 mod-97 check."""
    s = normalize_iban(iban)
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[0-9A-Z]+", s):
        return False
    expected = _LENGTHS.get(s[:2])
    if (len(s) != expected) if expected else not 15 <= len(s) <= 34:
        return False
    digits = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(digits) % 97 == 1


def iban_hash(iban: str, key: bytes) -> str:
    """C1 §2.4: hex HMAC-SHA256 of the normalised IBAN under `settings.iban_salt`."""
    return hmac.new(key, normalize_iban(iban).encode(), hashlib.sha256).hexdigest()


def iban_last4(iban: str) -> str:
    return normalize_iban(iban)[-4:]


def iban_candidates(text: str) -> list[str]:
    """C5 §4.3: valid IBANs found in page text, normalised. Never log the result."""
    upper = unicodedata.normalize("NFKC", text).upper()
    found = (normalize_iban(m.group(0)) for m in IBAN_PATTERN.finditer(upper))
    return list(dict.fromkeys(c for c in found if is_valid_iban(c)))
