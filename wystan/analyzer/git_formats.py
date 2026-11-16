"""The ``git log`` pretty formats the engine uses, and nothing else.

``--pretty=`` accepts only these exact strings (``git_arguments``): a free
format could ask for ``%G?`` (signature checks run the clone's
``gpg.program``) or any other placeholder that executes or leaks. Every
field of a record format ends in NUL (``%x00``), which no commit field can
hold (``git_history.split_records``).
"""

from __future__ import annotations

FIELD_END = "%x00"


def _fields(*placeholders: str) -> str:
    return "".join(f"{placeholder}{FIELD_END}" for placeholder in placeholders)


#: Fast history read: sha, committer time, author name, raw body.
FAST_RECORD = _fields("%H", "%ct", "%an", "%B")
#: Fallback walk and partial-clone read: sha, parents, committer time,
#: author name, raw body.
COMMIT_RECORD = _fields("%H", "%P", "%ct", "%an", "%B")
#: Daily digest: sha, parents, author name and email, ISO committer date, body.
DIGEST_RECORD = _fields("%H", "%P", "%an", "%ae", "%cI", "%B")
#: Commit-prefix mining: subjects, and subjects tagged before a file list.
SUBJECTS = "%s"
TAGGED_SUBJECTS = "format:COMMIT:%s"

#: Every ``--pretty=`` argument git may receive.
PRETTY_ARGUMENTS = frozenset({
    f"--pretty=format:{FAST_RECORD}", f"--pretty=format:{COMMIT_RECORD}",
    f"--pretty=format:{DIGEST_RECORD}", f"--pretty={SUBJECTS}", f"--pretty={TAGGED_SUBJECTS}",
})
