"""Product-language laws for product feature and user flow names.

A developer feature may be called ``trpc-router`` and a code flow
``validate-content-alignment``. A product feature and a user flow are read by
a product owner, so their names must say what the user gets or does. These
laws judge one name and return the codes of the rules it breaks.

A product feature is a noun phrase for a capability ("Document templates").
A user flow is a verb-first user goal ("Invite a team member").

Pure functions, no IO, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

__all__ = ["KIND_FEATURE", "KIND_FLOW", "LawContext", "product_name_violations"]

KIND_FEATURE = "feature"
KIND_FLOW = "flow"

LAW_ROUTE_SYNTAX = "route_syntax"
LAW_PUNCTUATION = "punctuation"
LAW_PARAM_RESIDUE = "param_residue"
LAW_GLUED_IDENTIFIER = "glued_identifier"
LAW_CONTAINER_NAME = "container_name"
LAW_TECHNOLOGY_NAME = "technology_name"
LAW_TOO_LONG = "too_long"
LAW_BARE_VERB = "bare_verb"
LAW_VERB_LED = "verb_led"
LAW_NO_OBJECT = "no_object"
LAW_NOT_VERB_FIRST = "not_verb_first"
LAW_IMPLEMENTATION_VERB = "implementation_verb"

_ROUTE_GLYPHS = re.compile(r"[$:{}\[\]_+/\\]|\.\w")
_EDGE_PUNCTUATION = " .,;:-–—!?"
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_GLUE_WORDS = frozenset({"to", "in", "up", "on", "of", "by", "out", "off"})
_MIN_GLUED_LENGTH = 6
_MIN_GLUED_PART = 3
_SHORT_WORD = 2
_MIN_STEM = 4
_ARTICLES = frozenset({"the", "a", "an", "my", "your", "our"})
# Lead words of a state or an outcome, not of something the user does.
_OUTCOME_LEADS = frozenset({"unable", "failed", "invalid", "error", "no", "not", "success"})


@dataclass(frozen=True)
class LawContext:
    """What the laws need to know about the repository being named."""

    ui_vocabulary: frozenset[str]
    """Every word the product shows its users."""
    goal_verbs: frozenset[str]
    """Verbs a user flow may start with: the vocabulary plus the lead words
    of the product's own buttons."""
    vocabulary_verbs: frozenset[str]
    """The vocabulary's verbs only; a button word such as "Email" is not
    proof that a one-word feature name is a verb."""
    brand_words: frozenset[str]
    """The product's own name; says nothing about a capability."""
    structural_words: frozenset[str]
    """Directory and layer names (components, lib, api)."""
    vocab: Mapping[str, Any]
    """The packaged naming vocabulary."""

    def listed(self, key: str) -> frozenset[str]:
        return frozenset(str(word).lower() for word in (self.vocab.get(key) or []))


def _same_stem(left: str, right: str) -> bool:
    if left == right:
        return True
    return min(len(left), len(right)) >= _MIN_STEM and (
        left.startswith(right) or right.startswith(left)
    )


def _segmentable(word: str, known: frozenset[str], parts: int = 0, glue: bool = False) -> bool:
    """True when ``word`` is several known words written together.

    Two plain words joined are usually an ordinary compound ("metadata"), so
    the split must have three parts or contain a glue word ("sign" + "in")."""
    if not word:
        return parts >= 3 or (parts == 2 and glue)
    for size in range(len(word), 1, -1):
        head = word[:size]
        is_glue = head in _GLUE_WORDS
        is_part = is_glue or (len(head) >= _MIN_GLUED_PART and head in known)
        if is_part and _segmentable(word[size:], known, parts + 1, glue or is_glue):
            return True
    return False


def _is_glued(word: str, ctx: LawContext) -> bool:
    known = ctx.ui_vocabulary | ctx.listed("known_acronyms")
    if len(word) < _MIN_GLUED_LENGTH or word in known or word.rstrip("s") in known:
        return False
    return _segmentable(word, known)


def _shared_violations(name: str, words: list[str], ctx: LawContext) -> list[str]:
    found: list[str] = []
    if _ROUTE_GLYPHS.search(name):
        found.append(LAW_ROUTE_SYNTAX)
    if name != name.strip(_EDGE_PUNCTUATION):
        found.append(LAW_PUNCTUATION)
    if len(words) > 1 and words[-1] in ctx.listed("product_name_param_residue"):
        found.append(LAW_PARAM_RESIDUE)
    if any(_is_glued(word, ctx) for word in words):
        found.append(LAW_GLUED_IDENTIFIER)
    if any(word in ctx.listed("product_name_technology") for word in words):
        found.append(LAW_TECHNOLOGY_NAME)
    meaningful = [
        word for word in words
        if word not in ctx.brand_words
        and word not in ctx.structural_words
        and len(word) > _SHORT_WORD
    ]
    if not meaningful:
        found.append(LAW_CONTAINER_NAME)
    if len(words) > int(ctx.vocab.get("compose_max_words") or 8):
        found.append(LAW_TOO_LONG)
    return found


def _feature_violations(words: list[str], ctx: LawContext, is_shown: bool) -> list[str]:
    # A one-word user-goal verb is how products label a capability ("Share",
    # "Search", "Export"); a one-word implementation verb is not.
    verbs = ctx.listed("product_name_implementation_verbs")
    if len(words) == 1 and words[0] in verbs and not is_shown:
        return [LAW_BARE_VERB]
    # A feature is a noun phrase ("Document signing"), not an instruction
    # ("Sign documents"). A page the product itself titles "Sign In" stands.
    if len(words) > 1 and words[0] in ctx.goal_verbs | verbs and not is_shown:
        return [LAW_VERB_LED]
    return []


def _flow_violations(words: list[str], ctx: LawContext, subject: frozenset[str]) -> list[str]:
    lead, rest = words[0], words[1:]
    if not any(word not in _GLUE_WORDS and word not in _ARTICLES for word in rest):
        return [LAW_NO_OBJECT]
    if lead in ctx.listed("product_name_implementation_verbs"):
        return [LAW_IMPLEMENTATION_VERB]
    if lead in ctx.goal_verbs:
        return []
    # The verb list is open-ended, so an unknown lead word is only rejected
    # when it is evidently not a verb: an article, an acronym, or the thing
    # the flow is about ("Certificate activity", "LLM full texts").
    is_subject = any(_same_stem(lead, word) for word in subject)
    if is_subject or lead in _ARTICLES | _OUTCOME_LEADS or lead in ctx.listed("known_acronyms"):
        return [LAW_NOT_VERB_FIRST]
    return []


def product_name_violations(
    name: str,
    kind: str,
    ctx: LawContext,
    *,
    is_shown: bool = False,
    subject: frozenset[str] = frozenset(),
) -> list[str]:
    """Codes of the product-language laws ``name`` breaks; empty when it passes.

    ``is_shown`` says the product itself uses this exact text as a page title
    or heading, which lets a one-word feature name that is also a verb stand
    ("Support", "Share"). ``subject`` holds the words for the thing a flow
    is about; a flow name that starts with one of them is not verb-first."""
    text = (name or "").strip()
    words = [word.lower() for word in _WORD.findall(text)]
    if not words:
        return [LAW_CONTAINER_NAME]
    found = _shared_violations(text, words, ctx)
    if kind == KIND_FLOW:
        found += _flow_violations(words, ctx, subject)
    else:
        found += _feature_violations(words, ctx, is_shown)
    return found
