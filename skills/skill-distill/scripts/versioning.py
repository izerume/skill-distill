#!/usr/bin/env python3
"""Project-local file operations used by the skill-distill agent workflow."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Read-only operations must not create import caches, even without caller -B.
_previous_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    import skill_distill as core
finally:
    sys.dont_write_bytecode = _previous_bytecode

VersionError = core.DistillError


def require(condition, message):
    if not condition:
        core.fail(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(path):
    files = core.manifest_skill_tree(Path(path))
    return {"algorithm": "snapshot-manifest-sha256-v1",
            "value": hashlib.sha256(canonical(files)).hexdigest(), "files": files}


def content(value):
    return {key: value[key] for key in ("algorithm", "value")}


def write(path, value):
    core.write_json_atomic(path, value)


def relative(base, value):
    rel = core.safe_relative_path(value, "managed relative path")
    path = base.joinpath(*rel.parts)
    for part in [*reversed(path.parents), path]:
        if part.exists() or part.is_symlink():
            if core.is_reparse_stat(part.lstat()):
                core.fail(f"managed path traverses a symlink/reparse point: {part}")
    return path


def read(path):
    relative(path.parent, path.name)
    result = core.read_json(path, "version record")
    require(isinstance(result, dict) and result.get("schema_version") == 1
            and not result.get("example_only"), f"unsupported or example version record: {path}")
    return result


def origin_from_entry(entry):
    require(isinstance(entry, dict), "invalid npx source entry")
    kind, source = entry.get("sourceType"), entry.get("source")
    require(isinstance(kind, str) and isinstance(source, str) and source, "incomplete npx source entry")
    if kind == "github":
        if source.startswith("https://github.com/"):
            source = urlsplit(source).path.strip("/")
        source = "https://github.com/" + source.removesuffix(".git").strip("/").lower()
    path = entry.get("skillPath") or ""
    require(isinstance(path, str), "invalid npx skillPath")
    path = path.replace("\\", "/").strip("/")
    if path == "SKILL.md":
        path = ""
    elif path.endswith("/SKILL.md"):
        path = path[:-len("/SKILL.md")]
    return {"source_type": kind, "source": source, "skill_path": path}


def source_origin(value):
    require(isinstance(value, dict) and set(value) == {"source_type", "source", "skill_path"}
            and all(isinstance(v, str) for v in value.values()) and value["source"], "invalid source origin")
    return origin_from_entry({"sourceType": value["source_type"], "source": value["source"],
                              "skillPath": value["skill_path"]})


def origin_id(origin):
    return "src-" + hashlib.sha256(canonical(origin)).hexdigest()


def binding_id(source):
    return source.get("binding_id", source["source_id"])


def global_lock_path():
    state_home = os.environ.get("XDG_STATE_HOME")
    return Path(state_home) / "skills/.skill-lock.json" if state_home else Path.home() / ".agents/.skill-lock.json"


def file_changes(old, new):
    before = {f["path"]: f["sha256"] for f in old}
    after = {f["path"]: f["sha256"] for f in new}
    return {"added": sorted(after.keys() - before.keys()),
            "removed": sorted(before.keys() - after.keys()),
            "modified": sorted(p for p in before.keys() & after.keys() if before[p] != after[p])}


def evidence_manifest(folder):
    return [core.skill_file_record(folder.joinpath(*name.split("/")), name)
            for name in sorted(core.collect_files(folder))]


def workflow_text(path):
    lines = (path / "SKILL.md").read_text(encoding="utf-8-sig").splitlines(keepends=True)
    require(lines and lines[0].strip() == "---", "tested workflow has no frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[index + 1:])
    core.fail("tested workflow has unclosed frontmatter")


def validate_snapshots(folder, sources, allow_unknown=False):
    require(isinstance(sources, list), "invalid source snapshot records")
    known = [s for s in sources if s.get("content") is not None]
    unknown = [s for s in sources if s.get("content") is None]
    require((sources and not unknown) or allow_unknown, "generated versions require complete source inputs")
    require(all(s.get("snapshot_key") is None and s.get("files") is None
                and s.get("baseline") == "unknown" for s in unknown), "unknown source snapshot contains fabricated inputs")
    if not known:
        manifest = read(folder / "sources.json")
        require(manifest.get("sources") == [] and not core.collect_files(folder / "sources"),
                "unknown source history contains unrecorded snapshots")
        return
    errors = []
    snapshots = core.load_and_verify_manifest(folder, errors)
    require(not errors, "source snapshot validation failed: " + "; ".join(errors))
    require(set(snapshots) == {s["snapshot_key"] for s in known}, "source snapshot membership mismatch")
    metadata = {s["id"]: s for s in core.read_json(folder / "sources.json", "source snapshots")["sources"]}
    for source in known:
        require(content(fingerprint(folder / "sources" / source["snapshot_key"])) == source["content"],
                "saved source fingerprint mismatch")
        entry = metadata[source["snapshot_key"]]
        if "origin" in entry:
            require(entry["origin"] == source["origin"], "source origin differs from snapshot metadata")


class VersionStore:
    def __init__(self, project):
        self.project = Path(project).resolve(strict=True)
        require(self.project.is_dir(), "project must be a directory")
        self.root = self.project / ".skill-distill" / "targets"

    def target(self, target_id):
        require(isinstance(target_id, str) and core.ID_RE.fullmatch(target_id), "invalid target ID")
        return relative(self.root, target_id)

    @contextmanager
    def lock(self, target):
        relative(self.project, target.relative_to(self.project).as_posix())
        target.mkdir(parents=True, exist_ok=True)
        with (target / "write.lock").open("a+b") as stream:
            if os.name == "nt":
                import msvcrt
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise VersionError("another operation holds the target lock") from exc
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def state(self, target_id):
        state = read(self.target(target_id) / "state.json")
        require(state.get("target_id") == target_id and type(state.get("revision")) is int
                and state["revision"] >= 1, "invalid target state")
        relative(self.project, state.get("active_path"))
        require(isinstance(state.get("source_bindings"), list), "source bindings missing")
        return state

    def release(self, target_id, release_id):
        require(isinstance(release_id, str) and re.fullmatch(r"r\d{6,}", release_id), "invalid release ID")
        folder = relative(self.target(target_id), "releases/" + release_id)
        record = read(folder / "release.json")
        require(record.get("target_id") == target_id and record.get("release_id") == release_id,
                "release identity mismatch")
        # Old imports recorded today's binding as if it were historical provenance.
        # Correct the read view without modifying the immutable record on disk.
        if record["origin"]["kind"] == "adopted":
            for source in record["sources"]:
                if source.get("baseline") == "provided_snapshot" and "origin_provenance" not in source:
                    source.update(binding_id=source["source_id"], source_id=None,
                                  origin=None, origin_provenance="unknown")
        actual = fingerprint(folder / "package")
        require(content(actual) == record["artifact"]["content"] and actual["files"] == record["artifact"]["files"],
                "saved release package was modified")
        validate_snapshots(folder / "run", record["sources"], allow_unknown=record["origin"]["kind"] == "adopted")
        if "evidence_files" in record:
            require(evidence_manifest(folder / "evidence") == record["evidence_files"], "saved evidence was modified")
            require(self.evidence(folder / "evidence", actual, folder / "package") == record["validation"], "saved validation evidence changed")
        return record

    def binding(self, raw):
        require(isinstance(raw, dict) and isinstance(raw.get("path"), str), "source requires a path")
        supplied = Path(raw["path"])
        path = (supplied if supplied.is_absolute() else self.project / supplied).resolve()
        origin = raw.get("origin")
        lock_path, lock_entry, scope = raw.get("lock_path"), raw.get("lock_entry"), "local"
        if origin is None and path.parent == self.project / ".agents/skills":
            lock_path, lock_entry, scope = str(self.project / "skills-lock.json"), path.name, "project"
        elif origin is None and path.parent == Path.home() / ".agents/skills":
            lock_path = str(global_lock_path())
            lock_entry, scope = path.name, "global"
        if lock_path:
            lock_path = str(Path(lock_path).resolve())
            if Path(lock_path).is_file():
                lock = core.read_json(lock_path, "npx skills lock")
                require(lock.get("version") in (1, 3), "unsupported npx lock version")
                entry = lock.get("skills", {}).get(lock_entry)
                if entry and entry.get("sourceType") != "local":
                    origin = origin_from_entry(entry)
            else:
                lock_path = None
        if origin is None:
            origin = {"source_type": "local", "source": "local-" + uuid.uuid4().hex, "skill_path": ""}
        origin = source_origin(origin)
        return {"source_id": origin_id(origin), "origin": origin,
                "installed_path": str(path), "scope": scope, "lock_path": lock_path, "lock_entry": lock_entry}

    def observe(self, binding, old):
        path = Path(binding["installed_path"])
        result = {"binding_id": binding["source_id"], "source_id": old["source_id"], "path": str(path),
                  "baseline": old.get("baseline", "generated_snapshot"),
                  "origin_state": "unknown" if old.get("origin") is None else "recorded"}
        if not path.exists():
            return {**result, "state": "missing"}
        try:
            upstream = None
            lock_path = binding.get("lock_path")
            if not lock_path and binding.get("scope") in ("project", "global"):
                discovered = self.project / "skills-lock.json" if binding["scope"] == "project" else global_lock_path()
                if discovered.is_file():
                    lock_path = discovered
            if lock_path:
                lock = core.read_json(lock_path, "npx skills lock")
                require(lock.get("version") in (1, 3), "unsupported npx lock version")
                entry = lock.get("skills", {}).get(binding["lock_entry"])
                require(isinstance(entry, dict), "source lock entry missing")
                expected_origin = old.get("origin") or binding["origin"]
                was_local = expected_origin["source_type"] == "local"
                is_local = entry.get("sourceType") == "local"
                if was_local != is_local or (not was_local and origin_from_entry(entry) != expected_origin):
                    return {**result, "state": "rebound"}
                upstream = {"ref": entry.get("ref"), "resolved_commit": None,
                            "reported_folder_hash": entry.get("computedHash", entry.get("skillFolderHash")),
                            "reported_hash_algorithm": "unknown"}
            actual = fingerprint(path)
            status = "unknown" if old["content"] is None else "unchanged" if content(actual) == old["content"] else "changed"
            return {**result, "state": status, "content": content(actual), "upstream": upstream,
                    **file_changes(old["files"] or [], actual["files"])}
        except (OSError, VersionError, ValueError) as exc:
            return {**result, "state": "unreadable", "reason": str(exc)}

    def capture(self, folder, bindings, allow_unknown=False):
        folder.mkdir()
        (folder / "sources").mkdir()
        records, sources = [], []
        for index, binding in enumerate(bindings, 1):
            path, key = Path(binding["installed_path"]), f"s{index:03}"
            snapshot = folder / "sources" / key
            try:
                before = fingerprint(path)
                files = core.copy_skill_tree(path, snapshot)
                after = fingerprint(path)
                require(before == after and files == before["files"], "source changed while taking snapshot")
                source = {"source_id": binding["source_id"], "binding_id": binding["source_id"],
                          "origin": binding["origin"], "origin_provenance": "observed_at_capture",
                          "content": content(before), "files": files, "snapshot_key": key}
                observed = self.observe(binding, source)
                require(observed["state"] == "unchanged", "source identity changed during snapshot")
                source["upstream"] = observed["upstream"]
            except (OSError, VersionError, ValueError) as exc:
                if not allow_unknown:
                    raise
                if snapshot.exists():
                    self.discard(snapshot)
                sources.append({"source_id": binding["source_id"], "binding_id": binding["source_id"], "origin": binding["origin"],
                                "content": None, "files": None, "snapshot_key": None, "baseline": "unknown",
                                "upstream": None, "reason": str(exc)})
                continue
            sources.append(source)
            records.append({"id": key, "original_path": str(path), "snapshot_path": "sources/" + key,
                            "files": files, "origin": source["origin"], "source_id": source["source_id"],
                            "upstream": source["upstream"]})
        write(folder / "sources.json", {"schema_version": 1, "sources": records})
        return sources

    def validate_locations(self, active, bindings, target_id):
        require(not core.is_within(active, self.project / ".skill-distill")
                and active != self.project, "active path overlaps version storage")
        for binding in bindings:
            source = Path(binding["installed_path"])
            require(not core.is_within(self.project / ".skill-distill", source)
                    and not core.is_within(source, self.project / ".skill-distill"), "source overlaps version storage")
            require(not core.is_within(active, source) and not core.is_within(source, active),
                    "active path overlaps a source package")
        if self.root.exists():
            for folder in self.root.iterdir():
                if folder.name != target_id and (folder / "state.json").exists():
                    other = self.state(folder.name)
                    other_active = relative(self.project, other["active_path"])
                    require(not core.is_within(active, other_active) and not core.is_within(other_active, active),
                            "active path overlaps another target")

    def import_sources(self, destination, baseline_run, raw_sources, bindings):
        baseline = Path(baseline_run).resolve(strict=True)
        errors = []
        verified = core.load_and_verify_manifest(baseline, errors)
        require(not errors, "historical snapshot invalid: " + "; ".join(errors))
        manifest = core.read_json(baseline / "sources.json", "historical sources")
        entries = {s["id"]: s for s in manifest["sources"]}
        destination.mkdir()
        (destination / "sources").mkdir()
        used, inputs, records = set(), [], []
        for index, (raw, binding) in enumerate(zip(raw_sources, bindings), 1):
            key = raw.get("snapshot_key")
            if key is None:
                matches = [key for key, item in entries.items()
                           if Path(item["original_path"]).resolve() == Path(binding["installed_path"])]
                require(len(matches) == 1, "supply snapshot_key to map this historical input")
                key = matches[0]
            require(key in verified and key not in used, "historical source mapping is missing or duplicated")
            used.add(key)
            alias = f"s{index:03}"
            files = core.copy_skill_tree(verified[key]["root"], destination / "sources" / alias)
            actual = fingerprint(destination / "sources" / alias)
            require(files == entries[key]["files"], "historical input changed while importing")
            entry = entries[key]
            historical = raw.get("historical_origin", entry.get("origin"))
            historical = source_origin(historical) if historical is not None else None
            if entry.get("origin") is not None:
                require(historical == source_origin(entry["origin"]), "supplied historical origin conflicts with snapshot")
            historical_id = origin_id(historical) if historical is not None else None
            if historical is not None and entry.get("source_id") is not None:
                require(historical_id == entry["source_id"], "historical source identity mismatch")
            provenance = "snapshot_record" if entry.get("origin") is not None else "supplied_record" if historical else "unknown"
            inputs.append({"source_id": historical_id, "binding_id": binding["source_id"], "origin": historical,
                           "origin_provenance": provenance,
                           "content": content(actual), "files": files, "snapshot_key": alias,
                           "baseline": "provided_snapshot", "upstream": entry.get("upstream") if historical else None})
            records.append({"id": alias, "original_path": entries[key]["original_path"],
                            "snapshot_path": "sources/" + alias, "files": files,
                            "origin": historical, "source_id": historical_id})
        require(used == set(entries), "historical input members cannot be silently omitted")
        write(destination / "sources.json", {"schema_version": 1, "sources": records})
        return inputs

    def register(self, target_id, active_path, sources, baseline_run=None, evidence_path=None, method_info=None):
        target = self.target(target_id)
        supplied = Path(active_path)
        active = supplied if supplied.is_absolute() else self.project / supplied
        require(core.is_within(active, self.project), "active path must stay in the project")
        active = relative(self.project, active.relative_to(self.project).as_posix())
        require(isinstance(sources, list), "sources must be a list; use [] for unknown history")
        bindings = [self.binding(raw) for raw in sources]
        require(len({b["source_id"] for b in bindings}) == len(bindings)
                and len({os.path.normcase(b["installed_path"]) for b in bindings}) == len(bindings), "duplicate source identity or location")
        self.validate_locations(active, bindings, target_id)
        original = fingerprint(active)
        if method_info is not None:
            require(isinstance(method_info, dict) and isinstance(method_info.get("package"), dict)
                    and method_info["package"].get("algorithm") == "snapshot-manifest-sha256-v1"
                    and isinstance(method_info["package"].get("value"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", method_info["package"]["value"]),
                    "adopted method requires its recorded package fingerprint")
        with self.lock(target):
            require(not (target / "state.json").exists(), "target is already registered")
            stage = target / (".register-" + uuid.uuid4().hex)
            stage.mkdir()
            try:
                if baseline_run is not None:
                    inputs = self.import_sources(stage / "run", baseline_run, sources, bindings)
                else:
                    inputs = self.capture(stage / "run", bindings, allow_unknown=True)
                    for source in inputs:
                        if source["content"] is not None:
                            source["baseline"] = "observed_at_adoption"
                copied = core.copy_skill_tree(active, stage / "package")
                require(copied == original["files"] and fingerprint(active) == original,
                        "active package changed during registration")
                record = {"schema_version": 1, "target_id": target_id, "release_id": "r000001",
                          "parent_release": None, "created_at": now(), "origin": {"kind": "adopted", "provenance": "partial"},
                          "sources": inputs, "method": method_info,
                          "artifact": {"path": "package", "content": content(original), "files": copied},
                          "validation": {"status": "unknown", "scope": "adopted without generation claims"}}
                if evidence_path is not None:
                    evidence_dir = Path(evidence_path).resolve(strict=True)
                    validation = self.evidence(evidence_dir, original, active)
                    core.collect_files(evidence_dir)
                    shutil.copytree(evidence_dir, stage / "evidence", symlinks=True)
                    require(self.evidence(stage / "evidence", original, active) == validation, "adopted evidence changed")
                    record.update(validation=validation, evidence_files=evidence_manifest(stage / "evidence"))
                write(stage / "release.json", record)
                releases = target / "releases"
                releases.mkdir(exist_ok=True)
                require(not (releases / "r000001").exists(), "initial release already exists; inspect prior registration")
                stage.rename(releases / "r000001")
                state = {"schema_version": 1, "target_id": target_id, "active_path": active.relative_to(self.project).as_posix(),
                         "current_release": "r000001", "revision": 1, "source_bindings": bindings}
                write(target / "state.json", state)
                return state
            finally:
                if stage.exists():
                    shutil.rmtree(stage)

    def inspect(self, target_id):
        target = self.target(target_id)
        if not (target / "state.json").exists():
            return {"target_id": target_id, "status": "unmanaged"}
        state = self.state(target_id)
        record = self.release(target_id, state["current_release"])
        active = relative(self.project, state["active_path"])
        if not active.exists():
            artifact = {"state": "missing"}
        else:
            try:
                actual = fingerprint(active)
                artifact = {"state": "clean" if content(actual) == record["artifact"]["content"] else "modified",
                            "content": content(actual), **file_changes(record["artifact"]["files"], actual["files"])}
            except (VersionError, OSError) as exc:
                artifact = {"state": "modified", "reason": str(exc)}
        by_id = {binding_id(s): s for s in record["sources"]}
        require(set(by_id) == {b["source_id"] for b in state["source_bindings"]}, "source binding membership changed")
        method = record.get("method")
        method_state = "unknown" if method is None else (
            "same" if method["package"] == self.method()["package"] else "changed")
        candidates = []
        work_root = target / "work"
        if work_root.exists():
            for path in sorted(work_root.iterdir()):
                run = read(relative(work_root, path.name) / "work.json")
                if run["status"] in ("building", "ready", "failed"):
                    candidates.append({"state": run["status"], "run_id": run["run_id"],
                                       "release_id": run.get("release_id"), "created_at": run["created_at"]})
        candidates.sort(key=lambda c: c["created_at"])
        return {"target_id": target_id, "status": "managed", "current_release": state["current_release"],
                "revision": state["revision"], "artifact": artifact,
                "sources": [self.observe(b, by_id[b["source_id"]]) for b in state["source_bindings"]],
                "source_history": ("unknown" if not record["sources"] or any(s["content"] is None for s in record["sources"])
                                   else "partial" if any(s.get("origin") is None for s in record["sources"])
                                   else "observed_at_adoption" if any(s.get("baseline") == "observed_at_adoption" for s in record["sources"])
                                   else "recorded_snapshot"),
                "method": {"state": method_state}, "candidate": candidates[-1] if candidates else {"state": "none"},
                "candidates": candidates, "pending_operations": self.pending_operations(target_id),
                "upstream": "not_queried"}

    def pending_operations(self, target_id):
        folder = relative(self.target(target_id), "operations")
        if not folder.exists():
            return []
        return [p.stem for p in sorted(folder.glob("op-*.json"))
                if read(p).get("status") not in ("committed", "restored", "aborted")]

    def method(self, info=None):
        require(info is None or isinstance(info, dict), "method metadata must be an object")
        info = dict(info or {})
        require("package" not in info, "method package fingerprint is computed, not supplied")
        return {"package": content(fingerprint(Path(__file__).resolve().parents[1])),
                "generation_settings": info.get("generation_settings"), "author_executor": info.get("author_executor")}

    def prepare(self, target_id, method_info=None, regenerate=False, accept_current_sources=False):
        target = self.target(target_id)
        with self.lock(target):
            state = self.state(target_id)
            require(state["source_bindings"], "source bindings are unknown; provide verified inputs before rebuilding")
            require(not self.pending_operations(target_id), "unfinished switch requires recovery")
            record = self.release(target_id, state["current_release"])
            report = self.inspect(target_id)
            require(report["artifact"]["state"] == "clean", "current package has local edits or is missing")
            require(accept_current_sources or all(s.get("origin") is not None for s in record["sources"]),
                    "historical source origin is unknown; explicitly select current sources before rebuilding")
            allowed = ("changed", "unchanged", "unknown", "rebound") if accept_current_sources else ("changed", "unchanged", "unknown")
            require(all(s["state"] in allowed for s in report["sources"]),
                    "source is missing, unreadable or rebound; resolve its binding first")
            method = self.method(method_info)
            if not regenerate and record.get("method") == method and all(s["state"] == "unchanged" for s in report["sources"]):
                return {"status": "up_to_date", "current_release": state["current_release"]}
            run_id = "run-" + uuid.uuid4().hex
            folder = target / "work" / run_id
            folder.mkdir(parents=True)
            run = {"schema_version": 1, "target_id": target_id, "run_id": run_id, "created_at": now(),
                   "status": "building", "expected_revision": state["revision"],
                   "expected_release": state["current_release"], "expected_artifact": record["artifact"]["content"],
                   "sources": [], "method": method, "accepted_current_sources": bool(accept_current_sources)}
            write(folder / "work.json", run)
            try:
                run["sources"] = self.capture(folder / "run", state["source_bindings"])
                write(folder / "work.json", run)
            except (OSError, VersionError, ValueError) as exc:
                run.update(status="failed", error=str(exc))
                write(folder / "work.json", run)
                raise
            return {**run, "path": str(folder)}

    def work(self, target_id, run_id):
        require(isinstance(run_id, str) and re.fullmatch(r"run-[0-9a-f]{32}", run_id), "invalid work ID")
        folder = relative(self.target(target_id), "work/" + run_id)
        run = read(folder / "work.json")
        require(run.get("target_id") == target_id and run.get("run_id") == run_id, "work identity mismatch")
        return folder, run

    def evidence(self, evidence_dir, candidate, candidate_path):
        report = read(evidence_dir / "report.json")
        require(report.get("scope") in ("smoke", "metadata"), "evidence scope must be smoke or metadata")
        require(report.get("artifact") == content(candidate), "evidence does not match candidate bytes")
        checks, outputs = report.get("checks"), report.get("outputs")
        require(isinstance(checks, list) and checks, "observed evidence checks are required")
        require(all(isinstance(c, dict) and c.get("passed") is True and isinstance(c.get("id"), str)
                    and isinstance(c.get("evidence"), str) and c["evidence"].strip() for c in checks),
                "evidence contains failed or incomplete checks")
        require(isinstance(outputs, list) and outputs, "actual evidence outputs are required")
        for output in outputs:
            require(relative(evidence_dir, output).is_file(), "evidence output is missing")
        require(len({c["id"] for c in checks}) == len(checks), "duplicate evidence check IDs")
        adjustment = report.get("post_test_adjustment")
        require(report["scope"] != "metadata" or adjustment is not None,
                "metadata-only evidence requires the tested package and adjustment record")
        if adjustment is not None:
            require(isinstance(adjustment, dict) and adjustment.get("kind") == "metadata_only", "unsupported post-test adjustment")
            tested = relative(evidence_dir, adjustment.get("tested_package"))
            old = fingerprint(tested)
            require(content(old) == report.get("tested_artifact"), "tested artifact fingerprint mismatch")
            require([f for f in old["files"] if f["path"] != "SKILL.md"] ==
                    [f for f in candidate["files"] if f["path"] != "SKILL.md"]
                    and workflow_text(tested) == workflow_text(candidate_path),
                    "post-test workflow or auxiliary files changed; replay affected cases")
            static = adjustment.get("checks")
            require(isinstance(static, list) and static and all(isinstance(c, dict) and c.get("passed") is True
                    and isinstance(c.get("evidence"), str) and c["evidence"].strip() for c in static),
                    "metadata adjustment requires observed compatibility checks")
        return {**report, "status": "passed"}

    def seal(self, target_id, run_id, candidate_path, evidence_path):
        target = self.target(target_id)
        with self.lock(target):
            folder, run = self.work(target_id, run_id)
            require(run["status"] == "building", "only a building candidate can be sealed")
            candidate = Path(candidate_path).resolve(strict=True)
            evidence_dir = Path(evidence_path).resolve(strict=True)
            require(core.is_within(candidate, folder) and core.is_within(evidence_dir, folder)
                    and not core.is_within(evidence_dir, candidate) and not core.is_within(candidate, evidence_dir),
                    "candidate and evidence must be separate directories inside the work folder")
            try:
                actual = fingerprint(candidate)
                errors = []
                active_name = Path(self.state(target_id)["active_path"]).name
                core.validate_frontmatter(candidate, errors, expected_name=active_name)
                core.validate_markdown_links(candidate, errors)
                require(not errors, "candidate structure invalid: " + "; ".join(errors))
                validation = self.evidence(evidence_dir, actual, candidate)
                releases = target / "releases"
                numbers = [int(p.name[1:]) for p in releases.iterdir() if re.fullmatch(r"r\d{6,}", p.name)]
                release_id = f"r{max(numbers, default=0) + 1:06}"
                stage = target / (".seal-" + uuid.uuid4().hex)
                stage.mkdir()
                try:
                    copied = core.copy_skill_tree(candidate, stage / "package")
                    require(copied == actual["files"], "candidate changed while sealing")
                    shutil.copytree(folder / "run", stage / "run", symlinks=True)
                    # collect_files rejects links and non-regular evidence resources.
                    core.collect_files(evidence_dir)
                    shutil.copytree(evidence_dir, stage / "evidence", symlinks=True)
                    require(self.evidence(stage / "evidence", fingerprint(stage / "package"), stage / "package") == validation,
                            "evidence changed while sealing")
                    record = {"schema_version": 1, "target_id": target_id, "release_id": release_id,
                              "parent_release": run["expected_release"], "created_at": now(),
                              "origin": {"kind": "generated", "provenance": "recorded"},
                              "sources": run["sources"], "method": run["method"],
                              "artifact": {"path": "package", "content": content(actual), "files": copied},
                              "validation": validation, "evidence_files": evidence_manifest(stage / "evidence"),
                              "base_revision": run["expected_revision"], "run_id": run_id,
                              "accepted_current_sources": run.get("accepted_current_sources", False)}
                    write(stage / "release.json", record)
                    validate_snapshots(stage / "run", run["sources"])
                    stage.rename(releases / release_id)
                finally:
                    if stage.exists():
                        shutil.rmtree(stage)
                run.update(status="ready", release_id=release_id)
                write(folder / "work.json", run)
                return record
            except (VersionError, OSError, ValueError) as exc:
                run.update(status="failed", error=str(exc))
                write(folder / "work.json", run)
                raise

    def promote(self, target_id, release_id, expected_revision=None):
        return self.switch(target_id, release_id, "update", expected_revision)

    def rollback(self, target_id, release_id, expected_revision=None):
        return self.switch(target_id, release_id, "rollback", expected_revision)

    def discard(self, path):
        path = relative(self.project, path.relative_to(self.project).as_posix())
        require(path != self.project and core.is_within(path.resolve(), self.project), "cleanup outside project")
        if path.exists():
            shutil.rmtree(path)

    def candidate_inputs(self, state, record):
        require(record["method"]["package"] == self.method()["package"], "distillation method changed since candidate preparation")
        by_id = {binding_id(s): s for s in record["sources"]}
        require(set(by_id) == {b["source_id"] for b in state["source_bindings"]}, "source membership changed")
        require(all(self.observe(b, by_id[b["source_id"]])["state"] == "unchanged" for b in state["source_bindings"]),
                "source changed since candidate preparation")

    def applied(self, target_id, record):
        run_id = record.get("run_id")
        if run_id and (self.target(target_id) / "work" / run_id / "work.json").exists():
            folder, run = self.work(target_id, run_id)
            run["status"] = "applied"
            write(folder / "work.json", run)

    def switch(self, target_id, release_id, kind, expected_revision):
        target = self.target(target_id)
        with self.lock(target):
            require(not self.pending_operations(target_id), "unfinished switch requires recovery")
            state = self.state(target_id)
            record = self.release(target_id, release_id)
            current = self.release(target_id, state["current_release"])
            if expected_revision is not None:
                require(type(expected_revision) is int and state["revision"] == expected_revision,
                        "candidate is stale: inspected target revision changed")
            if kind == "update":
                require(type(record.get("base_revision")) is int and state["revision"] == record["base_revision"],
                        "candidate is stale: captured target revision changed")
            active = relative(self.project, state["active_path"])
            require(active.exists() and content(fingerprint(active)) == current["artifact"]["content"],
                    "current package has local edits or is missing")
            self.validate_locations(active, state["source_bindings"], target_id)
            if kind == "update":
                require(record["origin"]["kind"] == "generated" and record["parent_release"] == state["current_release"],
                        "candidate was not built from the current release")
                evidence_dir = target / "releases" / release_id / "evidence"
                package = target / "releases" / release_id / "package"
                require(self.evidence(evidence_dir, fingerprint(package), package) == record["validation"],
                        "saved validation evidence changed")
                self.candidate_inputs(state, record)
            operation_id = "op-" + uuid.uuid4().hex
            staged = active.parent / f".{active.name}.next-{operation_id}"
            backup = active.parent / f".{active.name}.old-{operation_id}"
            core.copy_skill_tree(target / "releases" / release_id / "package", staged)
            operation = {"schema_version": 1, "target_id": target_id, "operation_id": operation_id,
                         "kind": kind, "status": "prepared", "created_at": now(),
                         "expected_revision": state["revision"], "from_release": state["current_release"],
                         "to_release": release_id, "active_path": state["active_path"],
                         "staged_path": staged.relative_to(self.project).as_posix(),
                         "backup_path": backup.relative_to(self.project).as_posix(),
                         "old_content": current["artifact"]["content"], "new_content": record["artifact"]["content"]}
            operations = target / "operations"
            operations.mkdir(exist_ok=True)
            journal = operations / (operation_id + ".json")
            try:
                require(content(fingerprint(staged)) == operation["new_content"], "staged package differs from saved release")
                require(content(fingerprint(active)) == operation["old_content"], "current package changed during staging")
                if kind == "update":
                    self.candidate_inputs(state, record)
                write(journal, operation)
                active.rename(backup)
                operation["status"] = "backed_up"
                write(journal, operation)
                staged.rename(active)
                operation["status"] = "installed"
                write(journal, operation)
                state.update(current_release=release_id, revision=state["revision"] + 1, last_operation=operation_id)
                write(target / "state.json", state)
                self.applied(target_id, record)
                self.discard(backup)
                operation["status"] = "committed"
                write(journal, operation)
                return state
            except (OSError, VersionError, ValueError):
                persisted = self.state(target_id)
                if persisted.get("last_operation") != operation_id:
                    if backup.exists() and content(fingerprint(backup)) == operation["old_content"]:
                        if active.exists() and content(fingerprint(active)) == operation["new_content"]:
                            active.rename(staged)
                        if not active.exists():
                            backup.rename(active)
                    if active.exists() and content(fingerprint(active)) == operation["old_content"]:
                        operation["status"] = "aborted"
                        write(journal, operation)
                raise
            finally:
                if staged.exists() and (not journal.exists() or read(journal)["status"] in ("aborted", "committed")):
                    self.discard(staged)

    def recover(self, target_id, operation_id=None):
        target = self.target(target_id)
        with self.lock(target):
            pending = self.pending_operations(target_id)
            if operation_id is None:
                require(len(pending) <= 1, "specify which pending operation to recover")
                if not pending:
                    return {"status": "no_pending_operation"}
                operation_id = pending[0]
            require(isinstance(operation_id, str) and re.fullmatch(r"op-[0-9a-f]{32}", operation_id), "invalid operation ID")
            journal = relative(target, "operations/" + operation_id + ".json")
            operation = read(journal)
            state = self.state(target_id)
            require(operation.get("target_id") == target_id and operation.get("operation_id") == operation_id,
                    "operation identity mismatch")
            active = relative(self.project, operation["active_path"])
            staged = relative(self.project, operation["staged_path"])
            backup = relative(self.project, operation["backup_path"])
            require(operation["active_path"] == state["active_path"]
                    and staged == active.parent / f".{active.name}.next-{operation_id}"
                    and backup == active.parent / f".{active.name}.old-{operation_id}", "invalid operation paths")
            old = self.release(target_id, operation["from_release"])
            new = self.release(target_id, operation["to_release"])
            require(operation["old_content"] == old["artifact"]["content"]
                    and operation["new_content"] == new["artifact"]["content"], "operation fingerprint mismatch")
            before = (state["revision"] == operation["expected_revision"]
                      and state["current_release"] == operation["from_release"])
            after = (state["revision"] == operation["expected_revision"] + 1
                     and state["current_release"] == operation["to_release"]
                     and state.get("last_operation") == operation_id)
            require(before or after, "target changed since this operation; preserve current files")
            def matches(path, expected):
                return path.exists() and content(fingerprint(path)) == expected
            old_active = matches(active, operation["old_content"])
            new_active = matches(active, operation["new_content"])
            if backup.exists():
                require(matches(backup, operation["old_content"]), "backup was modified; preserve files")
            if staged.exists():
                require(matches(staged, operation["new_content"]), "staged package was modified; preserve files")
            installed = new_active and (not old_active or backup.exists() or after)
            if installed:
                if before:
                    state.update(current_release=operation["to_release"], revision=state["revision"] + 1,
                                 last_operation=operation_id)
                    write(target / "state.json", state)
                operation["status"] = "committed"
                self.applied(target_id, new)
            elif before and not active.exists() and backup.exists():
                backup.rename(active)
                operation["status"] = "restored"
            elif before and old_active:
                operation["status"] = "aborted"
            else:
                core.fail("unrecognized current package; preserve files for inspection")
            if backup.exists():
                self.discard(backup)
            if staged.exists():
                self.discard(staged)
            write(journal, operation)
            return {"status": operation["status"], "operation_id": operation_id,
                    "current_release": state["current_release"], "revision": state["revision"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    digest = commands.add_parser("fingerprint", help="read-only complete package fingerprint")
    digest.add_argument("--path", required=True)
    inspect = commands.add_parser("inspect", help="read-only state and local-source comparison")
    inspect.add_argument("target")
    register = commands.add_parser("register", help="adopt an existing project-local artifact without rewriting it")
    register.add_argument("target")
    register.add_argument("--active", required=True)
    register.add_argument("--baseline-run", help="existing source snapshot run to preserve as the historical baseline")
    register.add_argument("--evidence", help="existing observed evidence directory with report.json")
    register.add_argument("--method", metavar="JSON", help="method record captured at original generation, including package fingerprint")
    sources = register.add_mutually_exclusive_group(required=True)
    sources.add_argument("--source", action="append", metavar="PACKAGE")
    sources.add_argument("--sources", metavar="JSON", help="list of source path/origin bindings")
    prepare = commands.add_parser("prepare", help="snapshot an explicitly requested update")
    prepare.add_argument("target")
    prepare.add_argument("--method", metavar="JSON", help="observed author executor and generation settings")
    prepare.add_argument("--regenerate", action="store_true")
    prepare.add_argument("--accept-current-sources", action="store_true", help="explicitly rebuild from the selected current bindings despite unverified historical origin")
    seal = commands.add_parser("seal", help="save a candidate with observed evidence; does not activate it")
    seal.add_argument("target")
    seal.add_argument("run")
    seal.add_argument("--candidate", required=True)
    seal.add_argument("--evidence", required=True)
    for name in ("promote", "rollback"):
        command = commands.add_parser(name)
        command.add_argument("target")
        command.add_argument("release")
        command.add_argument("--expected-revision", type=int)
    recover = commands.add_parser("recover", help="recover one recorded interrupted operation")
    recover.add_argument("target")
    recover.add_argument("--operation")
    args = parser.parse_args(argv)
    try:
        store = VersionStore(args.project)
        if args.command == "fingerprint":
            result = fingerprint(Path(args.path).resolve(strict=True))
        elif args.command == "inspect":
            result = store.inspect(args.target)
        elif args.command == "register":
            bindings = core.read_json(args.sources, "source bindings") if args.sources else [{"path": p} for p in args.source]
            method = core.read_json(args.method, "recorded generation method") if args.method else None
            result = store.register(args.target, args.active, bindings, args.baseline_run, args.evidence, method)
        elif args.command == "prepare":
            method = core.read_json(args.method, "observed method parameters") if args.method else None
            result = store.prepare(args.target, method, args.regenerate, args.accept_current_sources)
        elif args.command == "seal":
            result = store.seal(args.target, args.run, args.candidate, args.evidence)
        elif args.command == "recover":
            result = store.recover(args.target, args.operation)
        else:
            result = getattr(store, args.command)(args.target, args.release, args.expected_revision)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (VersionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
