#!/usr/bin/env python3
"""Classify skills, select targets, snapshot, validate, and compare packages."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from urllib.parse import unquote, urlsplit


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
RULE_ACTIONS = {"preserve", "merge", "route", "prioritize", "drop"}
RESOURCE_ACTIONS = {"copy", "adapt", "omit"}
FRONTMATTER_NOTICE = (
    "Frontmatter validation is basic; full YAML semantics are not checked."
)
SEMANTIC_NOTICE = (
    "Semantic coverage is not measured; quote checks confirm only declared contract entries."
)


class DistillError(Exception):
    """An expected input or filesystem error suitable for a concise CLI message."""


def fail(message):
    raise DistillError(message)


def is_reparse_stat(info):
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def reject_reparse_components(path):
    """Reject symlinks and Windows reparse points in a path and its parents."""
    path = Path(os.path.abspath(os.fspath(path)))
    components = list(reversed(path.parents)) + [path]
    for component in components:
        try:
            info = component.lstat()
        except FileNotFoundError:
            fail(f"path component does not exist: {component}")
        except OSError as exc:
            fail(f"cannot inspect path component {component}: {exc}")
        if is_reparse_stat(info):
            fail(f"symlink/junction/reparse point is not allowed: {component}")


def normalized_absolute(path):
    return Path(os.path.abspath(os.fspath(path)))


def is_within(path, root):
    try:
        Path(path).relative_to(Path(root))
        return True
    except ValueError:
        return False


def safe_relative_path(value, label):
    """Parse portable slash-separated paths and reject traversal/OS syntax."""
    if not isinstance(value, str) or not value:
        fail(f"{label} must be a non-empty relative path")
    if "\\" in value or value.startswith("/") or ":" in value or "\x00" in value:
        fail(f"{label} must be a safe relative path: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        fail(f"{label} must not contain empty, '.' or '..' components: {value!r}")
    reserved = {"CON", "PRN", "AUX", "NUL"}
    for number in range(1, 10):
        reserved.update({f"COM{number}", f"LPT{number}"})
    for part in parts:
        if part[-1:] in (".", " ") or any(char in '<>"|?*' for char in part):
            fail(f"{label} contains a non-portable path component: {value!r}")
        if part.split(".", 1)[0].upper() in reserved:
            fail(f"{label} contains a reserved path component: {value!r}")
    return PurePosixPath(*parts)


def safe_existing_file(root, relative, label):
    rel = safe_relative_path(relative, label)
    if root is None:
        fail(f"{label} cannot be checked because the candidate directory is unavailable")
    try:
        root = Path(root).resolve(strict=True)
    except OSError as exc:
        fail(f"{label} root directory is unavailable: {exc}")
    path = root.joinpath(*rel.parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        fail(f"{label} is missing or escapes its directory: {relative!r} ({exc})")
    if not resolved.is_file():
        fail(f"{label} is not a file: {relative!r}")
    return resolved


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path, label):
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read {label} JSON {path}: {exc}")


def write_json_atomic(path, value):
    path = normalized_absolute(path)
    parent = path.parent
    if not parent.is_dir():
        fail(f"output parent directory does not exist: {parent}")
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", delete=False,
            dir=parent, prefix=f".{path.name}.tmp-",
        ) as stream:
            temp_name = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temp_name, path)
    except (OSError, TypeError, ValueError) as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        fail(f"cannot write report {path}: {exc}")


def parse_source_arg(value):
    if "=" not in value:
        fail("--source must use ID=/absolute/skill-dir syntax")
    source_id, raw_path = value.split("=", 1)
    if not ID_RE.fullmatch(source_id):
        fail(f"unsafe source ID: {source_id!r}")
    safe_relative_path(source_id, "source ID")
    path = Path(raw_path)
    if not path.is_absolute():
        fail(f"source path must be absolute: {raw_path!r}")
    path = normalized_absolute(path)
    reject_reparse_components(path)
    if not path.is_dir():
        fail(f"source is not a directory: {path}")
    skill_file = path / "SKILL.md"
    try:
        skill_info = skill_file.lstat()
    except OSError as exc:
        fail(f"source must contain SKILL.md: {path} ({exc})")
    if is_reparse_stat(skill_info) or not stat.S_ISREG(skill_info.st_mode):
        fail(f"source SKILL.md must be a regular file without a symlink/junction: {skill_file}")
    return source_id, path.resolve(strict=True)


def iter_skill_entries(source):
    """The shared snapshot/fingerprint boundary, including empty directories."""
    source = Path(source)
    reject_reparse_components(source)
    if not source.is_dir():
        fail(f"source is not a directory: {source}")
    def walk(source_dir, relative_parts):
        try:
            with os.scandir(source_dir) as scan:
                entries = sorted(scan, key=lambda entry: entry.name)
        except OSError as exc:
            fail(f"cannot read source directory {source_dir}: {exc}")
        for entry in entries:
            source_path = Path(entry.path)
            rel_parts = relative_parts + (entry.name,)
            rel = "/".join(rel_parts)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                fail(f"cannot inspect source entry {source_path}: {exc}")
            if is_reparse_stat(info):
                fail(f"symlink/junction/reparse point is not allowed: {source_path}")
            if entry.name == ".git":
                continue
            if stat.S_ISDIR(info.st_mode):
                if entry.name == "__pycache__":
                    continue
                safe_relative_path(rel, "source package path")
                yield source_path, rel, True
                yield from walk(source_path, rel_parts)
                continue
            if not stat.S_ISREG(info.st_mode):
                fail(f"source contains a non-regular file: {source_path}")
            if entry.name.lower().endswith(".pyc"):
                continue
            safe_relative_path(rel, "source package path")
            yield source_path, rel, False
    yield from walk(source, ())


def skill_file_record(path, relative, target=None):
    digest, byte_count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if target is not None:
                target.write(chunk)
            digest.update(chunk)
            byte_count += len(chunk)
    return {"path": relative, "sha256": digest.hexdigest(), "bytes": byte_count}


def manifest_skill_tree(source):
    files = [skill_file_record(path, relative) for path, relative, directory
             in iter_skill_entries(source) if not directory]
    files.sort(key=lambda item: item["path"])
    if not any(item["path"] == "SKILL.md" for item in files):
        fail(f"source must contain SKILL.md: {source}")
    return files


def copy_skill_tree(source, destination):
    copied = []
    destination.mkdir()
    for path, relative, directory in iter_skill_entries(source):
        target = destination.joinpath(*relative.split("/"))
        if directory:
            target.mkdir()
        else:
            with target.open("xb") as stream:
                copied.append(skill_file_record(path, relative, stream))

    copied.sort(key=lambda item: item["path"])
    if not any(item["path"] == "SKILL.md" for item in copied):
        fail(f"source must contain SKILL.md: {source}")
    return copied


def command_snapshot(args):
    if not args.source:
        fail("snapshot requires at least one --source")
    sources = []
    seen_ids = set()
    for value in args.source:
        source_id, path = parse_source_arg(value)
        if source_id.casefold() in seen_ids:
            fail(f"duplicate source ID: {source_id}")
        seen_ids.add(source_id.casefold())
        sources.append((source_id, path))

    out_input = normalized_absolute(args.out)
    if os.path.lexists(out_input):
        fail(f"snapshot output already exists: {out_input}")
    parent = out_input.parent.resolve(strict=True)
    if not parent.is_dir():
        fail(f"snapshot output parent is not a directory: {parent}")
    out = parent / out_input.name
    for source_id, source_path in sources:
        resolved_source = source_path.resolve(strict=True)
        if is_within(out, resolved_source):
            fail(f"snapshot output must not be inside source {source_id}: {out}")

    stage = Path(tempfile.mkdtemp(prefix=f".{out.name}.tmp-", dir=parent))
    try:
        manifest_sources = []
        (stage / "sources").mkdir()
        for source_id, source_path in sources:
            snapshot_rel = f"sources/{source_id}"
            files = copy_skill_tree(source_path, stage / "sources" / source_id)
            manifest_sources.append({
                "id": source_id,
                "original_path": str(source_path.resolve(strict=True)),
                "snapshot_path": snapshot_rel,
                "files": files,
            })
        manifest = {"schema_version": 1, "sources": manifest_sources}
        with (stage / "sources.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        if os.path.lexists(out):
            fail(f"snapshot output appeared during creation: {out}")
        os.rename(stage, out)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise
    print(f"snapshot created: {out}")
    return 0


def add_error(errors, message):
    errors.append(str(message))


def load_and_verify_manifest(run_path, errors):
    sources = {}
    manifest_file = run_path / "sources.json"
    try:
        reject_reparse_components(run_path)
        if not run_path.is_dir():
            fail(f"run directory does not exist: {run_path}")
        reject_reparse_components(manifest_file)
        manifest = read_json(manifest_file, "sources manifest")
    except DistillError as exc:
        add_error(errors, exc)
        return sources
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        add_error(errors, "sources.json must be an object with schema_version: 1")
        return sources
    listed_sources = manifest.get("sources")
    if not isinstance(listed_sources, list) or not listed_sources:
        add_error(errors, "sources.json sources must be a non-empty array")
        return sources
    seen_ids = set()
    for source_index, record in enumerate(listed_sources):
        label = f"sources[{source_index}]"
        if not isinstance(record, dict):
            add_error(errors, f"{label} must be an object")
            continue
        source_id = record.get("id")
        if not isinstance(source_id, str) or not ID_RE.fullmatch(source_id):
            add_error(errors, f"{label} has an unsafe source id")
            continue
        try:
            safe_relative_path(source_id, f"{label} id")
        except DistillError as exc:
            add_error(errors, exc)
            continue
        if source_id.casefold() in seen_ids:
            add_error(errors, f"duplicate source id in manifest: {source_id}")
            continue
        seen_ids.add(source_id.casefold())
        original_path = record.get("original_path")
        if not isinstance(original_path, str) or not Path(original_path).is_absolute():
            add_error(errors, f"{label} original_path must be absolute")
        snapshot_rel = record.get("snapshot_path")
        expected_rel = f"sources/{source_id}"
        if snapshot_rel != expected_rel:
            add_error(errors, f"{label} snapshot_path must be {expected_rel!r}")
            continue
        try:
            snapshot_path = safe_existing_file(run_path, "sources.json", "manifest path").parent
            snapshot_root = snapshot_path / "sources" / source_id
            if not snapshot_root.is_dir():
                fail(f"snapshot directory is missing: {snapshot_root}")
            if is_reparse_stat(snapshot_root.lstat()):
                fail(f"snapshot directory is a symlink/junction: {snapshot_root}")
        except (DistillError, OSError) as exc:
            add_error(errors, f"{label}: {exc}")
            continue
        file_records = record.get("files")
        if not isinstance(file_records, list):
            add_error(errors, f"{label} files must be an array")
            continue
        file_map = {}
        for file_index, file_record in enumerate(file_records):
            file_label = f"{label}.files[{file_index}]"
            if not isinstance(file_record, dict):
                add_error(errors, f"{file_label} must be an object")
                continue
            rel = file_record.get("path")
            try:
                safe_relative_path(rel, f"{file_label} path")
            except DistillError as exc:
                add_error(errors, exc)
                continue
            if rel in file_map:
                add_error(errors, f"duplicate file in manifest: {source_id}/{rel}")
                continue
            file_map[rel] = file_record
            expected_hash = file_record.get("sha256")
            expected_bytes = file_record.get("bytes")
            if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
                add_error(errors, f"invalid SHA256 in manifest for {source_id}/{rel}")
                continue
            if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool) or expected_bytes < 0:
                add_error(errors, f"invalid byte count in manifest for {source_id}/{rel}")
                continue
            try:
                path = safe_existing_file(snapshot_root, rel, f"snapshot file {source_id}/{rel}")
                data = path.read_bytes()
            except (DistillError, OSError) as exc:
                add_error(errors, exc)
                continue
            if sha256_bytes(data).lower() != expected_hash.lower():
                add_error(errors, f"snapshot SHA256 mismatch for {source_id}/{rel}")
            if len(data) != expected_bytes:
                add_error(errors, f"snapshot byte count mismatch for {source_id}/{rel}")
        if "SKILL.md" not in file_map:
            add_error(errors, f"snapshot {source_id} manifest must include SKILL.md")
        try:
            actual_files = collect_files(snapshot_root)
            actual_set = set(actual_files)
            declared_set = set(file_map)
            for rel in sorted(actual_set - declared_set):
                add_error(errors, f"unlisted file in source snapshot: {source_id}/{rel}")
            for rel in sorted(declared_set - actual_set):
                add_error(errors, f"missing file in source snapshot: {source_id}/{rel}")
        except DistillError as exc:
            add_error(errors, exc)
        sources[source_id] = {
            "root": snapshot_root,
            "files": file_map,
        }
    return sources


def collect_files(root):
    result = []

    def walk(directory, prefix=()):
        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda item: item.name)
        except OSError as exc:
            fail(f"cannot inspect directory {directory}: {exc}")
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                fail(f"cannot inspect {path}: {exc}")
            if is_reparse_stat(info):
                fail(f"symlink/junction/reparse point in snapshot: {path}")
            parts = prefix + (entry.name,)
            if stat.S_ISDIR(info.st_mode):
                walk(path, parts)
            elif stat.S_ISREG(info.st_mode):
                result.append("/".join(parts))
            else:
                fail(f"non-regular file in snapshot: {path}")

    walk(Path(root))
    return result


def read_utf8_file(path, label):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read UTF-8 text for {label}: {exc}")


def validate_frontmatter(candidate, errors, expected_name=None):
    try:
        skill_file = safe_existing_file(candidate, "SKILL.md", "candidate SKILL.md")
        text = read_utf8_file(skill_file, "candidate SKILL.md")
    except DistillError as exc:
        add_error(errors, exc)
        return
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        add_error(errors, "candidate SKILL.md must begin with YAML frontmatter")
        return
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        add_error(errors, "candidate SKILL.md frontmatter has no closing ---")
        return
    values = {}
    for line in lines[1:closing]:
        match = re.match(r"^\s*(name|description)\s*:\s*(.*?)\s*$", line)
        if match:
            key, value = match.groups()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1].strip()
            values[key] = value
    for key in ("name", "description"):
        if not values.get(key, "").strip():
            add_error(errors, f"candidate frontmatter must have non-empty {key}")
    expected_name = expected_name or candidate.name
    if values.get("name", "").strip() and values["name"].strip() != expected_name:
        add_error(
            errors,
            f"candidate frontmatter name must match directory name {expected_name!r}",
        )


FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LINK_RE = re.compile(
    r"(?<!!)(?:\[([^\]\n]*)\])\(\s*(<[^>\n]*>|(?:\\.|[^)\s])+)(?:\s+[^)]*)?\s*\)"
)


def markdown_links_outside_fences(text):
    fence_char = None
    fence_length = 0
    links = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if fence_char is not None:
            closing = re.match(r"^ {0,3}(`+|~+)\s*$", line)
            if closing and closing.group(1)[0] == fence_char and len(closing.group(1)) >= fence_length:
                fence_char = None
                fence_length = 0
            continue
        if line.startswith("\t") or line.startswith("    "):
            continue
        opening = FENCE_OPEN_RE.match(line)
        if opening:
            fence_char = opening.group(1)[0]
            fence_length = len(opening.group(1))
            continue
        for match in LINK_RE.finditer(line):
            destination = match.group(2)
            if destination.startswith("<") and destination.endswith(">"):
                destination = destination[1:-1]
            destination = re.sub(r"\\([\\ ()])", r"\1", destination)
            links.append((line_number, destination))
    return links


def validate_markdown_links(candidate, errors):
    for markdown_file in iter_markdown_files(candidate):
        try:
            content = read_utf8_file(markdown_file, str(markdown_file))
        except DistillError as exc:
            add_error(errors, exc)
            continue
        for line_number, destination in markdown_links_outside_fences(content):
            if not destination or destination.startswith("#"):
                continue
            try:
                parsed = urlsplit(destination)
            except ValueError:
                add_error(errors, f"invalid Markdown link in {markdown_file}:{line_number}: {destination!r}")
                continue
            if parsed.scheme or parsed.netloc:
                continue
            link_path = unquote(parsed.path)
            if not link_path:
                continue
            if link_path.startswith("/"):
                target = candidate.joinpath(*[part for part in link_path.split("/") if part])
            else:
                target = markdown_file.parent / Path(*PurePosixPath(link_path).parts)
            try:
                resolved = target.resolve(strict=True)
                resolved.relative_to(candidate.resolve(strict=True))
                if not resolved.exists():
                    raise FileNotFoundError(target)
            except (OSError, ValueError) as exc:
                add_error(
                    errors,
                    f"broken or escaping Markdown link in {markdown_file}:{line_number}: "
                    f"{destination!r} ({exc})",
                )


def iter_markdown_files(root):
    for directory, child_dirs, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        kept_dirs = []
        for name in child_dirs:
            child = directory_path / name
            try:
                info = child.lstat()
            except OSError:
                continue
            if not is_reparse_stat(info) and stat.S_ISDIR(info.st_mode):
                kept_dirs.append(name)
        child_dirs[:] = kept_dirs
        for name in filenames:
            if name.lower().endswith(".md"):
                path = directory_path / name
                try:
                    info = path.lstat()
                except OSError:
                    continue
                if not is_reparse_stat(info) and stat.S_ISREG(info.st_mode):
                    yield path


def validate_rule_contract(contract, sources, candidate, errors):
    mapped_rules = []
    unresolved_drops = []
    raw_rules = contract.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        add_error(errors, "contract rules must be a non-empty array")
        return mapped_rules, unresolved_drops
    seen_ids = set()
    represented_sources = set()
    for index, rule in enumerate(raw_rules):
        label = f"rules[{index}]"
        if not isinstance(rule, dict):
            add_error(errors, f"{label} must be an object")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            add_error(errors, f"{label} must have a non-empty id")
            continue
        if rule_id in seen_ids:
            add_error(errors, f"duplicate rule id: {rule_id}")
        seen_ids.add(rule_id)
        for key in ("when", "behavior"):
            if not isinstance(rule.get(key), str) or not rule[key].strip():
                add_error(errors, f"{label} must have a non-empty {key}")
        source = rule.get("source")
        if not isinstance(source, dict):
            add_error(errors, f"{label} source must be an object")
            continue
        source_id = source.get("skill")
        source_file = source.get("file")
        quote = source.get("quote")
        if not isinstance(source_id, str) or source_id not in sources:
            add_error(errors, f"{label} names unknown source skill {source_id!r}")
            continue
        represented_sources.add(source_id)
        try:
            safe_relative_path(source_file, f"{label} source.file")
        except DistillError as exc:
            add_error(errors, exc)
            continue
        if not isinstance(quote, str) or not quote.strip():
            add_error(errors, f"{label} source.quote must be a non-empty string")
            continue
        if source_file not in sources[source_id]["files"]:
            add_error(errors, f"{label} source file is not in snapshot manifest: {source_id}/{source_file}")
            continue
        try:
            source_path = safe_existing_file(
                sources[source_id]["root"], source_file, f"{label} source file"
            )
            source_text = read_utf8_file(source_path, f"{source_id}/{source_file}")
        except DistillError as exc:
            add_error(errors, exc)
            continue
        if quote not in source_text:
            add_error(errors, f"{label} source quote is not present in {source_id}/{source_file}")

        disposition = rule.get("disposition")
        if not isinstance(disposition, dict):
            add_error(errors, f"{label} disposition must be an object")
            continue
        action = disposition.get("action")
        if not isinstance(action, str) or action not in RULE_ACTIONS:
            add_error(errors, f"{label} disposition.action must be one of {sorted(RULE_ACTIONS)}")
            continue
        reason = disposition.get("reason")
        if action in ("drop", "route", "prioritize") and (
            not isinstance(reason, str) or not reason.strip()
        ):
            add_error(errors, f"{label} action {action!r} requires a non-empty reason")
        if action == "drop":
            optional_target = disposition.get("target")
            if optional_target is not None:
                if not isinstance(optional_target, dict):
                    add_error(errors, f"{label} optional drop target must be an object")
                else:
                    target_file = optional_target.get("file")
                    target_quote = optional_target.get("quote")
                    try:
                        safe_relative_path(target_file, f"{label} target.file")
                        if not isinstance(target_quote, str) or not target_quote.strip():
                            fail(f"{label} target.quote must be a non-empty string")
                        target_path = safe_existing_file(candidate, target_file, f"{label} target.file")
                        if target_quote not in read_utf8_file(target_path, f"candidate/{target_file}"):
                            fail(f"{label} target quote is not present in candidate/{target_file}")
                    except DistillError as exc:
                        add_error(errors, exc)
            unresolved_drops.append({
                "id": rule_id,
                "source": {"skill": source_id, "file": source_file, "quote": quote},
                "reason": reason,
            })
            mapped_rules.append({"id": rule_id, "action": action, "mapped": False})
            continue

        target = disposition.get("target")
        if not isinstance(target, dict):
            add_error(errors, f"{label} action {action!r} requires a target object")
            mapped_rules.append({"id": rule_id, "action": action, "mapped": False})
            continue
        target_file = target.get("file")
        target_quote = target.get("quote")
        target_ok = True
        try:
            safe_relative_path(target_file, f"{label} target.file")
        except DistillError as exc:
            add_error(errors, exc)
            target_ok = False
        if not isinstance(target_quote, str) or not target_quote.strip():
            add_error(errors, f"{label} target.quote must be a non-empty string")
            target_ok = False
        if target_ok:
            try:
                target_path = safe_existing_file(candidate, target_file, f"{label} target.file")
                target_text = read_utf8_file(target_path, f"candidate/{target_file}")
                if target_quote not in target_text:
                    add_error(errors, f"{label} target quote is not present in candidate/{target_file}")
                    target_ok = False
            except DistillError as exc:
                add_error(errors, exc)
                target_ok = False
        mapped_rules.append({
            "id": rule_id,
            "source": {"skill": source_id, "file": source_file},
            "action": action,
            "target": {"file": target_file, "quote": target_quote},
            "mapped": target_ok,
        })
    for source_id in sorted(set(sources) - represented_sources):
        add_error(errors, f"source skill has no rule mapping: {source_id}")
    return mapped_rules, unresolved_drops


def resource_file_universe(sources):
    universe = set()
    for source_id, source in sources.items():
        for relative in source["files"]:
            if relative == "SKILL.md" or relative.lower() == "agents/openai.yaml":
                continue
            universe.add((source_id, relative))
    return universe


def validate_resources(contract, sources, candidate, errors):
    decisions = []
    raw_resources = contract.get("resources")
    if not isinstance(raw_resources, list):
        add_error(errors, "contract resources must be an array")
        return decisions
    expected = resource_file_universe(sources)
    seen = set()
    for index, decision in enumerate(raw_resources):
        label = f"resources[{index}]"
        if not isinstance(decision, dict):
            add_error(errors, f"{label} must be an object")
            continue
        source = decision.get("source")
        if not isinstance(source, dict):
            add_error(errors, f"{label} source must be an object")
            continue
        source_id, source_file = source.get("skill"), source.get("file")
        if not isinstance(source_id, str) or not isinstance(source_file, str):
            add_error(errors, f"{label} source must have skill and file strings")
            continue
        try:
            safe_relative_path(source_file, f"{label} source.file")
        except DistillError as exc:
            add_error(errors, exc)
            continue
        key = (source_id, source_file)
        if key not in expected:
            add_error(errors, f"{label} does not name an eligible source resource: {source_id}/{source_file}")
        if key in seen:
            add_error(errors, f"duplicate resource decision: {source_id}/{source_file}")
        seen.add(key)
        action = decision.get("action")
        if not isinstance(action, str) or action not in RESOURCE_ACTIONS:
            add_error(errors, f"{label} action must be one of {sorted(RESOURCE_ACTIONS)}")
            continue
        reason = decision.get("reason")
        if action in ("adapt", "omit") and (
            not isinstance(reason, str) or not reason.strip()
        ):
            add_error(errors, f"{label} action {action!r} requires a non-empty reason")
        target = decision.get("target")
        if not isinstance(target, str):
            add_error(errors, f"{label} target must be a relative path string")
            continue
        target_ok = True
        try:
            relative_target = safe_relative_path(target, f"{label} target")
            if action == "omit":
                if candidate is None:
                    fail(f"{label} cannot be checked because the candidate directory is unavailable")
                resolved_target = candidate.joinpath(*relative_target.parts).resolve(strict=False)
                resolved_target.relative_to(candidate.resolve(strict=True))
        except DistillError as exc:
            add_error(errors, exc)
            target_ok = False
        except (OSError, ValueError) as exc:
            add_error(errors, f"{label} omit target escapes or has no candidate root: {exc}")
            target_ok = False
        target_path = target
        byte_identical = None
        if action in ("copy", "adapt"):
            if not target_ok:
                add_error(errors, f"{label} {action} requires a safe target path")
            elif source_id in sources and source_file in sources[source_id]["files"]:
                try:
                    source_fs_path = safe_existing_file(
                        sources[source_id]["root"], source_file, f"{label} source file"
                    )
                    destination_fs_path = safe_existing_file(
                        candidate, target_path, f"{label} target"
                    )
                    source_bytes = source_fs_path.read_bytes()
                    destination_bytes = destination_fs_path.read_bytes()
                    byte_identical = source_bytes == destination_bytes
                    if action == "copy" and not byte_identical:
                        add_error(errors, f"{label} copy SHA256/bytes differ for {source_id}/{source_file}")
                except DistillError as exc:
                    add_error(errors, exc)
                except OSError as exc:
                    add_error(errors, f"{label} cannot compare resource bytes: {exc}")
        decisions.append({
            "source": {"skill": source_id, "file": source_file},
            "action": action,
            "target": target,
            "reason": reason,
            "byte_identical": byte_identical,
            "semantic_verification_required": action in ("adapt", "omit"),
        })
    for source_id, source_file in sorted(expected - seen):
        add_error(errors, f"missing resource decision for {source_id}/{source_file}")
    return decisions


def command_validate(args):
    errors = []
    warnings = [FRONTMATTER_NOTICE, SEMANTIC_NOTICE]
    run = normalized_absolute(args.run)
    candidate = normalized_absolute(args.candidate)
    candidate_ready = True
    try:
        reject_reparse_components(candidate)
        if not candidate.is_dir():
            fail(f"candidate directory does not exist: {candidate}")
    except DistillError as exc:
        add_error(errors, exc)
        candidate_ready = False
    try:
        contract = read_json(args.contract, "contract")
        if not isinstance(contract, dict) or contract.get("schema_version") != 1:
            add_error(errors, "contract must be an object with schema_version: 1")
            contract = {}
    except DistillError as exc:
        add_error(errors, exc)
        contract = {}
    sources = load_and_verify_manifest(run, errors)
    if candidate_ready:
        validate_frontmatter(candidate, errors)
        validate_markdown_links(candidate, errors)
    else:
        candidate = None
    mapped_rules, unresolved_drops = validate_rule_contract(
        contract, sources, candidate, errors
    )
    resource_decisions = validate_resources(contract, sources, candidate, errors)
    structural_valid = not errors
    report = {
        "schema_version": 1,
        "structural_valid": structural_valid,
        "preservation_gate": structural_valid and not unresolved_drops,
        "errors": errors,
        "warnings": warnings,
        "mapped_rules": mapped_rules,
        "unresolved_drops": unresolved_drops,
        "semantic_preservation": "not_measured",
        "resource_decisions": resource_decisions,
    }
    write_json_atomic(args.out, report)
    if structural_valid:
        print(f"validation report written: {normalized_absolute(args.out)}")
        return 0
    print(f"validation failed; report written: {normalized_absolute(args.out)}", file=sys.stderr)
    return 1


def require_nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} must be a non-empty string")
    return value


def parse_cases(value):
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        fail("cases JSON must be an object with a cases array")
    case_map = {}
    for index, case in enumerate(value["cases"]):
        if not isinstance(case, dict):
            fail(f"cases[{index}] must be an object")
        case_id = require_nonempty_string(case.get("id"), f"cases[{index}].id")
        stratum = require_nonempty_string(case.get("stratum"), f"cases[{index}].stratum")
        if case_id in case_map:
            fail(f"duplicate case id: {case_id}")
        case_map[case_id] = stratum
    if not case_map:
        fail("cases array must not be empty")
    return case_map


def parse_comparison_input(value, label, case_map):
    if not isinstance(value, dict):
        fail(f"{label} JSON must be an object")
    condition = require_nonempty_string(value.get("condition"), f"{label}.condition")
    executor = value.get("executor")
    if not isinstance(executor, dict):
        fail(f"{label}.executor must be an object")
    require_nonempty_string(executor.get("model"), f"{label}.executor.model")
    if "options" not in executor or not isinstance(executor["options"], dict):
        fail(f"{label}.executor.options must be an object")
    records = value.get("records")
    if not isinstance(records, list):
        fail(f"{label}.records must be an array")
    parsed_records = {}
    for index, record in enumerate(records):
        where = f"{label}.records[{index}]"
        if not isinstance(record, dict):
            fail(f"{where} must be an object")
        case_id = require_nonempty_string(record.get("case_id"), f"{where}.case_id")
        if case_id not in case_map:
            fail(f"{where} names unknown case {case_id!r}")
        trial = record.get("trial")
        if not isinstance(trial, int) or isinstance(trial, bool) or trial < 0:
            fail(f"{where}.trial must be a non-negative integer")
        key = (case_id, trial)
        if key in parsed_records:
            fail(f"duplicate case/trial in {label}: {case_id} trial {trial}")
        checks = record.get("checks")
        if not isinstance(checks, list) or not checks:
            fail(f"{where}.checks must be a non-empty array")
        check_map = {}
        for check_index, check in enumerate(checks):
            check_where = f"{where}.checks[{check_index}]"
            if not isinstance(check, dict):
                fail(f"{check_where} must be an object")
            check_id = require_nonempty_string(check.get("id"), f"{check_where}.id")
            if check_id in check_map:
                fail(f"duplicate check id in {where}: {check_id}")
            if not isinstance(check.get("passed"), bool):
                fail(f"{check_where}.passed must be boolean")
            if not isinstance(check.get("critical"), bool):
                fail(f"{check_where}.critical must be boolean")
            check_map[check_id] = {
                "passed": check["passed"],
                "critical": check["critical"],
            }
        parsed_records[key] = {"checks": check_map, "raw": record}
    return {
        "condition": condition,
        "executor": executor,
        "records": parsed_records,
    }


def validate_record_pair(baseline, candidate, pair):
    base_checks = baseline["records"][pair]["checks"]
    cand_checks = candidate["records"][pair]["checks"]
    if set(base_checks) != set(cand_checks):
        fail(
            f"check IDs differ for {pair[0]} trial {pair[1]}: "
            f"baseline={sorted(base_checks)}, candidate={sorted(cand_checks)}"
        )
    for check_id in base_checks:
        if base_checks[check_id]["critical"] != cand_checks[check_id]["critical"]:
            fail(
                f"critical marker differs for {pair[0]} trial {pair[1]} check {check_id}"
            )


def validate_complete_pairs(case_map, baseline, candidate):
    base_pairs = set(baseline["records"])
    candidate_pairs = set(candidate["records"])
    if base_pairs != candidate_pairs:
        missing_candidate = sorted(base_pairs - candidate_pairs)
        missing_baseline = sorted(candidate_pairs - base_pairs)
        fail(
            "baseline/candidate case-trial pairs do not match; "
            f"missing from candidate={missing_candidate}, missing from baseline={missing_baseline}"
        )
    trials_by_case = {}
    for case_id in case_map:
        trials = sorted(trial for record_case, trial in base_pairs if record_case == case_id)
        if not trials:
            fail(f"no records for case {case_id}")
        if trials != list(range(len(trials))):
            fail(f"trials for case {case_id} must be contiguous starting at 0: {trials}")
        trials_by_case[case_id] = trials
    if baseline["executor"] != candidate["executor"]:
        fail("baseline and candidate executor objects must match")
    for pair in sorted(base_pairs):
        validate_record_pair(baseline, candidate, pair)
    return sorted(base_pairs)


def classify_pair(base_passed, candidate_passed):
    if base_passed == candidate_passed:
        return "ties"
    return "gains" if candidate_passed else "regressions"


def summarize_group(pairs, case_map, baseline, candidate):
    sample_count = len(pairs)
    baseline_full = 0
    candidate_full = 0
    baseline_rule_passed = 0
    candidate_rule_passed = 0
    rule_count = 0
    full_changes = {name: [] for name in ("gains", "regressions", "ties")}
    rule_changes = {name: [] for name in ("gains", "regressions", "ties")}
    critical_failures = []
    for case_id, trial in pairs:
        pair = (case_id, trial)
        base_checks = baseline["records"][pair]["checks"]
        cand_checks = candidate["records"][pair]["checks"]
        base_full = all(check["passed"] for check in base_checks.values())
        cand_full = all(check["passed"] for check in cand_checks.values())
        baseline_full += int(base_full)
        candidate_full += int(cand_full)
        full_changes[classify_pair(base_full, cand_full)].append(
            {"case_id": case_id, "trial": trial}
        )
        base_rule_count = sum(check["passed"] for check in base_checks.values())
        cand_rule_count = sum(check["passed"] for check in cand_checks.values())
        baseline_rule_passed += base_rule_count
        candidate_rule_passed += cand_rule_count
        rule_count += len(base_checks)
        rule_changes[classify_pair(base_rule_count, cand_rule_count)].append(
            {
                "case_id": case_id,
                "trial": trial,
                "baseline_passed": base_rule_count,
                "candidate_passed": cand_rule_count,
                "check_count": len(base_checks),
            }
        )
        for check_id, check in cand_checks.items():
            if check["critical"] and not check["passed"]:
                critical_failures.append({
                    "case_id": case_id,
                    "trial": trial,
                    "check_id": check_id,
                })

    def change_report(changes):
        return {
            name: {"count": len(items), "case_trials": items}
            for name, items in changes.items()
        }

    return {
        "sample_count": sample_count,
        "rule_check_count": rule_count,
        "baseline_full_success_count": baseline_full,
        "candidate_full_success_count": candidate_full,
        "baseline_full_success_rate": baseline_full / sample_count if sample_count else 0.0,
        "candidate_full_success_rate": candidate_full / sample_count if sample_count else 0.0,
        "baseline_rule_pass_count": baseline_rule_passed,
        "candidate_rule_pass_count": candidate_rule_passed,
        "baseline_rule_pass_rate": baseline_rule_passed / rule_count if rule_count else 0.0,
        "candidate_rule_pass_rate": candidate_rule_passed / rule_count if rule_count else 0.0,
        "paired_full_success": change_report(full_changes),
        "paired_rule_passes": change_report(rule_changes),
        "candidate_critical_failures": critical_failures,
    }


def command_compare(args):
    case_map = parse_cases(read_json(args.cases, "cases"))
    baseline = parse_comparison_input(read_json(args.baseline, "baseline"), "baseline", case_map)
    candidate = parse_comparison_input(read_json(args.candidate, "candidate"), "candidate", case_map)
    pairs = validate_complete_pairs(case_map, baseline, candidate)
    strata = {}
    for stratum in dict.fromkeys(case_map.values()):
        stratum_pairs = [pair for pair in pairs if case_map[pair[0]] == stratum]
        strata[stratum] = summarize_group(stratum_pairs, case_map, baseline, candidate)
    overall = summarize_group(pairs, case_map, baseline, candidate)
    observed_gate_passed = all(
        summary["candidate_full_success_rate"] >= summary["baseline_full_success_rate"]
        and summary["candidate_rule_pass_rate"] >= summary["baseline_rule_pass_rate"]
        and not summary["candidate_critical_failures"]
        for summary in strata.values()
    )
    report = {
        "schema_version": 1,
        "baseline_condition": baseline["condition"],
        "candidate_condition": candidate["condition"],
        "executor": baseline["executor"],
        "strata": strata,
        "overall": overall,
        "observed_gate_passed": observed_gate_passed,
        "inference": "descriptive_only",
    }
    write_json_atomic(args.out, report)
    print(f"comparison report written: {normalized_absolute(args.out)}")
    return 0


def target_selection_module():
    # The installed tool may itself be inside the scanned source library.
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        import target_selection
    finally:
        sys.dont_write_bytecode = previous_bytecode
    return target_selection


def write_target_report(out, report):
    output = normalized_absolute(out)
    try:
        destination = output.parent.resolve(strict=True) / output.name
    except (OSError, RuntimeError) as exc:
        fail(f"cannot inspect selection output parent: {exc}")
    scope = report.get("classification")
    inventory = scope["inventory"] if scope else report["inventory"]
    for skill in inventory:
        if is_within(destination, normalized_absolute(skill["path"])):
            fail(f"selection output must stay outside source skill packages: {output}")
    write_json_atomic(output, report)
    print(f"{report.get('schema', 'target selection')} report written: {output}")
    return 0


def command_classify(args):
    module = target_selection_module()
    assignments = read_json(args.assignments, "task classifications") if args.assignments else None
    try:
        report = module.classify_targets(args.root, assignments)
    except ValueError as exc:
        fail(str(exc))
    return write_target_report(args.out, report)


def command_select(args):
    module = target_selection_module()

    assessments = read_json(args.assessments, "target assessments") if args.assessments else None
    usage = read_json(args.usage, "usage and cost estimates") if args.usage else None
    classification = read_json(args.classification, "task classification") if args.classification else None
    try:
        report = module.select_targets(args.root, assessments, usage, args.max_candidates,
                                       classification=classification, categories=args.category)
    except ValueError as exc:
        fail(str(exc))
    return write_target_report(args.out, report)


def make_parser():
    parser = argparse.ArgumentParser(prog="skill_distill.py")
    commands = parser.add_subparsers(dest="command", required=True)

    classify = commands.add_parser("classify", help="classify task families from names/descriptions without reading bodies or resources")
    classify.add_argument("--root", action="append", required=True, metavar="LIBRARY_OR_SKILL")
    classify.add_argument("--assignments", metavar="JSON", help="categories and role/tag assignments produced by the calling agent")
    classify.add_argument("--out", required=True, metavar="REPORT")

    select = commands.add_parser("select", help="select keep/compress/factor/merge targets from a skill library")
    select.add_argument("--root", action="append", required=True, metavar="LIBRARY_OR_SKILL")
    select.add_argument("--assessments", metavar="JSON", help="source-quoted semantic assessments produced by the calling agent")
    select.add_argument("--usage", metavar="JSON", help="optional observed usage and explicit cost forecasts")
    select.add_argument("--classification", metavar="JSON", help="metadata classification report")
    select.add_argument("--category", action="append", help="task category to inspect; repeat for cross-category groups")
    select.add_argument("--max-candidates", type=int, default=30)
    select.add_argument("--out", required=True, metavar="REPORT")

    snapshot = commands.add_parser("snapshot", help="copy source skill packages into a run")
    snapshot.add_argument("--source", action="append", required=True, metavar="ID=PATH")
    snapshot.add_argument("--out", required=True, metavar="RUN")

    validate = commands.add_parser("validate", help="validate candidate mappings and resources")
    validate.add_argument("--run", required=True)
    validate.add_argument("--candidate", required=True)
    validate.add_argument("--contract", required=True)
    validate.add_argument("--out", required=True, metavar="REPORT")

    compare = commands.add_parser("compare", help="compare paired baseline/candidate records")
    compare.add_argument("--cases", required=True)
    compare.add_argument("--baseline", required=True, metavar="BASE")
    compare.add_argument("--candidate", required=True, metavar="CAND")
    compare.add_argument("--out", required=True, metavar="REPORT")
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    try:
        if args.command == "classify":
            return command_classify(args)
        if args.command == "select":
            return command_select(args)
        if args.command == "snapshot":
            return command_snapshot(args)
        if args.command == "validate":
            return command_validate(args)
        if args.command == "compare":
            return command_compare(args)
        fail(f"unknown command: {args.command}")
    except DistillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
