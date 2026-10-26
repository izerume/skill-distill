import importlib.util
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / "skills/skill-distill/scripts/target_selection.py"
SPEC = importlib.util.spec_from_file_location("target_selection", MODULE)
target_selection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target_selection)
select_targets = target_selection.select_targets
classify_targets = target_selection.classify_targets


class TargetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def skill(self, name, body="Shared behavior.\n\nShared reference.", parent=None,
              policy="", files=None):
        path = (parent or self.root) / name
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(
            f"---\nname: {name}\n{policy}---\n# {name}\n{body}\n", encoding="utf-8")
        for relative, content in (files or {}).items():
            file = path / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def group(self, paths, kind="shared_behavior", **updates):
        quote = {"shared_behavior": "Shared behavior.", "shared_reference": "Shared reference.",
                 "repetition": "Repeat behavior."}[kind]
        result = {"members": list(map(str, paths)), "task_overlap": "same",
                  "behavior_overlap": "high", "workflow": "compatible",
                  "shared_reference": kind == "shared_reference", "internal_redundancy": kind == "repetition",
                  "evidence": [{"skill": str(p), "file": "SKILL.md", "quote": quote,
                                "kind": kind} for p in paths],
                  "reason": "Source behavior overlaps; preserve unique branches and scope."}
        result.update(updates)
        return result

    def report(self, groups=None, usage=None, roots=None, **kwargs):
        return select_targets(roots or [self.root], {"groups": groups} if groups is not None else None,
                              usage, **kwargs)

    def alternative(self, report, action, index=0):
        return next(a for a in report["decisions"][index]["alternatives"] if a["action"] == action)

    def estimate(self, paths, net, action="merge", **overrides):
        result = {"members": list(map(str, paths)), "action": action,
                  "baseline_per_run": net + 10, "candidate_per_run": 10,
                  "expected_runs": 1, "build_cost": 0, "evaluation_cost": 0, "maintenance_cost": 0}
        result.update(overrides)
        return result

    def classification(self, paths):
        return {"categories": [{"id": "motion", "name": "Motion"},
                               {"id": "writing", "name": "Writing"}],
                "assignments": [{"skill": str(p), "category": "motion", "roles": ["workflow"],
                                 "reason": "Names and descriptions describe motion tasks."} for p in paths]}

    def test_classification_reads_only_frontmatter_and_preserves_package_boundary(self):
        a = self.skill("animate", "BODY MUST NOT BE READ", files={
            "references/large.bin": b"\xff\x00", "examples/demo/SKILL.md": b"example"})
        (a / "SKILL.md").write_text(
            "---\nname: animate\ndescription: >-\n  Build motion\n  on the web.\n---\nBODY MUST NOT BE READ", encoding="utf-8")
        original_iterdir, original_open = Path.iterdir, Path.open
        def iterdir(path):
            self.assertFalse(a in path.parents, "classification descended into package resources")
            return original_iterdir(path)
        @contextmanager
        def open_metadata(path, *args, **kwargs):
            with original_open(path, *args, **kwargs) as stream:
                def lines():
                    for line in stream:
                        self.assertNotIn("BODY MUST NOT BE READ", line)
                        yield line
                header = lines()
                class Reader:
                    def readline(self):
                        return next(header, "")
                    def __iter__(self):
                        return header
                yield Reader()
        with patch.object(Path, "read_bytes", side_effect=AssertionError("resource content read")), \
             patch.object(Path, "iterdir", iterdir), patch.object(Path, "open", open_metadata):
            report = classify_targets([self.root, a / "examples/demo"])
        self.assertEqual([i["name"] for i in report["inventory"]], ["animate"])
        self.assertEqual(report["inventory"][0]["description"], "Build motion on the web.")
        self.assertNotIn("BODY MUST NOT BE READ", json.dumps(report))
        self.assertEqual(report["coverage"]["unclassified"], [report["inventory"][0]["id"]])
        self.assertEqual(report["status"], "needs_classification")

    def test_task_classification_keeps_nary_groups_and_related_categories(self):
        paths = [self.skill(n, n + " unique body") for n in ("animate", "audit", "review", "terms")]
        writing = self.skill("writing")
        data = self.classification(paths)
        data["assignments"][0].update(related_categories=["writing"], tags=["web"], roles=["workflow", "guidance"])
        report = classify_targets([self.root], data)
        self.assertEqual(len(report["candidate_groups"]), 1)
        self.assertEqual(len(report["candidate_groups"][0]["members"]), 4)
        self.assertEqual(report["candidate_groups"][0]["status"], "classification_only")
        self.assertEqual(report["coverage"]["classified"], 4)
        self.assertEqual(len(report["coverage"]["unclassified"]), 1)
        self.assertNotIn("plan", report)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            classify_targets([self.root], {**data, "assignments": [{**data["assignments"][0], "skill": "animate"}]})

    def test_classified_selection_reads_only_selected_category_resources(self):
        a, b = self.skill("animate"), self.skill("audit")
        other = self.skill("writer", files={"private.txt": "must not read"})
        data = self.classification([a, b])
        data["assignments"].append({"skill": str(other), "category": "writing", "roles": ["guidance"], "reason": "Writing task"})
        classification = classify_targets([self.root], data)
        original = Path.read_bytes
        def read_bytes(path):
            self.assertFalse(other == path.parent or other in path.parents, "read unrelated category")
            return original(path)
        with patch.object(Path, "read_bytes", read_bytes):
            report = select_targets([self.root], classification=classification, categories=["motion"], max_candidates=0)
        self.assertEqual({i["name"] for i in report["inventory"]}, {"animate", "audit"})
        self.assertEqual(len(report["classification"]["candidate_groups"][0]["members"]), 2)
        self.assertEqual(len(report["classification"]["deferred"]), 1)
        self.assertEqual(len(report["plan"]["unassessed"]), 2)
        self.assertEqual(report["plan"]["keep"], [])

    def test_classified_selection_requires_scope_and_current_metadata(self):
        a = self.skill("animate")
        classification = classify_targets([self.root], self.classification([a]))
        with self.assertRaisesRegex(ValueError, "choose at least one"):
            select_targets([self.root], classification=classification)
        with self.assertRaisesRegex(ValueError, "unknown selected category"):
            select_targets([self.root], classification=classification, categories=["missing"])
        (a / "SKILL.md").write_text("---\nname: changed\ndescription: New task\n---\nNew body", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "names/descriptions changed"):
            select_targets([self.root], classification=classification, categories=["motion"])

    def test_unassessed_keep_and_retrieval_are_not_semantic_proof(self):
        self.skill("a")
        self.skill("b")
        report = self.report(max_candidates=1)
        self.assertEqual(len(report["inventory"]), 2)
        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(report["candidates"][0]["status"], "retrieval_only")
        self.assertEqual(len(report["plan"]["keep"]), 0)
        self.assertEqual(len(report["plan"]["unassessed"]), 2)
        self.assertFalse(report["plan"]["selected"])
        self.assertEqual(report["decisions"], [])
        json.dumps(report, allow_nan=False)

    def test_merge_with_source_provenance_and_unknown_economics(self):
        a, b = self.skill("a"), self.skill("b")
        report = self.report([self.group([a, b])])
        self.assertEqual(report["plan"]["selected"][0]["action"], "merge")
        self.assertEqual(report["decisions"][0]["selected_action"], "merge")
        evidence = report["decisions"][0]["evidence"][0]
        self.assertTrue(evidence["source_sha256"])
        self.assertEqual(evidence["end"] - evidence["start"], len(evidence["quote"]))
        self.assertEqual(self.alternative(report, "merge")["economics"]["status"], "unknown")
        self.assertIsNone(self.alternative(report, "merge")["economics"]["net_expected_savings"])
        self.assertEqual(len(report["decisions"][0]["alternatives"]), 4)

    def test_compress_requires_distinct_repeated_spans(self):
        a = self.skill("a", "Repeat behavior.\n\nRepeat behavior.")
        group = self.group([a], "repetition")
        group["evidence"].append(dict(group["evidence"][0]))
        report = self.report([group])
        self.assertFalse(self.alternative(report, "compress")["eligible"])
        self.assertEqual(len(report["decisions"][0]["evidence"]), 1)
        group["evidence"][1]["occurrence"] = 1
        report = self.report([group])
        self.assertEqual(report["plan"]["selected"][0]["action"], "compress")
        self.assertEqual(report["candidates"][0]["status"], "retrieval_only")
        self.assertEqual(len(report["candidates"][0]["members"]), 1)

    def test_overlapping_repetition_does_not_count_twice(self):
        a = self.skill("a", "aaaaa")
        group = self.group([a], "repetition")
        group["evidence"][0]["quote"] = "aaaa"
        group["evidence"].append({**group["evidence"][0], "occurrence": 1})
        self.assertFalse(self.alternative(self.report([group]), "compress")["eligible"])

    def test_factor_preserves_different_invocation_policies(self):
        a = self.skill("a")
        b = self.skill("b", policy="disable-model-invocation: true\n")
        group = self.group([a, b], "shared_reference")
        report = self.report([group])
        self.assertEqual(report["plan"]["selected"][0]["action"], "factor")
        self.assertFalse(self.alternative(report, "merge")["eligible"])

    def reference_group(self, paths, quote):
        group = self.group(paths, "shared_reference")
        for evidence in group["evidence"]:
            evidence["quote"] = quote
        return group

    def test_factoring_distinct_material_can_reuse_a_source(self):
        motion = "Use 160ms for press feedback."
        typography = "Use 1.4 line height for body text."
        a = self.skill("a", motion + "\n\n" + typography)
        b, c = self.skill("b", motion), self.skill("c", typography)
        report = self.report([self.reference_group([a, b], motion), self.reference_group([a, c], typography)])
        selected = report["plan"]["selected"]
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(p["action"] == "factor" for p in selected))
        source_id = next(s["id"] for s in report["inventory"] if s["path"] == str(a))
        self.assertEqual(sum(source_id in p["members"] for p in selected), 2)
        self.assertFalse(report["plan"]["keep"])

    def test_shared_material_conflicts_are_pending_not_keep(self):
        quote = "Use 160ms for press feedback."
        a, b, c = [self.skill(n, quote) for n in "abc"]
        report = self.report([self.reference_group([a, b], quote), self.reference_group([a, c], quote)])
        self.assertEqual(len(report["plan"]["selected"]), 1)
        self.assertFalse(report["plan"]["keep"])
        self.assertEqual(len(report["plan"]["pending"]), 1)

    def test_nary_reference_group_beats_fragmenting_same_material_into_pairs(self):
        quote = "Use 160ms for press feedback."
        paths = [self.skill(n, quote) for n in "abcd"]
        groups = [self.reference_group(paths[:2], quote), self.reference_group(paths[2:], quote), self.reference_group(paths, quote)]
        for ordering in (groups, list(reversed(groups))):
            report = self.report(ordering)
            self.assertEqual(len(report["plan"]["selected"]), 1)
            self.assertEqual(len(report["plan"]["selected"][0]["members"]), 4)

    def test_unknown_economics_prefers_supported_library_coverage_not_one_large_quote(self):
        repeat = "Preserve these required details " + "with their stated conditions " * 30 + "."
        a = self.skill("a", "Shared behavior.\n\n" + repeat + "\n\n" + repeat)
        b = self.skill("b", "Shared behavior.")
        compression = self.group([a], "repetition")
        compression["evidence"][0]["quote"] = repeat
        compression["evidence"].append({**compression["evidence"][0], "occurrence": 1})
        merging = self.group([a, b])
        report = self.report([compression, merging])
        self.assertEqual(report["plan"]["selected"][0]["action"], "merge")
        # Explicit economic evidence still takes precedence over the fallback.
        usage = {"unit": "tokens", "estimates": [self.estimate([a], 100, action="compress")]}
        self.assertEqual(self.report([compression, merging], usage)["plan"]["selected"][0]["action"], "compress")

    def test_partial_workflow_merge_requires_preserved_routes_and_shared_context(self):
        shared = "Run a public regression before changing the implementation."
        a = self.skill("diagnose", shared + "\n\nFor diagnosis first reproduce the reported symptom.")
        b = self.skill("test-first", shared + "\n\nFor a new feature start from its specified public behavior.")
        group = self.group([a, b], behavior_overlap="partial", task_overlap="partial", workflow="complementary")
        for evidence in group["evidence"]:
            evidence["quote"] = shared
        group["evidence"] += [
            {"skill": str(a), "file": "SKILL.md", "quote": "For diagnosis first reproduce the reported symptom.", "kind": "unique_behavior"},
            {"skill": str(b), "file": "SKILL.md", "quote": "For a new feature start from its specified public behavior.", "kind": "boundary"},
        ]
        self.assertFalse(self.alternative(self.report([group]), "merge")["eligible"])
        group["composition_plan"] = {
            "strategy": "branches", "shared_context": "Reuse the public regression signal during a test-first bug fix.",
            "routes": [{"skill": str(a), "when": "reported bug", "preserve": "reproduce before diagnosis"},
                       {"skill": str(b), "when": "test-first feature or fix", "preserve": "new features start from specification"}],
            "ordering": "Only the bug route requires diagnostic reproduction; implementation follows its failing regression.",
            "checks": ["feature work must not require a pre-existing bug", "regression fails before implementation"],
        }
        report = self.report([group])
        self.assertEqual(report["plan"]["selected"][0]["action"], "merge")
        self.assertEqual(report["plan"]["selected"][0]["composition_plan"]["strategy"], "branches")
        for updates in ({"workflow": "conflicting"}, {"behavior_overlap": "none"}, {"task_overlap": "different"}):
            bad = {**group, **updates}
            self.assertFalse(self.alternative(self.report([bad]), "merge")["eligible"])
        (b / "agents").mkdir()
        (b / "agents/openai.yaml").write_text("policy:\n  allow_implicit_invocation: false\n")
        self.assertFalse(self.alternative(self.report([group]), "merge")["eligible"])

    def test_pair_evidence_is_not_a_single_skill_redundancy_review(self):
        a, b = self.skill("a"), self.skill("b")
        report = self.report([self.group([a, b])])
        self.assertEqual(len(report["plan"]["coverage"]["single_skill_unassessed"]), 2)
        single = self.group([a], internal_redundancy=False)
        single["evidence"][0]["kind"] = "unique_behavior"
        report = self.report([self.group([a, b]), single])
        self.assertEqual(len(report["plan"]["coverage"]["single_skill_unassessed"]), 1)

    def test_compression_can_disclose_conditional_material_without_claiming_repetition(self):
        sql = "When writing SQL, qualify warehouse tables and use half-open date ranges."
        python = "When writing Python, annotate public parameters and return values."
        a = self.skill("coding", "Preserve requested behavior.\n\n" + sql + "\n\n" + python)
        group = self.group([a], internal_redundancy=False)
        group["evidence"] = [{"skill": str(a), "file": "SKILL.md", "quote": quote, "kind": "unique_behavior"} for quote in (sql, python)]
        self.assertFalse(self.alternative(self.report([group]), "compress")["eligible"])
        group["disclosure_plan"] = {
            "keep_core": "Keep requested-behavior preservation and task-language dispatch in the entrypoint.",
            "branches": [{"file": "SKILL.md", "quote": sql, "when": "writing SQL", "preserve": "all warehouse and date-filter rules"},
                         {"file": "SKILL.md", "quote": python, "when": "writing Python", "preserve": "all public type-annotation rules"}],
            "checks": ["SQL requests reach SQL rules", "Python requests do not load SQL-only material"],
        }
        group["evidence"].append({"skill": str(a), "file": "SKILL.md", "quote": "Preserve requested behavior.", "kind": "repetition"})
        report = self.report([group])
        self.assertEqual(report["plan"]["selected"][0]["action"], "compress")
        self.assertEqual(len(report["plan"]["selected"][0]["disclosure_plan"]["branches"]), 2)
        self.assertEqual(len(report["plan"]["selected"][0]["evidence_regions"]), 2)
        group["disclosure_plan"]["branches"][0]["quote"] = "not source evidence"
        with self.assertRaises(ValueError):
            self.report([group])

    def test_missing_member_evidence_is_not_counted_as_assessed(self):
        a, b = self.skill("a"), self.skill("b")
        group = self.group([a, b])
        group["evidence"] = group["evidence"][:1]
        report = self.report([group])
        self.assertEqual(len(report["plan"]["unassessed"]), 1)
        self.assertEqual(len(report["plan"]["keep"]), 1)
        self.assertFalse(report["plan"]["selected"])

    def test_paraphrased_repeated_behavior_can_be_compressed(self):
        a = self.skill("numbers", "Keep all supplied numbers unchanged.\n\nRetain every input number without alteration.")
        group = self.group([a], "repetition")
        group["evidence"] = [
            {"skill": str(a), "file": "SKILL.md", "quote": text, "kind": "repetition"}
            for text in ("Keep all supplied numbers unchanged.", "Retain every input number without alteration.")
        ]
        report = self.report([group])
        self.assertEqual(report["plan"]["selected"][0]["action"], "compress")

    def test_task_descriptions_retrieve_asymmetric_skills_without_example_label_noise(self):
        a = self.skill("writer-a", "Unique long material " + " ".join("word" + str(i) for i in range(400)))
        b = self.skill("writer-b", "A short wording guide.")
        for path in (a, b):
            p = path / "SKILL.md"
            text = p.read_text(encoding="utf-8")
            text = text.replace(f"name: {path.name}\n", f"name: {path.name}\ndescription: Preserve numerical claims while rewriting uncertainty in scientific abstracts\n")
            p.write_text(text, encoding="utf-8")
        noise = self.skill("noise", ("Prefer:\n\nAvoid:\n\n" * 40) + "Inventory scheduling instructions.")
        report = self.report(max_candidates=1)
        names = {item["id"]: item["name"] for item in report["inventory"]}
        self.assertEqual({names[s] for s in report["candidates"][0]["members"]}, {"writer-a", "writer-b"})
        self.assertIn("scientific abstracts", next(i["description"] for i in report["inventory"] if i["name"] == "writer-a"))

    def test_ignored_bytecode_cache_does_not_change_declared_invocation_policy(self):
        a = self.skill("cached", files={"scripts/__pycache__/helper.pyc": b"ignored bytecode"})
        report = self.report()
        item = next(i for i in report["inventory"] if i["path"] == str(a))
        self.assertTrue(item["invocation_policy"]["known"])
        self.assertTrue(item["inventory_complete"])

    def test_crlf_frontmatter_and_multiline_source_evidence(self):
        paths = [self.skill("a"), self.skill("b")]
        for path in paths:
            text = f"---\nname: {path.name}\ndescription: Preserve numerical facts\n---\nKeep supplied numbers.\nPreserve their units.\n"
            (path / "SKILL.md").write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        group = self.group(paths)
        for evidence in group["evidence"]:
            evidence["quote"] = "Keep supplied numbers.\nPreserve their units."
        report = self.report([group])
        self.assertTrue(all(i["description"] == "Preserve numerical facts" for i in report["inventory"]))
        self.assertEqual(report["plan"]["selected"][0]["action"], "merge")

    def test_lower_complexity_adequate_action_wins_without_economics(self):
        a, b = self.skill("a"), self.skill("b")
        group = self.group([a, b], "shared_reference")
        group["evidence"] += self.group([a, b])["evidence"]
        report = self.report([group])
        self.assertTrue(self.alternative(report, "merge")["eligible"])
        self.assertEqual(report["plan"]["selected"][0]["action"], "factor")

    def test_complementary_same_topic_and_partial_behavior_keep(self):
        a, b = self.skill("a"), self.skill("b")
        for updates in ({"workflow": "complementary"}, {"behavior_overlap": "none"},
                        {"behavior_overlap": "partial"}, {"task_overlap": "different"},
                        {"workflow": "conflicting"}):
            with self.subTest(updates=updates):
                report = self.report([self.group([a, b], **updates)],
                                     {"events": [{"skills": [str(a), str(b)], "count": 100}]})
                self.assertFalse(report["plan"]["selected"])
                self.assertTrue(self.alternative(report, "keep")["eligible"])
                self.assertEqual(len(report["plan"]["keep"]), 2)

    def test_invocation_mismatch_and_unknown_policy_block_merge(self):
        a = self.skill("a")
        variations = [
            {"policy": "disable-model-invocation: true\n"},
            {"policy": "disable-model-invocation: maybe\n"},
            {"policy": "disable-model-invocation: true\ndisable-model-invocation: false\n"},
            {"files": {"agents/openai.yaml": "policy:\n  allow_implicit_invocation: false\n"}},
            {"files": {"agents/openai.yaml": "policy: {allow_implicit_invocation: false}\n"}},
            {"files": {"agents/openai.yaml": b"\xff\xfe"}},
            {"policy": "disable-model-invocation: false\ndisable-model-invocation: false\n"},
            {"files": {"agents/openai.yaml": "policy:\n  allow_implicit_invocation: true\n  allow_implicit_invocation: false\n"}},
        ]
        for index, variation in enumerate(variations):
            with self.subTest(variation=variation):
                b = self.skill(f"b{index}", **variation)
                report = self.report([self.group([a, b])])
                self.assertFalse(self.alternative(report, "merge")["eligible"])
                self.assertFalse(report["plan"]["selected"])

    def test_id_references_and_matching_explicit_invocation_policies(self):
        a = self.skill("a", policy="disable-model-invocation: true\n",
                       files={"agents/openai.yaml": "policy:\n  allow_implicit_invocation: false\n"})
        b = self.skill("b", policy="disable-model-invocation: true\n",
                       files={"agents/openai.yaml": "policy:\n  allow_implicit_invocation: false\n"})
        initial = self.report()
        ids = {i["path"]: i["id"] for i in initial["inventory"]}
        group = self.group([a, b])
        group["members"] = [ids[str(a)], ids[str(b)]]
        for claim in group["evidence"]:
            claim["skill"] = ids[claim["skill"]]
        report = self.report([group], {"events": [{"skills": group["members"], "count": 0}]})
        self.assertEqual(report["plan"]["selected"][0]["action"], "merge")
        self.assertEqual(report["inventory"][0]["invocation_policy"]["signature"], [True, False])

    def test_same_name_paths_ids_and_ambiguous_name_error(self):
        a = self.skill("same", parent=self.root / "one")
        b = self.skill("same", parent=self.root / "two", body="Distinct behavior.")
        report = self.report()
        self.assertEqual([i["name"] for i in report["inventory"]], ["same", "same"])
        ids = [i["id"] for i in report["inventory"]]
        self.assertNotEqual(*ids)
        self.assertEqual(ids, [i["id"] for i in self.report(roots=[b, a])["inventory"]])
        group = self.group([a, b])
        group["members"] = ["same", str(b)]
        with self.assertRaises(ValueError):
            self.report([group])

    def test_complete_package_duplicate_identity_and_nested_suppression(self):
        files = {"examples/nested/SKILL.md": "nested example", "agents/openai.yaml": "policy:\n  allow_implicit_invocation: true\n", "references/r.txt": "resource"}
        a = self.skill("same", parent=self.root / "one", files=files)
        b = self.skill("same", parent=self.root / "two", files=files)
        report = self.report(roots=[self.root, a, a / "examples/nested"])
        self.assertEqual(len(report["inventory"]), 2)
        self.assertIsNotNone(report["inventory"][1]["exact_duplicate_of"])
        self.assertGreater(report["inventory"][0]["all_bytes"], report["inventory"][0]["entrypoint_bytes"])
        report = self.report([self.group([a, b])])
        self.assertFalse(report["plan"]["selected"])
        (b / "references/r.txt").write_text("different resource")
        self.assertIsNone(self.report()["inventory"][1]["exact_duplicate_of"])
        (b / "references/r.txt").write_text("resource")
        (b / "agents/openai.yaml").write_text("policy:\n  allow_implicit_invocation: false\n")
        self.assertIsNone(self.report()["inventory"][1]["exact_duplicate_of"])

    def test_stale_invalid_and_outside_evidence_fail(self):
        a, b = self.skill("a"), self.skill("b")
        for changes in ({"quote": "does not exist"}, {"occurrence": 999},
                        {"occurrence": True}, {"file": "../SKILL.md"}, {"file": "missing.txt"},
                        {"kind": "unknown"}, {"kind": []}, {"skill": "unknown"}):
            with self.subTest(changes=changes):
                group = self.group([a, b])
                group["evidence"][0].update(changes)
                with self.assertRaises(ValueError):
                    self.report([group])
        group = self.group([a, b])
        group["evidence"] = group["evidence"][:1]
        self.assertFalse(self.alternative(self.report([group]), "merge")["eligible"])
        group = self.group([a])
        group["evidence"] = self.group([b])["evidence"]
        with self.assertRaises(ValueError):
            self.report([group])

    def test_usage_economics_formula_and_forecast_independent_of_counts(self):
        a, b = self.skill("a"), self.skill("b")
        estimate = self.estimate([a, b], 5, expected_runs=4, build_cost=3, evaluation_cost=2, maintenance_cost=1)
        report = self.report([self.group([a, b])], {"events": [{"skills": [str(a), str(b)], "count": 9000}],
                                                "unit": "tokens", "estimates": [estimate]})
        economics = self.alternative(report, "merge")["economics"]
        self.assertEqual(economics["net_expected_savings"], 14)
        self.assertEqual(economics["expected_runs"], 4)
        self.assertEqual(economics["unit"], "tokens")
        json.dumps(report, allow_nan=False)
        for net in (0, -2):
            report = self.report([self.group([a, b])], {"unit": "usd", "estimates": [self.estimate([a, b], net)]})
            self.assertTrue(self.alternative(report, "merge")["eligible"])
            self.assertFalse(self.alternative(report, "merge")["selection_eligible"])
            self.assertFalse(report["plan"]["selected"])

    def test_invalid_numeric_and_usage_inputs(self):
        a, b = self.skill("a"), self.skill("b")
        for value in (-1, True, float("nan"), float("inf"), "1", None, []):
            with self.subTest(value=value):
                for field in ("baseline_per_run", "candidate_per_run", "expected_runs", "build_cost", "evaluation_cost", "maintenance_cost"):
                    with self.assertRaises(ValueError):
                        self.report(usage={"unit": "usd", "estimates": [self.estimate([a, b], 1, **{field: value})]})
        for count in (-1, True, 1.5, "2", None):
            with self.assertRaises(ValueError):
                self.report(usage={"events": [{"skills": [str(a)], "count": count}]})
        for usage in ({"estimates": [self.estimate([a, b], 1)]}, {"events": [{"skills": ["unknown"], "count": 0}]},
                      {"unit": "bytes"}, {"events": {}}, {"estimates": [self.estimate([a, b], 1)] , "unit": []}):
            with self.assertRaises(ValueError):
                self.report(usage=usage)

    def test_global_conflicting_group_plan_beats_first_pair(self):
        a, b, c, d = [self.skill(n) for n in "abcd"]
        groups = [self.group([a, b]), self.group([a, c]), self.group([b, d])]
        usage = {"unit": "usd", "estimates": [self.estimate([a, b], 9), self.estimate([a, c], 8), self.estimate([b, d], 8)]}
        for ordering in (groups, list(reversed(groups))):
            report = self.report(ordering, usage)
            selected = report["plan"]["selected"]
            self.assertEqual(sum(p["economics"]["net_expected_savings"] for p in selected), 16)
            selected_members = [s for p in selected for s in p["members"]]
            self.assertEqual(len(selected_members), len(set(selected_members)))
            self.assertTrue(report["plan"]["optimal_for_objective"])
            self.assertTrue(report["plan"]["deferred"][0]["conflicts_with"])

    def test_invalid_roots_and_max_candidates(self):
        for roots in ([], "not a list", [self.root / "missing"], [None]):
            with self.assertRaises(ValueError):
                select_targets(roots)
        for value in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                self.report(max_candidates=value)

    def test_schema_errors_and_conflicting_estimates_are_errors(self):
        a, b = self.skill("a"), self.skill("b")
        for assessments in ({}, {"groups": {}}, {"groups": [None]}):
            with self.assertRaises(ValueError):
                select_targets([self.root], assessments)
        for changes in ({"shared_reference": 1}, {"internal_redundancy": None},
                        {"workflow": "unknown"}, {"reason": ""}, {"evidence": None},
                        {"members": [str(a), str(a)]}):
            with self.assertRaises(ValueError):
                self.report([self.group([a, b], **changes)])
        estimate = self.estimate([a, b], 1)
        with self.assertRaises(ValueError):
            self.report(usage={"unit": "usd", "estimates": [estimate, estimate]})

    def test_excluded_and_reparse_paths_have_diagnostics(self):
        a = self.skill("a")
        self.skill("ignored", parent=self.root / "node_modules")
        try:
            (self.root / "alias").symlink_to(a, target_is_directory=True)
        except OSError:
            pass  # Windows may not grant symlink creation in test environments.
        report = self.report()
        self.assertEqual(len(report["inventory"]), 1)
        self.assertTrue(any("node_modules" in d["path"] for d in report["diagnostics"]))
        if (self.root / "alias").is_symlink():
            self.assertTrue(any("reparse" in d["reason"] for d in report["diagnostics"]))
            with self.assertRaises(ValueError):
                self.report(roots=[self.root / "alias"])


if __name__ == "__main__":
    unittest.main()
