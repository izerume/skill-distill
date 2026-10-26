import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "skill-distill" / "scripts" / "skill_distill.py"


class SkillDistillCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *map(str, args)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def make_skill(self, parent, name, body, files=None):
        skill = parent / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(body, encoding="utf-8")
        for relative, content in (files or {}).items():
            path = skill / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return skill

    def make_source_tree(self, parent):
        alpha = self.make_skill(
            parent,
            "alpha",
            "---\nname: alpha\ndescription: Alpha source\n---\n"
            "# Alpha\nPreserve this exact instruction.\n",
            {
                "references/a.txt": b"alpha resource\n",
                "agents/openai.yaml": b"metadata excluded from resource ledger\n",
            },
        )
        beta = self.make_skill(
            parent,
            "beta",
            "---\nname: beta\ndescription: Beta source\n---\n# Beta\nUse these examples.\n",
            {"references/examples.md": b"Example bytes\n"},
        )
        return alpha, beta

    def make_candidate(self, parent):
        return self.make_skill(
            parent,
            "candidate",
            "---\nname: candidate\ndescription: Distilled skill\n---\n"
            "# Distilled\nPreserve this exact instruction.\nUse these examples.\n"
            "[Examples](references/B/examples.md)\n"
            "```markdown\n[Example](missing-fenced.md)\n```\n"
            "    [Example](missing-indented.md)\n",
            {
                "references/A/a.txt": b"alpha resource\n",
                "references/B/examples.md": b"Example bytes\n",
            },
        )

    def snapshot(self, alpha, beta, out):
        return self.run_cli(
            "snapshot",
            "--source",
            f"A={alpha}",
            "--source",
            f"B={beta}",
            "--out",
            out,
        )

    def contract(self, drop=False):
        disposition = (
            {"action": "drop", "reason": "Superseded by current platform behavior."}
            if drop
            else {
                "action": "preserve",
                "target": {
                    "file": "SKILL.md",
                    "quote": "Preserve this exact instruction.",
                },
            }
        )
        rules = [] if drop else [
            {
                "id": "alpha-preservation",
                "source": {
                    "skill": "A",
                    "file": "SKILL.md",
                    "quote": "Preserve this exact instruction.",
                },
                "when": "When applying the distilled skill.",
                "behavior": "Keep the instruction available.",
                "disposition": disposition,
            }
        ]
        if drop:
            rules = [
                {
                    "id": "alpha-drop",
                    "source": {
                        "skill": "A",
                        "file": "SKILL.md",
                        "quote": "Preserve this exact instruction.",
                    },
                    "when": "When applying the distilled skill.",
                    "behavior": "Keep the instruction available.",
                    "disposition": disposition,
                }
            ]
        rules.append({
            "id": "beta-examples",
            "source": {"skill": "B", "file": "SKILL.md", "quote": "Use these examples."},
            "when": "When examples clarify the task.",
            "behavior": "Make the source examples available.",
            "disposition": {
                "action": "preserve",
                "target": {"file": "SKILL.md", "quote": "Use these examples."},
            },
        })
        return {
            "schema_version": 1,
            "rules": rules,
            "resources": [
                {
                    "source": {"skill": "A", "file": "references/a.txt"},
                    "action": "copy",
                    "target": "references/A/a.txt",
                },
                {
                    "source": {"skill": "B", "file": "references/examples.md"},
                    "action": "copy",
                    "target": "references/B/examples.md",
                },
            ],
        }

    def write_json(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_snapshot_copies_package_and_rejects_existing_destination(self):
        alpha, beta = self.make_source_tree(self.root / "source")
        (alpha / ".git").mkdir()
        (alpha / ".git" / "ignored.txt").write_text("ignore", encoding="utf-8")
        (alpha / "__pycache__").mkdir()
        (alpha / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
        (alpha / "module.pyc").write_bytes(b"ignored")
        run = self.root / "run"

        result = self.snapshot(alpha, beta, run)

        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((run / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual([source["id"] for source in manifest["sources"]], ["A", "B"])
        self.assertEqual(
            (run / "sources" / "A" / "references" / "a.txt").read_bytes(),
            b"alpha resource\n",
        )
        copied_paths = {item["path"] for item in manifest["sources"][0]["files"]}
        skill_entry = next(item for item in manifest["sources"][0]["files"] if item["path"] == "SKILL.md")
        self.assertIn("SKILL.md", copied_paths)
        self.assertEqual(skill_entry["bytes"], (alpha / "SKILL.md").stat().st_size)
        self.assertEqual(len(skill_entry["sha256"]), 64)
        self.assertNotIn(".git/ignored.txt", copied_paths)
        self.assertNotIn("module.pyc", copied_paths)
        self.assertFalse((run / "sources" / "A" / "__pycache__").exists())

        again = self.snapshot(alpha, beta, run)
        self.assertNotEqual(again.returncode, 0)
        self.assertTrue((run / "sources.json").is_file())

        link = alpha / "external.md"
        try:
            link.symlink_to(beta / "SKILL.md")
        except OSError:
            pass
        else:
            linked_run = self.root / "linked-run"
            rejected = self.snapshot(alpha, beta, linked_run)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("symlink/junction", rejected.stderr.lower())
            self.assertFalse(linked_run.exists())

    def test_validate_accepts_complete_contract_and_rejects_bad_mapping_or_resource(self):
        alpha, beta = self.make_source_tree(self.root / "source")
        run = self.root / "run"
        snap = self.snapshot(alpha, beta, run)
        self.assertEqual(snap.returncode, 0, snap.stderr)
        candidate = self.make_candidate(self.root)
        contract = self.root / "contract.json"
        report = self.root / "report.json"
        value = self.contract()
        self.write_json(contract, value)

        result = self.run_cli(
            "validate", "--run", run, "--candidate", candidate,
            "--contract", contract, "--out", report,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        valid = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(valid["structural_valid"])
        self.assertTrue(valid["preservation_gate"])
        self.assertEqual(valid["semantic_preservation"], "not_measured")
        self.assertEqual({rule["source"]["skill"] for rule in valid["mapped_rules"]}, {"A", "B"})
        self.assertEqual(len(valid["resource_decisions"]), 2)

        value["rules"][0]["disposition"]["target"]["quote"] = "Missing from candidate"
        self.write_json(contract, value)
        bad_mapping = self.run_cli(
            "validate", "--run", run, "--candidate", candidate,
            "--contract", contract, "--out", report,
        )
        self.assertEqual(bad_mapping.returncode, 1)
        self.assertFalse(json.loads(report.read_text(encoding="utf-8"))["structural_valid"])

        value = self.contract()
        self.write_json(contract, value)
        (candidate / "references" / "B" / "examples.md").write_bytes(b"tampered\n")
        bad_resource = self.run_cli(
            "validate", "--run", run, "--candidate", candidate,
            "--contract", contract, "--out", report,
        )
        self.assertEqual(bad_resource.returncode, 1)
        invalid = json.loads(report.read_text(encoding="utf-8"))
        self.assertFalse(invalid["structural_valid"])
        self.assertTrue(any("hash" in error.lower() or "sha256" in error.lower() for error in invalid["errors"]))

        (candidate / "references" / "B" / "examples.md").write_bytes(b"Example bytes\n")
        snapshot_skill = run / "sources" / "A" / "SKILL.md"
        snapshot_skill.write_bytes(snapshot_skill.read_bytes() + b"tampered\n")
        bad_snapshot = self.run_cli(
            "validate", "--run", run, "--candidate", candidate,
            "--contract", contract, "--out", report,
        )
        self.assertEqual(bad_snapshot.returncode, 1)
        snapshot_report = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(any("snapshot sha256 mismatch" in error.lower() for error in snapshot_report["errors"]))

    def test_validate_rejects_empty_contract_or_unrepresented_source(self):
        alpha, beta = self.make_source_tree(self.root / "source")
        run = self.root / "run"
        self.assertEqual(self.snapshot(alpha, beta, run).returncode, 0)
        candidate = self.make_candidate(self.root)
        contract_path = self.root / "contract.json"
        report_path = self.root / "report.json"
        complete = self.contract()
        for rules in ([], complete["rules"][:1]):
            with self.subTest(rule_count=len(rules)):
                partial = {**complete, "rules": rules}
                self.write_json(contract_path, partial)
                result = self.run_cli(
                    "validate", "--run", run, "--candidate", candidate,
                    "--contract", contract_path, "--out", report_path,
                )
                self.assertNotEqual(result.returncode, 0)
                report = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertFalse(report["preservation_gate"])

    def test_drop_is_reported_and_closes_preservation_gate(self):
        alpha, beta = self.make_source_tree(self.root / "source")
        run = self.root / "run"
        snapshot = self.snapshot(alpha, beta, run)
        self.assertEqual(snapshot.returncode, 0, snapshot.stderr)
        candidate = self.make_candidate(self.root)
        contract = self.root / "contract.json"
        report = self.root / "report.json"
        self.write_json(contract, self.contract(drop=True))

        result = self.run_cli(
            "validate", "--run", run, "--candidate", candidate,
            "--contract", contract, "--out", report,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(value["structural_valid"])
        self.assertFalse(value["preservation_gate"])
        self.assertEqual(value["unresolved_drops"][0]["id"], "alpha-drop")
        self.assertEqual(value["semantic_preservation"], "not_measured")

    def test_compare_reports_paired_regression_and_rejects_missing_case(self):
        cases = {"cases": [{"id": "c1", "stratum": "easy"}, {"id": "c2", "stratum": "hard"}]}
        baseline = {
            "condition": "original",
            "executor": {"model": "fixed-model", "options": {"temperature": 0}},
            "records": [
                {"case_id": case_id, "trial": 0, "checks": [
                    {"id": "rule-a", "passed": True, "critical": True},
                    {"id": "rule-b", "passed": True, "critical": False},
                ]}
                for case_id in ("c1", "c2")
            ],
        }
        candidate = json.loads(json.dumps(baseline))
        candidate["condition"] = "distilled"
        candidate["records"][1]["checks"][0]["passed"] = False
        cases_path = self.root / "cases.json"
        baseline_path = self.root / "baseline.json"
        candidate_path = self.root / "candidate.json"
        report_path = self.root / "comparison.json"
        self.write_json(cases_path, cases)
        self.write_json(baseline_path, baseline)
        self.write_json(candidate_path, candidate)

        compared = self.run_cli(
            "compare", "--cases", cases_path, "--baseline", baseline_path,
            "--candidate", candidate_path, "--out", report_path,
        )

        self.assertEqual(compared.returncode, 0, compared.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["inference"], "descriptive_only")
        self.assertFalse(report["observed_gate_passed"])
        self.assertEqual(report["overall"]["sample_count"], 2)
        self.assertEqual(report["overall"]["baseline_full_success_count"], 2)
        self.assertEqual(report["overall"]["candidate_full_success_count"], 1)
        regressions = report["overall"]["paired_full_success"]["regressions"]["case_trials"]
        self.assertEqual(regressions, [{"case_id": "c2", "trial": 0}])

        candidate["records"].pop()
        self.write_json(candidate_path, candidate)
        missing = self.run_cli(
            "compare", "--cases", cases_path, "--baseline", baseline_path,
            "--candidate", candidate_path, "--out", report_path,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("pair", missing.stderr.lower())


    def test_select_cli_uses_semantic_evidence_and_keeps_sources_read_only(self):
        library = self.root / "library"
        alpha = self.make_skill(library, "alpha", "---\nname: alpha\ndescription: Rewrite supplied text\n---\nPreserve the caller's requested output format.\n")
        beta = self.make_skill(library, "beta", "---\nname: beta\ndescription: Rewrite supplied text\n---\nKeep the output format explicitly requested by the caller.\n")
        facts = {"groups": [{
            "members": [str(alpha), str(beta)], "task_overlap": "same",
            "behavior_overlap": "high", "workflow": "compatible",
            "shared_reference": False, "internal_redundancy": False,
            "reason": "Both apply the same caller-selected rewrite output contract.",
            "evidence": [
                {"skill": str(alpha), "file": "SKILL.md", "quote": "Preserve the caller's requested output format.", "kind": "shared_behavior"},
                {"skill": str(beta), "file": "SKILL.md", "quote": "Keep the output format explicitly requested by the caller.", "kind": "shared_behavior"},
            ],
        }]}
        facts_path = self.root / "assessments.json"
        out = self.root / "selection.json"
        self.write_json(facts_path, facts)
        before = {str(p): p.read_bytes() for p in library.rglob("*") if p.is_file()}
        selected = self.run_cli("select", "--root", library, "--assessments", facts_path, "--out", out)
        self.assertEqual(selected.returncode, 0, selected.stderr)
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual({x["name"] for x in report["inventory"]}, {"alpha", "beta"})
        self.assertEqual([x["action"] for x in report["plan"]["selected"]], ["merge"])
        blocked = self.run_cli("select", "--root", library, "--out", alpha / "selection.json")
        self.assertNotEqual(blocked.returncode, 0)
        self.assertFalse((alpha / "selection.json").exists())
        self.assertEqual(before, {str(p): p.read_bytes() for p in library.rglob("*") if p.is_file()})

    def test_classification_cli_routes_selected_categories_and_protects_all_sources(self):
        library = self.root / "library"
        a = self.make_skill(library, "motion", "---\nname: motion\ndescription: Build web animations\n---\nAnimate UI.\n")
        b = self.make_skill(library, "writing", "---\nname: writing\ndescription: Write articles\n---\nWrite text.\n")
        inventory = self.root / "inventory.json"
        result = self.run_cli("classify", "--root", library, "--out", inventory)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(inventory.read_text(encoding="utf-8"))
        self.assertEqual(data["coverage"]["classified"], 0)
        data["categories"] = [{"id": "motion", "name": "Motion"}, {"id": "writing", "name": "Writing"}]
        data["assignments"] = [{"skill": str(p), "category": p.name, "roles": ["workflow"],
                                "reason": "Task described in metadata"} for p in (a, b)]
        assignments, classified = self.root / "assignments.json", self.root / "classified.json"
        self.write_json(assignments, data)
        result = self.run_cli("classify", "--root", library, "--assignments", assignments, "--out", classified)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(classified.read_text(encoding="utf-8"))["status"], "classified")
        out = self.root / "selected.json"
        args = ("select", "--root", library, "--classification", classified, "--category", "motion")
        result = self.run_cli(*args, "--out", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([i["name"] for i in json.loads(out.read_text(encoding="utf-8"))["inventory"]], ["motion"])
        for command in (("classify", "--root", library), args):
            result = self.run_cli(*command, "--out", b / "report.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((b / "report.json").exists())

    def test_select_installed_inside_scanned_library_does_not_write_import_cache(self):
        package = self.make_skill(
            self.root, "self-tool", "---\nname: self-tool\ndescription: Select local skills\n---\nRead skill packages.\n",
            {"scripts/skill_distill.py": CLI.read_bytes(),
             "scripts/target_selection.py": (CLI.parent / "target_selection.py").read_bytes()},
        )
        before = {p.relative_to(package).as_posix(): p.read_bytes() for p in package.rglob("*") if p.is_file()}
        result = subprocess.run(
            [sys.executable, str(package / "scripts/skill_distill.py"), "select", "--root", str(package), "--out", str(self.root / "report.json")],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, {p.relative_to(package).as_posix(): p.read_bytes() for p in package.rglob("*") if p.is_file()})

    def test_select_output_parent_alias_cannot_overwrite_a_source(self):
        import os
        package = self.make_skill(self.root, "source", "---\nname: source\ndescription: Keep source content\n---\nOriginal instruction.\n")
        alias = self.root / "output-alias"
        try:
            os.symlink(package, alias, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlink unavailable: {exc}")
        before = (package / "SKILL.md").read_bytes()
        result = self.run_cli("select", "--root", package, "--out", alias / "SKILL.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((package / "SKILL.md").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
