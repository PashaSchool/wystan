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
    render, all of it joins that feature. Its user flows follow their developer feature, else the
    product feature that owns the pages they start on, else lose their
    parent.
  * an unnameable **user flow** leaves ``user_flows``. Its member code flows
    stay in the flow layer without a ``user_flow_id``.

Files, lines and code flows are never dropped.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from wystan.pipeline_v2.product_language_names import JOINS_PREFIX, is_unnameable

__all__ = ["SHARED_REASON", "demote_unnameable_features", "drop_unnameable_flows"]

SHARED_REASON = "unnameable_product_feature"
_MIN_STEM = 4


def _same_stem(left: str, right: str) -> bool:
    if left == right:
        return True
    return min(len(left), len(right)) >= _MIN_STEM and (
        left.startswith(right) or right.startswith(left)
    )


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


def _joined_feature(feature: Any, survivors: list[str]) -> str | None:
    """The surviving feature whose page shows this one's code, when the
    naming pass recorded one."""
    for note in feature.name_evidence or []:
        if str(note).startswith(JOINS_PREFIX):
            target = str(note)[len(JOINS_PREFIX):]
            return target if target in survivors else None
    return None


def demote_unnameable_features(
    product_features: list[Any],
    developer_features: list[Any],
    user_flows: list[Any],
    flows: list[Any] = (),
) -> dict[str, Any]:
    """Remove unnameable product features in place; returns telemetry."""
    demoted = sorted((pf for pf in product_features if is_unnameable(pf)), key=lambda pf: pf.name)
    gone = {pf.name for pf in demoted}
    survivors = [pf.name for pf in product_features if pf.name not in gone]
    telemetry: dict[str, Any] = {"demoted": [], "devs_rehomed": 0, "devs_unowned": 0}
    joins = {pf.name: _joined_feature(pf, survivors) for pf in demoted}
    telemetry["joined"] = {name: target for name, target in joins.items() if target}
    new_home: dict[str, str | None] = {}
    for dev in sorted(developer_features, key=lambda d: d.name):
        if dev.product_feature_id not in gone:
            continue
        home = joins.get(dev.product_feature_id) or _home_for(dev, survivors)
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
    for user_flow in user_flows:
        if user_flow.product_feature_id not in gone:
            continue
        home = joins.get(user_flow.product_feature_id) or new_home.get(
            str(getattr(user_flow, "domain", "") or ""))
        user_flow.product_feature_id = home or _flow_home(user_flow, list(flows), owner_of)
        key = "flows_rehomed" if user_flow.product_feature_id else "flows_unparented"
        telemetry[key] += 1
    for pf in demoted:
        product_features.remove(pf)
        telemetry["demoted"].append({
            "pf": pf.name, "name": pf.display_name, "laws": list(pf.name_evidence or []),
        })
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
