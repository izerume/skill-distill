"""Read-only, standard-library target selection for skill libraries.

select_targets returns JSON data with inventory (stable path-derived IDs, resource
hashes, byte counts and declared invocation policy), diagnostics, retrieval-only
candidates, assessed decisions (keep/compress/factor/merge alternatives), usage,
and plan. plan.selected contains disjoint candidate-build interventions, not
runtime-validated products; keep/deferred/unassessed retain their reasons.
Evidence offsets are Unicode character offsets into UTF-8 source with universal
newlines, as with Python text reads; resource hashes retain the original bytes.
Policy parsing deliberately supports literal boolean declarations only: absent
keys use documented defaults, unsupported/ambiguous YAML remains unknown.
Economics are forecasts in the supplied common unit, never byte/token proxies.
"""

import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import stat


_SKIP = {".git", "node_modules", "__pycache__", "venv", ".venv"}
_KINDS = {"shared_behavior", "shared_reference", "repetition", "boundary", "unique_behavior"}
_ACTIONS = ("keep", "compress", "factor", "merge")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400)


def _absolute(value):
    _require(isinstance(value, (str, os.PathLike)) and isinstance(os.fspath(value), str) and bool(os.fspath(value)),
             "root must be a nonempty path")
    try:
        path = Path(os.path.abspath(value))
        for part in [*reversed(path.parents), path]:
            _require(not _reparse(part), f"explicit root traverses symlink/junction/reparse: {part}")
        _require(path.is_dir(), f"root is not a directory: {path}")
        return path
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"cannot inspect root {value}: {exc}") from exc


def _declarations(text, key):
    # Retain literal declarations even when their values cannot be interpreted.
    return [match.group(1).strip() for match in re.finditer(
        r"^[ \t]*" + re.escape(key) + r"[ \t]*:[ \t]*(.*?)[ \t]*$", text, re.M)]


def _boolean(raw):
    value = raw.split(" #", 1)[0].strip().lower()
    return {"true": True, "false": False}.get(value)


def _description_and_body(text):
    parts = re.split(r"^---[ \t]*$", text, maxsplit=2, flags=re.M)
    if not text.startswith("---") or len(parts) != 3:
        return "", text
    lines = parts[1].splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^description[ \t]*:[ \t]*(.*)$", line)
        if not match:
            continue
        value = match.group(1).strip()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            block = []
            for following in lines[index + 1:]:
                if following.strip() and not following[0].isspace():
                    break
                block.append(following.strip())
            value = ("\n" if value.startswith("|") else " ").join(block).strip()
        return value.strip("\"'"), parts[2]
    return "", parts[2]


def _prose_paragraphs(body):
    # Code and example labels should not dominate a shortlist of behavior text.
    prose, fence = [], None
    for line in body.splitlines():
        match = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)[0]
            fence = None if fence == marker else marker if fence is None else fence
        elif fence is None and not re.match(r"^#{1,6}[ \t]+", line):
            prose.append(line)
    result = []
    for paragraph in re.split(r"\n\s*\n", "\n".join(prose)):
        value = paragraph.strip()
        words = re.findall(r"\w+", value)
        if len(words) >= 3 or (len(words) >= 2 and value.endswith((".", "。", "!", "?"))):
            result.append(value)
    return result


def _idf_cosine_sets(documents):
    frequency = {}
    for words in documents:
        for word in words:
            frequency[word] = frequency.get(word, 0) + 1
    weights = {word: (1 + math.log((len(documents) + 1) / (count + 1))) ** 2
               for word, count in frequency.items()}
    norms = [math.sqrt(sum(weights[word] for word in words)) for words in documents]
    def similarity(i, j):
        denominator = norms[i] * norms[j]
        return sum(weights[word] for word in documents[i] & documents[j]) / denominator if denominator else 0
    return similarity


def _policy(texts, complete):
    skill = texts.get("SKILL.md", "")
    front = ""
    if skill.startswith("---\n") or skill.startswith("---\r\n"):
        parts = re.split(r"^---\s*$", skill, maxsplit=2, flags=re.M)
        front = parts[1] if len(parts) == 3 else skill
    front_unknown = bool(front) and (
        len(re.split(r"^---\s*$", skill, maxsplit=2, flags=re.M)) != 3
        or bool(re.search(r"[&*]|^\s*<<\s*:", front, re.M)))
    disabled = _declarations(front, "disable-model-invocation")
    yaml = texts.get("agents/openai.yaml")
    implicit = []
    yaml_unknown = False
    if yaml is not None:
        # Indented policy mapping and policy.allow_implicit_invocation are
        # supported. Inline maps/anchors/duplicate policy maps are not guessed.
        implicit = _declarations(yaml, "policy.allow_implicit_invocation")
        blocks = list(re.finditer(r"^policy[ \t]*:[ \t]*(.*)$", yaml, re.M))
        if len(blocks) > 1:
            yaml_unknown = True
        for block in blocks:
            if block.group(1).strip().split("#", 1)[0].strip():
                yaml_unknown = True
            tail = yaml[block.end():]
            lines = []
            for line in tail.splitlines():
                if line.strip() and not line[0].isspace() and not line.startswith("#"):
                    break
                lines.append(line)
            implicit.extend(_declarations("\n".join(lines), "allow_implicit_invocation"))
        # A key outside a recognized mapping is not assumed to be policy.
        if len(_declarations(yaml, "allow_implicit_invocation")) != len(implicit) - len(
                _declarations(yaml, "policy.allow_implicit_invocation")):
            yaml_unknown = True
        if re.search(r"[&*]|^\s*<<\s*:", yaml, re.M):
            yaml_unknown = True
    def interpret(values, default):
        if not values:
            return default, "default"
        parsed = [_boolean(value) for value in values]
        if None in parsed:
            return None, "unknown"
        if len(set(parsed)) > 1:
            return None, "conflicting"
        if len(values) > 1:
            return None, "ambiguous"
        return parsed[0], "declared"
    disable, ds = interpret(disabled, False)
    allow, als = interpret(implicit, True)
    if front_unknown or ("disable-model-invocation" in front and not disabled):
        disable, ds = None, "unknown"
    if yaml_unknown or not complete:
        allow, als = None, "unknown"
    known = disable is not None and allow is not None
    return {"disable_model_invocation": {"declarations": disabled, "value": disable, "status": ds},
            "allow_implicit_invocation": {"declarations": implicit, "value": allow, "status": als},
            "known": known, "signature": [disable, allow] if known else None}


def _skill_id(path):
    return "skill-" + hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest()[:20]


def _metadata(path):
    # Stop at the frontmatter boundary; neither the body nor resources are read.
    lines = []
    # Text buffering can decode body bytes even when only the header is wanted.
    with (path / "SKILL.md").open("rb") as stream:
        def header_line():
            line = bytearray()
            while True:
                char = stream.read(1)
                if not char:
                    break
                line.extend(char)
                if char in (b"\r", b"\n"):
                    if char == b"\r" and stream.peek(1)[:1] == b"\n":
                        line.extend(stream.read(1))
                    break
            return bytes(line)
        first = header_line().decode("utf-8-sig")
        if first.strip() == "---":
            lines.append(first)
            while True:
                raw = header_line()
                if not raw:
                    raise ValueError(f"unclosed SKILL.md frontmatter: {path}")
                line = raw.decode("utf-8")
                lines.append(line)
                if line.strip() == "---":
                    break
    front = "".join(lines).replace("\r\n", "\n").replace("\r", "\n")
    description, _ = _description_and_body(front)
    header = "".join(lines[1:-1]).replace("\r\n", "\n").replace("\r", "\n")
    names = _declarations(header, "name")
    name = names[0].strip("\"'") if names else path.name
    digest = hashlib.sha256(json.dumps([name, description], ensure_ascii=False).encode()).hexdigest()
    return {"id": _skill_id(path), "path": str(path), "name": name,
            "description": description, "metadata_sha256": digest}


def _scan(roots, metadata_only=False):
    diagnostics, packages, seen_dirs = [], {}, set()
    def diagnostic(path, reason):
        diagnostics.append({"path": str(path), "reason": reason})
    def children(path):
        try:
            return sorted(path.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            diagnostic(path, f"unreadable directory: {exc}")
            return None
    def package(path):
        if metadata_only:
            try:
                packages[str(path)] = (_metadata(path), {})
            except (OSError, UnicodeError, ValueError) as exc:
                raise ValueError(f"cannot read skill metadata {path}: {exc}") from exc
            return
        files, texts, complete = [], {}, True
        def walk(folder):
            nonlocal complete
            entries = children(folder)
            if entries is None:
                complete = False
                return
            for entry in entries:
                try:
                    if _reparse(entry):
                        diagnostic(entry, "skipped symlink/junction/reparse path")
                        complete = False
                    elif entry.is_dir():
                        if entry.name in _SKIP:
                            diagnostic(entry, "skipped excluded directory")
                        else:
                            walk(entry)
                    elif entry.is_file():
                        data = entry.read_bytes()
                        relative = entry.relative_to(path).as_posix()
                        files.append({"file": relative, "bytes": len(data),
                                      "sha256": hashlib.sha256(data).hexdigest()})
                        try:
                            texts[relative] = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
                        except UnicodeError:
                            pass
                    else:
                        diagnostic(entry, "skipped non-regular file")
                        complete = False
                except OSError as exc:
                    diagnostic(entry, f"unreadable package resource: {exc}")
                    complete = False
        walk(path)
        _require("SKILL.md" in texts, f"SKILL.md must be readable UTF-8: {path}")
        files.sort(key=lambda item: item["file"])
        digest = hashlib.sha256()
        for item in files:
            digest.update(item["file"].encode())
            digest.update(b"\0" + item["sha256"].encode() + b"\n")
        skill_text = texts["SKILL.md"]
        description, _ = _description_and_body(skill_text)
        names = _declarations(skill_text.split("---", 2)[1], "name") if skill_text.startswith("---") and skill_text.count("---") >= 2 else []
        item = {"id": _skill_id(path),
                "path": str(path), "name": names[0].strip("\"'") if names else path.name,
                "description": description,
                "files": files, "all_bytes": sum(f["bytes"] for f in files),
                "entrypoint_bytes": next(f["bytes"] for f in files if f["file"] == "SKILL.md"),
                "inventory_complete": complete, "package_sha256": digest.hexdigest() if complete else None,
                "invocation_policy": _policy(texts, complete and not any(
                    f["file"] == "agents/openai.yaml" and f["file"] not in texts for f in files)),
                "exact_duplicate_of": None}
        packages[str(path)] = (item, texts)
    def descend(path):
        normalized = os.path.normcase(str(path))
        if normalized in seen_dirs:
            return
        seen_dirs.add(normalized)
        entries = children(path)
        if entries is None:
            return
        for entry in entries:
            if entry.name == "SKILL.md":
                try:
                    if _reparse(entry):
                        diagnostic(entry, "skipped symlink/junction/reparse entrypoint")
                        return
                    _require(entry.is_file(), f"SKILL.md is not a file: {entry}")
                except OSError as exc:
                    raise ValueError(f"cannot inspect {entry}: {exc}") from exc
                package(path)
                return
        for entry in entries:
            try:
                if _reparse(entry):
                    diagnostic(entry, "skipped symlink/junction/reparse path")
                elif entry.is_dir():
                    if entry.name in _SKIP:
                        diagnostic(entry, "skipped excluded directory")
                    else:
                        descend(entry)
            except OSError as exc:
                diagnostic(entry, f"cannot inspect path: {exc}")
    # Parents first: explicitly supplied nested example roots do not bypass the
    # package boundary established by another supplied root.
    for root in sorted(set(roots), key=lambda p: (len(p.parts), str(p))):
        if any(root == Path(p) or Path(p) in root.parents for p in packages):
            continue
        try:
            list(root.iterdir())
        except OSError as exc:
            raise ValueError(f"cannot read explicit root {root}: {exc}") from exc
        descend(root)
    ordered = sorted(packages.values(), key=lambda pair: pair[0]["path"])
    hashes = {}
    for item, _ in ordered:
        digest = item.get("package_sha256")
        if digest is not None:
            item["exact_duplicate_of"] = hashes.get(digest)
            hashes.setdefault(digest, item["id"])
    return ordered, diagnostics


def classify_targets(roots, assignments=None):
    """Read names/descriptions and validate agent-supplied task classifications.

    No model is called here. Without assignments, return a metadata review queue.
    Families may contain complementary roles and platform branches; membership
    establishes neither redundancy nor a decision to merge.
    """
    _require(isinstance(roots, list) and roots, "roots must be a nonempty list")
    scanned, diagnostics = _scan([_absolute(root) for root in roots], metadata_only=True)
    inventory = [item for item, _ in scanned]
    by_id = {item["id"]: item for item in inventory}
    by_path = {os.path.normcase(item["path"]): item["id"] for item in inventory}
    raw = assignments if assignments is not None else {}
    _require(isinstance(raw, dict), "classification must be an object")
    if "inventory" in raw:
        previous = raw["inventory"]
        _require(isinstance(previous, list) and all(isinstance(i, dict) for i in previous),
                 "classification inventory must be a list of objects")
        _require(len(previous) == len(by_id) and {i.get("id") for i in previous} == set(by_id),
                 "classification inventory does not match current roots")
        _require(all(i.get("metadata_sha256") == by_id[i["id"]]["metadata_sha256"] for i in previous),
                 "classification names/descriptions changed; classify current metadata")
    categories, rows = raw.get("categories", []), raw.get("assignments", [])
    _require(isinstance(categories, list) and isinstance(rows, list),
             "classification categories/assignments must be lists")
    category_map = {}
    for category in categories:
        _require(isinstance(category, dict), "category must be an object")
        key, name = category.get("id"), category.get("name")
        _require(isinstance(key, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", key),
                 "category id must use lowercase letters, digits and hyphens")
        _require(key not in category_map, f"duplicate category: {key}")
        _require(isinstance(name, str) and name.strip(), "category name must be nonempty")
        category_map[key] = {"id": key, "name": name}
    normalized = {}
    for row in rows:
        _require(isinstance(row, dict), "classification assignment must be an object")
        ref = row.get("skill")
        _require(isinstance(ref, str), "assignment skill must be an inventory ID or absolute path")
        key = ref if ref in by_id else by_path.get(os.path.normcase(os.path.abspath(ref))) if os.path.isabs(ref) else None
        _require(key is not None, f"unknown or ambiguous classification skill: {ref!r}; use ID or absolute path")
        _require(key not in normalized, f"duplicate classification assignment: {key}")
        primary = row.get("category")
        _require(isinstance(primary, str) and primary in category_map, f"unknown category: {primary}")
        related, roles, tags = row.get("related_categories", []), row.get("roles", []), row.get("tags", [])
        for label, values in (("related_categories", related), ("roles", roles), ("tags", tags)):
            _require(isinstance(values, list) and all(isinstance(v, str) and v.strip() for v in values),
                     f"{label} must be a list of nonempty strings")
            _require(len(values) == len(set(values)), f"duplicate {label}")
        _require(all(c in category_map and c != primary for c in related), "invalid related category")
        _require(bool(roles) and set(roles) <= {"workflow", "guidance", "tool", "reference", "router"},
                 "roles must contain workflow/guidance/tool/reference/router")
        reason = row.get("reason")
        _require(isinstance(reason, str) and reason.strip(), "classification reason must be nonempty")
        normalized[key] = {"skill": key, "category": primary, "related_categories": sorted(related),
                           "roles": sorted(roles), "tags": sorted(tags), "reason": reason}
    groups = []
    for key in sorted(category_map):
        members = sorted(s for s, row in normalized.items()
                         if key == row["category"] or key in row["related_categories"])
        if len(members) >= 2:
            groups.append({"category": key, "members": members, "status": "classification_only"})
    unclassified = [i["id"] for i in inventory if i["id"] not in normalized]
    return {"schema": "skill-classification/v1", "inventory": inventory, "diagnostics": diagnostics,
            "categories": [category_map[k] for k in sorted(category_map)],
            "assignments": [normalized[k] for k in sorted(normalized)], "candidate_groups": groups,
            "coverage": {"total": len(inventory), "classified": len(normalized), "unclassified": unclassified},
            "status": "classified" if inventory and not unclassified else "needs_classification",
            "basis": "names_and_descriptions_only", "semantic_author": "calling_agent",
            "next": "choose task categories before detailed source assessment; category count is not a merge target"}


def _number(value, label, integer=False):
    _require(type(value) in ((int,) if integer else (int, float)), f"{label} must be a nonnegative {'integer' if integer else 'number'}")
    try:
        valid = value >= 0 and math.isfinite(value)
    except OverflowError:
        valid = False
    _require(valid, f"{label} must be finite and nonnegative")
    return value


def select_targets(roots, assessments=None, usage=None, max_candidates=30,
                   classification=None, categories=None):
    """Select a disjoint library plan without writes or execution.

    roots: nonempty list of package/library paths. References in assessments and
    usage must be inventory IDs or absolute package paths (names are rejected).
    Invalid/stale evidence, schema violations and unreadable explicit roots
    raise ValueError. Missing economics is represented by null, never zero.
    Decisions contain all four alternatives with eligibility/reasons/economics;
    evidence remains agent judgment with validated source spans and source hashes.
    Plan objective maximizes known positive net savings, distinct packages
    covered, evidence-content coverage, then favors lower action complexity.
    Compression can consolidate repetition or disclose source-backed optional
    branches. Partial workflow fusion requires explicit source-preserving routes.
    A bounded deterministic set-packing search reports whether it proved this
    objective optimal; it does not assert optimal semantic or runtime quality.
    """
    _require(isinstance(roots, list) and roots, "roots must be a nonempty list")
    _number(max_candidates, "max_candidates", integer=True)
    scope = None
    scan_roots = [_absolute(root) for root in roots]
    if classification is not None:
        _require(isinstance(categories, list) and categories, "choose at least one category with classification")
        scope = classify_targets(roots, classification)
        known = {c["id"] for c in scope["categories"]}
        _require(all(isinstance(c, str) and c in known for c in categories), "unknown selected category")
        _require(len(categories) == len(set(categories)), "duplicate selected category")
        chosen = set(categories)
        selected = {r["skill"] for r in scope["assignments"]
                    if chosen & {r["category"], *r["related_categories"]}}
        _require(bool(selected), "selected categories have no classified skills")
        scan_roots = [Path(i["path"]) for i in scope["inventory"] if i["id"] in selected]
        scope["selected_categories"] = sorted(chosen)
        scope["deferred"] = [i["id"] for i in scope["inventory"] if i["id"] not in selected]
    else:
        _require(categories is None, "categories require classification")
    scanned, diagnostics = _scan(scan_roots)
    inventory = [pair[0] for pair in scanned]
    by_id = {item["id"]: (item, texts) for item, texts in scanned}
    by_path = {os.path.normcase(item["path"]): item["id"] for item in inventory}
    def resolve(ref):
        _require(isinstance(ref, str), "skill reference must be an inventory ID or absolute path")
        if ref in by_id:
            return ref
        if os.path.isabs(ref):
            key = os.path.normcase(os.path.abspath(ref))
            if key in by_path:
                return by_path[key]
        raise ValueError(f"unknown or ambiguous skill reference: {ref!r}; use inventory ID or absolute package path")
    def members(raw):
        _require(isinstance(raw, list) and raw, "members/skills must be a nonempty list")
        result = [resolve(ref) for ref in raw]
        _require(len(result) == len(set(result)), "duplicate skill in members/skills")
        return sorted(result)
    observed, estimates, unit = [], {}, None
    if usage is not None:
        _require(isinstance(usage, dict), "usage must be an object")
        events, raw_estimates = usage.get("events", []), usage.get("estimates", [])
        _require(isinstance(events, list) and isinstance(raw_estimates, list), "usage events/estimates must be lists")
        unit = usage.get("unit")
        _require(unit is None or unit in ("tokens", "usd", "milliseconds"), "invalid usage unit")
        _require(not raw_estimates or unit is not None, "cost estimates require a common unit")
        for event in events:
            _require(isinstance(event, dict), "usage event must be an object")
            observed.append({"skills": members(event.get("skills")), "count": _number(event.get("count"), "count", True)})
        for raw in raw_estimates:
            _require(isinstance(raw, dict), "estimate must be an object")
            group = members(raw.get("members"))
            action = raw.get("action")
            _require(action in _ACTIONS[1:], "invalid estimate action")
            fields = ("baseline_per_run", "candidate_per_run", "expected_runs", "build_cost", "evaluation_cost", "maintenance_cost")
            costs = {key: _number(raw.get(key), key) for key in fields}
            try:
                net = (costs["baseline_per_run"] - costs["candidate_per_run"]) * costs["expected_runs"] - costs["build_cost"] - costs["evaluation_cost"] - costs["maintenance_cost"]
                _require(math.isfinite(net), "net expected savings overflow")
            except OverflowError as exc:
                raise ValueError("net expected savings overflow") from exc
            key = (tuple(group), action)
            _require(key not in estimates, "duplicate estimate for members/action")
            estimates[key] = {"status": "estimate", "unit": unit, **costs, "net_expected_savings": net,
                              "expected_runs_source": "explicit forecast"}
    candidates = []
    prose_sets, metadata_sets = [], []
    for item, texts in scanned:
        _, body = _description_and_body(texts["SKILL.md"])
        paragraphs = _prose_paragraphs(body)
        prose_sets.append(set(re.findall(r"\w+", "\n".join(paragraphs).lower())))
        metadata_sets.append(set(re.findall(r"\w+", (item["name"] + " " + item["description"]).lower())))
        repeated = len(paragraphs) - len(set(paragraphs))
        if repeated:
            duplicate_bytes = sum(len(p.encode("utf-8")) for p in paragraphs) - sum(len(p.encode("utf-8")) for p in set(paragraphs))
            candidates.append({"members": [item["id"]], "status": "retrieval_only",
                               "lexical_overlap": None, "duplicate_paragraphs": repeated,
                               "shared_resource_hashes": 0, "semantic_equivalence": "unassessed",
                               "score": duplicate_bytes / max(1, len(body.encode("utf-8")))})
    metadata_similarity = _idf_cosine_sets(metadata_sets)
    body_similarity = _idf_cosine_sets(prose_sets)
    for (i, (a, at)), (j, (b, bt)) in itertools.combinations(enumerate(scanned), 2):
        same = a["package_sha256"] is not None and a["package_sha256"] == b["package_sha256"]
        lexical = body_similarity(i, j)
        metadata = metadata_similarity(i, j)
        paragraphs_a = set(_prose_paragraphs(_description_and_body(at["SKILL.md"])[1]))
        paragraphs_b = set(_prose_paragraphs(_description_and_body(bt["SKILL.md"])[1]))
        def reference_hashes(item):
            return {f["sha256"] for f in item["files"] if f["file"].startswith(("references/", "reference/", "scripts/"))}
        hashes_a, hashes_b = reference_hashes(a), reference_hashes(b)
        shared_resources = len(hashes_a & hashes_b)
        if same or lexical or metadata or shared_resources:
            candidates.append({"members": sorted([a["id"], b["id"]]), "status": "exact_duplicate" if same else "retrieval_only",
                               "lexical_overlap": lexical, "metadata_overlap": metadata, "duplicate_paragraphs": len(paragraphs_a & paragraphs_b),
                               "shared_resource_hashes": shared_resources,
                               "semantic_equivalence": "unassessed", "score": .6 * metadata + .3 * lexical + .1 * shared_resources / (1 + shared_resources)})
    candidates.sort(key=lambda c: (-c["score"], c["members"]))
    total_candidates = len(candidates)
    candidates = candidates[:max_candidates]
    groups = []
    if assessments is not None:
        _require(isinstance(assessments, dict) and isinstance(assessments.get("groups"), list), "assessments must contain a groups list")
        groups = assessments["groups"]
    decisions, proposals, assessed, single_reviewed = [], [], set(), set()
    for index, raw in enumerate(groups):
        _require(isinstance(raw, dict), "assessment group must be an object")
        group = members(raw.get("members"))
        for key, values in (("task_overlap", ("same", "partial", "different")),
                            ("behavior_overlap", ("high", "partial", "none")),
                            ("workflow", ("compatible", "branchable", "complementary", "conflicting", "unrelated"))):
            _require(raw.get(key) in values, f"invalid assessment {key}")
        for key in ("shared_reference", "internal_redundancy"):
            _require(type(raw.get(key)) is bool, f"{key} must be boolean")
        _require(isinstance(raw.get("reason"), str) and raw["reason"].strip(), "assessment reason must be nonempty")
        _require(isinstance(raw.get("evidence"), list), "assessment evidence must be a list")
        evidence, spans = [], set()
        for claim in raw["evidence"]:
            _require(isinstance(claim, dict), "evidence must be an object")
            skill = resolve(claim.get("skill"))
            _require(skill in group, "evidence skill must belong to group")
            file, quote = claim.get("file"), claim.get("quote")
            _require(isinstance(file, str) and file and "\\" not in file and ":" not in file and all(p not in ("", ".", "..") for p in file.split("/")), "evidence file must be a safe relative path")
            _require(isinstance(quote, str) and quote.strip(), "evidence quote must be nonempty")
            _require(isinstance(claim.get("kind"), str) and claim["kind"] in _KINDS, "invalid evidence kind")
            occurrence = _number(claim.get("occurrence", 0), "occurrence", True)
            item, texts = by_id[skill]
            _require(file in texts, f"evidence file unavailable or not UTF-8: {skill}/{file}")
            source = texts[file]
            offsets, start = [], 0
            while True:
                found = source.find(quote, start)
                if found < 0:
                    break
                offsets.append(found)
                start = found + 1
            _require(occurrence < len(offsets), f"stale or invalid quote occurrence: {skill}/{file}")
            start = offsets[occurrence]
            span = (skill, file, start, start + len(quote), claim["kind"])
            if span in spans:
                continue
            spans.add(span)
            evidence.append({"skill": skill, "file": file, "quote": quote, "kind": claim["kind"],
                             "occurrence": occurrence, "start": start, "end": start + len(quote),
                             "source_sha256": next(f["sha256"] for f in item["files"] if f["file"] == file),
                             "provenance": "agent judgment; source quote verified"})
        def covers(kind):
            return {e["skill"] for e in evidence if e["kind"] == kind} == set(group)
        evidenced_members = {e["skill"] for e in evidence}
        assessed.update(evidenced_members)
        if len(group) == 1 and evidenced_members == set(group):
            single_reviewed.update(group)
        composition = raw.get("composition_plan")
        if composition is not None:
            _require(isinstance(composition, dict), "composition_plan must be an object")
            _require(composition.get("strategy") in ("branches", "pipeline"), "composition strategy must be branches or pipeline")
            for key in ("shared_context", "ordering"):
                _require(isinstance(composition.get(key), str) and composition[key].strip(), f"composition {key} must be nonempty")
            routes = composition.get("routes")
            _require(isinstance(routes, list) and routes, "composition routes must cover every source")
            normalized_routes = []
            for route in routes:
                _require(isinstance(route, dict), "composition route must be an object")
                skill = resolve(route.get("skill"))
                _require(skill in group, "composition route must name a group member")
                for key in ("when", "preserve"):
                    _require(isinstance(route.get(key), str) and route[key].strip(), f"composition route {key} must be nonempty")
                normalized_routes.append({"skill": skill, "when": route["when"], "preserve": route["preserve"]})
            _require(len(normalized_routes) == len(group) and {r["skill"] for r in normalized_routes} == set(group), "composition routes must cover every source exactly once")
            cases = composition.get("checks")
            _require(isinstance(cases, list) and cases and all(isinstance(c, str) and c.strip() for c in cases), "composition checks must be nonempty case descriptions")
            composition = {"strategy": composition["strategy"], "shared_context": composition["shared_context"],
                           "routes": normalized_routes, "ordering": composition["ordering"], "checks": cases}
        disclosure = raw.get("disclosure_plan")
        disclosed_spans = set()
        if disclosure is not None:
            _require(len(group) == 1 and isinstance(disclosure, dict), "disclosure_plan requires a single source")
            _require(isinstance(disclosure.get("keep_core"), str) and disclosure["keep_core"].strip(), "disclosure keep_core must preserve common instructions")
            branches = disclosure.get("branches")
            _require(isinstance(branches, list) and branches, "disclosure branches must be nonempty")
            normalized_branches = []
            for branch in branches:
                _require(isinstance(branch, dict), "disclosure branch must be an object")
                for key in ("file", "quote", "when", "preserve"):
                    _require(isinstance(branch.get(key), str) and branch[key].strip(), f"disclosure branch {key} must be nonempty")
                occurrence = _number(branch.get("occurrence", 0), "disclosure occurrence", True)
                matching = [e for e in evidence if e["skill"] == group[0] and e["file"] == branch["file"]
                            and e["quote"] == branch["quote"] and e["occurrence"] == occurrence
                            and e["kind"] in ("unique_behavior", "boundary", "repetition")]
                _require(matching, "disclosure branch must reference its verified source evidence")
                anchor = matching[0]
                disclosed_spans.add((anchor["skill"], anchor["file"], anchor["start"], anchor["end"]))
                normalized_branches.append({"file": branch["file"], "quote": branch["quote"], "occurrence": occurrence,
                                            "when": branch["when"], "preserve": branch["preserve"]})
            cases = disclosure.get("checks")
            _require(isinstance(cases, list) and cases and all(isinstance(c, str) and c.strip() for c in cases), "disclosure checks must be nonempty case descriptions")
            disclosure = {"keep_core": disclosure["keep_core"], "branches": normalized_branches, "checks": cases}
        unique_covered = {e["skill"] for e in evidence if e["kind"] in ("unique_behavior", "boundary")} == set(group)
        directly_overlapping = raw["behavior_overlap"] == "high" and raw["workflow"] in ("compatible", "branchable")
        planned_workflow = (composition is not None and unique_covered and raw["behavior_overlap"] in ("high", "partial")
                            and raw["workflow"] in ("compatible", "branchable", "complementary"))
        repetitions = [e for e in evidence if e["kind"] == "repetition"]
        distinct_repetition = any(
            (a["file"] != b["file"] or a["end"] <= b["start"] or b["end"] <= a["start"])
            for a, b in itertools.combinations(repetitions, 2))
        policies = [by_id[s][0]["invocation_policy"] for s in group]
        policy_match = all(p["known"] for p in policies) and all(p["signature"] == policies[0]["signature"] for p in policies)
        digests = [by_id[s][0]["package_sha256"] for s in group]
        duplicate = len([d for d in digests if d is not None]) != len(set(d for d in digests if d is not None))
        checks = {
            "keep": [],
            "compress": ([] if len(group) == 1 else ["compression requires one entrypoint"])
                        + ([] if (raw["internal_redundancy"] and distinct_repetition) or disclosure is not None
                           else ["requires distinct redundant spans or a source-backed conditional disclosure plan"]),
            "factor": ([] if len(group) >= 2 else ["factoring requires multiple entrypoints"]) + ([] if raw["shared_reference"] and covers("shared_reference") else ["requires substantive shared-reference judgment and source evidence for every member"]),
            "merge": ([] if len(group) >= 2 else ["merging requires multiple entrypoints"])
                     + ([] if raw["task_overlap"] in ("same", "partial") else ["task scopes do not overlap"])
                     + ([] if directly_overlapping or planned_workflow else ["requires strong overlap or a composition plan with shared context, preserved source routes and unique/boundary evidence"])
                     + ([] if covers("shared_behavior") else ["requires shared-behavior source evidence for every member"])
                     + ([] if policy_match else ["invocation boundaries differ or are unknown"]),
        }
        if duplicate:
            for action in _ACTIONS[1:]:
                checks[action].append("exact package duplicates are aliases, not a semantic fusion opportunity")
        alternatives = []
        for action in _ACTIONS:
            cost = estimates.get((tuple(group), action))
            eligible = not checks[action]
            positive = cost is None or cost["net_expected_savings"] > 0
            reasons = checks[action] or [
                {"keep": "retains existing scope, entrypoints and invocation policy; successful baseline",
                 "compress": ("conditional branch material can be disclosed while preserving its full behavior and common core"
                              if disclosure is not None else "distinct repeated behavior can be compressed while preserving scope and modes"),
                 "factor": "shared references can be extracted while preserving separate entrypoints, scopes and policies",
                 "merge": "strong shared behavior supports a candidate with all unique branches and boundaries preserved"}[action]]
            if action != "keep" and not positive:
                reasons = reasons + ["nonpositive net expected savings excludes selection"]
            alternatives.append({"action": action, "eligible": eligible, "selection_eligible": eligible and positive,
                                 "reasons": reasons, "economics": cost if cost is not None else {"status": "unknown", "unit": unit, "net_expected_savings": None}})
        decision = {"id": f"group-{index + 1}", "members": group, "facts": {k: raw[k] for k in ("task_overlap", "behavior_overlap", "workflow", "shared_reference", "internal_redundancy")},
                    "reason": raw["reason"], "evidence": evidence, "invocation_policies": {s: by_id[s][0]["invocation_policy"] for s in group},
                    "alternatives": alternatives, "composition_plan": composition, "disclosure_plan": disclosure,
                    "selected_action": "keep", "status": "keep" if evidenced_members == set(group) else "needs_assessment"}
        decisions.append(decision)
        def regions(kind, selected_spans=None):
            buckets = {}
            for e in evidence:
                if (e["kind"] == kind or (selected_spans is not None and
                        (e["skill"], e["file"], e["start"], e["end"]) in selected_spans)):
                    buckets.setdefault((e["skill"], e["file"]), []).append((e["start"], e["end"]))
            result = []
            for (skill, file), intervals in sorted(buckets.items()):
                merged = []
                for start, end in sorted(intervals):
                    if merged and start <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                    else:
                        merged.append((start, end))
                text = by_id[skill][1][file]
                result.extend({"skill": skill, "file": file, "start": start, "end": end,
                               "bytes": len(text[start:end].encode("utf-8"))} for start, end in merged)
            return result
        for alternative in alternatives[1:]:
            if alternative["selection_eligible"]:
                cost = alternative["economics"]
                kind = {"factor": "shared_reference", "merge": "shared_behavior", "compress": "repetition"}[alternative["action"]]
                if alternative["action"] == "compress" and not (raw["internal_redundancy"] and distinct_repetition):
                    kind = None
                footprint = regions(kind, disclosed_spans if alternative["action"] == "compress" else None)
                proposals.append({"group": decision["id"], "members": group, "action": alternative["action"],
                                  "economics": cost, "evidence_regions": footprint,
                                  "evidence_coverage_bytes": sum(r["bytes"] for r in footprint),
                                  "composition_plan": composition if alternative["action"] == "merge" else None,
                                  "disclosure_plan": disclosure if alternative["action"] == "compress" else None,
                                  "preservation": "preserve all declared scopes, modes, unique branches and invocation policies; runtime validation required"})
    # Reference extractions lock source regions; a full rewrite locks its members.
    complexity = {"compress": 1, "factor": 2, "merge": 3}
    def weight(p):
        value = p["economics"]["net_expected_savings"]
        return (value if value is not None else 0, len(p["members"]), p["evidence_coverage_bytes"], -complexity[p["action"]])
    def conflicts(a, b):
        if a["group"] == b["group"]:
            return True
        common = set(a["members"]) & set(b["members"])
        if not common:
            return False
        if a["action"] != "factor" or b["action"] != "factor":
            return True
        return any(x["skill"] == y["skill"] and x["file"] == y["file"]
                   and x["start"] < y["end"] and y["start"] < x["end"]
                   for x in a["evidence_regions"] for y in b["evidence_regions"])
    def add_score(score, covered, proposal):
        now = covered | set(proposal["members"])
        w = weight(proposal)
        return (score[0] + w[0], len(now), score[2] + w[2], score[3] + w[3]), now
    proposals.sort(key=lambda p: (tuple(-v for v in weight(p)), p["members"], p["group"], p["action"]))
    best, best_score, covered = [], (0, 0, 0, 0), set()
    for proposal in proposals:
        if not any(conflicts(proposal, existing) for existing in best):
            best.append(proposal)
            best_score, covered = add_score(best_score, covered, proposal)
    nodes, exhausted = 0, False
    options = proposals
    masks = [sum(1 << j for j, other in enumerate(options) if i == j or conflicts(p, other))
             for i, p in enumerate(options)]
    def search(index, blocked, selected, score, covered):
        nonlocal nodes, exhausted, best, best_score
        nodes += 1
        if nodes > 100000:
            exhausted = True
            return
        if score > best_score:
            best, best_score = list(selected), score
        if index == len(options):
            return
        remaining = [p for j, p in enumerate(options[index:], index) if not blocked & (1 << j)]
        remaining_weights = [weight(p) for p in remaining]
        possible_members = covered | {s for p in remaining for s in p["members"]}
        upper = (score[0] + sum(w[0] for w in remaining_weights), len(possible_members),
                 score[2] + sum(w[2] for w in remaining_weights), score[3])
        if upper <= best_score:
            return
        proposal = options[index]
        if not blocked & (1 << index):
            next_score, next_members = add_score(score, covered, proposal)
            search(index + 1, blocked | masks[index], selected + [proposal], next_score, next_members)
        if not exhausted:
            search(index + 1, blocked, selected, score, covered)
    # Avoid recursion limits for very large externally supplied assessment sets.
    if len(options) <= 200:
        search(0, 0, [], (0, 0, 0, 0), set())
    else:
        exhausted = True
    selected_ids = {p["group"]: p for p in best}
    occupied = {s for p in best for s in p["members"]}
    deferred = []
    eligible_groups = {}
    for decision in decisions:
        eligible = [p for p in proposals if p["group"] == decision["id"]]
        if eligible:
            for skill in decision["members"]:
                eligible_groups.setdefault(skill, []).append(decision["id"])
        if decision["id"] in selected_ids:
            decision["selected_action"] = selected_ids[decision["id"]]["action"]
            decision["status"] = "selected"
        elif eligible:
            conflict_groups = sorted({p["group"] for p in best if any(conflicts(option, p) for option in eligible)})
            decision["selected_action"] = None
            decision["status"] = "deferred"
            deferred.append({"group": decision["id"], "reason": "eligible material conflicts with selected content or was deferred by the bounded allocation",
                             "conflicts_with": conflict_groups})
    keep = [{"skill": item["id"], "reason": "no justified intervention in the current evidenced assessment scope"}
            for item in inventory if item["id"] in assessed and item["id"] not in occupied and item["id"] not in eligible_groups]
    pending = [{"skill": item["id"], "groups": eligible_groups[item["id"]], "reason": "eligible intervention exists but is not selected"}
               for item in inventory if item["id"] not in occupied and item["id"] in eligible_groups]
    return {"inventory": inventory, "diagnostics": diagnostics, "candidates": candidates,
            "classification": scope,
            "retrieval": {"status": "retrieval_only", "total_pairs": total_candidates, "returned": len(candidates), "max_candidates": max_candidates},
            "decisions": decisions, "usage": {"events": observed, "unit": unit, "estimates": [{"members": list(key[0]), "action": key[1], **value} for key, value in estimates.items()], "observed_counts_are_forecasts": False},
            "plan": {"selected": best, "keep": keep, "pending": pending, "deferred": deferred,
                     "unassessed": [item["id"] for item in inventory if item["id"] not in assessed],
                     "coverage": {"single_skill_reviewed": sorted(single_reviewed),
                                  "single_skill_unassessed": [i["id"] for i in inventory if i["id"] not in single_reviewed]},
                     "selection_method": "bounded content-aware allocation", "optimal_for_objective": not exhausted,
                     "search_nodes": nodes, "objective": "maximize known positive net savings, then distinct package coverage, then source-evidence content coverage, then minimize action complexity",
                     "status": "candidate-build selection; runtime validation not performed"}}
