"""fixb134 M4b — the PF slug-migration lane (``WYSTAN_PF_SLUG_SANITIZE``).

fixb133 cleaned the DISPLAY channel and deliberately left ``pf.name``
alone. That left router machinery inside the JOIN ID on live boards:

* umami ``'(.)sessions'`` / ``'(.)replays'`` — an intercepting marker in
  the id (their displays are already clean);
* cal.com ``'alby-(alby)'`` / ``'paypal-(paypal)'`` — the mint collision
  self-qualifier baked into the slug (and, via R5-1 identity-parity, the
  reason those displays could not be cleaned either);
* documenso ``'[-htmltopdf]+'``, epic-stack ``'robots[.]txt'``,
  kentcdodds-com ``'[.]well-known'`` — escape / regex residue ids.

``pf.name`` IS the join key (``Feature.product_feature_id`` stores it), so
a rename is only safe as the E3a pattern does it
(``emission_hard_gate.py:147-172``): rename the PF **and re-stamp every
consumer channel in the SAME pass**. The
``stage_8_6_compactor.py:236-238`` shape — re-slug without propagation —
is the known landmine and is never copied here.

Scope discipline:

* runs at EMISSION (after the hard gate, before Stage 7), NOT in
  ``naming_contract`` — the fixb133 slug-stable law says the naming
  contract never rewrites names, and that law keeps passing untouched;
* ``anchor_id`` is NOT touched — anchor identity is not the slug (Seam 1
  stays rejected);
* ``display_name`` is NOT touched — fixb133 already owns that channel;
* every rename is reported in ``scan_meta.pf_slug_sanitize`` so lineage
  and the wardens can see the whole migration.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any

__all__ = [
    "PF_SLUG_SANITIZE_ENV",
    "pf_slug_sanitize_enabled",
    "run_pf_slug_sanitize",
    "sanitized_slug",
    "slug_has_marker_residue",
]

PF_SLUG_SANITIZE_ENV = "WYSTAN_PF_SLUG_SANITIZE"

#: A parenthesised disambiguator tail in a SLUG: ``alby-(alby)``,
#: ``airtable-(iot-ot)``. Only the SELF-restating ones migrate here — the
#: informative ones are legitimate ids (and E3a already owns the
#: ``-(route-…)`` family).
_SLUG_PAREN_TAIL_RE = re.compile(r"^(?P<base>.+?)-\((?P<qual>[^()]+)\)$")

#: Marker shapes that may never live in a join id.
_INTERCEPT_RE = re.compile(r"\(\.{1,3}\)")
_ESCAPE_RE = re.compile(r"\[[^\[\]]*\]")


def pf_slug_sanitize_enabled() -> bool:
    """Default **ON** since the 2026-08-09 pack-№36 flip (KEY_SCHEMA 69;
    warden №40 GO — umami '(.)sessions'->'sessions' with devs/ufs
    restamped, zero dangling ids across all four PF-key channels). Unset ≡
    explicit ``1``; explicit ``0``/``false`` ⇒ no rename, no ``scan_meta``
    key ⇒ byte-identical (kill-switch forever). The truthy set is preserved
    LITERALLY — only the default moved ``"0"`` -> ``"1"``."""
    return os.environ.get(
        PF_SLUG_SANITIZE_ENV, "1"
    ).strip().lower() in {"1", "true"}


def _self_qualifier_base(name: str) -> str | None:
    """``alby-(alby)`` -> ``alby``; ``None`` when the tail is informative."""
    from wystan.pipeline_v2.pf_display_doctrine import same_phrase

    m = _SLUG_PAREN_TAIL_RE.match(name or "")
    if not m:
        return None
    base, qual = m.group("base"), m.group("qual")
    return base if same_phrase(base, qual) else None


def slug_has_marker_residue(name: str) -> bool:
    """True when a PF slug carries router machinery a join id must not."""
    n = name or ""
    if not n:
        return False
    if _INTERCEPT_RE.search(n) or "@" in n:
        return True
    if _ESCAPE_RE.search(n) or "[" in n or "]" in n:
        return True
    if n.count("(") != n.count(")"):
        return True
    return _self_qualifier_base(n) is not None


def sanitized_slug(name: str) -> str:
    """The clean id for a residue-carrying slug (before collision
    resolution). Falls back to ``name`` when nothing human survives."""
    from wystan.pipeline_v2.emission_integrity import canonical_slug
    from wystan.pipeline_v2.extractors._route_markers import sanitize_segment

    raw = (name or "").strip()
    if not raw:
        return raw
    base = _self_qualifier_base(raw)
    if base is not None:
        raw = base
    # A parallel slot is ORGANISATIONAL for the display walk (it names no
    # capability, so sanitize_segment drops it) — but an ID must survive:
    # peel the marker instead of losing the row's identity entirely.
    if raw.startswith("@"):
        raw = raw.lstrip("@") or raw
    cleaned, _literal = sanitize_segment(raw)
    if not cleaned:
        cleaned = raw.lstrip("@")
    out = canonical_slug(cleaned)
    return out or canonical_slug(name) or name


def _iter_flows(
    product_features: list[Any],
    developer_features: list[Any] | None,
    flows: list[Any] | None,
) -> list[Any]:
    """Every distinct Flow object reachable from the emitted tree.

    Flows are shared BY REFERENCE between the containment views
    (``developer_features[].flows[]``, ``features[].flows[]``) and the
    top-level bipartite ``flows[]`` array, so de-duplicating on ``id()``
    restamps each object exactly once and all views see it."""
    seen: set[int] = set()
    out: list[Any] = []
    for holder in (list(product_features or [])
                   + list(developer_features or [])):
        for fl in (getattr(holder, "flows", None) or []):
            if id(fl) not in seen:
                seen.add(id(fl))
                out.append(fl)
    for fl in (flows or []):
        if id(fl) not in seen:
            seen.add(id(fl))
            out.append(fl)
    return out


def run_pf_slug_sanitize(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
    flows: list[Any] | None = None,
    coverage_gaps: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Migrate residue-carrying ``pf.name`` ids in place, re-stamping every
    consumer channel in the SAME pass (the E3a law). Returns the
    ``scan_meta.pf_slug_sanitize`` telemetry, or ``None`` when the flag is
    off (no mutation, no key)."""
    if not pf_slug_sanitize_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True,
        "renames": {},
        "devs_restamped": 0,
        "ufs_restamped": 0,
        # Warden §39 blocker — pf.name is held by FOUR declared channels,
        # not two. A rename that misses one leaves a dead ref (the
        # eval-side `dangling-pf-keys` detector reads exactly this shape).
        "shared_owners_restamped": 0,
        "cross_links_restamped": 0,
        "coverage_gaps_restamped": 0,
        "collisions_laddered": 0,
        "skipped_no_gain": [],
    }
    products = [
        pf for pf in (product_features or [])
        if getattr(pf, "layer", "product") == "product"
    ]
    if not products:
        return tele

    def _name(pf: Any) -> str:
        return str(getattr(pf, "name", "") or "")

    devs_by_pf: dict[str, list[Any]] = defaultdict(list)
    for d in (developer_features or []):
        pid = getattr(d, "product_feature_id", None)
        if pid:
            devs_by_pf[str(pid)].append(d)

    # ── the OTHER declared PF-key channels (types.py sweep) ──────────────
    # :347  FlowSharedPath.owner_product_feature  ("PF key (id or name)")
    #       + owner_display, which re-renders from the migrated PF;
    # :1207 UserFlow.cross_links[]  ("other product_feature_ids touched");
    # :1511 CoverageGap.product_feature_id ("the home product-feature key").
    all_flows = _iter_flows(product_features, developer_features, flows)
    pf_by_name = {_name(pf): pf for pf in products}

    taken = {_name(pf) for pf in products}

    # Sorted for determinism — the ladder's suffixes must not depend on
    # dict/list order (the set-iteration trap).
    for pf in sorted(products, key=_name):
        name = _name(pf)
        if not name or not slug_has_marker_residue(name):
            continue
        base = sanitized_slug(name)
        if not base or base == name:
            tele["skipped_no_gain"].append(name)
            continue
        new = base
        i = 2
        while new in taken:
            new = f"{base}-{i}"
            i += 1
        if new != base:
            tele["collisions_laddered"] += 1
        taken.discard(name)
        taken.add(new)
        pf.name = new
        # E3a law — the join key moves with the row, in the same pass.
        for d in devs_by_pf.pop(name, []):
            d.product_feature_id = new
            devs_by_pf[new].append(d)
            tele["devs_restamped"] += 1
        for uf in (user_flows or []):
            if str(getattr(uf, "product_feature_id", "") or "") == name:
                uf.product_feature_id = new
                tele["ufs_restamped"] += 1
            links = getattr(uf, "cross_links", None)
            if links:
                swapped = [new if str(x) == name else x for x in links]
                if swapped != list(links):
                    uf.cross_links = swapped
                    tele["cross_links_restamped"] += 1
        for fl in all_flows:
            for sp in (getattr(fl, "shared_paths", None) or []):
                if str(getattr(sp, "owner_product_feature", "") or "") != name:
                    continue
                sp.owner_product_feature = new
                # owner_display re-renders from the MIGRATED PF (the row is
                # the same capability — only its key moved).
                owner_pf = pf_by_name.get(name)
                if owner_pf is not None:
                    sp.owner_display = (
                        getattr(owner_pf, "display_name", None)
                        or new
                    )
                tele["shared_owners_restamped"] += 1
        for gap in (coverage_gaps or []):
            if str(getattr(gap, "product_feature_id", "") or "") == name:
                gap.product_feature_id = new
                tele["coverage_gaps_restamped"] += 1
        pf_by_name[new] = pf_by_name.pop(name, pf)
        tele["renames"][name] = new
    return tele
