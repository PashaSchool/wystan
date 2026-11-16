"""orphan_uf_path_attach — #3A: last-chance attach of None journeys by path ownership.

THE CLASS (keyed-world census 2026-08-03): 69 real UFs with
``product_feature_id = None`` — journeys born of the 6.7d abstraction
with NO domain match to any PF (hoppscotch ×29 — legacy of the dissolved
Common). Existing rails are blind: I16-rehome (6.99) cures MIS-homed
(entry-owner mismatch), not None-born; token/container-rehome need mint tele.

MECHANISM (deterministic, $0): for an orphan real UF, collect the owners
of all member-flow files (entry + paths) via a dev→PF join; if ONE PF
holds ≥ ``_STRONG_SHARE`` of the weighted occurrences — attach to it.
Weak/zero ownerships stay honest orphans (conservation over invention;
the residual edge of Common is a separate cycle).

Order: the post-UF family, BEFORE B96 (6.9969) — attach-first-then-demote:
a journey that finds a home saves its PF from reading as 0-UF.

Flag ``WYSTAN_ORPHAN_UF_PATH_ATTACH`` default ON since flip-pack #18
(KEY_SCHEMA 53; unset ≡ ``1``). Explicit ``0`` ⇒ byte-identical.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable
from typing import Any

__all__ = [
    "ORPHAN_UF_PATH_ATTACH_ENV",
    "orphan_uf_path_attach_enabled",
    "run_orphan_uf_owner_attach",
    "run_orphan_uf_path_attach",
]

ORPHAN_UF_PATH_ATTACH_ENV = "WYSTAN_ORPHAN_UF_PATH_ATTACH"

#: Strong ownership: one PF holds ≥60% of a journey's weighted file
#: occurrences (the count-grain threshold of the widget-micro precedent;
#: hoppscotch exhibits resolve at 100%/60%+, weak 50/50 honestly stay).
_STRONG_SHARE = 0.6


class _ScopeFilter:
    """Rule S2 (:mod:`rehome_scopes`): an orphan journey is attached only to
    a product feature of its own module scope, so an owner of another scope
    does not vote. A repository journey is then judged as if the nested
    modules' features did not exist. Without a nested module every journey
    and feature is in the root scope and no vote is left out."""

    def __init__(
        self, product_features: list[Any], developer_features: list[Any] | None,
        user_flows: list[Any] | None, flow_by_id: dict[str, Any], module_scopes: Any,
    ) -> None:
        from wystan.pipeline_v2.rehome_scopes import (
            REPOSITORY_ROOT,
            journey_scopes,
            product_feature_scopes,
        )

        self._root = REPOSITORY_ROOT
        self._is_active = bool(module_scopes)
        self._feature = product_feature_scopes(
            product_features or [], developer_features or [], module_scopes)
        self._journey = journey_scopes(list(user_flows or []), flow_by_id, module_scopes)

    def votes(self, owners: Counter, journey: Any) -> Counter:
        """``owners`` without the features of another scope than ``journey``'s."""
        if not self._is_active:
            return owners
        scope = self._journey.get(id(journey), self._root)
        return Counter({
            pf: n for pf, n in owners.items() if self._feature.get(pf, self._root) == scope
        })


def _flows_by_id(flows: Iterable[Any]) -> dict[str, Any]:
    """``{id | uuid | name: flow}``: member ids are "uuid or name"."""
    by_id: dict[str, Any] = {}
    for fl in flows:
        for key in (getattr(fl, "id", None), getattr(fl, "uuid", None),
                    getattr(fl, "name", None)):
            if key:
                by_id.setdefault(str(key), fl)
    return by_id


def orphan_uf_path_attach_enabled() -> bool:
    """#3A — default **ON** since flip-pack #18 (KEY_SCHEMA 53, 2026-08-04):
    live hoppscotch(6)+unkey(4) + the offline world breadth (18 attaches
    across 7 boards, surgical, weak ones honestly stay). Unset ≡ explicit
    ``1``; explicit ``0`` = kill-switch forever."""
    return os.environ.get(ORPHAN_UF_PATH_ATTACH_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def run_orphan_uf_path_attach(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
    flows: list[Any] | None,
    module_scopes: Any = None,
) -> dict[str, Any] | None:
    """Attach None journeys to a PF by strong path ownership (in place);
    telemetry for ``scan_meta.orphan_uf_path_attach``; ``None`` when the
    flag is off. ``module_scopes`` (rule S2): only owners of the journey's
    own module scope vote."""
    if not orphan_uf_path_attach_enabled():
        return None
    tele: dict[str, Any] = {
        "enabled": True,
        "attached": {},
        "weak_left": [],
        "unresolvable_left": 0,
        "considered": 0,
    }
    pf_names = {
        str(getattr(p, "name", "") or "")
        for p in (product_features or [])
        if getattr(p, "layer", "product") == "product"
    }
    if not pf_names:
        return tele
    file2pf: dict[str, str] = {}
    for f in (developer_features or []):
        pf = str(getattr(f, "product_feature_id", "") or "")
        if pf in pf_names:
            for p in (getattr(f, "paths", None) or ()):
                file2pf.setdefault(str(p), pf)
    # member_flow_ids = "uuid or name" (models/types:1134); uuids are
    # stamped at the exit — in this rail's slot live mids can be NAMES.
    flow_by_id = _flows_by_id(flows or [])
    in_scope = _ScopeFilter(
        product_features, developer_features, user_flows, flow_by_id, module_scopes)
    for uf in sorted(
        (u for u in (user_flows or [])
         if not getattr(u, "synthesized", False)
         and not getattr(u, "product_feature_id", None)),
        key=lambda u: str(getattr(u, "name", "") or ""),
    ):
        tele["considered"] += 1
        owners: Counter[str] = Counter()
        for mid in (getattr(uf, "member_flow_ids", None) or ()):
            fl = flow_by_id.get(str(mid))
            if fl is None:
                continue
            cand = [getattr(fl, "entry_point_file", None)]
            cand += list(getattr(fl, "paths", None) or ())
            for p in cand:
                own = file2pf.get(str(p or ""))
                if own:
                    owners[own] += 1
        owners = in_scope.votes(owners, uf)
        if not owners:
            tele["unresolvable_left"] += 1
            continue
        top, n = owners.most_common(1)[0]
        share = n / max(1, sum(owners.values()))
        if share >= _STRONG_SHARE:
            uf.product_feature_id = top
            tele["attached"].setdefault(top, []).append(
                str(getattr(uf, "name", "") or ""))
        else:
            tele["weak_left"].append(str(getattr(uf, "name", "") or ""))
    return tele


def run_orphan_uf_owner_attach(
    product_features: list[Any],
    developer_features: list[Any] | None,
    user_flows: list[Any] | None,
    flows: list[Any] | None = None,
    module_scopes: Any = None,
) -> dict[str, Any]:
    """Attach parentless journeys by who owns their member flows (in place).

    The path rail above votes with every file a member flow touches, so files
    a journey merely imports vote too and a feature that lists shared files
    collects journeys that are not its own. This rail votes with the member
    flows themselves: each one belongs to exactly one developer feature, and
    that feature to at most one product feature. A flow's developer feature
    is the one that lists it, or, for a flow no feature lists in memory, the
    one named by its ``primary_feature`` (the output is assembled from both). A journey is attached when
    one product feature owns at least ``_STRONG_SHARE`` of its member flows.

    Unlike the path rail, a journey marked ``synthesized`` is judged too: what
    matters here is that it has member flows with an owner, not how the
    journey was formed (langflow: the 12 journeys this rail exists for were
    all synthesized and all had member flows). A journey with no member flow
    is skipped.

    Meant for the end of finalize, when ownership no longer changes: a
    journey orphaned by a dissolved container is then judged against the
    feature its code finally went to. Journeys whose flows no product feature
    owns stay without a parent and are counted as ``code_unowned``.

    ``module_scopes`` (rule S2): only owners of the journey's own module
    scope count; a member flow owned by another scope's feature counts as
    owned by none.
    """
    tele: dict[str, Any] = {
        "attached": {}, "considered": 0, "code_unowned": 0, "split_left": 0,
    }
    pf_names = {
        str(getattr(p, "name", "") or "")
        for p in (product_features or [])
        if getattr(p, "layer", "product") == "product"
    }
    flow_owner: dict[str, str | None] = {}
    owner_of_dev: dict[str, str | None] = {}

    def _index(fl: Any, owner: str | None) -> None:
        for key in (getattr(fl, "id", None), getattr(fl, "uuid", None),
                    getattr(fl, "name", None)):
            if key:
                flow_owner.setdefault(str(key), owner)

    for dev in sorted(developer_features or [], key=lambda d: str(getattr(d, "name", ""))):
        pf = str(getattr(dev, "product_feature_id", "") or "")
        owner = pf if pf in pf_names else None
        owner_of_dev[str(getattr(dev, "name", "") or "")] = owner
        for fl in (getattr(dev, "flows", None) or ()):
            _index(fl, owner)
    for fl in (flows or ()):
        _index(fl, owner_of_dev.get(str(getattr(fl, "primary_feature", "") or "")))
    member_flows = _flows_by_id(
        [fl for dev in developer_features or () for fl in getattr(dev, "flows", None) or ()]
        + list(flows or ()))
    in_scope = _ScopeFilter(
        product_features, developer_features, user_flows, member_flows, module_scopes)
    for uf in sorted(
        (u for u in (user_flows or [])
         if not getattr(u, "product_feature_id", None)),
        key=lambda u: str(getattr(u, "name", "") or ""),
    ):
        members = [str(mid) for mid in (getattr(uf, "member_flow_ids", None) or ())]
        if not members:
            continue
        tele["considered"] += 1
        owners = Counter(flow_owner.get(mid) for mid in members)
        owners.pop(None, None)
        scoped = in_scope.votes(owners, uf)
        # A member owned by another scope's feature is weighed as if it
        # were not there (rule S2): it neither votes nor dilutes the share.
        counted = len(members) - (sum(owners.values()) - sum(scoped.values()))
        owners = scoped
        if not owners:
            tele["code_unowned"] += 1
            continue
        top, count = sorted(owners.items(), key=lambda item: (-item[1], item[0]))[0]
        if count / counted >= _STRONG_SHARE:
            uf.product_feature_id = top
            tele["attached"].setdefault(top, []).append(
                str(getattr(uf, "name", "") or ""))
        else:
            tele["split_left"] += 1
    return tele
