"""The YIELD-TRADE matching engine.

A match is scored 0 to 100 as a weighted blend of two things:

    40%  price compatibility   does the asking price fit the buyer's budget?
    60%  volume fulfilment     how much of the needed quantity can this listing cover?

Volume carries more weight because a cheap listing that covers 10% of an order still leaves the
buyer shopping around, whereas a slightly dearer one that covers all of it closes the deal.

Price compatibility is 1.0 at or under the buyer's maximum and falls linearly to 0 once the ask
exceeds that maximum by PRICE_TOLERANCE (25%). Anything beyond that is not a match at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

PRICE_WEIGHT = 0.40
VOLUME_WEIGHT = 0.60
PRICE_TOLERANCE = 0.25


@dataclass(frozen=True)
class MatchScore:
    price: float  # 0 to 1
    volume: float  # 0 to 1
    total: float  # 0 to 100

    def to_dict(self) -> dict:
        return {
            "score": round(self.total, 1),
            "price_score": round(self.price * 100, 1),
            "volume_score": round(self.volume * 100, 1),
        }


def price_score(ask: Decimal | float, max_price: Decimal | float) -> float:
    ask, max_price = float(ask), float(max_price)
    if max_price <= 0:
        return 0.0
    if ask <= max_price:
        return 1.0
    overshoot = (ask - max_price) / max_price
    return max(0.0, 1.0 - overshoot / PRICE_TOLERANCE)


def volume_score(available: Decimal | float, needed: Decimal | float) -> float:
    available, needed = float(available), float(needed)
    if needed <= 0 or available <= 0:
        return 0.0
    return min(1.0, available / needed)


def score(ask, max_price, available, needed) -> MatchScore:
    p, v = price_score(ask, max_price), volume_score(available, needed)
    return MatchScore(price=p, volume=v, total=100.0 * (PRICE_WEIGHT * p + VOLUME_WEIGHT * v))


def rank_listings(request, listings: Iterable) -> list[tuple]:
    """Open listings of the same crop that are not priced out, best match first.

    Ties on score go to the cheaper ask, then to a listing in the buyer's district.
    """
    scored = []
    for l in listings:
        if l.crop_id != request.crop_id or not l.is_open:
            continue
        s = score(l.price_per_kg, request.max_price_per_kg, l.quantity_kg, request.quantity_kg)
        if s.price <= 0:
            continue
        local = bool(request.district) and l.district.strip().lower() == request.district.strip().lower()
        scored.append((l, s, float(l.price_per_kg), not local))
    scored.sort(key=lambda t: (-t[1].total, t[2], t[3]))
    return [(l, s) for l, s, _, _ in scored]


def rank_requests(listing, requests: Iterable) -> list[tuple]:
    """The mirror image for a farmer: open requests for this crop that could take the produce."""
    if not listing.is_open:
        return []
    scored = []
    for r in requests:
        if r.crop_id != listing.crop_id or r.status != "open":
            continue
        s = score(listing.price_per_kg, r.max_price_per_kg, listing.quantity_kg, r.quantity_kg)
        if s.price <= 0:
            continue
        scored.append((r, s))
    scored.sort(key=lambda t: (-t[1].total, -float(t[0].max_price_per_kg)))
    return scored


_CENT = Decimal("0.01")


def _q(value) -> str:
    """Quantities and money always leave the API with two decimals."""
    return str(Decimal(value).quantize(_CENT))


def fulfilment_plan(request, ranked: Sequence[tuple], by: str = "score") -> dict:
    """Greedy plan to cover a request, filling from one end of the ranking.

    by="score": best match first. Favours fewer sellers and full coverage, not the lowest bill.
    by="cost":  cheapest ask first among the matched listings. Lowest bill, possibly more sellers.
    """
    if by == "cost":
        ranked = sorted(ranked, key=lambda t: (float(t[0].price_per_kg), -t[1].total))
    needed = Decimal(request.quantity_kg)
    remaining = needed
    lines, spend = [], Decimal("0")
    for listing, _ in ranked:
        if remaining <= 0:
            break
        take = min(remaining, Decimal(listing.quantity_kg))
        if take <= 0:
            continue
        lines.append({"listing": listing.pk, "take_kg": _q(take), "price_per_kg": _q(listing.price_per_kg)})
        spend += take * Decimal(listing.price_per_kg)
        remaining -= take
    covered = needed - remaining
    return {
        "strategy": by,
        "sellers": len(lines),
        "lines": lines,
        "covered_kg": _q(covered),
        "shortfall_kg": _q(max(remaining, Decimal("0"))),
        "covered_pct": round(float(covered / needed) * 100, 1) if needed > 0 else 0.0,
        "avg_price_per_kg": _q(spend / covered) if covered > 0 else None,
        "total_cost": _q(spend),
    }
