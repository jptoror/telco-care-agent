"""Grounding verifier: the LLM proposes an answer, deterministic code decides whether to trust it.

Every money amount in the answer must be traceable to a number returned by a tool during the session.
"""

import re
from decimal import Decimal, InvalidOperation

# "$49.50", "USD 49,50", "49.50 dolares", "US$ 5". Plain integers without a currency mark are ignored
# (they are usually counts, days or speeds). Billing is in USD, so any other currency is always unsupported.
_MONEY = re.compile(
    r"(?:US\$|USD|\$)\s?(\d{1,6}(?:[.,]\d{1,2})?)"
    r"|(\d{1,6}[.,]\d{2})\s?(?:USD|US\$|d[oó]lares|dollars)?",
    re.IGNORECASE,
)
_WRONG_CURRENCY = re.compile(r"€|\bEUR\b|\beuros?\b|\bCOP\b|\bpesos\b|£|\bMXN\b", re.IGNORECASE)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _dec(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def amounts_in(text: str) -> set[Decimal]:
    out = set()
    for m in _MONEY.finditer(text):
        d = _dec(m.group(1) or m.group(2))
        if d is not None:
            out.add(d)
    return out


def numbers_in(text: str) -> set[Decimal]:
    return {d for d in (_dec(n) for n in _NUMBER.findall(text)) if d is not None}


class Evidence:
    """Numbers seen in tool results. Absolute values too, so '-49.50' supports '49.50'."""

    def __init__(self):
        self.numbers: set[Decimal] = set()

    def add_text(self, text: str):
        for n in numbers_in(text):
            self.numbers.add(n)
            self.numbers.add(abs(n))

    def unsupported(self, answer: str) -> list[str]:
        bad = [str(a) for a in sorted(amounts_in(answer)) if a not in self.numbers]
        if _WRONG_CURRENCY.search(answer):
            bad.append("non-USD currency")
        return bad
