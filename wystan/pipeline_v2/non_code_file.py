"""Is this file unmistakably not code? Decided from the file's own properties.

A feature's lines of code are the lines a team maintains as code. A tokenizer
vocabulary, an API description dumped by a tool, a bundle a build emitted
belong to their feature and stay listed there, but their lines say nothing
about how large the feature is.

The rules are narrow on purpose: when in doubt the file is code. Anything a
team keeps by hand stays code: a manifest, a config or a reference table of
a few thousand lines, a migration a framework scaffolded, a large source
file with ordinary names in it. Only five properties count, each one a
machine's signature:

  * a generator's banner standing as a comment line of its own at the top;
  * the source-map trailer a build tool appends;
  * minified shape: lines hundreds of bytes long on average, and most of
    them long;
  * a megabyte of script or stylesheet whose identifiers are mostly one or
    two letters (a bundle put through a code formatter keeps its minified
    names);
  * a data-format file longer than anybody maintains by hand.

A property of shape must hold at BOTH ends of the file: a source file that
opens with one long constant, or a data file whose first lines are short and
whose body is not, is code.

The rules look at the extension, the size, the first bytes and the last
bytes of a file. They never look at a directory name, so they hold for any
repository. Classification reads at most ``HEAD_BYTES + TAIL_BYTES`` of a
file and matches patterns only against lines cut to ``LINE_CAP`` characters:
the engine scans repositories it does not trust.

Prose (``PROSE_EXTENSIONS``) is not judged here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import NamedTuple

__all__ = [
    "CLASS_BUNDLED",
    "CLASS_DATA",
    "CLASS_GENERATED",
    "CLASS_MINIFIED",
    "DATA_AUTHORED_MAX_LINES",
    "FileSample",
    "HEAD_BYTES",
    "LINE_CAP",
    "MACHINE_SIZED_BYTES",
    "NON_CODE_CLASSES",
    "SMALL_FILE_MAX_BYTES",
    "TAIL_BYTES",
    "classify_sample",
    "non_code_class",
    "read_sample",
]

CLASS_DATA = "data"
CLASS_GENERATED = "generated"
CLASS_BUNDLED = "bundled"
CLASS_MINIFIED = "minified"
NON_CODE_CLASSES = (CLASS_DATA, CLASS_GENERATED, CLASS_BUNDLED, CLASS_MINIFIED)

# A generator's banner and the shape of the first lines fit in this.
HEAD_BYTES = 8192
# The other end of the file: its last line (a source-map trailer) and enough
# lines to check that the shape of the head is the shape of the file.
TAIL_BYTES = 4096
# No pattern sees more of a line than this: a banner is short, and a crafted
# line of megabytes must not cost a pattern more than a short one does.
LINE_CAP = 240

# Below this a file is judged only by what it declares about itself (a
# banner, a trailer), never by its shape or length.
SMALL_FILE_MAX_BYTES = 64 * 1024

# Serialisations that hold values and no behaviour.
DATA_EXTENSIONS = frozenset({
    ".json", ".jsonl", ".ndjson", ".geojson", ".yaml", ".yml", ".xml",
})
# A data-format file longer than this is a dump, an export or a vocabulary.
# Measured on the eleven repositories with an accepted map: hand-kept
# reference data and specifications reach 9,069 lines (client library
# specifications, price tables, map data); from 10,000 estimated lines up
# the files are tokenizer vocabularies, API descriptions written by a tool,
# snapshots and generated resource definitions. The length is estimated
# from the line density of the head and of the tail, taking the sparser of
# the two, so the file is never read to count it and a file is called long
# only when both ends say so.
DATA_AUTHORED_MAX_LINES = 10_000

# Minified or packed text. Hand-written code averages 30 to 50 bytes a line;
# files a team keeps with long lines (tables, templates, inline icons)
# measured up to 282; build output starts at 546.
MINIFIED_MEAN_LINE_BYTES = 500
# Minified means the WHOLE file is long lines. A template with inline values
# or a table with some long rows reaches the mean with long lines among short
# ones, so more than half of the lines seen at the two ends must be long too.
# Measured on 28 clones: of 360 files the mean alone calls minified, 321 are
# above a half; build output whose short lines are a shebang, a blank or an
# export keeps 0.6 and up. The 39 at a half or below (SVGs with inline
# images, long-row tables, bundles opening with a license comment) count as
# code: the rule cannot tell them apart. A line counts as long from the bound
# the mean uses.
MINIFIED_LONG_LINE_SHARE = 0.5
LONG_LINE_BYTES = MINIFIED_MEAN_LINE_BYTES

# A megabyte of script or stylesheet is machine-made only when it also looks
# it: a bundle put through a code formatter has ordinary line lengths and no
# trailer, but its identifiers are still the minifier's. Only the languages
# that are shipped bundled are asked: short names in a megabyte of C or of a
# word list are tables and loop counters, and that file is code.
MACHINE_SIZED_BYTES = 1024 * 1024
BUNDLE_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".jsx", ".css"})
# Fewer identifiers than this in a sample say nothing about naming.
MIN_IDENTIFIERS = 100
# Share of identifiers of one or two characters, over the head and the tail
# together. Measured: hand-written and generated-but-readable source of this
# size 0.01 to 0.16; reformatted bundles 0.41 and up. The bound sits midway.
SHORT_IDENTIFIER_SHARE = 0.3
SHORT_IDENTIFIER_CHARS = 2
# Words of two letters that are the language's, not a minifier's.
_SHORT_KEYWORDS = frozenset({"if", "in", "do", "of", "as", "is", "or", "to"})

# A generator states itself at the top of the file, above any code.
BANNER_LINES = 15

PROSE_EXTENSIONS = frozenset({".md", ".mdx", ".markdown", ".rst", ".adoc", ".txt"})

_COMMENT_LEADER = r"(?://+|#+|/\*+|\*+|--+|<!--+|;+|%+)"
# The banner must BE the comment line, from its first word. Three forms, each
# a statement about this file by the tool that wrote it:
#   "Code generated ... DO NOT EDIT"          (the form Go formalised)
#   "@generated"                               (the annotation, alone or first;
#                                               the whole token: "@generated-x"
#                                               is another tool's word)
#   "This file is|was auto-generated ..."      (automatically, autogenerated)
# A sentence that mentions generated things, a "@generated" inside prose and
# a scaffold's "Generated by <tool>" (the file is then edited by hand) do
# not start this way.
_BANNER_RE = re.compile(
    rf"(?i)^\s*{_COMMENT_LEADER}\s*(?:"
    r"code generated\b.{0,160}\bdo not edit\b"
    r"|@generated(?=\s|$|\*/|-->)"
    r"|this (?:file|code|module) (?:is|was|has been) "
    r"(?:auto[- ]?generated|automatically generated)\b"
    r")"
)
# The source-map specification's trailer: only a build tool writes it, as
# the last line of the file and from that line's first character. The same
# text inside a string or a longer line is somebody's code about source maps.
_SOURCE_MAP_TRAILER = (b"//# sourceMappingURL=", b"//@ sourceMappingURL=", b"/*# sourceMappingURL=")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


class FileSample(NamedTuple):
    """What classification is allowed to know about a file."""

    size: int
    head: bytes
    tail: bytes


def read_sample(abs_path: Path) -> FileSample | None:
    """Size, first ``HEAD_BYTES`` and last ``TAIL_BYTES`` of a regular file;
    ``None`` when it cannot be read, is empty or is not a regular file."""
    try:
        if not os.path.isfile(abs_path):
            return None
        size = os.stat(abs_path).st_size
        if size <= 0:
            return None
        with open(abs_path, "rb") as handle:
            head = handle.read(HEAD_BYTES)
            if size <= HEAD_BYTES:
                return FileSample(size, head, head[-TAIL_BYTES:])
            handle.seek(size - TAIL_BYTES)
            return FileSample(size, head, handle.read(TAIL_BYTES))
    except OSError:
        return None


def _extension(rel_path: str) -> str:
    base = rel_path.lower().replace("\\", "/").rsplit("/", 1)[-1]
    return os.path.splitext(base)[1]


def _has_banner(head_text: str) -> bool:
    return any(
        _BANNER_RE.match(line[:LINE_CAP])
        for line in head_text.splitlines()[:BANNER_LINES]
    )


def _newline_density(chunk: bytes) -> float:
    return chunk.count(b"\n") / len(chunk) if chunk else 0.0


def _estimated_lines(sample: FileSample) -> float:
    """Length of the file in lines, from the sparser of its two ends."""
    density = min(_newline_density(sample.head), _newline_density(sample.tail))
    return sample.size * density


def _mean_line_bytes(chunk: bytes) -> float:
    return len(chunk) / (chunk.count(b"\n") + 1)


def _seen_line_lengths(sample: FileSample) -> list[int]:
    """Lengths of the non-empty lines seen at the two ends of a large file.

    The head's last line and the tail's first line are cut by the sample: their
    real length is at least what is seen, so they count when that is already
    long and are left out otherwise. An empty line says nothing about how the
    text is written."""
    head = sample.head.split(b"\n")
    tail = sample.tail.split(b"\n")
    lines = [(line, False) for line in head[:-1]] + [(head[-1], True), (tail[0], True)]
    lines += [(line, False) for line in tail[1:]]
    return [
        len(line) for line, is_cut in lines
        if line.strip() and not (is_cut and len(line) < LONG_LINE_BYTES)
    ]


def _is_minified(sample: FileSample) -> bool:
    if (_mean_line_bytes(sample.head) < MINIFIED_MEAN_LINE_BYTES
            or _mean_line_bytes(sample.tail) < MINIFIED_MEAN_LINE_BYTES):
        return False
    lengths = _seen_line_lengths(sample)
    long_lines = sum(1 for size in lengths if size >= LONG_LINE_BYTES)
    return bool(lengths) and long_lines / len(lengths) > MINIFIED_LONG_LINE_SHARE


def _has_source_map_trailer(tail: bytes) -> bool:
    lines = tail.rstrip().rsplit(b"\n", 1)
    return lines[-1].lstrip(b"\r").startswith(_SOURCE_MAP_TRAILER)


def _has_minifier_names(text: str) -> bool:
    names = [
        name for line in text.splitlines()
        for name in _IDENTIFIER_RE.findall(line[:LINE_CAP])
        if name not in _SHORT_KEYWORDS
    ]
    if len(names) < MIN_IDENTIFIERS:
        return False
    short = sum(1 for name in names if len(name) <= SHORT_IDENTIFIER_CHARS)
    return short / len(names) >= SHORT_IDENTIFIER_SHARE


def _is_reformatted_bundle(ext: str, sample: FileSample, head_text: str) -> bool:
    if ext not in BUNDLE_EXTENSIONS or sample.size < MACHINE_SIZED_BYTES:
        return False
    tail_text = sample.tail.decode("utf-8", errors="replace")
    return _has_minifier_names(head_text + "\n" + tail_text)


def _shape_class(ext: str, sample: FileSample, head_text: str) -> str | None:
    """What a large file's shape says; ``None`` for a small one."""
    if sample.size <= SMALL_FILE_MAX_BYTES:
        return None
    if _is_minified(sample):
        return CLASS_MINIFIED
    if ext in DATA_EXTENSIONS:
        long_data = _estimated_lines(sample) > DATA_AUTHORED_MAX_LINES
        return CLASS_DATA if long_data else None
    if _is_reformatted_bundle(ext, sample, head_text):
        return CLASS_BUNDLED
    return None


def classify_sample(rel_path: str, sample: FileSample) -> str | None:
    """The non-code class of a file, or ``None`` when it counts as code.

    Pure. What the file declares comes first (a banner, a trailer), then
    what its shape says once it is large."""
    ext = _extension(rel_path)
    if ext in PROSE_EXTENSIONS or b"\x00" in sample.head:
        return None
    head_text = sample.head.decode("utf-8", errors="replace")
    if ext not in DATA_EXTENSIONS and _has_banner(head_text):
        return CLASS_GENERATED
    if _has_source_map_trailer(sample.tail):
        return CLASS_BUNDLED
    return _shape_class(ext, sample, head_text)


def non_code_class(abs_path: Path, rel_path: str) -> str | None:
    """Read the bounded sample of ``abs_path`` and classify it."""
    sample = read_sample(Path(abs_path))
    if sample is None:
        return None
    return classify_sample(rel_path, sample)
