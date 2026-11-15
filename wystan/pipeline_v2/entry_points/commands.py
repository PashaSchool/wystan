"""Adapter: command-line command trees.

A command is declared at a registration site (``cobra.Command{Use:, Short:}``,
detected by :mod:`wystan.pipeline_v2.cli_commands`). Its parent is the
command whose package registers it (``cmd.AddCommand(prCmd.NewCmdPR(f))``).
The root command names the binary, so a command's address is the words a
user types: ``gh pr create``.

Parents are resolved for Go, from the constructor functions a registering
function calls. For other languages the commands are reported without a
parent: no parent is guessed from a directory.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from wystan.pipeline_v2.cli_commands import CliCluster, CommandSite, detect_cli_clusters_cached
from wystan.pipeline_v2.entry_points.record import KIND_COMMAND, LABEL_DESCRIPTION, EntryPoint
from wystan.pipeline_v2.product_strings import _read_text

__all__ = ["ADAPTER", "command_entries"]

ADAPTER = "cli-commands"
_GO_MODULE = re.compile(r"^module\s+(\S+)", re.M)
_GO_IMPORT = re.compile(r'^\s*(?:(\w+)\s+)?"([^"\s]+)"', re.M)
_GO_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", re.M)
_GO_CALL = re.compile(r"(?:\b(\w+)\.)?\b([A-Za-z_]\w*)\s*\(")
_MAX_DEPTH = 8

Constructor = tuple[str, str]  # (package directory, function name)


def _directory(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _functions(text: str) -> list[tuple[str, int, int, str]]:
    """``(name, first line, last line, body)`` of each top-level Go function."""
    starts = [(m.group(1), m.start()) for m in _GO_FUNC.finditer(text)]
    found = []
    for i, (name, offset) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else len(text)
        first = text.count("\n", 0, offset) + 1
        found.append((name, first, first + text.count("\n", offset, end), text[offset:end]))
    return found


def _go_tree(
    repo_path: Path, cluster: CliCluster,
) -> tuple[dict[Constructor, CommandSite], dict[Constructor, Constructor]]:
    """Each command by the function that builds it, and who registers whom.

    A command is built by a constructor function
    (``func NewCmdCreate(...) *cobra.Command``). The command a function
    builds is the parent of every command whose constructor that function
    calls, in the same package or an imported one. The registering call is
    not matched by name: projects wrap it (``cmdutil.AddGroup(cmd, ...)``),
    and a constructor has no other reason to call another constructor."""
    module_dir = "" if cluster.module in ("", ".") else cluster.module.rstrip("/")
    manifest = f"{module_dir}/go.mod" if module_dir else "go.mod"
    module = _GO_MODULE.search(_read_text(repo_path, manifest) or "")
    prefix = module.group(1).rstrip("/") + "/" if module else ""
    sites_by_file: dict[str, list[CommandSite]] = {}
    for site in cluster.sites:
        sites_by_file.setdefault(site.file, []).append(site)

    built: dict[Constructor, CommandSite] = {}
    bodies: list[tuple[Constructor, str, dict[str, str]]] = []
    for file in sorted(cluster.files):
        text = _read_text(repo_path, file) or ""
        directory = _directory(file)
        imports = {
            alias or path.rsplit("/", 1)[-1]:
                (f"{module_dir}/" if module_dir else "") + path[len(prefix):]
            for alias, path in _GO_IMPORT.findall(text.split("\nfunc ", 1)[0])
            if prefix and path.startswith(prefix)
        }
        for name, first, last, body in _functions(text):
            inside = sorted(
                (s for s in sites_by_file.get(file, []) if first <= s.line <= last and s.command),
                key=lambda s: s.line,
            )
            if inside:
                built.setdefault((directory, name), inside[0])
            bodies.append(((directory, name), body, imports))

    parent_of: dict[Constructor, Constructor] = {}
    for parent, body, imports in bodies:
        if parent not in built:
            continue
        for alias, function in _GO_CALL.findall(body):
            child = (imports.get(alias, "") if alias else parent[0], function)
            if child in built and child != parent:
                parent_of.setdefault(child, parent)
    return built, parent_of


def _flat_tree(
    _repo_path: Path, cluster: CliCluster,
) -> tuple[dict[Constructor, CommandSite], dict[Constructor, Constructor]]:
    """Commands with no parents, for a language with no registration
    grammar here yet. Nothing is guessed from where the files are."""
    return {(s.file, str(s.line)): s for s in cluster.sites if s.command}, {}


#: Registration grammar per language. A new language is one entry here.
_TREE_RESOLVERS = {"go": _go_tree}


def _cluster_entries(repo_path: Path, cluster: CliCluster) -> list[EntryPoint]:
    built, parent_of = _TREE_RESOLVERS.get(cluster.lang, _flat_tree)(repo_path, cluster)

    def address(key: Constructor) -> str:
        words, cursor = [built[key].command or ""], key
        while cursor in parent_of and len(words) < _MAX_DEPTH:
            cursor = parent_of[cursor]
            words.append(built[cursor].command or "")
        return " ".join(reversed(words))

    entries: dict[str, EntryPoint] = {}
    for key in sorted(built):
        site = built[key]
        entry = EntryPoint(
            kind=KIND_COMMAND,
            address=address(key),
            file=site.file,
            label=site.summary,
            label_source=LABEL_DESCRIPTION if site.summary else None,
            parent=address(parent_of[key]) if key in parent_of else None,
            symbol=site.handler,
            adapter=ADAPTER,
        )
        entries.setdefault(entry.address, entry)
    return list(entries.values())


def command_entries(ctx: Any) -> list[EntryPoint]:
    """Every command the scan unit's shipped binaries declare."""
    repo_path = Path(getattr(ctx, "repo_path", "."))
    entries: list[EntryPoint] = []
    for cluster in detect_cli_clusters_cached(ctx):
        entries.extend(_cluster_entries(repo_path, cluster))
    return entries
