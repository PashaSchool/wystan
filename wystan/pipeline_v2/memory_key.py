"""The digest an answer memory is keyed by.

A key is the SHA-256 of its payload written as JSON (sorted keys, text
kept as it is). The payload can hold text read from the repository: a
module's root path is one. Git paths are decoded by GitPython with
``surrogateescape``, so a path byte that is not UTF-8 arrives as a lone
surrogate (``tools/m\\udcffod``), which strict UTF-8 cannot encode: hashing
it raised, and the caller's ``try`` then skipped the whole naming pass or
veto for the repository.

The text is encoded with ``surrogatepass``: every string encodes, the
same string always to the same bytes, two different strings never to the
same bytes (a surrogate becomes a three-byte sequence that no valid
string encodes to). A string without a surrogate encodes exactly as
strict UTF-8 did, so every key that could be computed before is the key
it was.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# The error handler that lets a lone surrogate through (see above). Valid
# text never reaches it.
_SURROGATES = "surrogatepass"


def memory_key(payload: dict[str, Any]) -> str:
    """Hex SHA-256 of ``payload`` as sorted JSON; never raises on text."""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8", _SURROGATES)).hexdigest()
