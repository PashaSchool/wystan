"""fixb147 — ANCHOR IDENTITY for a bare ``ws:`` workspace product feature.

Two rungs, one flag (``WYSTAN_WS_ANCHOR_IDENTITY``, default **ON**
since flip-pack №46, KEY_SCHEMA 81). Both answer the same question —
*what is this workspace, as a product?* — from the workspace's OWN
manifest, and nothing else. No vocabulary, no per-repo branch, no
README.

RUNG A — ``cli:`` identity for the veto-freed row that ABSTAINS
---------------------------------------------------------------
fixb143 round-3 (i-a) freed the published-artifact rows from the
dev-tooling lane, and then had to ABSTAIN on the one shape the product
side could not home: a BARE ``ws:`` anchor holding >= ``FLOOR_JOURNEYS``
journeys (``_destination_survives`` — a bare workspace anchor IS a
structural container, and 6.9966 dissolves those). The abstain is
never-worse but it is not the answer: on trigger.dev the row IS the
shipped ``trigger`` CLI — 8 journeys of deploy/dev/init commands — and
it lands in the lane wearing the repo's own name.

The defect is IDENTITY, not classification: the row is anchored on the
*workspace directory* while the product it names is the *command
surface* the manifest declares. Supply that identity — ``cli:<ws-dir>``
(the fixb125 ``CliCluster.canonical_id`` form) + the fixb125-Q1 display
``"<bin> CLI"`` — and BOTH downstream predicates flip on their own,
with no change to their code:

* :func:`surface_taxonomy._destination_survives` — the anchor is no
  longer bare ``ws:`` ⇒ a destination survives ⇒ no abstain;
* :func:`stage_6_9965_token_journey_rehome._is_structural_home` — a
  ``cli:`` anchor is not a structural container ⇒ 6.9966 stops
  dissolving it ⇒ the journeys stay home.

SCOPE IS HARD — only the row that WOULD ABSTAIN. Re-anchoring every
published workspace was measured and rejected (probe 2026-08-13): it
silently walks 5 more trigger.dev rows out of ``_is_structural_home``
(the 6.9965/6.9966 re-home SOURCE domain) and out of the
``ws_anchor_no_uf`` census class. This module supplies nothing on its
own; the abstain site asks, and only for the row it is about to lane.

The binary NAME is npm semantics via the existing
:func:`cli_commands._p1_node` — a dict ``bin`` names its own commands,
a STRING ``bin`` means "the command is the package name" (``npm``'s own
rule). Never a path stem: ``create-twenty-app``'s ``"bin":
"dist/cli.cjs"`` is the command ``create-twenty-app``, not ``cli``.

RUNG B — npm SCOPE as identity when the bare remainder is degenerate
--------------------------------------------------------------------
B27's rung-4 authored test (``manifest_display._authored_slug_name``)
rejects a package ``name`` whose scope-stripped remainder is just the
directory slug again — ``@novu/js`` at ``packages/js`` is "the path
spelled twice", not an authored display. Correct in general, and wrong
for exactly one shape: when the remainder is DEGENERATE (alnum length
<= 2 — the ``short_name`` gate class verbatim) it names nothing at all,
and the author's SCOPE is the only identity in the manifest. ``js`` ->
``Novu JS``.

Deliberately NOT unconditional: a non-degenerate remainder keeps its
own word (``@novu/react`` stays ``React``, ``@trigger.dev/rsc`` stays
``Rsc``). The probe measured the alternative — prefixing every scoped
package produced 5 repo-echo displays ('Trigger.dev Rsc',
'Trigger.dev React Hooks'). The honest boundary of this rung is the
degenerate class and nothing more.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# The module-private P1-strict reader is imported DELIBERATELY (not
# re-implemented): it is the engine's ONE answer to "what does this
# node manifest declare as its binary", and the fixb125 CLI-cluster
# detector reads it through the same function. A local copy would be
# free to drift — and the drift this sprint exists to kill (a path stem
# read as a command name) is exactly that kind of second opinion.
from wystan.pipeline_v2.cli_commands import _p1_node

__all__ = [
    "WS_ANCHOR_IDENTITY_ENV",
    "bare_ws_dir",
    "cli_identity_for_anchor",
    "ws_anchor_identity_enabled",
]

WS_ANCHOR_IDENTITY_ENV = "WYSTAN_WS_ANCHOR_IDENTITY"

#: A manifest is small; anything larger is not one (a work bound, not a
#: tuning knob — mirrors ``manifest_display._MAX_MANIFEST_BYTES``).
_MAX_MANIFEST_BYTES = 256 * 1024


def ws_anchor_identity_enabled() -> bool:
    """fixb147 anchor identity (both rungs) — default **ON** since
    flip-pack №46 (KEY_SCHEMA 80 -> 81, 2026-08-14): unset ≡ explicit
    ``1`` byte-identically. Explicit ``0``/``false``/``off``/``no`` (and
    explicit ``""``) restores the pre-flip lane — no manifest is read for
    this, the abstain record stands, and every board is byte-identical to
    KEY_SCHEMA 80 — and stays a kill-switch forever. The truthy set is
    preserved LITERALLY across the flip; only the get-default moved
    ``""`` → ``"1"``.

    Keyed proof (trigger.dev ×3 batteries + novu): the abstaining row
    COMMITS as product — PF 'Trigger CLI' (``cli:packages/cli-v3``,
    24121 LOC) on the live keyed board in all three batteries; novu's
    'Js' becomes 'Novu JS' and the product-right gate reads CLEAN
    (``short_name=0`` — the world-80 install blocker is lifted). I22
    dangling dev ``product_feature_id`` 14 -> 0 alongside. Wardens №50
    NO-RESURRECTION / №51 CLEAR / №52 CLEAR."""
    return os.environ.get(WS_ANCHOR_IDENTITY_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def bare_ws_dir(anchor_id: Any) -> str | None:
    """The workspace directory of a **bare** ``ws:`` anchor, else ``None``.

    Bare means the anchor carries no mint/fold provenance prefix —
    ``mint:entry-evidence->ws:packages/js`` is NOT bare (something
    already elected that unit on its own evidence), which is the same
    reading :func:`surface_taxonomy._destination_survives` uses. A
    traversal segment disqualifies the anchor (containment)."""
    aid = str(anchor_id or "").strip()
    if not aid.startswith("ws:"):
        return None
    rel = aid[3:]
    raw = [s for s in rel.split("/") if s]
    segs = [s for s in raw if s not in (".", "..")]
    if not segs or len(segs) != len(raw):
        return None
    return "/".join(segs)


def _read_manifest_text(pkg_dir: Path) -> str | None:
    """Bounded ``package.json`` read; ``None`` on anything unusual."""
    pj = pkg_dir / "package.json"
    try:
        if not pj.is_file() or pj.stat().st_size > _MAX_MANIFEST_BYTES:
            return None
        return pj.read_text(encoding="utf-8", errors="strict")
    except OSError:
        return None
    except UnicodeDecodeError:
        return None


def declared_cli_binary(repo_path: Any, ws_dir: str) -> str | None:
    """The command name this workspace's manifest DECLARES, or ``None``.

    npm semantics, via the existing :func:`cli_commands._p1_node` — the
    same P1-strict reader the fixb125 CLI-cluster detector uses, so one
    engine answer to "what is this package's binary called":

    * ``"bin": {"trigger": "./dist/esm/index.js"}`` -> ``trigger``
      (the declared command, first by sort);
    * ``"bin": "dist/cli.cjs"`` -> the PACKAGE NAME (npm installs a
      string bin under the package's own name) — never the path stem.

    ``private: true`` ⇒ ``None``: the ``_is_published_cli`` doctrine
    (operator ruling 2026-07-06) — customers install and drive it is
    what makes a CLI a product, and a private package ships to nobody.
    """
    root = Path(str(repo_path))
    text = _read_manifest_text(root / ws_dir)
    if text is None:
        return None
    ok, _evidence, name = _p1_node(text, root, ws_dir, [])
    if not ok or not name:
        return None
    import json as _json

    try:
        doc = _json.loads(text)
    except ValueError:
        return None
    if not isinstance(doc, dict) or doc.get("private") is True:
        return None
    binary = str(name).strip()
    return binary or None


def cli_identity_for_anchor(
    repo_path: Any, anchor_id: Any,
) -> tuple[str, str] | None:
    """``(anchor_id, display_name)`` of the CLI product a bare ``ws:``
    workspace declares — or ``None`` when it declares none.

    The anchor id is the fixb125 cluster form (``cli:<manifest dir>``)
    so the two mechanisms cannot mint divergent identities for one
    command surface. The display is fixb125's own
    :func:`stage_6_86_anchored_mint.cli_pf_display` ("<bin> CLI"),
    titleized through the naming contract's segment word so the label
    reads as a product name ('Trigger CLI'). Imports are lazy — this
    module stays import-light and callers pay one cached read.
    """
    ws_dir = bare_ws_dir(anchor_id)
    if ws_dir is None or repo_path is None:
        return None
    binary = declared_cli_binary(repo_path, ws_dir)
    if not binary:
        return None
    from wystan.pipeline_v2.naming_contract import (
        _display_word,
        load_naming_vocab,
    )
    from wystan.pipeline_v2.stage_6_86_anchored_mint import cli_pf_display

    display = _display_word(cli_pf_display(binary), load_naming_vocab())
    if not display.strip():
        return None
    return "cli:%s" % ws_dir, display
