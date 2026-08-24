"""fixb125 — CLI **command-anchor supplier** (gate G1).

THE CLASS (probe canon, ledger 2026-08-06 "PROBE CLI ops-vs-product" +
"PROBE fan-in")
==============================================================
A repo's own shipped command-line interface is a PRODUCT surface — the
thing a user installs and types — yet on the measured world its
developer unit sits in ``platform_infrastructure`` with no product
right: caddy ``cmd``, lobe-chat ``cli``, ollama ``cmd``/``launch``,
tracecat ``tracecat-admin``, unkey ``api``. Meanwhile a repo's *ops*
command surface (rake maintenance tasks, codegen scripts, cargo-xtask,
NestJS CQRS ``*.command.ts``) must stay off the product map.

The probe measured every discriminating axis on 16 boards / 34 clusters
and ratified exactly one gate. It is reproduced here verbatim; the axes
it REFUTED (co-location with the server binary, import-direction,
publish flags, fan-in from product modules, help-verb vocabulary) are
deliberately absent and must not be reintroduced without a new probe.

THE UNIT OF JUDGEMENT is the **CLI entry cluster** — the registration
sites grouped by their nearest owning manifest — never the board: onyx
carries a product CLI (``cli/``) and an ops CLI (``tools/ods``) at the
same time, so a per-board verdict is impossible.

GATE G1 = P0 ∧ P1-strict
========================
``P0`` — **import-binding**: the registration site resolves to the CLI
framework through a real import. Both arms count:

* VENDOR — ``spf13/cobra``, ``urfave/cli``, ``clap``, ``click``,
  ``typer``, ``commander``, ``@oclif/core`` …
* IN-REPO — a self-hosted framework reached through the same selector
  (unkey's ``github.com/unkeyed/unkey/pkg/cli``). Vendor-only binding
  loses 62 of unkey's 85 sites — measured.

P0 alone is what a naive census sees, and it carries ~18 % pure noise:
``std::process::Command::new`` in a Tauri shell and NestJS CQRS
``*.command.ts`` are NOT command registrations (novu "24:17" was void).
Those die on the import-binding rung, named as anti-cases.

``P1-strict`` — **distribution**: the cluster's nearest manifest
declares an installable binary (go ``package main`` + ``func main``,
``[project.scripts]``, ``package.json`` ``bin``, Cargo ``[[bin]]`` /
crate ``src/main.rs``) AND that declared entry target RESOLVES INTO the
cluster. The strictness is load-bearing:

* fastapi declares ``fastapi.cli:main`` at the root while its typer
  sites live in ``scripts/`` — the entry does not resolve → OPS;
* twenty has ZERO bin declarations against 90 nest-commander sites →
  OPS (the thinnest anti-case, and the one an import-direction gate
  would have shipped: twenty scored the highest internal ratio in the
  world).

Measured on the 16-board matrix: recall 1.00 (13/13 product clusters),
anti-cases 5/5 (fastapi / chatwoot-rake / onyx-argparse ×3 /
core-redplanet-std / twenty), precision 0.62, harm-adjusted
LOC-precision 82.9 %.

KNOWN LIMITS (named, not bought — fan-in probe REFUTED every tune)
==================================================================
G1 admits **distributed developer-tooling**: a devtool that is really
shipped as a binary is, by distribution, indistinguishable from a
shipped product CLI. The two measured residents are

* ``onyx tools/ods`` — onyx-devtools, 6 215 LOC (81 % of the residue),
* ``unkey web/tools/gha-fetch-digest`` — a CI helper, 188 LOC.

The fan-in axis probed as a tune (board-grounded / UF-journey /
anchor-independent, both scopes) was REFUTED as circular: the
denominator is empty on 12/21 clusters (a good CLI is self-contained by
definition), the ALL-scope variant correlates 0.706 with the promotion
state it was meant to predict, and it inverts on meilisearch. Every
variant that kills both harmful FPs also kills lobe-chat's 6 901-LOC
product CLI — a worse gate, not a tune. ``npm private:true`` is not
wired (0 % of the harmful class, JS-only asymmetry) and the
intent-of-audience verb axis is parked as a dictionary (mechanisms, not
vocabularies: corroboration only, never a gate).

WHAT THIS MODULE DOES **NOT** DO
================================
It does not mint anything. It supplies COMMAND ANCHORS — the
registration ``file:line`` plus the declared command name — that the
Stage 6.86 ladder feeds into the lineage of an ALREADY EXISTING dev
unit (the S1-manifest anchor-supplier precedent). The promotion, the
mint bar, the double-mint guard and the telemetry all live at the
consuming seam.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from wystan.pipeline_v2.data import load_yaml

__all__ = [
    "CLI_ANCHOR_SUPPLY_ENV",
    "CliCluster",
    "CommandSite",
    "cli_anchor_supply_enabled",
    "cluster_of_paths",
    "detect_cli_clusters",
    "detect_cli_clusters_cached",
    "load_cli_frameworks",
    "reset_cluster_cache",
    "supplied_tile_admits",
]

#: fixb125+126 — CLI anchor supply. Default **ON** (flip #31, 2026-08-07,
#: warden CLEAR-WITH-DEBT #30-bis on c22/c23, KS 65; unset ≡ explicit
#: ``1``). Explicit ``0`` ⇒ the detector is never called, no
#: ``scan_meta`` key, board byte-identical (kill-switch forever).
CLI_ANCHOR_SUPPLY_ENV = "WYSTAN_CLI_ANCHOR_SUPPLY"

_VOCAB_FILE = "cli-frameworks.yaml"

#: Read cap per source file — a command registration lives near the top
#: of the file it declares; the same bound the probe measured with.
_READ_CAP = 60_000


def cli_anchor_supply_enabled() -> bool:
    """Default **ON** (flip #31, KS 65). Unset ≡ ``1``; explicit ``0`` =
    kill-switch forever."""
    return os.environ.get(CLI_ANCHOR_SUPPLY_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


@dataclass(frozen=True)
class CommandSite:
    """One command-registration site: the anchor evidence."""

    file: str
    line: int
    command: str | None = None
    #: fixb126 — the author-declared one-liner at the SAME registration
    #: site (cobra ``Short:``, commander ``.description()``). Journey-
    #: naming evidence; ``None`` for frameworks that declare none.
    summary: str | None = None
    #: fixb128 (NS-3) — the handler SYMBOL this site names for the command
    #: (cobra ``RunE: ShowHandler``). The command's OWN member flow is the
    #: flow whose ENTRY symbol equals it. ``None`` when the framework
    #: declares no handler convention or the site inlines a closure.
    handler: str | None = None


@dataclass(frozen=True)
class CliCluster:
    """One G1-passing CLI entry cluster."""

    #: cluster identity = the owning manifest's directory (``"."`` at
    #: repo root). Stable, author-declared, never a derived guess.
    module: str
    framework: str
    lang: str
    manifest: str
    #: the binary the manifest declares (display evidence, never a gate)
    bin_name: str | None
    sites: tuple[CommandSite, ...]
    files: frozenset[str]
    #: why P1-strict passed — carried into telemetry verbatim
    evidence: tuple[str, ...] = field(default=())

    @property
    def canonical_id(self) -> str:
        return "cli:%s" % (self.module or ".")

    @property
    def site_tree(self) -> str:
        """fixb126 — the cluster's OWN evidence tree: the common
        directory prefix of every registration-site file.

        This, not ``module``, is the containment basis of the
        supplied-tile fence: ollama declares its cobra commands under
        ``cmd/`` while its manifest (``go.mod``) sits at the repo ROOT,
        so a module-keyed fence would be inert there by construction
        (the exact hole ``_cli_foreign`` documents for root clusters).

        ``""`` when the sites themselves span the repo root — the fence
        then falls back to strict site-ownership, never to "everything
        is contained".
        """
        dirs = sorted({s.file.rsplit("/", 1)[0] if "/" in s.file else ""
                       for s in self.sites})
        if not dirs:
            return ""
        head = dirs[0].split("/") if dirs[0] else []
        k = len(head)
        for other in dirs[1:]:
            segs = other.split("/") if other else []
            j = 0
            while j < min(k, len(segs)) and segs[j] == head[j]:
                j += 1
            k = j
        return "/".join(head[:k])


@dataclass(frozen=True)
class _Framework:
    name: str
    lang: str
    extensions: tuple[str, ...]
    site: "re.Pattern[str]"
    imp: "re.Pattern[str] | None"
    selector: str | None
    command: "re.Pattern[str] | None"
    summary: "re.Pattern[str] | None" = None
    #: fixb128 (NS-3) — group 1 names this command's HANDLER symbol
    #: (cobra ``RunE:``, urfave ``Action:``). ``None`` for frameworks
    #: that declare none: those keep the pre-fixb128 binding untouched.
    handler: "re.Pattern[str] | None" = None


def load_cli_frameworks() -> dict[str, Any]:
    """The packaged framework table (``data/cli-frameworks.yaml``)."""
    return load_yaml(_VOCAB_FILE) or {}


def _frameworks(vocab: dict[str, Any]) -> list[_Framework]:
    out: list[_Framework] = []
    for raw in vocab.get("frameworks") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        lang = str(raw.get("lang") or "").strip()
        site = str(raw.get("site") or "").strip()
        if not (name and lang and site):
            continue
        imp_raw = raw.get("import")
        cmd_raw = raw.get("command")
        sum_raw = raw.get("summary")
        hnd_raw = raw.get("handler")
        out.append(_Framework(
            name=name,
            lang=lang,
            extensions=tuple(str(e) for e in (raw.get("extensions") or ())),
            site=re.compile(site, re.M),
            imp=re.compile(str(imp_raw), re.M) if imp_raw else None,
            selector=(str(raw["selector"]).strip()
                      if raw.get("selector") else None),
            command=re.compile(str(cmd_raw)) if cmd_raw else None,
            summary=re.compile(str(sum_raw)) if sum_raw else None,
            handler=re.compile(str(hnd_raw)) if hnd_raw else None,
        ))
    out.sort(key=lambda f: f.name)
    return out


def _skip_re(vocab: dict[str, Any]) -> "re.Pattern[str]":
    segs = [re.escape(str(s)) for s in (vocab.get("skip_segments") or ())]
    if not segs:
        return re.compile(r"(?!)")
    return re.compile(r"(^|/)(%s)/" % "|".join(segs))


def _test_re(vocab: dict[str, Any]) -> "re.Pattern[str]":
    pats = [str(p) for p in (vocab.get("test_patterns") or ())]
    if not pats:
        return re.compile(r"(?!)")
    return re.compile("|".join("(?:%s)" % p for p in pats), re.I)


def _read(root: Path, rel: str) -> str:
    try:
        with open(root / rel, "r", errors="ignore") as fh:
            return fh.read(_READ_CAP)
    except OSError:
        return ""


def _dirname(rel: str) -> str:
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


def _nearest(rel: str, dirs_with_manifest: dict[str, str]) -> tuple[str, str] | None:
    """``(manifest-dir, manifest-name)`` of the NEAREST manifest above
    *rel*, walking to the repo root. ``""`` is the root directory."""
    d = _dirname(rel)
    while True:
        name = dirs_with_manifest.get(d)
        if name is not None:
            return d or ".", name
        if not d:
            return None
        d = _dirname(d)


def _under(path: str, prefix: str) -> bool:
    if prefix in ("", "."):
        return True
    return path == prefix or path.startswith(prefix + "/")


# ── P1-strict: does the manifest declare a binary that resolves here? ──


def _p1_node(text: str, _root: Path, _mdir: str,
             _rels: list[str]) -> tuple[bool, list[str], str | None]:
    try:
        doc = json.loads(text)
    except ValueError:
        return False, ["package.json unparseable"], None
    if not isinstance(doc, dict):
        return False, ["package.json is not an object"], None
    name = doc.get("name")
    binv = doc.get("bin")
    if not binv:
        return False, ["package.json declares no bin (name=%s)" % name], (
            str(name) if name else None)
    if isinstance(binv, dict):
        names = sorted(str(k) for k in binv)
    else:
        names = [str(name) if name else str(binv)]
    # The cluster is inside this package by construction (nearest
    # manifest), so a declared bin resolves into it.
    return True, ["package.json bin=%s" % names], (names[0] if names else None)


_PY_NAME_RE = re.compile(r'^name\s*=\s*["\']([^"\']+)', re.M)
_PY_SCRIPTS_BLOCK_RE = re.compile(r"\[project\.scripts\]([^\[]*)")
_PY_SCRIPT_ENTRY_RE = re.compile(r'^\s*[\w.-]+\s*=\s*["\']([\w.]+)\s*:', re.M)
_PY_CONSOLE_ENTRY_RE = re.compile(r'["\'][\w.-]+\s*=\s*([\w.]+)\s*:')


def _p1_py(text: str, _root: Path, mdir: str,
           rels: list[str]) -> tuple[bool, list[str], str | None]:
    nm = _PY_NAME_RE.search(text)
    pkg_name = nm.group(1) if nm else None
    entries: list[str] = []
    blk = _PY_SCRIPTS_BLOCK_RE.search(text)
    if blk:
        entries += _PY_SCRIPT_ENTRY_RE.findall(blk.group(1))
    if "console_scripts" in text:
        entries += _PY_CONSOLE_ENTRY_RE.findall(text)
    if not entries:
        return False, ["no [project.scripts] / console_scripts"], pkg_name
    tops = {e.split(".")[0] for e in entries}
    base = "" if mdir in ("", ".") else mdir + "/"
    resolved = 0
    for rel in rels:
        sub = rel[len(base):] if base and rel.startswith(base) else rel
        segs = sub.split("/")
        head = segs[0]
        if head in tops or (head == "src" and len(segs) > 1 and segs[1] in tops):
            resolved += 1
    ev = ["entries=%s tops=%s -> %d/%d cluster files under entry package"
          % (sorted(entries)[:3], sorted(tops), resolved, len(rels))]
    return resolved > 0, ev, pkg_name


_RUST_NAME_RE = re.compile(r'^name\s*=\s*["\']([^"\']+)', re.M)
_RUST_BIN_PATH_RE = re.compile(r"(^|/)src/bin/[^/]+\.rs$")


def _p1_rust(text: str, root: Path, mdir: str,
             rels: list[str]) -> tuple[bool, list[str], str | None]:
    nm = _RUST_NAME_RE.search(text)
    crate = nm.group(1) if nm else None
    ev: list[str] = []
    has_bin_section = "[[bin]]" in text
    main_rs = (root / (mdir if mdir not in ("", ".") else "") / "src"
               / "main.rs")
    has_main = main_rs.is_file() or any(
        _RUST_BIN_PATH_RE.search(rel) for rel in rels)
    if has_bin_section:
        ev.append("Cargo.toml [[bin]]")
    if has_main:
        ev.append("crate src/main.rs (implicit bin target)")
    return (has_bin_section or has_main), ev or ["lib-only crate"], crate


_GO_MODULE_RE = re.compile(r"^module\s+(\S+)", re.M)
_VERSION_SEG_RE = re.compile(r"^v\d+$")


def _go_bin_name(module_path: str | None) -> str | None:
    """The binary a Go module ships: the last MEANINGFUL path segment.
    A trailing major-version segment is module machinery, never a name
    (``github.com/caddyserver/caddy/v2`` → ``caddy``)."""
    if not module_path:
        return None
    segs = [s for s in module_path.split("/") if s]
    while segs and _VERSION_SEG_RE.match(segs[-1]):
        segs.pop()
    return segs[-1] if segs else None


def _p1_go(text: str, _root: Path, mdir: str, rels: list[str],
           main_dirs: frozenset[str]) -> tuple[bool, list[str], str | None]:
    mod = _GO_MODULE_RE.search(text)
    module_name = mod.group(1) if mod else None
    scope = [d for d in sorted(main_dirs) if _under(d, mdir)]
    hits: list[str] = []
    for rel in rels:
        d = _dirname(rel)
        for md in scope:
            # the binary IS the cluster dir, sits under it, or the
            # cluster dir sits under the binary's package
            if d == md or _under(d, md) or _under(md, d):
                hits.append(md)
                break
    if not hits:
        return False, ["no reachable `package main` in module"], _go_bin_name(
            module_name)
    return True, ["package main+func main at: %s"
                  % ", ".join(sorted(set(hits))[:4])], _go_bin_name(module_name)


_GO_IMPORT_RE = re.compile(r'^\s*(?:(\w+)\s+)?"([^"]+)"', re.M)


def _p1_none(_t: str, _r: Path, _m: str, _rels: list[str],
             _c: frozenset[str]) -> tuple[bool, list[str], str | None]:
    """A language with no installable-binary concept for this shape —
    ruby rake tasks are the measured member (chatwoot anti-case)."""
    return False, ["no binary target for this manifest kind"], None


#: P1-strict resolver per manifest language. A DISPATCH TABLE, never an
#: if/elif chain: the trunk-purity law (G3) forbids a shared pipeline
#: stage from branching on a language literal, and a table is the house
#: replacement (the parsers themselves are per-language by nature).
_P1_RESOLVERS: dict[
    str,
    "Any",
] = {
    "node": lambda t, r, m, rels, _c: _p1_node(t, r, m, rels),
    "py": lambda t, r, m, rels, _c: _p1_py(t, r, m, rels),
    "rust": lambda t, r, m, rels, _c: _p1_rust(t, r, m, rels),
    "go": _p1_go,
    "php": _p1_none,
    "rb": _p1_none,
}

#: Cheap "does this manifest declare ANY binary" prefilter, same
#: dispatch-table shape. MUST be a superset of the strict resolver.
_PREFILTERS: dict[str, "Any"] = {
    "node": lambda t, r, m: _p1_node(t, r, m, [])[0],
    "py": lambda t, _r, _m: bool(
        _PY_SCRIPTS_BLOCK_RE.search(t) or "console_scripts" in t),
    "rust": lambda t, r, m: _p1_rust(t, r, m, [])[0],
    "php": lambda t, _r, _m: '"bin"' in t,
}


def _command_of(fw: _Framework, text: str, start: int) -> str | None:
    """The command name declared at the registration site — the
    ``Use:`` / ``.command("x")`` evidence.

    FORWARD-only, bounded window: a backward window makes two adjacent
    registrations report the FIRST one's name (measured on ollama's
    ``run``/``pull`` pair)."""
    if fw.command is None:
        return None
    m = fw.command.search(text, start, start + 400)
    return m.group(1) if m else None


def _summary_of(fw: _Framework, text: str, start: int) -> str | None:
    """fixb126 — the author-declared one-liner of the command registered
    at *start* (cobra ``Short:``, commander ``.description()``).

    Same FORWARD-only bounded window as :func:`_command_of` and for the
    same measured reason: a backward window makes two adjacent
    registrations report the FIRST one's prose.
    """
    if fw.summary is None:
        return None
    m = fw.summary.search(text, start, start + 400)
    if m is None:
        return None
    val = m.group(1).strip()
    return val or None


def _handler_of(fw: _Framework, text: str, start: int) -> str | None:
    """fixb128 (NS-3) — the HANDLER SYMBOL the registration at *start*
    names for this command (cobra ``RunE: ShowHandler``).

    Same FORWARD-only bounded window as :func:`_summary_of`, for the same
    measured reason. An INLINE closure (``RunE: func(cmd, args) …``)
    names no reusable symbol and is excluded by the pattern itself, so a
    command that inlines its body reports ``None`` and keeps the
    pre-fixb128 binding rather than abstaining on a phantom symbol.
    """
    if fw.handler is None:
        return None
    m = fw.handler.search(text, start, start + 400)
    if m is None:
        return None
    val = m.group(1).strip()
    return val or None


def _p0_bound(fw: _Framework, text: str) -> bool:
    """P0 — import-binding, vendor arm ∪ in-repo self-hosted arm."""
    if fw.imp is not None and fw.imp.search(text):
        return True
    if fw.selector:
        for m in _GO_IMPORT_RE.finditer(text):
            alias, path = m.group(1), m.group(2)
            if (alias or path.rsplit("/", 1)[-1]) == fw.selector:
                return True
    return False


def _sites_in(fw: _Framework, rel: str, text: str) -> list[CommandSite]:
    out: list[CommandSite] = []
    for m in fw.site.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        out.append(CommandSite(file=rel, line=line,
                               command=_command_of(fw, text, m.start()),
                               summary=_summary_of(fw, text, m.start()),
                               handler=_handler_of(fw, text, m.start())))
    return out


def _tracked(ctx: Any) -> list[str]:
    return sorted(
        str(p).replace("\\", "/") for p in (getattr(ctx, "tracked_files", None) or ())
    )


def detect_cli_clusters(ctx: Any) -> tuple[CliCluster, ...]:
    """Every **G1-passing** CLI entry cluster of the scan unit.

    Deterministic, ``$0``, no LLM, no thresholds — G1 is two boolean
    predicates. Returns ``()`` when nothing passes (the overwhelmingly
    common case: the detector is inert on repos without a shipped CLI).
    """
    root = Path(getattr(ctx, "repo_path", "."))
    vocab = load_cli_frameworks()
    fws = _frameworks(vocab)
    if not fws:
        return ()
    skip_re, test_re = _skip_re(vocab), _test_re(vocab)
    manifests: dict[str, list[str]] = {
        str(k): [str(v) for v in (vals or ())]
        for k, vals in (vocab.get("manifests") or {}).items()
    }

    tracked = [p for p in _tracked(ctx)
               if not skip_re.search(p) and not test_re.search(p)]
    if not tracked:
        return ()
    tracked_set = frozenset(tracked)

    # ── manifest index per language (pure path arithmetic, no reads) ──
    manifest_dirs: dict[str, dict[str, str]] = {}
    for lang, names in manifests.items():
        by_dir: dict[str, str] = {}
        for rel in tracked:
            base = rel.rsplit("/", 1)[-1]
            if base in names:
                d = _dirname(rel)
                cur = by_dir.get(d)
                if cur is None or names.index(base) < names.index(cur):
                    by_dir[d] = base
        manifest_dirs[lang] = by_dir

    langs_present = {fw.lang for fw in fws}

    # ── binaries DECLARED IN CODE (Go's ``package main`` + ``func main``:
    #    a Go module's binary target lives in source, not in go.mod).
    #    WHICH languages and WHICH markers is DATA (``code_declared_bins``
    #    in the framework YAML) — the trunk never names a language (G3
    #    trunk-purity law), and a new ecosystem is a YAML edit.
    code_bins: dict[str, frozenset[str]] = {}
    for _lang, _spec in sorted((vocab.get("code_declared_bins") or {}).items()):
        if _lang not in langs_present or not manifest_dirs.get(_lang):
            continue
        _exts = tuple(str(e) for e in (_spec.get("extensions") or ()))
        _marks = [re.compile(str(p), re.M) for p in (_spec.get("markers") or ())]
        if not (_exts and _marks):
            continue
        _found: set[str] = set()
        for rel in tracked:
            if not rel.endswith(_exts):
                continue
            text = _read(root, rel)
            if all(m.search(text) for m in _marks):
                _found.add(_dirname(rel) or ".")
        code_bins[_lang] = frozenset(_found)

    # ── binaries declared by a CONVENTIONAL PATH (Rust ``src/bin/*.rs``,
    #    the implicit multi-binary crate). Also data. The scan prefilter
    #    MUST be a superset of the strict per-cluster test, else a cluster
    #    dies unread (measured: meilisearch ``crates/fuzzers``).
    path_bins: dict[str, frozenset[str]] = {}
    for _lang, _pats in sorted((vocab.get("path_declared_bins") or {}).items()):
        if _lang not in langs_present:
            continue
        _res = [re.compile(str(p)) for p in (_pats or ())]
        _owners: set[str] = set()
        for rel in tracked:
            if any(r.search(rel) for r in _res):
                near = _nearest(rel, manifest_dirs.get(_lang) or {})
                if near is not None:
                    _owners.add(near[0])
        path_bins[_lang] = frozenset(_owners)

    # ── manifest text cache + "declares a binary at all" prefilter ────
    manifest_text: dict[str, str] = {}

    def _mtext(mdir: str, mname: str) -> str:
        key = "%s/%s" % ("" if mdir in ("", ".") else mdir, mname)
        key = key.lstrip("/")
        if key not in manifest_text:
            manifest_text[key] = _read(root, key)
        return manifest_text[key]

    def _declares_any_bin(lang: str, mdir: str, mname: str) -> bool:
        """Cheap gate used ONLY to bound the file scan. MUST be a
        superset of the strict per-cluster resolution below."""
        if any(_under(d, mdir) for d in code_bins.get(lang, frozenset())):
            return True
        if mdir in path_bins.get(lang, frozenset()):
            return True
        pre = _PREFILTERS.get(lang)
        if pre is None:
            return False
        return bool(pre(_mtext(mdir, mname), root, mdir))

    # ── P0 pass: read only files that can possibly matter ─────────────
    exts_by_lang: dict[str, set[str]] = {}
    for fw in fws:
        exts_by_lang.setdefault(fw.lang, set()).update(fw.extensions)

    bound: dict[str, list[tuple[str, tuple[CommandSite, ...]]]] = {}
    for lang, exts in sorted(exts_by_lang.items()):
        by_dir = manifest_dirs.get(lang) or {}
        if not by_dir:
            continue
        lang_fws = [fw for fw in fws if fw.lang == lang]
        for rel in tracked:
            if not rel.endswith(tuple(sorted(exts))):
                continue
            near = _nearest(rel, by_dir)
            if near is None:
                continue
            mdir, mname = near
            if not _declares_any_bin(lang, mdir, mname):
                continue
            text = _read(root, rel)
            if not text:
                continue
            for fw in lang_fws:
                if not rel.endswith(fw.extensions):
                    continue
                found = _sites_in(fw, rel, text)
                if not found:
                    continue
                if not _p0_bound(fw, text):
                    continue  # census noise: unbound `Command` token
                bound.setdefault(fw.name, []).append((rel, tuple(found)))

    if not bound:
        return ()

    # ── cluster by nearest manifest, then P1-strict ───────────────────
    fw_by_name = {fw.name: fw for fw in fws}
    clusters: list[CliCluster] = []
    for fw_name in sorted(bound):
        fw = fw_by_name[fw_name]
        by_dir = manifest_dirs.get(fw.lang) or {}
        grouped: dict[tuple[str, str], list[tuple[str, tuple[CommandSite, ...]]]] = {}
        for rel, sites in bound[fw_name]:
            near = _nearest(rel, by_dir)
            if near is None:
                continue
            grouped.setdefault(near, []).append((rel, sites))
        for (mdir, mname), entries in sorted(grouped.items()):
            entries.sort()
            rels = [rel for rel, _ in entries]
            text = _mtext(mdir, mname)
            resolve = _P1_RESOLVERS.get(fw.lang, _p1_none)
            ok, ev, binname = resolve(
                text, root, mdir, rels, code_bins.get(fw.lang, frozenset()))
            if not ok:
                continue
            cluster_sites: list[CommandSite] = []
            for _rel, ss in entries:
                cluster_sites.extend(ss)
            clusters.append(CliCluster(
                module=mdir or ".",
                framework=fw.name,
                lang=fw.lang,
                manifest=mname,
                bin_name=binname,
                sites=tuple(cluster_sites),
                files=frozenset(r for r in rels if r in tracked_set),
                evidence=tuple(ev),
            ))
    clusters.sort(key=lambda c: (c.module, c.framework))
    return tuple(clusters)


#: fixb126 — per-process memo of :func:`detect_cli_clusters`. The 6.86
#: mint and the 6.7d-tail command-journey mint ask the SAME question of
#: the SAME unit; detection walks every tracked source file, so asking
#: twice doubles the scan's cheapest-but-not-free deterministic pass.
#: Keyed on (repo_path, tracked-file set) so a monorepo's per-unit scans
#: never share an entry. Cleared by :func:`reset_cluster_cache` in tests.
_CLUSTER_MEMO: dict[tuple[str, int], tuple[CliCluster, ...]] = {}


def reset_cluster_cache() -> None:
    """Drop the per-process cluster memo (test hygiene)."""
    _CLUSTER_MEMO.clear()


def detect_cli_clusters_cached(ctx: Any) -> tuple[CliCluster, ...]:
    """:func:`detect_cli_clusters`, memoized per (repo, tracked set).

    Same value, same order, same determinism — a pure memo over a pure
    function.
    """
    key = (str(getattr(ctx, "repo_path", ".")), hash(tuple(_tracked(ctx))))
    hit = _CLUSTER_MEMO.get(key)
    if hit is None:
        hit = detect_cli_clusters(ctx)
        _CLUSTER_MEMO[key] = hit
    return hit


def supplied_tile_admits(
    cluster: CliCluster, dev_paths: Iterable[str],
) -> bool:
    """fixb126 — may a freshly SUPPLIED CLI tile admit the unit owning
    *dev_paths*?

    ``True`` for exactly two shapes, and nothing else:

    * the unit OWNS registration sites of THIS cluster
      (:func:`cluster_of_paths` authority — ollama ``cmd`` + ``launch``);
    * the unit lives WHOLLY inside the cluster's own evidence tree
      (:attr:`CliCluster.site_tree` — ollama ``cmd/config``, ``cmd/tui``,
      ``cmd/internal``; the module-keyed fence cannot see these because
      ollama's manifest sits at the repo ROOT).

    A root-degenerate evidence tree (sites spanning the repo root) falls
    back to site-ownership alone — containment would otherwise admit the
    whole repo, which is the magnet this fence exists to stop.
    """
    paths = [str(p).replace("\\", "/") for p in dev_paths]
    if not paths:
        return False
    if cluster_of_paths((cluster,), paths) is not None:
        return True
    tree = cluster.site_tree
    if not tree:
        return False
    return all(p == tree or p.startswith(tree + "/") for p in paths)


def cluster_of_paths(
    clusters: Iterable[CliCluster], paths: Iterable[str],
) -> CliCluster | None:
    """The cluster whose registration sites *paths* OWNS, or ``None``.

    Ownership is exact-file: a dev unit that owns a declared command
    registration site IS the CLI's code. Deterministic tie-break by
    (most owned sites, cluster id)."""
    owned = frozenset(paths)
    if not owned:
        return None
    best: tuple[int, str] | None = None
    winner: CliCluster | None = None
    for c in clusters:
        n = len(owned & c.files)
        if not n:
            continue
        key = (-n, c.canonical_id)
        if best is None or key < best:
            best, winner = key, c
    return winner
