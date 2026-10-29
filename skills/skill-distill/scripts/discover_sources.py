"""Discover common local skill locations without choosing a distillation scope."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def _scanner():
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        import target_selection
    finally:
        sys.dont_write_bytecode = previous
    return target_selection


def _absolute(path):
    return Path(os.path.abspath(path))


def _within(path, root):
    return path == root or root in path.parents


def discover_sources(home=None, project=None, environ=None, extra_roots=()):
    """Read directory entries and skill frontmatter; never read bodies/resources."""
    home = _absolute(home if home is not None else Path.home())
    project = _absolute(project if project is not None else Path.cwd())
    env = os.environ if environ is None else environ
    codex = _absolute(env.get("CODEX_HOME") or home / ".codex")
    config = _absolute(env.get("XDG_CONFIG_HOME") or home / ".config")
    locations = []
    for name in (".agents", ".codex", ".claude", ".cursor", ".github", ".pi"):
        locations.append((f"Project {name}", project / name / "skills", "project"))
    locations.append(("Project skills directory", project / "skills", "project"))
    for name in (".agents", ".claude", ".cursor", ".gemini"):
        locations.append((f"User {name}", home / name / "skills", "user"))
    locations.extend([
        ("User Codex", codex / "skills", "user"),
        ("Codex official/system built-ins", codex / "skills/.system", "system"),
        ("Codex plugin cache", codex / "plugins/cache", "plugin"),
        ("User Pi", home / ".pi/agent/skills", "user"),
        ("User OpenCode", config / "opencode/skills", "user"),
        ("User Magpie library", config / "magpie/library/skills", "user"),
        ("User skill manager", home / ".skills-manager/skills", "user"),
    ])
    locations.extend(("Additional source", _absolute(p), "additional") for p in extra_roots)
    system_roots = [codex / "skills/.system", project / ".codex/skills/.system"]
    plugin_roots = [codex / "plugins/cache", project / ".codex/plugins/cache"]
    roots, packages, diagnostics, seen = [], {}, [], set()
    scanner = _scanner()
    for label, path, kind in locations:
        path = _absolute(path)
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        source_id = "source-" + hashlib.sha256(key.encode()).hexdigest()[:16]
        record = {"id": source_id, "label": label, "path": str(path),
                  "kind": kind, "status": "missing", "counts": {}}
        roots.append(record)
        if not path.exists():
            continue
        try:
            report = scanner.classify_targets([path])
        except (ValueError, OSError) as exc:
            record["status"] = "unavailable"
            diagnostics.append({"path": str(path), "reason": str(exc)})
            continue
        record["status"] = "scanned"
        diagnostics.extend(report["diagnostics"])
        for item in report["inventory"]:
            package_path = _absolute(item["path"])
            package_kind = kind
            if any(_within(package_path, p) for p in plugin_roots):
                package_kind = "plugin"
            elif any(_within(package_path, p) for p in system_roots):
                package_kind = "system"
            record["counts"][package_kind] = record["counts"].get(package_kind, 0) + 1
            package = packages.setdefault(item["id"], {
                "id": item["id"], "path": item["path"], "name": item["name"],
                "description": item["description"], "kind": package_kind, "sources": [],
            })
            package["sources"].append(source_id)
    return {"schema": "skill-source-discovery/v1", "roots": roots,
            "inventory": list(packages.values()), "diagnostics": diagnostics,
            "requires_user_selection": True,
            "provenance": "Location categories only; upstream authorship and active plugin versions are not verified."}


def select_sources(report, source_ids, *, include_system, include_plugins):
    """Translate the user's choices into exact package paths, never broad parents."""
    if type(include_system) is not bool or type(include_plugins) is not bool:
        raise ValueError("official/system and plugin inclusion must both be decided")
    selected = set(source_ids)
    known = {r["id"]: r for r in report["roots"]}
    if not selected or selected - known.keys():
        raise ValueError("select at least one discovered source ID; unknown IDs are invalid")
    if any(known[s]["status"] != "scanned" for s in selected):
        raise ValueError("selected sources must have been scanned successfully")
    paths = [item["path"] for item in report["inventory"]
             if selected.intersection(item["sources"])
             and (include_system or item["kind"] != "system")
             and (include_plugins or item["kind"] != "plugin")]
    return {"source_ids": sorted(selected), "include_system": include_system,
            "include_plugins": include_plugins, "package_paths": paths}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=str(Path.cwd()))
    parser.add_argument("--home", help="override the user home for discovery")
    parser.add_argument("--extra-root", action="append", default=[])
    args = parser.parse_args(argv)
    report = discover_sources(args.home, args.project, extra_roots=args.extra_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
