import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/skill-distill/scripts"
sys.path.insert(0, str(SCRIPTS))
import versioning


class VersioningTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / ".work/versioning-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.store = versioning.VersionStore(self.project)

    def package(self, path, body="Keep the requested behavior.", files=None):
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(
            "---\nname: demo\ndescription: A local test skill\n---\n" + body, encoding="utf-8")
        for name, content in (files or {}).items():
            file = path / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding="utf-8")
        return path

    def tree(self, path):
        return {p.relative_to(path).as_posix(): p.read_bytes()
                for p in path.rglob("*") if p.is_file()}

    def managed(self):
        source = self.package(self.root / "source")
        active = self.package(self.project / "distilled/demo", "Original output.")
        self.store.register("demo", active, [{"path": str(source)}])
        return source, active

    def built(self, body="Updated output.", **prepare_options):
        work = self.store.prepare("demo", **prepare_options)
        folder = Path(work["path"])
        candidate = self.package(folder / "candidate", body)
        evidence = folder / "evidence"
        evidence.mkdir()
        (evidence / "reply.txt").write_text("Observed candidate output.", encoding="utf-8")
        report = {"schema_version": 1, "scope": "smoke",
                  "artifact": versioning.content(versioning.fingerprint(candidate)),
                  "checks": [{"id": "behavior", "passed": True, "evidence": "Observed reply preserves the requested behavior."}],
                  "outputs": ["reply.txt"]}
        (evidence / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return work, candidate, evidence

    def test_inspection_is_read_only_and_fingerprint_covers_snapshot_resources(self):
        before = self.tree(self.project)
        report = self.store.inspect("demo")
        self.assertEqual(report["status"], "unmanaged")
        self.assertEqual(before, self.tree(self.project))
        self.assertFalse((self.project / ".skill-distill").exists())
        source = self.package(self.root / "source", files={"node_modules/runtime/data.txt": "one"})
        first = versioning.fingerprint(source)
        (source / "node_modules/runtime/data.txt").write_text("two", encoding="utf-8")
        self.assertNotEqual(first["value"], versioning.fingerprint(source)["value"])
        copied = self.root / "snapshot"
        import skill_distill
        self.assertEqual(skill_distill.copy_skill_tree(source, copied), versioning.fingerprint(source)["files"])

    def test_register_preserves_active_package_and_inspect_reports_source_changes(self):
        source = self.package(self.root / "source", files={"scripts/run.py": "print(1)"})
        active = self.package(self.project / "distilled/demo", "Existing hand-authored output.")
        original = self.tree(active)
        state = self.store.register("demo", active, [{"path": str(source)}])
        self.assertEqual(state["current_release"], "r000001")
        self.assertEqual(self.tree(active), original)
        before = self.tree(self.project)
        report = self.store.inspect("demo")
        self.assertEqual(report["artifact"]["state"], "clean")
        self.assertEqual(report["sources"][0]["state"], "unchanged")
        self.assertEqual(before, self.tree(self.project))
        (source / "scripts/run.py").write_text("print(2)", encoding="utf-8")
        report = self.store.inspect("demo")
        self.assertEqual(report["sources"][0]["state"], "changed")
        self.assertEqual(report["sources"][0]["modified"], ["scripts/run.py"])
        saved = self.project / ".skill-distill/targets/demo/releases/r000001"
        self.assertEqual((saved / "run/sources/s001/scripts/run.py").read_text(), "print(1)")
        self.assertEqual(self.tree(active), original)

    def test_prepare_and_seal_preserve_current_and_bind_evidence_to_saved_bytes(self):
        source, active = self.managed()
        (source / "SKILL.md").write_text("---\nname: source\n---\nNew source behavior.", encoding="utf-8")
        original = self.tree(active)
        work, candidate, evidence = self.built()
        frozen = Path(work["path"]) / "run/sources/s001/SKILL.md"
        self.assertIn("New source behavior", frozen.read_text())
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        self.assertEqual(record["release_id"], "r000002")
        self.assertEqual(record["validation"]["status"], "passed")
        self.assertEqual(self.store.inspect("demo")["candidate"]["state"], "ready")
        self.assertEqual(self.store.inspect("demo")["current_release"], "r000001")
        self.assertEqual(self.tree(active), original)
        saved = self.project / ".skill-distill/targets/demo/releases/r000002"
        self.assertEqual(self.tree(saved / "package"), self.tree(candidate))
        self.assertTrue((saved / "evidence/reply.txt").is_file())

    def test_promote_rollback_and_noop_use_saved_packages_without_source_updates(self):
        source, active = self.managed()
        original = self.tree(active)
        work, candidate, evidence = self.built()
        release = self.store.seal("demo", work["run_id"], candidate, evidence)
        changed = self.tree(candidate)
        state = self.store.promote("demo", release["release_id"])
        self.assertEqual(state["revision"], 2)
        self.assertEqual(self.tree(active), changed)
        before = self.tree(self.project)
        self.assertEqual(self.store.prepare("demo")["status"], "up_to_date")
        self.assertEqual(self.tree(self.project), before)
        self.store.rollback("demo", "r000001")
        self.assertEqual(self.tree(active), original)
        work, candidate, evidence = self.built("Another output.")
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        self.assertEqual(record["release_id"], "r000003")
        import shutil
        shutil.rmtree(source)
        self.store.rollback("demo", "r000002")
        self.assertEqual(self.tree(active), changed)
        self.assertFalse(source.exists())

    def test_failed_or_stale_evidence_and_local_edits_do_not_replace_current(self):
        source, active = self.managed()
        original = self.tree(active)
        work, candidate, evidence = self.built()
        report_path = evidence / "report.json"
        report = json.loads(report_path.read_text())
        report["checks"][0]["passed"] = False
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(versioning.VersionError, "failed"):
            self.store.seal("demo", work["run_id"], candidate, evidence)
        work, candidate, evidence = self.built()
        (candidate / "SKILL.md").write_text("Changed after the recorded smoke run.", encoding="utf-8")
        with self.assertRaises(versioning.VersionError):
            self.store.seal("demo", work["run_id"], candidate, evidence)
        work, candidate, evidence = self.built()
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        (active / "SKILL.md").write_text("My local instruction.", encoding="utf-8")
        with self.assertRaisesRegex(versioning.VersionError, "local edits"):
            self.store.promote("demo", record["release_id"])
        self.assertEqual((active / "SKILL.md").read_text(), "My local instruction.")
        self.assertNotEqual(self.tree(active), original)
        self.assertEqual(self.store.inspect("demo")["current_release"], "r000001")

    def test_source_rebound_and_late_source_changes_are_not_silently_accepted(self):
        source = self.package(self.project / ".agents/skills/source")
        lock = self.project / "skills-lock.json"
        data = {"version": 1, "skills": {"source": {"sourceType": "github", "source": "owner/one", "skillPath": "skills/source/SKILL.md"}}}
        lock.write_text(json.dumps(data), encoding="utf-8")
        active = self.package(self.project / "distilled/demo")
        self.store.register("demo", active, [{"path": str(source)}])
        work, candidate, evidence = self.built()
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        original = self.tree(active)
        (source / "SKILL.md").write_text("A newer local source.", encoding="utf-8")
        with self.assertRaisesRegex(versioning.VersionError, "source changed"):
            self.store.promote("demo", record["release_id"])
        data["skills"]["source"]["source"] = "owner/two"
        lock.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.store.inspect("demo")["sources"][0]["state"], "rebound")
        with self.assertRaisesRegex(versioning.VersionError, "rebound"):
            self.store.prepare("demo")
        self.assertEqual(self.tree(active), original)

    def test_failed_second_rename_restores_original_package(self):
        self.managed()
        work, candidate, evidence = self.built()
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        active = self.project / "distilled/demo"
        original = self.tree(active)
        import os
        rename = os.rename
        def fail_install(source, destination, *args, **kwargs):
            if ".next-op-" in Path(source).name:
                raise PermissionError("Simulated Windows directory lock")
            return rename(source, destination, *args, **kwargs)
        with patch.object(os, "rename", fail_install):
            with self.assertRaises(PermissionError):
                self.store.promote("demo", record["release_id"])
        self.assertEqual(self.tree(active), original)
        self.assertEqual(self.store.inspect("demo")["current_release"], "r000001")

    def test_crashed_switch_can_be_recovered_from_actual_directory_state(self):
        self.managed()
        work, candidate, evidence = self.built()
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        active = self.project / "distilled/demo"
        original = self.tree(active)
        code = """
import os,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import versioning
rename = os.rename
def crash(source, destination, *args, **kwargs):
    if '.next-op-' in Path(source).name:
        os._exit(73)
    return rename(source, destination, *args, **kwargs)
os.rename = crash
versioning.VersionStore(sys.argv[2]).promote('demo', sys.argv[3])
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, str(SCRIPTS), str(self.project), record["release_id"]], capture_output=True)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertFalse(active.exists())
        before = self.tree(self.project)
        self.assertEqual(len(self.store.inspect("demo")["pending_operations"]), 1)
        self.assertEqual(self.tree(self.project), before)
        self.store.recover("demo")
        self.assertEqual(self.tree(active), original)
        self.assertEqual(self.store.inspect("demo")["pending_operations"], [])
        self.store.promote("demo", record["release_id"])
        self.assertEqual(self.store.inspect("demo")["current_release"], "r000002")

    def test_saved_evidence_changes_block_promotion(self):
        self.managed()
        work, candidate, evidence = self.built()
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        saved = self.project / ".skill-distill/targets/demo/releases" / record["release_id"]
        (saved / "evidence/reply.txt").write_text("Different output after the checks.", encoding="utf-8")
        with self.assertRaisesRegex(versioning.VersionError, "evidence"):
            self.store.promote("demo", record["release_id"])
        self.assertEqual(self.store.inspect("demo")["current_release"], "r000001")

    def test_internal_cli_inspection_and_fingerprint_are_read_only(self):
        package = self.package(self.project / "distilled/demo")
        before = self.tree(self.project)
        command = [sys.executable, "-B", str(SCRIPTS / "versioning.py"), "--project", str(self.project)]
        result = subprocess.run([*command, "inspect", "demo"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unmanaged")
        result = subprocess.run([*command, "fingerprint", "--path", str(package)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), versioning.fingerprint(package))
        self.assertEqual(self.tree(self.project), before)

    def test_recorded_metadata_adjustment_keeps_tested_workflow_and_static_check(self):
        self.managed()
        work, candidate, evidence = self.built()
        import shutil
        shutil.copytree(candidate, evidence / "tested-package")
        before = versioning.fingerprint(candidate)
        text = (candidate / "SKILL.md").read_text(encoding="utf-8")
        (candidate / "SKILL.md").write_text(text.replace("A local test skill", "Updated discovery description"), encoding="utf-8")
        report_path = evidence / "report.json"
        report = json.loads(report_path.read_text())
        report["artifact"] = versioning.content(versioning.fingerprint(candidate))
        report["tested_artifact"] = versioning.content(before)
        report["post_test_adjustment"] = {"kind": "metadata_only", "tested_package": "tested-package",
                                           "checks": [{"id": "host-metadata", "passed": True, "evidence": "Observed supported metadata check."}]}
        report_path.write_text(json.dumps(report), encoding="utf-8")
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        self.assertIn("post_test_adjustment", record["validation"])
        work, candidate, evidence = self.built("Changed workflow after testing.")
        shutil.copytree(candidate, evidence / "tested-package")
        report_path = evidence / "report.json"
        report = json.loads(report_path.read_text())
        report["tested_artifact"] = report["artifact"]
        report["post_test_adjustment"] = {"kind": "metadata_only", "tested_package": "tested-package",
                                           "checks": [{"id": "host", "passed": True, "evidence": "Metadata checked."}]}
        (candidate / "SKILL.md").write_text(text + "Another behavior.", encoding="utf-8")
        report["artifact"] = versioning.content(versioning.fingerprint(candidate))
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(versioning.VersionError, "workflow"):
            self.store.seal("demo", work["run_id"], candidate, evidence)

    def test_adoption_uses_known_historical_inputs_instead_of_newer_installed_sources(self):
        source = self.package(self.root / "source", "Historical source.")
        active = self.package(self.project / "distilled/demo", "Existing historical output.")
        import skill_distill
        from argparse import Namespace
        baseline = self.root / "historical-run"
        skill_distill.command_snapshot(Namespace(source=[f"old={source}"], out=str(baseline)))
        (source / "SKILL.md").write_text("Newer installed source.", encoding="utf-8")
        self.store.register("demo", active, [{"path": str(source)}], baseline_run=baseline)
        report = self.store.inspect("demo")
        self.assertEqual(report["sources"][0]["state"], "changed")
        self.assertEqual(report["sources"][0]["baseline"], "provided_snapshot")
        self.assertEqual(report["method"]["state"], "unknown")

    def test_managed_locations_do_not_escape_project_or_overlap_another_target(self):
        source, active = self.managed()
        outside = self.package(self.root / "outside")
        with self.assertRaisesRegex(versioning.VersionError, "project"):
            self.store.register("outside", outside, [{"path": str(source)}])
        with self.assertRaisesRegex(versioning.VersionError, "another target"):
            self.store.register("duplicate", active, [{"path": str(source)}])
        self.assertEqual(self.store.inspect("demo")["artifact"]["state"], "clean")

    def test_source_change_during_staging_blocks_the_switch(self):
        source, active = self.managed()
        original = self.tree(active)
        work, candidate, evidence = self.built()
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        import skill_distill
        copy = skill_distill.copy_skill_tree
        def change_source(package, destination):
            result = copy(package, destination)
            if ".next-op-" in Path(destination).name:
                (source / "SKILL.md").write_text("Source advanced during staging.", encoding="utf-8")
            return result
        with patch.object(skill_distill, "copy_skill_tree", change_source):
            with self.assertRaisesRegex(versioning.VersionError, "source changed"):
                self.store.promote("demo", record["release_id"])
        self.assertEqual(self.tree(active), original)

    def test_an_older_candidate_cannot_overwrite_a_newly_selected_release(self):
        self.managed()
        first_work, first, first_evidence = self.built("First selected output.")
        second_work, second, second_evidence = self.built("Another concurrent output.")
        first_release = self.store.seal("demo", first_work["run_id"], first, first_evidence)
        second_release = self.store.seal("demo", second_work["run_id"], second, second_evidence)
        self.store.promote("demo", first_release["release_id"])
        with self.assertRaisesRegex(versioning.VersionError, "stale"):
            self.store.promote("demo", second_release["release_id"])
        self.assertEqual(self.tree(self.project / "distilled/demo"), self.tree(first))

    def test_crash_after_install_completes_state_once(self):
        self.managed()
        work, candidate, evidence = self.built()
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        code = """
import os,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import versioning,skill_distill
write = skill_distill.write_json_atomic
def crash(path, value):
    if Path(path).name == 'state.json':
        os._exit(74)
    return write(path, value)
skill_distill.write_json_atomic = crash
versioning.VersionStore(sys.argv[2]).promote('demo', sys.argv[3])
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, str(SCRIPTS), str(self.project), record["release_id"]], capture_output=True)
        self.assertEqual(result.returncode, 74, result.stderr)
        self.assertEqual(self.tree(self.project / "distilled/demo"), self.tree(candidate))
        self.assertEqual(self.store.recover("demo")["status"], "committed")
        report = self.store.inspect("demo")
        self.assertEqual(report["current_release"], "r000002")
        self.assertEqual(report["revision"], 2)
        self.assertEqual(self.store.recover("demo")["status"], "no_pending_operation")

    def test_local_lock_entry_replaced_with_git_is_a_rebound_even_for_equal_bytes(self):
        source = self.package(self.project / ".agents/skills/local-source")
        active = self.package(self.project / "distilled/demo")
        lock = self.project / "skills-lock.json"
        data = {"version": 1, "skills": {"local-source": {"sourceType": "local", "source": "../authored", "skillPath": "SKILL.md"}}}
        lock.write_text(json.dumps(data), encoding="utf-8")
        self.store.register("demo", active, [{"path": str(source)}])
        data["skills"]["local-source"] = {"sourceType": "github", "source": "another/repo", "skillPath": "skills/local-source/SKILL.md"}
        lock.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.store.inspect("demo")["sources"][0]["state"], "rebound")
        with self.assertRaisesRegex(versioning.VersionError, "rebound"):
            self.store.prepare("demo")

    def test_explicit_revision_cannot_override_a_candidates_captured_revision(self):
        self.managed()
        work, candidate, evidence = self.built()
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        self.store.rollback("demo", "r000001")
        revision = self.store.inspect("demo")["revision"]
        self.assertEqual(revision, 2)
        with self.assertRaisesRegex(versioning.VersionError, "stale"):
            self.store.promote("demo", record["release_id"], expected_revision=revision)
        self.assertEqual(self.store.inspect("demo")["current_release"], "r000001")

    def test_adoption_preserves_unknown_history_without_inventing_sources(self):
        active = self.package(self.project / "distilled/orphan", "An old artifact with no surviving source record.")
        original = self.tree(active)
        self.store.register("orphan", active, [])
        report = self.store.inspect("orphan")
        self.assertEqual(report["sources"], [])
        self.assertEqual(report["source_history"], "unknown")
        self.assertEqual(report["artifact"]["state"], "clean")
        self.store.rollback("orphan", "r000001")
        self.assertEqual(self.tree(active), original)
        with self.assertRaisesRegex(versioning.VersionError, "source bindings"):
            self.store.prepare("orphan")
        missing = self.project / "missing-source"
        active2 = self.package(self.project / "distilled/known-missing", "Another historical package.")
        self.store.register("known-missing", active2, [{"path": str(missing)}])
        self.assertEqual(self.store.inspect("known-missing")["sources"][0]["state"], "missing")
        self.package(missing, "Source found later.")
        self.assertEqual(self.store.inspect("known-missing")["sources"][0]["state"], "unknown")
        self.assertEqual(self.store.prepare("known-missing")["status"], "building")

    def test_a_new_npx_origin_is_detected_after_initially_untracked_adoption(self):
        source = self.package(self.project / ".agents/skills/source")
        active = self.package(self.project / "distilled/demo")
        self.store.register("demo", active, [{"path": str(source)}])
        lock = {"version": 1, "skills": {"source": {"sourceType": "github", "source": "new/owner", "skillPath": "skills/source/SKILL.md"}}}
        (self.project / "skills-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        self.assertEqual(self.store.inspect("demo")["sources"][0]["state"], "rebound")

    def test_historical_bytes_do_not_inherit_the_current_installations_origin(self):
        source = self.package(self.project / ".agents/skills/source", "Source from repository A.")
        active = self.package(self.project / "distilled/demo", "Artifact made from A.")
        lock_path = self.project / "skills-lock.json"
        lock = {"version": 1, "skills": {"source": {"sourceType": "github", "source": "owner/repo-a", "skillPath": "skills/source/SKILL.md"}}}
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        import skill_distill
        from argparse import Namespace
        baseline = self.root / "historical-a"
        skill_distill.command_snapshot(Namespace(source=[f"A={source}"], out=str(baseline)))
        lock["skills"]["source"]["source"] = "owner/repo-b"
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        (source / "SKILL.md").write_text("---\nname: source\n---\nSource from repository B.", encoding="utf-8")
        state = self.store.register("demo", active, [{"path": str(source)}], baseline_run=baseline)
        saved = self.project / ".skill-distill/targets/demo/releases/r000001/release.json"
        historical = json.loads(saved.read_text(encoding="utf-8"))["sources"][0]
        self.assertIsNone(historical["origin"])
        self.assertIsNone(historical["source_id"])
        self.assertEqual(historical["binding_id"], state["source_bindings"][0]["source_id"])
        report = self.store.inspect("demo")
        self.assertEqual(report["source_history"], "partial")
        self.assertEqual(report["sources"][0]["origin_state"], "unknown")
        with self.assertRaisesRegex(versioning.VersionError, "origin"):
            self.store.prepare("demo")
        work, candidate, evidence = self.built(accept_current_sources=True)
        record = self.store.seal("demo", work["run_id"], candidate, evidence)
        self.store.promote("demo", record["release_id"])
        self.assertEqual(record["sources"][0]["origin"]["source"], "https://github.com/owner/repo-b")
        self.assertIsNone(json.loads(saved.read_text(encoding="utf-8"))["sources"][0]["origin"])

    def test_recorded_historical_origin_stays_independent_from_current_binding(self):
        source = self.package(self.project / ".agents/skills/source", "Shared bytes in two repositories.")
        active = self.package(self.project / "distilled/demo")
        import skill_distill
        from argparse import Namespace
        baseline = self.root / "origin-recorded-run"
        skill_distill.command_snapshot(Namespace(source=[f"A={source}"], out=str(baseline)))
        metadata_path = baseline / "sources.json"
        metadata = json.loads(metadata_path.read_text())
        origin_a = {"source_type": "github", "source": "https://github.com/owner/a", "skill_path": "skills/source"}
        metadata["sources"][0]["origin"] = origin_a
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        lock = {"version": 1, "skills": {"source": {"sourceType": "github", "source": "owner/b", "skillPath": "skills/source/SKILL.md"}}}
        (self.project / "skills-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        self.store.register("demo", active, [{"path": str(source)}], baseline_run=baseline)
        report = self.store.inspect("demo")
        self.assertEqual(report["sources"][0]["state"], "rebound")
        self.assertEqual(report["sources"][0]["origin_state"], "recorded")
        saved = self.project / ".skill-distill/targets/demo/releases/r000001/release.json"
        self.assertEqual(json.loads(saved.read_text())["sources"][0]["origin"], origin_a)
        with self.assertRaisesRegex(versioning.VersionError, "rebound"):
            self.store.prepare("demo")
        self.assertEqual(self.store.prepare("demo", accept_current_sources=True)["status"], "building")

    def test_old_import_records_are_reported_as_unverified_without_rewriting_them(self):
        source = self.package(self.root / "source")
        active = self.package(self.project / "distilled/demo")
        import skill_distill
        from argparse import Namespace
        baseline = self.root / "legacy-run"
        skill_distill.command_snapshot(Namespace(source=[f"old={source}"], out=str(baseline)))
        state = self.store.register("demo", active, [{"path": str(source)}], baseline_run=baseline)
        release_dir = self.project / ".skill-distill/targets/demo/releases/r000001"
        path = release_dir / "release.json"
        record = json.loads(path.read_text())
        source_record = record["sources"][0]
        source_record.pop("origin_provenance")
        source_record.pop("binding_id")
        source_record["source_id"] = state["source_bindings"][0]["source_id"]
        source_record["origin"] = state["source_bindings"][0]["origin"]
        path.write_text(json.dumps(record), encoding="utf-8")
        snapshot_path = release_dir / "run/sources.json"
        snapshots = json.loads(snapshot_path.read_text())
        snapshots["sources"][0].pop("origin")
        snapshots["sources"][0].pop("source_id")
        snapshot_path.write_text(json.dumps(snapshots), encoding="utf-8")
        before = self.tree(self.project)
        self.assertEqual(self.store.inspect("demo")["source_history"], "partial")
        self.assertEqual(self.tree(self.project), before)


if __name__ == "__main__":
    unittest.main()
