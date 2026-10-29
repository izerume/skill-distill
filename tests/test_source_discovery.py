import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/skill-distill/scripts"
sys.path.insert(0, str(SCRIPTS))
import discover_sources as discovery


class SourceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.home = self.base / "home"
        self.project = self.base / "project"
        self.home.mkdir()
        self.project.mkdir()

    def skill(self, path):
        path.mkdir(parents=True)
        (path / "SKILL.md").write_bytes(
            b"---\nname: sample\ndescription: Sample skill\n---\n\xffinvalid body\n")
        (path / "resource.bin").write_bytes(b"resource unchanged")
        return str(path)

    def discover(self, **kwargs):
        return discovery.discover_sources(self.home, self.project, environ={}, **kwargs)

    def test_common_locations_metadata_only_and_read_only(self):
        expected = self.skill(self.home / ".agents/skills/a")
        self.skill(self.project / ".claude/skills/b")
        before = {str(p): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        report = self.discover()
        self.assertEqual(len(report["inventory"]), 2)
        self.assertIn(expected, [i["path"] for i in report["inventory"]])
        self.assertTrue(report["requires_user_selection"])
        after = {str(p): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_selected_parent_does_not_leak_system_or_plugins(self):
        user = self.skill(self.home / ".codex/skills/user")
        self.skill(self.home / ".codex/skills/.system/core")
        self.skill(self.home / ".codex/plugins/cache/vendor/p/1/skills/plugin")
        report = self.discover()
        roots = [r["id"] for r in report["roots"] if r["status"] == "scanned"]
        result = discovery.select_sources(report, roots, include_system=False, include_plugins=False)
        self.assertEqual(result["package_paths"], [user])
        self.assertNotIn(str(self.home / ".codex/skills"), result["package_paths"])

    def test_system_and_plugin_choices_are_independent(self):
        system = self.skill(self.home / ".codex/skills/.system/core")
        plugin = self.skill(self.home / ".codex/plugins/cache/vendor/p/1/skills/plugin")
        report = self.discover()
        roots = [r["id"] for r in report["roots"] if r["status"] == "scanned"]
        self.assertEqual(discovery.select_sources(report, roots, include_system=True, include_plugins=False)["package_paths"], [system])
        self.assertEqual(discovery.select_sources(report, roots, include_system=False, include_plugins=True)["package_paths"], [plugin])

    def test_project_selection_stays_separate_from_home(self):
        self.skill(self.home / ".agents/skills/user")
        project = self.skill(self.project / ".agents/skills/project")
        report = self.discover()
        root = next(r for r in report["roots"] if r["path"] == str(self.project / ".agents/skills"))
        result = discovery.select_sources(report, [root["id"]], include_system=False, include_plugins=False)
        self.assertEqual(result["package_paths"], [project])

    def test_custom_codex_home_and_overlapping_roots(self):
        codex = self.base / "custom-codex"
        path = self.skill(codex / "skills/.system/core")
        report = discovery.discover_sources(self.home, self.project, environ={"CODEX_HOME": str(codex)}, extra_roots=[codex / "skills"])
        self.assertEqual(len(report["inventory"]), 1)
        self.assertEqual(report["inventory"][0]["kind"], "system")
        ids = [r["id"] for r in report["roots"] if r["status"] == "scanned"]
        self.assertEqual(discovery.select_sources(report, ids, include_system=True, include_plugins=False)["package_paths"], [path])

    def test_missing_sources_and_unanswered_choices_do_not_select(self):
        report = self.discover()
        self.assertEqual(report["inventory"], [])
        with self.assertRaises(ValueError):
            discovery.select_sources(report, [], include_system=False, include_plugins=False)
        with self.assertRaises(ValueError):
            discovery.select_sources(report, [report["roots"][0]["id"]], include_system=False, include_plugins=False)
        with self.assertRaises(ValueError):
            discovery.select_sources(report, ["unknown"], include_system=None, include_plugins=False)

    def test_cli_returns_json_without_a_source_selection(self):
        self.skill(self.project / ".agents/skills/a")
        env = {**os.environ, "CODEX_HOME": str(self.home / ".codex"), "XDG_CONFIG_HOME": str(self.home / ".config")}
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "discover_sources.py"), "--home", str(self.home), "--project", str(self.project)], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["requires_user_selection"])

    def test_header_line_endings_and_unreadable_body(self):
        for ending in (b"\n", b"\r\n", b"\r"):
            with self.subTest(ending=ending):
                path = self.home / ".agents/skills/line-endings"
                path.mkdir(parents=True, exist_ok=True)
                header = ending.join([b"---", b"name: exact-name", b"description: Exact description", b"---", b"\xffinvalid body"])
                (path / "SKILL.md").write_bytes(b"\xef\xbb\xbf" + header)
                item = self.discover()["inventory"][0]
                self.assertEqual(item["name"], "exact-name")
                self.assertEqual(item["description"], "Exact description")


if __name__ == "__main__":
    unittest.main()
