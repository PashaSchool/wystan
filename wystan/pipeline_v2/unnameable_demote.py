"""What cannot be named in product language is not in the product layer.

The naming ladder stamps ``unnameable:<law>`` on a product feature or user
flow when no name passes the product-language laws: the only words for it are
a package name ("Ee"), a framework ("Remix") or an implementation verb
("Ingest", "Handle CORS requests"). Such a row describes how the software is
built. This pass removes it from what a product owner is shown:

  * an unnameable **product feature** leaves ``product_features``. Each of its
    developer features joins the surviving product feature its code lives
    under by name (``packages/ee/server-only/signing`` joins ``signing``), or
    becomes unowned. When the feature's code is what another feature's pages
    render, all of it joins that feature. A user flow goes with the join only
    when its own code went there: the strong share of its member flows must
    belong to developer features that now have that home. Otherwise it
    follows its developer feature, else the product feature that owns the
    pages it starts on, else it loses its parent.
  * an unnameable **user flow** leaves ``user_flows``. Its member code flows
    stay in the flow layer without a ``user_flow_id``.

Files, lines and code flows are never dropped.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from wystan.pipeline_v2.ownership_moves import credit_lines, mark_not_product
from wystan.pipeline_v2.product_language_names import JOINS_PREFIX, is_unnameable
from wystan.pipeline_v2.rehome_scopes import (
    REPOSITORY_ROOT,
    journey_scopes_from_flows,
    product_feature_scopes,
    row_scopes,
)

__all__ = ["SHARED_REASON", "demote_unnameable_features", "drop_unnameable_flows"]

SHARED_REASON = "unnameable_product_feature"
# Left on a feature the demotion veto judged to be plumbing: its code goes to
# the platform lane and its journeys are not product journeys.
PLUMBING_NOTE = "model:plumbing"
_MIN_STEM = 4
# A journey belongs where this share of its member flows is owned: the same
# share the owner attach uses (orphan_uf_path_attach).
_STRONG_SHARE = 0.6


def _same_stem(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < _MIN_STEM:
        return False
    shorter, longer = sorted((left, right), key=len)
    # The same word in another form ("auth", "authentication"), not the first
    # word of a longer name: a directory called after the product is not the
    # stem of every feature whose slug starts with the product's name.
    return longer.startswith(shorter) and longer[len(shorter)].isalnum()


def _home_for(dev: Any, survivors: list[str]) -> str | None:
    """The surviving product feature whose slug names the directory most of
    ``dev``'s files are in, or the developer feature itself."""
    segments: Counter[str] = Counter()
    for path in dev.paths or []:
        segments.update(set(path.lower().split("/")[:-1]))
    ranked = [dev.name.lower()] + [seg for seg, _ in sorted(
        segments.items(), key=lambda item: (-item[1], item[0]),
    )]
    for word in ranked:
        match = sorted(slug for slug in survivors if _same_stem(word, slug.lower()))
        if match:
            return match[0]
    return None


def _flow_home(user_flow: Any, flows: list[Any], owner_of: dict[str, str]) -> str | None:
    """The product feature that owns most of the files a user flow's code
    flows start in; ``None`` on a tie or when nobody owns them."""
    votes: Counter[str] = Counter()
    for flow in flows:
        if flow.user_flow_id != user_flow.id:
            continue
        owner = owner_of.get(flow.entry_point_file or "")
        if owner:
            votes[owner] += 1
    ranked = votes.most_common(2)
    if not ranked or (len(ranked) == 2 and ranked[0][1] == ranked[1][1]):
        return None
    return ranked[0][0]


def _code_went_to(
    user_flow: Any, target: str, flows: list[Any], owner_of_dev: dict[str, str | None],
) -> bool:
    """True when the strong share of a user flow's member flows belongs to
    developer features whose product feature is now ``target``."""
    members = [flow for flow in flows if flow.user_flow_id == user_flow.id]
    if not members:
        return False
    there = sum(
        1 for flow in members
        if owner_of_dev.get(str(getattr(flow, "primary_feature", "") or "")) == target
    )
    return there / len(members) >= _STRONG_SHARE


def _credit_lines(dev: Any, home: str | None, by_slug: dict[str, Any]) -> None:
    """A developer feature that moves takes its lines along: the feature it
    joins is credited with them at once."""
    credit_lines(int(getattr(dev, "loc", None) or 0), None, by_slug.get(home or ""))


def _mark_not_product(not_product: list[Any]) -> list[dict[str, str]]:
    """Journeys of plumbing that found no product feature are not product
    journeys. They are not deleted: they stay in the journey layer with no
    parent and a mark that keeps them out of the capability split."""
    return [mark_not_product(journey) for journey in sorted(not_product, key=lambda j: str(j.id))]


def _joined_feature(feature: Any, survivors: list[str]) -> str | None:
    """The surviving feature whose page shows this one's code, when the
    naming pass recorded one."""
    for note in feature.name_evidence or []:
        if str(note).startswith(JOINS_PREFIX):
            target = str(note)[len(JOINS_PREFIX):]
            return target if target in survivors else None
    return None


class _ScopedHomes:
    """Rule S2 (:mod:`rehome_scopes`): a row or a journey of a removed
    feature goes only to a feature of its own module scope, whether by a
    stated join, by the name of its directory or by the owner of its pages.
    A repository item is placed exactly as if no nested module had been
    read. Without a nested module every item and feature is in the root
    scope and every list here is the full list."""

    def __init__(
        self, product_features: list[Any], developer_features: list[Any],
        user_flows: list[Any], flows: list[Any], module_scopes: Any,
    ) -> None:
        self._feature = product_feature_scopes(product_features, developer_features, module_scopes)
        self._row = row_scopes(developer_features, module_scopes)
        self._journey = journey_scopes_from_flows(user_flows, flows, module_scopes)

    def of_row(self, dev: Any) -> str:
        return self._row.get(id(dev), REPOSITORY_ROOT)

    def of_journey(self, user_flow: Any) -> str:
        return self._journey.get(id(user_flow), REPOSITORY_ROOT)

    def same(self, scope: str, target: str | None) -> str | None:
        """``target`` when it is a feature of ``scope``, else ``None``."""
        return target if target and self._feature.get(target, REPOSITORY_ROOT) == scope else None

    def survivors(self, survivors: list[str], scope: str) -> list[str]:
        return [slug for slug in survivors if self._feature.get(slug, REPOSITORY_ROOT) == scope]

    def owners(self, owner_of: dict[str, str], scope: str) -> dict[str, str]:
        return {path: slug for path, slug in owner_of.items() if self._feature.get(slug, REPOSITORY_ROOT) == scope}


def demote_unnameable_features(
    product_features: list[Any],
    developer_features: list[Any],
    user_flows: list[Any],
    flows: list[Any] = (),
    module_scopes: Any = None,
) -> dict[str, Any]:
    """Remove unnameable product features in place; returns telemetry.

    ``module_scopes`` is the scan's record of nested modules (rule S2):
    what leaves a removed feature goes only to a feature of its own scope.
    ``None`` or an empty record: one scope, the pass as it was."""
    demoted = sorted((pf for pf in product_features if is_unnameable(pf)), key=lambda pf: pf.name)
    gone = {pf.name for pf in demoted}
    survivors = [pf.name for pf in product_features if pf.name not in gone]
    scoped = _ScopedHomes(product_features, developer_features, user_flows, list(flows), module_scopes)
    telemetry: dict[str, Any] = {"demoted": [], "devs_rehomed": 0, "devs_unowned": 0}
    joins = {pf.name: _joined_feature(pf, survivors) for pf in demoted}
    telemetry["joined"] = {name: target for name, target in joins.items() if target}
    plumbing = {pf.name for pf in demoted if PLUMBING_NOTE in (pf.name_evidence or [])}
    by_slug = {pf.name: pf for pf in product_features}
    new_home: dict[str, str | None] = {}
    moved_from: dict[str, list[str]] = {}
    for dev in sorted(developer_features, key=lambda d: d.name):
        if dev.product_feature_id not in gone:
            continue
        scope = scoped.of_row(dev)
        # Plumbing has no home by resemblance: only a stated join moves it.
        by_name = None if dev.product_feature_id in plumbing else _home_for(
            dev, scoped.survivors(survivors, scope))
        home = scoped.same(scope, joins.get(dev.product_feature_id)) or by_name
        moved_from.setdefault(dev.product_feature_id, []).append(dev.name)
        _credit_lines(dev, home, by_slug)
        new_home[dev.name] = home
        dev.product_feature_id = home
        if home is None:
            dev.shared_reason = SHARED_REASON
            telemetry["devs_unowned"] += 1
        else:
            telemetry["devs_rehomed"] += 1
    owner_of = {
        path: pf.name
        for pf in sorted(product_features, key=lambda pf: pf.name) if pf.name not in gone
        for path in pf.paths or []
    }
    telemetry["flows_rehomed"] = telemetry["flows_unparented"] = 0
    telemetry["flows_not_following_join"] = 0
    owner_of_dev = {dev.name: dev.product_feature_id for dev in developer_features}
    journeys_of: Counter[str] = Counter()
    all_flows = list(flows)
    not_product: list[Any] = []
    owners_in: dict[str, dict[str, str]] = {}
    for user_flow in user_flows:
        if user_flow.product_feature_id not in gone:
            continue
        journeys_of[user_flow.product_feature_id] += 1
        scope = scoped.of_journey(user_flow)
        joined = scoped.same(scope, joins.get(user_flow.product_feature_id))
        if joined and not _code_went_to(user_flow, joined, all_flows, owner_of_dev):
            # The feature joined another one; this journey's code did not.
            telemetry["flows_not_following_join"] += 1
            joined = None
        home = joined or scoped.same(scope, new_home.get(str(getattr(user_flow, "domain", "") or "")))
        was_plumbing = user_flow.product_feature_id in plumbing
        if scope not in owners_in:
            owners_in[scope] = scoped.owners(owner_of, scope)
        user_flow.product_feature_id = home or _flow_home(user_flow, all_flows, owners_in[scope])
        if was_plumbing and not user_flow.product_feature_id:
            not_product.append(user_flow)
            continue
        key = "flows_rehomed" if user_flow.product_feature_id else "flows_unparented"
        telemetry[key] += 1
    for pf in demoted:
        product_features.remove(pf)
        telemetry["demoted"].append({
            "pf": pf.name, "name": pf.display_name, "laws": list(pf.name_evidence or []),
            "journeys": journeys_of.get(pf.name, 0),
        })
    # How much of the journey layer sat on features that were removed.
    telemetry["journeys_on_demoted"] = sum(journeys_of.values())
    telemetry["plumbing_journeys"] = _mark_not_product(not_product)
    # A removed feature's own line count leaves with it; what its developer
    # features carry stays. The difference is the part of any change in the
    # layer's total that this removal explains.
    telemetry["ruler_gap"] = sum(
        sum(int(getattr(d, "loc", None) or 0) for d in developer_features if d.name in moved_from.get(pf.name, ()))
        - int(getattr(pf, "loc", None) or 0)
        for pf in demoted if getattr(pf, "loc", None) is not None
    )
    return telemetry


def drop_unnameable_flows(user_flows: list[Any], flows: list[Any]) -> dict[str, Any]:
    """Remove unnameable user flows in place; returns telemetry.

    The member code flows stay in the flow layer and lose their
    ``user_flow_id``: they are implementation steps, not a user journey."""
    dropped = [uf for uf in user_flows if is_unnameable(uf)]
    if not dropped:
        return {"dropped": 0, "names": []}
    ids = {uf.id for uf in dropped}
    for flow in flows:
        if flow.user_flow_id in ids:
            flow.user_flow_id = None
    from wystan.pipeline_v2.journey_lineage_audit import report_journey_kill

    report_journey_kill("unnameable_demote.drop_unnameable_flows", sorted(ids))
    user_flows[:] = [uf for uf in user_flows if uf.id not in ids]
    return {"dropped": len(dropped), "names": sorted(uf.name for uf in dropped)}
