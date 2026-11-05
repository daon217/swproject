import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import ci

class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for p in (".ci", "apps", "services/api"):
            (self.root / p).mkdir(parents=True, exist_ok=True)
        self.project = dict(name="api", path="services/api", runtime="python", enabled=False, version="", install=[], check=[], build=[])
    def write(self):
        (self.root / ".ci/projects.json").write_text(json.dumps({"projects": [self.project]}))
    def enable(self):
        (self.root / "services/api/app.py").write_text("x = 1")
        self.project.update(enabled=True, version="3.12", install=[["python", "-m", "pip", "--version"]], check=[["python", "-V"]], build=[["python", "-m", "compileall", "."]])
        self.write()
    def test_empty_project_is_skipped(self):
        self.write()
        self.assertEqual(ci.plan(self.root), ([], ["api"]))
    def test_code_without_ci_is_error(self):
        self.write()
        (self.root / "services/api/app.py").write_text("x=1")
        with self.assertRaises(ValueError):
            ci.plan(self.root)
    def test_enabled_project_is_selected(self):
        self.enable()
        self.assertEqual(ci.plan(self.root)[0][0]["python_version"], "3.12")
    def test_node_lts_major_is_supported(self):
        self.enable()
        self.project.update(runtime="node", version="22")
        self.write()
        self.assertEqual(ci.plan(self.root)[0][0]["version"], "22")
    def test_python_still_requires_minor_version(self):
        self.enable()
        self.project["version"] = "3"
        self.write()
        with self.assertRaises(ValueError):
            ci.plan(self.root)
    def test_missing_check_is_error(self):
        self.enable()
        self.project["check"] = []
        self.write()
        with self.assertRaises(ValueError):
            ci.plan(self.root)
    def test_path_escape_is_error(self):
        self.project["path"] = "../outside"
        self.write()
        with self.assertRaises(ValueError):
            ci.plan(self.root)
    def test_failed_command_is_not_suppressed(self):
        self.enable()
        with patch("ci.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["python"])):
            with self.assertRaises(subprocess.CalledProcessError):
                ci.run(self.root, "api", "check")
    def test_unregistered_project_is_error(self):
        self.write()
        (self.root / "apps/new").mkdir()
        with self.assertRaises(ValueError):
            ci.plan(self.root)
