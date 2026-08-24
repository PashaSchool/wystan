"""Stage 6.9966 — B (container journey-rehome): deterministic name-first
re-home of cross-domain journeys stuck on a STRUCTURAL container PF.

THE DISEASE (grounded, det-container-journey-rehome.md §1; census class
monorepo/shared-package topology): a container PF (``ws:``/``hub:`` anchor
or a generic-bucket dir like ``components/general``) HOLDS N journeys that
are NOT about its own identity — their member-flow entry files live in
shared plumbing (``newstore``/``helpers``/``composables``), so member-
majority vote homes them on the container. The container carries packaging
provenance, NOT product right. hoppscotch ``Common`` holds 7 journeys about
7 different domains (realtime/collections/cookies/environments/rest/sharing/
auth); documenso ``General`` holds 5 (signing/envelope/pdf) whose real
domain-dirs exist in code (``components/general/{envelope-editor,
direct-template,pdf-viewer}``) but carry NO PF.

WHY A NEW STAGE, NOT AN EXTENSION OF 6.9965 (Stream A verdict): 6.9965 is a
pure RE-POINTER with a no-mint contract + 2-arg signature — it moves a
journey only when a real-domain PF ALREADY names it, and leaves the
container-homed-without-target residual UNTOUCHED (``:224-228``). That
residual IS B's input. B must MINT the absent domain-PF from the code-dir,
so it needs dev_features + ctx (repo tree for the no-husk probe). Clean
composition: 6.9965 places what it can, B mints/dissolves the rest.

THE RULER (mechanism, not dictionary — rule-no-magic-tuning):
  * SOURCE — a STRUCTURAL container (``_is_structural_home`` OR generic-
    bucket-at-bare-root) that is OVERSIZED (scale-invariant loc percentile)
    and holds >= FLOOR_JOURNEYS journeys resolving to >= FLOOR_DOMAINS
    DISTINCT domains != its own identity (domain-DIVERSITY, NOT real_uf<=1
    — Stream C: common has real_uf=7=held=7). GUARDS skip UI-kit / name-dedup
    / cohesive-single-domain (a different disease).
  * TARGET — a CODE domain (§6.2): a component/domain-dir under the container
    carrying real owned LOC. Name-first: the journey's NAME (resource+name
    entity tokens, universal-synonym-normalized) must NAME the domain; path
    only corroborates (Stream B: path misleads — REST -> top dir `graphql`,
    realtime -> `newstore`).
  * MINT-GATE (§6.4, over-mint is the highest risk) — a minted domain-PF must
    pass 3 product-right tests: PATH (a real journey re-homes here — journey-
    gated), ENTITY/no-husk (the code-dir carries owned LOC > 0 — leafroute
    ``_LocProbe`` / I2 phantom-guard), DEMO (the dir is a product surface, NOT
    infra-shape helpers/utils/config/firebase/embeds). Any fail -> the journey
    is honest-residual (``pfid=None, residual=True``), NEVER left on the
    container, NEVER a husk mint.
  * AGGREGATE (§6.5) — a journey whose NAME names no entity after stripping
    verbs + the container's OWN identity tokens ('Browse general', 'Manage
    <container>'), with member paths that fan out with no dominant domain-dir
    -> DISSOLVE (honest-residual / downstream demote), NEVER force-rehomed.

CONSERVATION (§6.7): journey pfid moves go through the overturn-ledger rung
``container-journey-rehome`` (``finalize_arbiter`` replay-verifies free);
a mint CARVES the domain-dir's member files off the container onto the new
PF (re-attribution, canon §2 — the minted PF is never a 0-LOC husk); every
journey ends with a home (mint / existing / honest-residual), 0 lost.

Gated by ``WYSTAN_CONTAINER_JOURNEY_REHOME`` (default **OFF**). Unset ≡
explicit ``0``/``false``/``off``/``no`` ⇒ the stage is a pure no-op
(byte-identical OFF-world forever; kill-switch). No KEY_SCHEMA bump (append
law; the bump rides the separate flip commit).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wystan.pipeline_v2.stage_6_9965_token_journey_rehome import (
    _MATCH_STOPWORDS,
    _is_structural_home,
    _singular,
    _tokens,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from wystan.models.types import Feature, UserFlow

CONTAINER_JOURNEY_REHOME_ENV = "WYSTAN_CONTAINER_JOURNEY_REHOME"

#: Pin-cycle-3 M1 — capability mint-guard (SEPARATE flag from the stage's own
#: WYSTAN_CONTAINER_JOURNEY_REHOME arm; default OFF). When armed, a mint
#: candidate that is a capability-MECHANISM (not a product domain) FAILs the
#: mint-gate → the journey is honest-residual, never a peer tile.
CAPABILITY_MINT_GUARD_ENV = "WYSTAN_CAPABILITY_MINT_GUARD"

#: New-behaviour flag → default **OFF** (unlike the default-ON 6.9965 twin).
#: Only the explicit truthy set arms it; everything else (incl. unset) is the
#: byte-identical no-op OFF-world.
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# ── source-detect floors (scale-invariant; NO per-repo magic numbers) ──────
FLOOR_JOURNEYS = 3          # container must hoard >= this many journeys
FLOOR_DOMAINS = 2           # ...resolving to >= this many DISTINCT domains
FANOUT_FLOOR = 4            # distinct member-entry dirs for path-fanout aggregate
DOMINANT_FLOOR = 0.5        # a domain-dir share that overrides fan-out (path rail)
AFFINITY_FLOOR = 0.5        # domain-token coverage a journey needs to name a domain

#: UNIVERSAL product synonyms (§6.3 step-2; scale-invariant, NOT per-repo).
#: Applied SYMMETRICALLY to journey tokens AND domain-leaf tokens. `envelope`
#: is DELIBERATELY absent — it matches code-dir `envelope-editor` DIRECTLY
#: (§6.2), never via a dictionary entry (the magic-tuning trap, Stream B).
_SYNONYMS = {
    "authenticate": "auth", "signin": "auth", "login": "auth",
    "share": "sharing", "desktop": "clients",
}

#: Generic bucket / container-identity names — a PF so named carries no
#: product right; a journey token that is only one of these names no domain.
_GENERIC_BUCKET = frozenset({
    "general", "common", "misc", "shared", "core", "src", "backend", "app",
})

#: Directory-parent segments that mark a product SURFACE vs infra plumbing
#: (SurfaceScopeClassifier proxy — the demo-test shape).
_PRODUCT_PARENTS = frozenset({
    "components", "pages", "views", "features", "modules", "screens",
})
_INFRA_PARENTS = frozenset({
    "helpers", "services", "composables", "lib", "newstore", "platform",
    "utils", "util", "kernel", "functional", "std", "sync", "types",
    "constants", "hooks", "assets", "public", "locales", "config", "api",
    "backend", "worker", "workers", "middleware", "plugins",
})
#: Leaf names that are never a product domain even under a product parent
#: (nav-shell / infra masquerade — canon anti-mint shapes firebase/embeds/app).
_INFRA_LEAF = frozenset({
    "firebase", "embeds", "embed", "app", "utils", "util", "config",
    "helpers", "backend", "std", "kernel", "functional", "sync", "assets",
    "public", "locales", "spotlight", "shared",
})

#: The engine's OWN structural-token name-evidence marker (Stage naming). A PF
#: whose name resolved only to an unresolved structural dir token carries this;
#: a REAL feature carries route/nav/schema evidence instead. This is the
#: demote-discriminator (§container-husk-demote signal #4): it distinguishes a
#: hollow structural husk from an honest journey-less product feature.
_UNRESOLVED_DIR_TOKEN = "unresolved-dir-token"


def container_journey_rehome_enabled() -> bool:
    """Default **ON** since the 2026-07-29 flip (KEY_SCHEMA 43; keyed proof
    hoppscotch Common + documenso General + twenty-server demoted green). Unset
    ≡ explicit ``"1"``; explicit ``0``/``false``/``off``/``no`` is the kill-
    switch forever (byte-identical OFF-world). The pre-flip WIDE truthy set is
    preserved LITERALLY — only the ``os.environ.get`` default moved ``"0"`` →
    ``"1"``."""
    return os.environ.get(CONTAINER_JOURNEY_REHOME_ENV, "1").strip().lower() \
        in _TRUTHY


def capability_mint_guard_enabled() -> bool:
    """Pin-cycle-3 M1 — default **ON** since the 2026-07-29 flip-pack №11
    (KEY_SCHEMA 46; keyed exhibit-gate hoppscotch 8/8 green — Cookies gone,
    UF conserved). Unset ≡ explicit ``"1"``; explicit ``0``/``false``/``off``/
    ``no`` leaves the 6.9966 mint-gate byte-identical to the pre-guard world —
    a kill-switch forever. The pre-flip truthy set is preserved LITERALLY —
    only the ``os.environ.get`` default moved ``"0"`` → ``"1"``."""
    return os.environ.get(CAPABILITY_MINT_GUARD_ENV, "1").strip().lower() \
        in _TRUTHY


# ── §M1 capability-mechanism discriminator (mechanisms, not dictionaries) ───
# A container-carved domain is a CAPABILITY-MECHANISM (fails mint → shared/
# honest-residual, never a peer tile) iff ALL of:
#   (1) it owns NO state-entity — no module named after the leaf under a
#       state-convention directory in its package, AND
#   (2) it owns NO structured schema sub-tree — no directory named after the
#       leaf inside a shared data/schema/types package (its schema, if any, is
#       a flat leaf, not a structured directory), AND
#   (3) transport fan-in >= 1 — its core module is imported BY the request/
#       transport machinery of >= 1 OTHER domain (inbound consumption direction;
#       the mechanism a request journey passes THROUGH, not a product domain).
# A product domain owns an entity (store OR structured schema) and/or is not a
# dependency inside another domain's transport. Signals reuse structural stack
# conventions (scale-invariant), never per-repo paths.

#: state-store convention dir names (cross-framework; a module named after the
#: domain living here == the domain owns first-class state).
_STATE_DIRS = frozenset({
    "newstore", "store", "stores", "state", "slices", "atoms", "redux",
    "vuex", "pinia", "models", "entities", "reducers",
})
#: shared data/schema/types package or dir name segments (a structured sub-tree
#: named after the domain here == the domain owns a schema entity).
_SCHEMA_SEGMENTS = frozenset({
    "data", "schema", "schemas", "types", "models", "entities", "domain",
})
#: request/transport machinery path segments (consumption-direction fan-in).
_TRANSPORT_SEGMENTS = frozenset({
    "interceptor", "interceptors", "requestrunner", "request-runner",
    "dispatch", "transport", "relay", "kernel", "httpclient", "http-client",
    "fetcher",
})
_SOURCE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _leaf_variants(leaf: str) -> frozenset[str]:
    lo = leaf.lower()
    return frozenset({lo, _singular(lo), lo.rstrip("s"), lo + "s"})


def _repo_root(ctx: Any) -> "Path | None":
    from wystan.pipeline_v2.transport_handoff import _attr
    rp = _attr(ctx, "repo_path", None)
    if rp and Path(str(rp)).is_dir():
        return Path(str(rp))
    return None


def _owns_state_entity(repo: "Path", pkg_root: str, leaf: str) -> str | None:
    """A module named after the leaf under a state-convention dir in the
    package → owns first-class state (bounded convention probe, no full walk)."""
    variants = _leaf_variants(leaf)
    for sd in sorted(_STATE_DIRS):
        for base in ("src", "app", "lib", ""):
            d = (repo / pkg_root / base / sd) if base else (repo / pkg_root / sd)
            if not d.is_dir():
                continue
            for name in sorted(variants):
                for ext in _SOURCE_EXTS:
                    if (d / f"{name}{ext}").is_file():
                        return f"{sd}/{name}{ext}"
                if (d / name).is_dir():
                    return f"{sd}/{name}/"
    return None


def _owns_structured_schema(repo: "Path", leaf: str) -> str | None:
    """A DIRECTORY named after the leaf under a shared data/schema/types package
    → owns a structured schema entity (vs a flat leaf file)."""
    variants = _leaf_variants(leaf)
    roots = sorted(repo.glob("packages/*")) + sorted(repo.glob("*"))
    for pkg in roots:
        if not pkg.is_dir():
            continue
        segs = pkg.name.lower().replace("_", "-").split("-")
        if not (set(segs) & _SCHEMA_SEGMENTS):
            continue
        for sub in ("src", ""):
            base = (pkg / sub) if sub else pkg
            for name in sorted(variants):
                d = base / name
                if d.is_dir():
                    try:
                        if any(d.iterdir()):
                            return str(d.relative_to(repo))
                    except OSError:
                        continue
    return None


def _transport_fanin(repo: "Path", pkg_root: str, leaf: str,
                     surface_dirs: set[str]) -> list[str]:
    """Files under a TRANSPORT-convention path (and NOT under the domain's own
    surface dir) whose import lines reference the leaf token → the domain's core
    module is consumed BY the request-transport of another domain."""
    pkg = repo / pkg_root
    if not pkg.is_dir():
        return []
    stem = leaf.lower().rstrip("s")
    if len(stem) < 3:
        return []
    hits: set[str] = set()
    for f in pkg.rglob("*"):
        if f.suffix not in _SOURCE_EXTS:
            continue
        if ".spec." in f.name or ".test." in f.name:
            continue
        rel = str(f.relative_to(repo))
        low = rel.lower()
        if not any(seg in low for seg in _TRANSPORT_SEGMENTS):
            continue
        if any(rel == sd or rel.startswith(sd.rstrip("/") + "/")
               for sd in surface_dirs):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            if "import" not in line and "from " not in line:
                continue
            if re.search(rf"[\"'/.\-]{re.escape(stem)}", line.lower()):
                hits.add(rel)
                break
    return sorted(hits)


def _is_capability_mechanism(
    leaf: str, info: dict, container: "Feature", ctx: Any,
) -> tuple[bool, dict]:
    """Return ``(is_capability, detail)``. Vacuously ``False`` (never a
    capability — the mint proceeds) when there is no live repo tree to probe
    (synthetic unit scenes), mirroring ``_LocProbe``'s no-channel-open rule so
    the guard is byte-identical off-tree."""
    repo = _repo_root(ctx)
    if repo is None:
        return False, {"no_channel": True}
    pkg_root = _anchor_path(container)
    surface_dirs = {p.rsplit("/", 1)[0] for p in (info.get("paths") or ())
                    if "/" in str(p)}
    store = _owns_state_entity(repo, pkg_root, leaf)
    schema = _owns_structured_schema(repo, leaf)
    owns_entity = bool(store) or bool(schema)
    fanin: list[str] = []
    if not owns_entity:
        fanin = _transport_fanin(repo, pkg_root, leaf, surface_dirs)
    cap = (not owns_entity) and (len(fanin) >= 1)
    return cap, {"store": store, "schema": schema,
                 "owns_entity": owns_entity, "fanin": len(fanin),
                 "fanin_files": fanin[:5], "capability": cap}


# ── token helpers ─────────────────────────────────────────────────────────
def _norm(toks: "frozenset[str]") -> frozenset[str]:
    """Universal-synonym normalize (symmetric on both journey + domain sides)."""
    return frozenset(_SYNONYMS.get(t, t) for t in toks)


def _leaf_tokens(leaf: str) -> frozenset[str]:
    """Distinctive tokens of a domain-dir leaf (synonym-normalized)."""
    out = set()
    for w in leaf.replace("_", "-").split("-"):
        wl = w.lower()
        if len(wl) >= 2 and wl not in _MATCH_STOPWORDS:
            out.add(_singular(wl))
    return _norm(frozenset(out))


def _anchor_path(pf: "Feature") -> str:
    a = str(getattr(pf, "anchor_id", None) or "")
    for pre in ("route:", "ws:", "dev:", "hub:", "fdir:"):
        if a.startswith(pre):
            return a[len(pre):]
    return a


# ── §6.1 source-detection ─────────────────────────────────────────────────
def _is_container_shape(pf: "Feature") -> bool:
    """Structural container OR generic-bucket-at-bare-root. Reuses 6.9965
    ``_is_structural_home`` (``ws:``/``dev:`` anchor, stoplist name, <=2 char)
    and extends it with the generic-bucket dir class (documenso
    ``route:.../components/general`` — a ``route:`` anchor whose leaf is a
    generic bucket name), which ``_is_structural_home`` alone misses."""
    if _is_structural_home(pf):
        return True
    apath = _anchor_path(pf)
    leaf = apath.rstrip("/").rsplit("/", 1)[-1].lower() if apath else ""
    name = str(getattr(pf, "name", None) or "").lower()
    if leaf in _GENERIC_BUCKET or name in _GENERIC_BUCKET:
        return True
    return False


def _oversized(pf: "Feature", loc_median: float) -> bool:
    """Scale-invariant oversize: the container carries >= the board's median
    PF LOC. Ratio/percentile only — never an absolute per-repo threshold."""
    return float(getattr(pf, "loc", 0) or 0) >= max(1.0, loc_median)


def _build_domain_set(pf: "Feature", cdir: str) -> dict[str, dict[str, Any]]:
    """§6.2 CODE-domain-set from the container's member files: leaf -> {loc,
    shape (product|infra), paths}. Shape = product iff seen under a product
    parent (or as a direct child of a components-rooted generic bucket)."""
    dom: dict[str, dict[str, Any]] = {}

    def add(leaf: str, shape: str, loc: int, path: str) -> None:
        leaf = leaf.lower()
        e = dom.setdefault(leaf, {"loc": 0, "shape": "infra", "paths": set()})
        e["loc"] += loc
        e["paths"].add(path)
        if shape == "product":
            e["shape"] = "product"

    for m in (getattr(pf, "member_files", None) or []):
        p = (m.get("path") if isinstance(m, dict) else getattr(m, "path", None)) or ""
        p = str(p).replace("\\", "/")
        loc = int((m.get("loc") if isinstance(m, dict) else getattr(m, "loc", 0)) or 0)
        if cdir not in p:
            continue
        rest = p.split(cdir, 1)[1].lstrip("/").split("/")
        if len(rest) < 2:
            continue
        placed = False
        for i in range(len(rest) - 1):
            seg = rest[i].lower()
            leaf = rest[i + 1]
            if leaf.endswith((".ts", ".tsx", ".vue", ".js", ".jsx")):
                leaf = leaf.rsplit(".", 1)[0]
            if seg in _PRODUCT_PARENTS:
                add(leaf, "product", loc, p); placed = True; break
            if seg in _INFRA_PARENTS:
                add(leaf, "infra", loc, p); placed = True; break
        if not placed and cdir.rstrip("/").rsplit("/", 1)[-1] in _GENERIC_BUCKET \
                and "components" in cdir:
            add(rest[0], "product", loc, p)
    return {k: v for k, v in dom.items() if k not in _GENERIC_BUCKET}


def _entry_dirs(uf: "UserFlow", flow_by_id: dict[str, Any]) -> dict[str, int]:
    dirs: dict[str, int] = {}
    for mid in (getattr(uf, "member_flow_ids", None) or []):
        fl = flow_by_id.get(mid)
        if fl is None:
            continue
        for p in (getattr(fl, "paths", None) or []):
            d = str(p).replace("\\", "/").rsplit("/", 1)[0] if "/" in str(p) else ""
            dirs[d] = dirs.get(d, 0) + 1
    return dirs


def _dominant_domain_dir(edirs: dict[str, int], domset: dict) -> tuple[str | None, float]:
    if not edirs:
        return None, 0.0
    tot = sum(edirs.values())
    score: dict[str, int] = {}
    for dd, c in edirs.items():
        for seg in dd.split("/"):
            if seg in domset:
                score[seg] = score.get(seg, 0) + c
    if not score:
        return None, 0.0
    leaf = max(sorted(score), key=lambda k: score[k])
    return leaf, score[leaf] / tot


# ── §6.3 per-journey resolution ────────────────────────────────────────────
def _resolve(
    uf: "UserFlow", ident: "frozenset[str]", domset: dict,
    existing: dict[str, frozenset], edirs: dict[str, int],
) -> tuple[str, str | None, dict]:
    name_ent = _norm(_tokens(getattr(uf, "name", None))) - ident
    res_ent = _norm(_tokens(getattr(uf, "resource", None))) - ident
    n_dirs = len(edirs)
    dominant = (max(edirs.values()) / sum(edirs.values())) if edirs else 0.0

    # AGGREGATE — name names no entity (verb + container-identity only). Path
    # rail may still rescue it if one domain-dir dominates; else dissolve.
    if not name_ent:
        leaf, sh = _dominant_domain_dir(edirs, domset)
        if leaf and sh >= DOMINANT_FLOOR:
            return "RESOLVES-ABSENT", leaf, {"via": "path-dominant", "share": round(sh, 2)}
        return "AGGREGATE", None, {"reason": "name-generic",
                                   "fanout_dirs": n_dirs, "dominant": round(dominant, 2)}

    entity = name_ent | res_ent
    # RESOLVES-EXISTING — an existing real-domain PF already names this entity.
    best_ex = None
    for pfname, ptoks in existing.items():
        ov = entity & ptoks
        if ov and len(ov) / len(entity) >= AFFINITY_FLOOR:
            sc = (len(ov), pfname)
            if best_ex is None or sc > best_ex[0]:
                best_ex = (sc, pfname)
    if best_ex is not None:
        return "RESOLVES-EXISTING", best_ex[1], {"tokens": sorted(entity & existing[best_ex[1]])}

    # name-first vs domain-set: rank product-shape > resource-overlap > cov > LOC.
    cands = []
    for leaf, info in domset.items():
        core = _leaf_tokens(leaf)
        if not core:
            continue
        ov = core & entity
        if not ov:
            continue
        cov = len(ov) / len(core)
        if cov < AFFINITY_FLOOR:
            continue
        # rank: product-shape > resource-token overlap > entity-token overlap
        # COUNT > owned-LOC. LOC (not cov) is the final tiebreak so the REAL
        # feature dir wins over a same-head stub ('envelope-editor' 4711 LOC
        # beats 'envelope' 171 LOC; cov is the acceptance GATE, not the rank —
        # else the shortest-name husk always wins).
        cands.append((1 if info["shape"] == "product" else 0,
                      len(core & res_ent), len(ov), info["loc"], leaf))
    if not cands:
        if n_dirs >= FANOUT_FLOOR and dominant < DOMINANT_FLOOR:
            return "AGGREGATE", None, {"reason": "path-fanout",
                                       "fanout_dirs": n_dirs, "dominant": round(dominant, 2)}
        return "HONEST-RESIDUAL", None, {"reason": "no-domain-dir", "ent": sorted(entity)}
    cands.sort(reverse=True)
    leaf = cands[0][4]
    return "RESOLVES-ABSENT", leaf, {"shape": domset[leaf]["shape"], "loc": domset[leaf]["loc"]}


# ── §6.4 mint-gate ─────────────────────────────────────────────────────────
def _mint_ok(leaf: str, info: dict, loc_probe: Any) -> tuple[bool, dict]:
    """3 tests (PATH already true — journey-gated by construction here):
    ENTITY/no-husk (owned LOC > 0, leafroute ``_LocProbe`` on the live tree,
    board-loc fallback offline) + DEMO (product surface, not infra shape)."""
    board_loc = int(info.get("loc", 0) or 0)
    if loc_probe is not None and getattr(loc_probe, "channel", False):
        no_husk = loc_probe.loc_of(set(info.get("paths") or ())) > 0
    else:
        no_husk = board_loc > 0
    demo = info.get("shape") == "product" and leaf not in _INFRA_LEAF
    return (no_husk and demo), {"no_husk": no_husk, "demo_ok": demo,
                                "loc": board_loc, "shape": info.get("shape")}


# ── mint machinery (reuse: aggregate_product_feature + canonical_slug) ──────
def _mint_pf(
    leaf: str, info: dict, container: "Feature",
    developer_features: list["Feature"], product_features: list["Feature"],
    used_slugs: set[str],
) -> "Feature | None":
    from wystan.models.types import Feature, MemberFile
    from wystan.pipeline_v2.emission_integrity import canonical_slug
    from wystan.pipeline_v2.nav_taxonomy import aggregate_product_feature

    display = leaf.replace("-", " ").replace("_", " ").title()
    slug = canonical_slug(display) or canonical_slug(leaf)
    if not slug:
        return None
    base, n = slug, 2
    while slug in used_slugs:
        slug = canonical_slug(f"{base} {n}"); n += 1
    used_slugs.add(slug)

    dom_paths = {str(p) for p in (info.get("paths") or ())}
    # contrib = dev features living wholly-or-partly under the domain-dir (for
    # authors/commits/health). The BODY (member_files) is carved from the
    # container so the minted PF is never a 0-LOC husk (I2 / canon §2).
    contrib = [
        d for d in developer_features
        if any(str(p) in dom_paths for p in (getattr(d, "paths", None) or []))
    ]
    desc = (f"Domain '{display}' re-attributed from container "
            f"'{getattr(container, 'name', '')}' (container-journey-rehome).")
    if contrib:
        pf = aggregate_product_feature(name=slug, display_name=display,
                                       description=desc, contrib=contrib)
    else:
        # no dev feature maps to the code-dir — construct the row directly
        # (aggregate_product_feature divides by len(contrib)); the carved
        # member files below still give it a real body.
        from datetime import datetime, timezone
        pf = Feature(
            name=slug, display_name=display, description=desc,
            paths=[], authors=[], total_commits=0, bug_fixes=0,
            bug_fix_ratio=0.0,
            last_modified=datetime.fromtimestamp(0, timezone.utc),
            health_score=0.0, layer="product", name_confidence="high",
        )
    pf.layer = "product"
    pf.anchor_id = f"container-rehome:{getattr(container, 'anchor_id', '')}/{leaf}"
    pf.surface_scope = "product"
    pf.split_from = getattr(container, "name", None)
    # carve the domain-dir member files off the container onto the minted PF.
    carved: list[Any] = []
    kept: list[Any] = []
    for m in (getattr(container, "member_files", None) or []):
        mp = str((m.get("path") if isinstance(m, dict) else getattr(m, "path", None)) or "")
        (carved if mp in dom_paths else kept).append(m)
    container.member_files = kept
    container.paths = [p for p in (getattr(container, "paths", None) or [])
                       if str(p) not in dom_paths]
    carved_loc = sum(
        int((m.get("loc") if isinstance(m, dict) else getattr(m, "loc", 0)) or 0)
        for m in carved)
    pf.member_files = [
        MemberFile(
            path=str((m.get("path") if isinstance(m, dict) else getattr(m, "path", None))),
            role="anchor", confidence=1.0,
            evidence="container-journey-rehome carve",
            primary=True,
            loc=int((m.get("loc") if isinstance(m, dict) else getattr(m, "loc", 0)) or 0),
        ) for m in carved
    ]
    pf.paths = sorted(dom_paths)
    # stamp the minted PF's own owned LOC now (no-husk / I2 — 6.998 recompute
    # will refine it, but the row must never leave this stage as a 0-LOC husk).
    pf.loc = carved_loc
    product_features.append(pf)
    return pf


# ── entry point ────────────────────────────────────────────────────────────
def run_container_journey_rehome(
    product_features: list["Feature"],
    user_flows: list["UserFlow"],
    developer_features: list["Feature"],
    ctx: Any,
    flows: list[Any] | None = None,
) -> dict[str, Any]:
    """Detect container PFs hoarding cross-domain journeys; mint the absent
    domain-PFs from code-dirs and re-home each journey by name; dissolve
    aggregates; leave the rest honest-residual. Conservation by construction
    (ledger rung + carve). Returns telemetry."""
    from wystan.pipeline_v2.overturn_ledger import propose_pf_now

    tele: dict[str, Any] = {
        "enabled": True, "applied": False,
        "containers": [], "minted": [], "rehomed": 0, "dissolved": 0,
        "residual": 0, "moves": [], "skipped": [],
        # container-husk-demote (same flag): a container emptied of ALL its
        # journeys and confirmed a structural husk demotes product -> dev.
        "demoted": [], "demote_devs_repointed": 0, "demote_devs_unowned": 0,
        "demote_skipped": [],
    }
    _guard_on = capability_mint_guard_enabled()
    if _guard_on:
        # Pin-cycle-3 M1 telemetry — added ONLY when the guard is armed so the
        # OFF-world telemetry (serialized scan_meta.container_journey_rehome)
        # stays byte-identical to the pre-guard world (the stage itself is
        # default-ON, so unconditional keys would break byte-identity).
        tele["capability_guard_enabled"] = True
        tele["capability_guarded"] = []
    loc_probe = None
    try:
        from wystan.pipeline_v2.leafroute_promotion import _LocProbe
        sample = [str((m.get("path") if isinstance(m, dict) else getattr(m, "path", None)))
                  for pf in product_features
                  for m in (getattr(pf, "member_files", None) or [])[:2]][:50]
        loc_probe = _LocProbe(ctx, sample)
    except Exception:  # noqa: BLE001 — probe is best-effort; board-loc fallback
        loc_probe = None

    flow_by_id: dict[str, Any] = {}
    for fl in (flows or []):
        for k in (getattr(fl, "uuid", None), getattr(fl, "id", None),
                  getattr(fl, "name", None)):
            if k is not None:
                flow_by_id.setdefault(k, fl)

    # UF index by current home slug (name-keyed, like 6.9965).
    pf_slugs = {str(getattr(pf, "name", "") or "") for pf in product_features}
    held_by_home: dict[str, list["UserFlow"]] = {}
    for uf in user_flows:
        h = getattr(uf, "product_feature_id", None)
        if h:
            held_by_home.setdefault(str(h), []).append(uf)

    # existing real-domain PFs (name tokens) for RESOLVES-EXISTING.
    existing: dict[str, frozenset] = {}
    for pf in product_features:
        if _is_container_shape(pf):
            continue
        toks = _norm(_tokens(getattr(pf, "name", None), getattr(pf, "display_name", None)))
        if toks:
            existing[str(getattr(pf, "name", "") or "")] = toks

    locs = [float(getattr(pf, "loc", 0) or 0) for pf in product_features]
    loc_median = sorted(locs)[len(locs) // 2] if locs else 0.0

    used_slugs = set(pf_slugs)
    demoted_names: set[str] = set()
    for container in list(product_features):
        cname = str(getattr(container, "name", "") or "")
        if not _is_container_shape(container) or not _oversized(container, loc_median):
            continue
        # map container -> its held journeys (by name-slug OR canonical bucket).
        held = held_by_home.get(cname, [])
        if not held:
            # UF pfid may be a slugged form of the container name; match loosely.
            from wystan.pipeline_v2.emission_integrity import canonical_slug
            cslug = canonical_slug(cname)
            held = [u for u in user_flows
                    if canonical_slug(str(getattr(u, "product_feature_id", "") or "")) == cslug]
        if len(held) < FLOOR_JOURNEYS:
            continue

        cdir = _anchor_path(container)
        domset = _build_domain_set(container, cdir)
        ident = _norm(_tokens(cname, getattr(container, "display_name", None))) | _GENERIC_BUCKET

        # classify every held journey; measure domain-diversity for the gate.
        plans: list[tuple["UserFlow", str, str | None, dict]] = []
        domains: set[str] = set()
        for uf in held:
            edirs = _entry_dirs(uf, flow_by_id)
            verdict, tgt, det = _resolve(uf, ident, domset, existing, edirs)
            plans.append((uf, verdict, tgt, det))
            if verdict in ("RESOLVES-ABSENT", "RESOLVES-EXISTING") and tgt:
                domains.add(tgt)

        # GUARDS + domain-diversity gate (source-detect §6.1).
        if len(domains) < FLOOR_DOMAINS:
            tele["skipped"].append({"container": cname, "reason": "cohesive/low-diversity",
                                    "domains": sorted(domains)})
            continue
        if _ui_kit_guard(held):
            tele["skipped"].append({"container": cname, "reason": "ui-kit-demo"})
            continue

        tele["containers"].append({"container": cname, "held": len(held),
                                   "domains": sorted(domains)})
        minted_this: dict[str, "Feature"] = {}
        for uf, verdict, tgt, det in plans:
            uid = str(getattr(uf, "id", "") or "")
            uname = str(getattr(uf, "name", "") or "")
            if verdict == "RESOLVES-ABSENT" and tgt:
                info = domset.get(tgt) or {}
                # Pin-cycle-3 M1 — capability mint-guard leg (SEPARATE flag,
                # default OFF). A capability-MECHANISM candidate (owns no state/
                # schema entity AND is consumed by another domain's transport)
                # FAILs the mint → the journey is honest-residual, never a peer
                # tile. OFF ⇒ this branch is skipped entirely (byte-identical).
                if _guard_on and tgt not in minted_this:
                    is_cap, cap_det = _is_capability_mechanism(
                        tgt, info, container, ctx)
                    if is_cap:
                        tele["capability_guarded"].append({
                            "container": cname, "domain": tgt, **cap_det})
                        _residual(uf, tele, uid, uname, cname,
                                  reason=f"capability-mechanism:{cap_det}")
                        continue
                ok, mg = _mint_ok(tgt, info, loc_probe)
                if not ok:
                    _residual(uf, tele, uid, uname, cname, reason=f"mint-gate-fail:{mg}")
                    continue
                if tgt not in minted_this:
                    minted_pf = _mint_pf(tgt, info, container, developer_features,
                                         product_features, used_slugs)
                    if minted_pf is None:
                        _residual(uf, tele, uid, uname, cname, reason="mint-slug-fail")
                        continue
                    minted_this[tgt] = minted_pf
                    tele["minted"].append({"container": cname, "domain": tgt,
                                           "pf": str(getattr(minted_pf, "name", "")),
                                           "loc": mg["loc"]})
                target_slug = str(getattr(minted_this[tgt], "name", ""))
                propose_pf_now(uf, target_slug, rung="container-journey-rehome")
                if getattr(uf, "lane_ref", None) is not None:
                    uf.lane_ref = None
                if getattr(uf, "residual", False):
                    uf.residual = False
                tele["rehomed"] += 1
                tele["moves"].append({"uf": uid, "name": uname, "from": cname,
                                      "to": target_slug, "verdict": "mint"})
            elif verdict == "RESOLVES-EXISTING" and tgt:
                propose_pf_now(uf, tgt, rung="container-journey-rehome")
                if getattr(uf, "lane_ref", None) is not None:
                    uf.lane_ref = None
                if getattr(uf, "residual", False):
                    uf.residual = False
                tele["rehomed"] += 1
                tele["moves"].append({"uf": uid, "name": uname, "from": cname,
                                      "to": tgt, "verdict": "existing"})
            elif verdict == "AGGREGATE":
                _residual(uf, tele, uid, uname, cname, reason="aggregate", dissolved=True)
            else:
                _residual(uf, tele, uid, uname, cname, reason="honest-residual")

        # ── container-husk-demote (§Phase-1.5, SAME flag) ──────────────────
        # After ALL journeys were extracted, if the container is now an empty
        # structural husk (4-signal AND), demote product -> dev so it no longer
        # renders as a product feature. Its born domains shared-attribute their
        # carved dirs; the rest of its devs become honest-unowned dev-layer.
        born_paths = {
            str(getattr(pf, "name", "") or ""): {
                str(p) for p in ((domset.get(tgt) or {}).get("paths") or ())
            }
            for tgt, pf in minted_this.items()
        }
        # was_rehome_source: B moved >=1 journey OUT of this container this run
        # (any move out — rehome / existing / dissolve / honest-residual counts).
        moved_out = sum(
            1 for uf in held
            if str(getattr(uf, "product_feature_id", "") or "") != cname)
        skip = _husk_demote_skip_reason(container, user_flows,
                                        was_rehome_source=moved_out >= 1)
        if skip is None:
            _demote_container(container, born_paths, developer_features,
                              user_flows, tele)
            demoted_names.add(cname)
        else:
            tele["demote_skipped"].append({"container": cname, "reason": skip})

    # Filter demoted containers out of the product layer (they now live in
    # developer_features). Post-loop so the loop's list() snapshot is intact.
    if demoted_names:
        product_features[:] = [
            pf for pf in product_features
            if str(getattr(pf, "name", "") or "") not in demoted_names
        ]

    tele["applied"] = bool(
        tele["rehomed"] or tele["dissolved"] or tele["residual"]
        or tele["demoted"])
    return tele


#: UI-kit primitive names (scale-invariant design-system vocabulary — never a
#: per-repo term). A container whose EVERY held journey's resource is one of
#: these is a UI-kit demo (plane·Propel), a noise-suppress class, NOT B.
_UI_PRIMITIVES = frozenset({
    "avatar", "icon", "toast", "tooltip", "popover", "toolbar", "badge",
    "spinner", "button", "dropdown", "modal", "chip", "skeleton", "switch",
    "slider", "checkbox", "radio", "accordion", "breadcrumb", "pagination",
    "menu", "drawer", "dialog", "card", "tag", "alert", "banner",
})


def _ui_kit_guard(held: list["UserFlow"]) -> bool:
    """plane·Propel class — EVERY held journey's resource is a UI-kit primitive
    (avatar/icon/toast/tooltip/...). A container with even one real-domain
    journey (resource carries a non-primitive entity token) is NOT UI-kit."""
    if not held:
        return False
    for uf in held:
        res = _tokens(getattr(uf, "resource", None))
        if not res or (res - _UI_PRIMITIVES):
            return False
    return True


def _residual(uf: "UserFlow", tele: dict, uid: str, uname: str, cname: str,
              *, reason: str, dissolved: bool = False) -> None:
    """Honest fallback — the journey leaves the container with NO invented
    home (``pfid=None, residual=True``); never dropped, never left on the
    container. AGGREGATE journeys are marked dissolved (downstream demote)."""
    from wystan.pipeline_v2.overturn_ledger import propose_pf_now
    propose_pf_now(uf, None, rung="container-journey-rehome")
    uf.residual = True
    if dissolved:
        tele["dissolved"] += 1
    else:
        tele["residual"] += 1
    tele["moves"].append({"uf": uid, "name": uname, "from": cname,
                          "to": None, "verdict": reason})


#: shared_reason marker for a dev left honestly unowned by the demote (its code
#: is plumbing with no product surface — the canon dev-layer honest residual).
_DEMOTE_UNOWNED_REASON = "container-husk-demote: plumbing residual (no product surface)"


def _husk_demote_skip_reason(
    container: "Feature", user_flows: list["UserFlow"],
    was_rehome_source: bool,
) -> str | None:
    """The 4-signal AND (binding). Returns None ⇒ demote; a reason ⇒ skip.

      1. structural anchor (``_is_container_shape`` — ws:/hub:/dev:/fdir: or
         a generic-name-at-bare-root bucket);
      2. ∧ 0 journeys still homed on it AFTER re-home (fully emptied);
      3. ∧ 0 flows;
      4. ∧ ( ``was_rehome_source`` — B moved >=1 journey OUT of this PF THIS
         stage-run (rehome / existing / dissolve / honest-residual — any move
         out counts) — OR ``name_evidence`` carries the engine's own
         structural-token marker ``unresolved-dir-token`` ).

    Signal #4's rehome-source arm (operator ruling): a route-extractor can
    name a generic bucket CONFIDENTLY (documenso 'General' — name_evidence=None,
    name_confidence=high) so the ``unresolved-dir-token`` marker is absent even
    though the PF is plainly a container (it just yielded >=1 journey to a real
    domain). The over-demote guard still holds: a REAL journey-less feature is
    NEVER a rehome-source (B's §6.1 domain-diversity source-detect never fires
    on it), and it carries route/nav/schema evidence not the structural token —
    so neither arm of the OR is satisfied → never demoted (canon §3 honest gap).
    The token stays an OR-corroborator (belt-and-suspenders)."""
    if not _is_container_shape(container):
        return "not-structural"
    cname = str(getattr(container, "name", "") or "")
    still_held = sum(
        1 for uf in user_flows
        if str(getattr(uf, "product_feature_id", "") or "") == cname)
    if still_held:
        return f"still-holds-{still_held}-journeys"
    if getattr(container, "flows", None):
        return "has-flows"
    if not was_rehome_source:
        ev = getattr(container, "name_evidence", None) or []
        if not any(_UNRESOLVED_DIR_TOKEN in str(e) for e in ev):
            # neither arm of signal #4 → a real journey-less feature (never a
            # rehome-source, carries route/nav/schema evidence) → honest gap.
            return "not-rehome-source-nor-unresolved-dir-token"
    return None


def _demote_container(
    container: "Feature", born_paths: dict[str, set[str]],
    developer_features: list["Feature"], user_flows: list["UserFlow"],
    tele: dict[str, Any],
) -> None:
    """Demote an emptied structural-husk container product→dev. Its born
    domains shared-attribute their carved dirs (dev re-point); the rest of its
    devs become honest-unowned dev-layer; the container itself becomes a
    developer_feature holding its residual plumbing member_files (0 orphan).
    Removal from ``product_features`` is done by the caller (post-loop)."""
    cname = str(getattr(container, "name", "") or "")
    repointed = unowned = 0
    for dev in list(developer_features):
        if dev is container:
            continue
        if str(getattr(dev, "product_feature_id", "") or "") != cname:
            continue
        dev_paths = {str(p) for p in (getattr(dev, "paths", None) or [])}
        target = None
        for born_slug, paths in sorted(born_paths.items()):
            if dev_paths & paths:
                target = born_slug
                break
        if target is not None:
            dev.product_feature_id = target  # born domain owns its carved dir
            if getattr(dev, "shared_reason", None):
                dev.shared_reason = None
            repointed += 1
        else:
            dev.product_feature_id = None     # honest unowned plumbing dev
            dev.shared_reason = _DEMOTE_UNOWNED_REASON
            unowned += 1
    # the container becomes a developer_feature holding its residual plumbing
    # (absorb any same-name dev twin so there is exactly ONE 'cname' dev).
    twins = [d for d in developer_features
             if d is not container and str(getattr(d, "name", "") or "") == cname]
    seen = {str((mf.get("path") if isinstance(mf, dict) else getattr(mf, "path", None)))
            for mf in (getattr(container, "member_files", None) or [])}
    seen_p = set(str(p) for p in (getattr(container, "paths", None) or []))
    for tw in twins:
        for mf in (getattr(tw, "member_files", None) or []):
            mp = str((mf.get("path") if isinstance(mf, dict) else getattr(mf, "path", None)))
            if mp not in seen:
                seen.add(mp)
                container.member_files.append(mf)
        for p in (getattr(tw, "paths", None) or []):
            if str(p) not in seen_p:
                seen_p.add(str(p))
                container.paths = list(getattr(container, "paths", None) or []) + [p]
        developer_features.remove(tw)
    container.layer = "developer"
    container.product_feature_id = None
    developer_features.append(container)
    tele["demote_devs_repointed"] += repointed
    tele["demote_devs_unowned"] += unowned
    tele["demoted"].append({
        "container": cname, "anchor": str(getattr(container, "anchor_id", "") or ""),
        "members": len(getattr(container, "member_files", None) or []),
        "devs_repointed": repointed, "devs_unowned": unowned,
        "twins_absorbed": len(twins),
    })


# ════════════════════════════════════════════════════════════════════════════
# Stage 6.9966-FM — Common Tier-2 FILE-SOURCED container minting
# ════════════════════════════════════════════════════════════════════════════
# THE DISEASE (grounded, draw-variance probe 2026-07-31): the 6.9966 container
# decomposition of a monorepo shared-package blob is JOURNEY-DRIVEN on BOTH
# ends — the source-detect diversity gate (>= FLOOR_DOMAINS journeys resolving
# to distinct domains) AND the rehome actuator (a domain-PF mints only when a
# journey names it). So the SAME container flickers between keyed draws:
#   * hoppscotch ``common`` draw K1 — 13 journeys / 9 domains → 5 domain-PFs
#     minted + container demoted;
#   * hoppscotch ``common`` draw K2 — 3 GENERIC journeys / 1 domain → the
#     diversity gate skips → ``common`` survives as a 79 301-LOC blob.
# The decomposition VERDICT (should this container split, and into WHAT) must
# not depend on which journeys the LLM happened to draw.
#
# THE STABLE SUBSTRATE (draw-independent): Stage 8.9.5 (llm_component_split,
# phase_layer2 — runs BEFORE this phase) labels the container's ``components``
# children ``domain`` vs ``ui`` with a prompt-hash-CACHED call. The label cache
# is content-hash-keyed (never scrubbed, never flag-keyed), so it is
# BYTE-IDENTICAL across draws (probe: both draws 19 domains + 5 groupings,
# cache_hits=1 llm_calls=0, features_split=1). 8.9.5 MATERIALISES each labelled
# domain as a developer sub-feature carved off the container, tagged
# ``evidence="sub-domain of '<container>'"`` — the ``_make_subfeature`` marker.
# THIS stage reads those materialised sub-domain dev features (no cache
# reconstruction, no prompt drift) as the file-domain substrate.
#
# THE ANTI-CASE (binding, from probe): PURE file-diversity OVER-FIRES — the
# sibling packages ``hoppscotch-sh-admin`` (17 product-shape file-dirs) and
# ``hoppscotch-desktop`` (4) both have ``components`` subtrees, yet 8.9.5 does
# NOT split them (they are not the repo blob → not oversized at 8.9.5's cut →
# ZERO sub-domain dev features). Gating on "container holds >= FLOOR_DOMAINS
# component sub-domain dev features SPLIT FROM ITSELF" reuses 8.9.5's own
# candidate verdict and excludes sh-admin/desktop at the CONTAINER gate.
#
# THE MECHANISM (deterministic, journey-free):
#   1. GATE — container-shape ∧ oversized ∧ >= FLOOR_DOMAINS 8.9.5 component
#      sub-domain leaves (the single-generic-components-blob 8.9.5 vetted).
#   2. MINT — one domain-PF per leaf that passes the SAME 6.9966 product-right
#      tests: ``_mint_ok`` (no-husk owned-LOC > 0 + DEMO product-surface, not
#      infra-leaf) AND ``_is_capability_mechanism`` (cookies-class stays
#      shared, never a peer tile) AND the MEDIAN-LOC FLOOR (lead ruling
#      2026-07-31; scale-invariant, the stage's own upper-median idiom, never
#      an absolute number): a domain mints only when its owned LOC >= the
#      median LOC over ALL the container's candidate label-domains. The
#      sub-median tail (hoppscotch workspace 230 / profile 364 / accesstokens
#      488 / documentation 496 / aiexperiments 512) stays residual on the
#      demoted husk (conserved), trimming the mint-set 15 → 10; the median
#      ELEMENT itself is kept (>=), so an all-equal-LOC fan-out is never
#      trimmed. Reuses ``_mint_pf`` — members CARVED off the container (canon
#      §2, never a 0-LOC husk). Only fires when >= FLOOR_DOMAINS leaves
#      survive (a lone domain is not a decomposition).
#   3. ATTACH — the container's held journeys re-home BY NAME onto the minted
#      (now EXISTING) domains via ``_resolve`` with an EMPTY domset (so the
#      attach can only RESOLVES-EXISTING, never journey-mint — decomposition
#      stays file-driven). Journeys that name no minted domain leave as honest-
#      residual (canon §3); journeyless domains are honest product-gaps.
#   4. HUSK — the container, emptied BY FILE-CARVE, demotes product→dev via the
#      SAME 4-signal ``_husk_demote_skip_reason``, with ``was_rehome_source``
#      EXTENDED to fire on the file-carve (``bool(minted)``) — so the demote is
#      draw-independent even when 0 journeys moved (the journeyless-container
#      case), not gated on the journey layer.
#
# COMPOSITION with 6.9966 (order: file-mint runs FIRST, justified): running
# file-mint BEFORE the journey-rehome means the draw-INDEPENDENT decomposition
# lands before the draw-DEPENDENT 6.9966 ever sees the container — on K1 6.9966
# would otherwise journey-mint 5 + demote ``common`` before file-mint could act.
# After file-mint, the container is already demoted (gone from product_features)
# and the 15 domain-PFs are EXISTING targets 6.9966 re-homes OTHER containers'
# journeys into (RESOLVES-EXISTING, never a double-mint). No changes to 6.9966.
#
# Gated by ``WYSTAN_CONTAINER_FILE_MINT`` — default **ON** since the
# 2026-07-31 flip-pack №15 (KEY_SCHEMA 50; keyed 2-draw proof hoppscotch —
# mint-set identical d1==d2, PF 20==20 diff ∅, Common demoted on both draws,
# 10 domains stable incl. history). Unset ≡ explicit ``1``; explicit
# 0/false/off/no ⇒ the stage is never called (no scan_meta key ⇒
# byte-identical OFF-world) — a kill-switch forever.

CONTAINER_FILE_MINT_ENV = "WYSTAN_CONTAINER_FILE_MINT"

#: Component-collection container segments whose LLM-vetted children are the
#: file-domain substrate — the SAME subset 8.9.5 descends into (never ``ui`` /
#: ``widgets``). Kept identical to Stage 8.9.5 ``_COMPONENT_SEGS``.
_COMPONENT_SEGS = frozenset({"components", "component", "hooks", "hook"})


def container_file_mint_enabled() -> bool:
    """Default **ON** since the 2026-07-31 flip-pack №15 (KEY_SCHEMA 50; keyed
    2-draw closing proof hoppscotch — mint-set IDENTICAL d1==d2 (PF 20==20,
    diff ∅), Common demoted on both draws, 10 domains exactly, history kept
    without flicker). Unset ≡ explicit ``"1"``; explicit ``0``/``false``/
    ``off``/``no`` stays a kill-switch forever (the stage is never called ⇒
    no scan_meta key ⇒ byte-identical OFF-world). The pre-flip WIDE truthy set
    is preserved LITERALLY — only the ``os.environ.get`` default moved
    ``"0"`` → ``"1"``."""
    return os.environ.get(CONTAINER_FILE_MINT_ENV, "1").strip().lower() in _TRUTHY


def _component_domain_leaves(
    cname: str, cdir: str, developer_features: list["Feature"],
) -> dict[str, set[str]]:
    """The 8.9.5 file-domain substrate: ``leaf -> {member paths}`` for every
    component sub-domain dev feature SPLIT FROM this container (``evidence=
    "sub-domain of '<cname>'"``) whose paths live under the container's
    ``components``/``hooks`` subtree. Draw-independent — the 8.9.5 labels are
    prompt-hash-cached, so the materialised sub-features are byte-identical
    across draws. Excludes 8.9's deterministic top-level infra splits
    (``newstore``/``composables``/…) — those live OUTSIDE the ``components``
    subtree (8.9 STOPS at ``components``, only 8.9.5 descends into it)."""
    from wystan.pipeline_v2.stage_8_9_anchor_subdecompose import (
        _SUBDOMAIN_MARKER,
    )

    if not cdir:
        return {}
    want = f"{_SUBDOMAIN_MARKER} of '{cname}'"
    leaves: dict[str, set[str]] = {}
    for dev in developer_features:
        if dev is None or str(getattr(dev, "name", "") or "") == cname:
            continue
        # split-source marker lives on every carved member's evidence.
        src_ok = False
        for m in (getattr(dev, "member_files", None) or []):
            ev = str(
                (m.get("evidence") if isinstance(m, dict)
                 else getattr(m, "evidence", None)) or "")
            if ev == want:
                src_ok = True
                break
        if not src_ok:
            continue
        for p in (getattr(dev, "paths", None) or []):
            p = str(p).replace("\\", "/")
            if cdir not in p:
                continue
            rest = p.split(cdir, 1)[1].lstrip("/").split("/")
            for i in range(len(rest) - 1):
                if rest[i].lower() in _COMPONENT_SEGS:
                    leaves.setdefault(rest[i + 1].lower(), set()).add(p)
                    break
    return leaves


def run_container_file_mint(
    product_features: list["Feature"],
    user_flows: list["UserFlow"],
    developer_features: list["Feature"],
    ctx: Any,
    flows: list[Any] | None = None,
) -> dict[str, Any]:
    """File-sourced container minting (Common Tier-2). Decompose an 8.9.5-
    eligible single-generic-components-blob container into its file-domain PFs
    DETERMINISTICALLY (journey-independent), attach the container's journeys by
    name onto the minted domains, and demote the file-emptied container. A
    domain mints only when it passes the reused 6.9966 guards AND the
    scale-invariant median-LOC floor (owned LOC >= the median over ALL the
    container's candidate label-domains; sub-floor leaves stay residual on the
    demoted husk — conserved). Runs BEFORE 6.9966. Conservation by construction
    (``_mint_pf`` carve + overturn ledger + ``_demote_container``). Returns
    telemetry."""
    from wystan.pipeline_v2.emission_integrity import canonical_slug
    from wystan.pipeline_v2.overturn_ledger import propose_pf_now

    tele: dict[str, Any] = {
        "enabled": True, "applied": False,
        "containers": [], "minted": [], "rehomed": 0, "dissolved": 0,
        "residual": 0, "moves": [], "skipped": [],
        "mint_gate_failed": [], "capability_guarded": [], "floor_filtered": [],
        "demoted": [], "demote_devs_repointed": 0, "demote_devs_unowned": 0,
        "demote_skipped": [],
    }
    _guard_on = capability_mint_guard_enabled()
    loc_probe = None
    try:
        from wystan.pipeline_v2.leafroute_promotion import _LocProbe
        sample = [str((m.get("path") if isinstance(m, dict)
                       else getattr(m, "path", None)))
                  for pf in product_features
                  for m in (getattr(pf, "member_files", None) or [])[:2]][:50]
        loc_probe = _LocProbe(ctx, sample)
    except Exception:  # noqa: BLE001 — probe is best-effort; board-loc fallback
        loc_probe = None

    flow_by_id: dict[str, Any] = {}
    for fl in (flows or []):
        for k in (getattr(fl, "uuid", None), getattr(fl, "id", None),
                  getattr(fl, "name", None)):
            if k is not None:
                flow_by_id.setdefault(k, fl)

    held_by_home: dict[str, list["UserFlow"]] = {}
    for uf in user_flows:
        h = getattr(uf, "product_feature_id", None)
        if h:
            held_by_home.setdefault(str(h), []).append(uf)

    # existing real-domain PFs (name tokens) for the RESOLVES-EXISTING attach —
    # grown with each minted domain so the attach can name it.
    existing: dict[str, frozenset] = {}
    for pf in product_features:
        if _is_container_shape(pf):
            continue
        toks = _norm(_tokens(getattr(pf, "name", None),
                             getattr(pf, "display_name", None)))
        if toks:
            existing[str(getattr(pf, "name", "") or "")] = toks

    locs = [float(getattr(pf, "loc", 0) or 0) for pf in product_features]
    loc_median = sorted(locs)[len(locs) // 2] if locs else 0.0
    used_slugs = {str(getattr(pf, "name", "") or "") for pf in product_features}
    demoted_names: set[str] = set()

    for container in list(product_features):
        cname = str(getattr(container, "name", "") or "")
        if not _is_container_shape(container) \
                or not _oversized(container, loc_median):
            continue
        cdir = _anchor_path(container)
        cand_leaves = _component_domain_leaves(cname, cdir, developer_features)
        # ── GATE (§1): 8.9.5-eligible single-generic-components-blob ──────
        if len(cand_leaves) < FLOOR_DOMAINS:
            continue  # not an 8.9.5-decomposed container (excludes sh-admin)

        domset_all = _build_domain_set(container, cdir)
        # ── §2 MEDIAN-LOC FLOOR (lead ruling 2026-07-31; scale-invariant) ──
        # Upper-median LOC over ALL the container's candidate label-domains
        # (guard-rejected ones included — the median describes the whole
        # fan-out, not the survivors) using the stage's own ``loc_median``
        # idiom. A domain mints only when its owned LOC >= this floor; the
        # median element itself passes (>=), so an all-equal-LOC fan-out is
        # never trimmed. Sub-floor leaves are never carved — their files stay
        # on the container and ride into the demoted husk (conserved).
        cand_locs = sorted(
            int((domset_all.get(lf) or {}).get("loc", 0) or 0)
            for lf in cand_leaves if domset_all.get(lf)
        )
        dom_floor = cand_locs[len(cand_locs) // 2] if cand_locs else 0
        # ── evaluate the mint-set WITHOUT mutating (partial-decompose guard) ─
        plan: list[tuple[str, dict]] = []
        for leaf in sorted(cand_leaves,
                           key=lambda k: -int((domset_all.get(k) or {}).get("loc", 0) or 0)):
            info = domset_all.get(leaf)
            if not info:
                continue
            if _guard_on:
                is_cap, cap_det = _is_capability_mechanism(
                    leaf, info, container, ctx)
                if is_cap:
                    tele["capability_guarded"].append(
                        {"container": cname, "domain": leaf, **cap_det})
                    continue
            ok, mg = _mint_ok(leaf, info, loc_probe)
            if not ok:
                tele["mint_gate_failed"].append(
                    {"container": cname, "domain": leaf, **mg})
                continue
            leaf_loc = int(info.get("loc", 0) or 0)
            if leaf_loc < dom_floor:
                tele["floor_filtered"].append(
                    {"container": cname, "domain": leaf,
                     "loc": leaf_loc, "floor": dom_floor})
                continue
            plan.append((leaf, info))
        # a lone surviving domain is not a decomposition → leave untouched
        # (byte-identical to not firing on this container).
        if len(plan) < FLOOR_DOMAINS:
            tele["skipped"].append(
                {"container": cname, "reason": "under-floor-after-guards",
                 "survivors": len(plan), "candidates": len(cand_leaves)})
            continue

        tele["containers"].append(
            {"container": cname, "candidate_leaves": sorted(cand_leaves),
             "minted_count": len(plan), "loc_floor": dom_floor})

        # ── MINT (§2): one domain-PF per surviving leaf; carve off container ─
        minted_this: dict[str, "Feature"] = {}
        for leaf, info in plan:
            minted_pf = _mint_pf(leaf, info, container, developer_features,
                                 product_features, used_slugs)
            if minted_pf is None:
                tele["mint_gate_failed"].append(
                    {"container": cname, "domain": leaf, "reason": "slug-fail"})
                continue
            minted_this[leaf] = minted_pf
            mname = str(getattr(minted_pf, "name", "") or "")
            existing[mname] = _norm(_tokens(mname,
                                            getattr(minted_pf, "display_name", None)))
            tele["minted"].append(
                {"container": cname, "domain": leaf, "pf": mname,
                 "loc": int(info.get("loc", 0) or 0)})

        # ── ATTACH (§3): held journeys re-home BY NAME onto minted domains ──
        held = held_by_home.get(cname, [])
        if not held:
            cslug = canonical_slug(cname)
            held = [u for u in user_flows
                    if canonical_slug(
                        str(getattr(u, "product_feature_id", "") or "")) == cslug]
        ident = _norm(_tokens(cname, getattr(container, "display_name", None))) \
            | _GENERIC_BUCKET
        for uf in held:
            uid = str(getattr(uf, "id", "") or "")
            uname = str(getattr(uf, "name", "") or "")
            edirs = _entry_dirs(uf, flow_by_id)
            # EMPTY domset ⇒ RESOLVES-EXISTING only (never a journey-mint —
            # decomposition stays purely file-driven).
            verdict, tgt, _det = _resolve(uf, ident, {}, existing, edirs)
            if verdict == "RESOLVES-EXISTING" and tgt:
                propose_pf_now(uf, tgt, rung="container-file-mint")
                if getattr(uf, "lane_ref", None) is not None:
                    uf.lane_ref = None
                if getattr(uf, "residual", False):
                    uf.residual = False
                tele["rehomed"] += 1
                tele["moves"].append({"uf": uid, "name": uname, "from": cname,
                                      "to": tgt, "verdict": "existing"})
            else:
                _residual(uf, tele, uid, uname, cname,
                          reason=f"honest-residual:{verdict.lower()}",
                          dissolved=(verdict == "AGGREGATE"))

        # ── HUSK (§4): file-emptied container demotes product→dev ───────────
        born_paths = {
            str(getattr(pf, "name", "") or ""): {
                str(p) for p in ((domset_all.get(leaf) or {}).get("paths") or ())
            }
            for leaf, pf in minted_this.items()
        }
        # was_rehome_source EXTENDED — file-carve (bool(minted_this)) is itself
        # a "moved members out" signal, so the demote fires draw-independently
        # even when 0 journeys moved (journeyless-container case).
        moved_out = sum(
            1 for uf in held
            if str(getattr(uf, "product_feature_id", "") or "") != cname)
        skip = _husk_demote_skip_reason(
            container, user_flows,
            was_rehome_source=bool(minted_this) or moved_out >= 1)
        if skip is None:
            _demote_container(container, born_paths, developer_features,
                              user_flows, tele)
            demoted_names.add(cname)
        else:
            tele["demote_skipped"].append({"container": cname, "reason": skip})

    if demoted_names:
        product_features[:] = [
            pf for pf in product_features
            if str(getattr(pf, "name", "") or "") not in demoted_names
        ]

    tele["applied"] = bool(
        tele["minted"] or tele["rehomed"] or tele["dissolved"]
        or tele["residual"] or tele["demoted"])
    return tele
