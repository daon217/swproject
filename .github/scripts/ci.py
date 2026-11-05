"""Validate project build contracts and execute commands without a shell."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".html", ".kt", ".swift"}
MANIFESTS = {"package.json", "pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.py", "manifest.json"}

def plan(root):
    projects = json.loads((root / ".ci/projects.json").read_text(encoding="utf-8"))["projects"]
    active, skipped, names, paths = [], [], set(), set()
    for p in projects:
        name, path = p["name"], p["path"]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or name in names:
            raise ValueError("Invalid or duplicate project name")
        names.add(name)
        rel = Path(path)
        if rel.is_absolute() or ".." in rel.parts or len(rel.parts) != 2 or rel.parts[0] not in {"apps", "services"}:
            raise ValueError(f"{name}: invalid path")
        directory = (root / rel).resolve()
        if not directory.is_relative_to(root.resolve()) or not directory.is_dir() or path in paths:
            raise ValueError(f"{name}: missing, duplicate or unsafe directory")
        paths.add(path)
        if p["runtime"] not in {"python", "node"} or type(p["enabled"]) is not bool:
            raise ValueError(f"{name}: invalid runtime/enabled")
        has_code = any(f.is_file() and (f.suffix in SUFFIXES or f.name in MANIFESTS) for f in directory.rglob("*"))
        if not p["enabled"]:
            if has_code:
                raise ValueError(f"{name}: code exists but CI is disabled; configure .ci/projects.json")
            skipped.append(name)
            continue
        if not has_code:
            raise ValueError(f"{name}: enabled without code")
        version_pattern = r"\d+(?:\.\d+){0,2}" if p["runtime"] == "node" else r"\d+\.\d+(?:\.\d+)?"
        if not re.fullmatch(version_pattern, p["version"]):
            raise ValueError(f"{name}: runtime version required")
        for phase in ("install", "check", "build"):
            commands = p[phase]
            if not isinstance(commands, list) or not commands or not all(
                isinstance(cmd, list) and cmd and all(isinstance(arg, str) and arg.strip() for arg in cmd)
                for cmd in commands
            ):
                raise ValueError(f"{name}: {phase} requires nonempty argument arrays")
        active.append({**p, "python_version": p["version"] if p["runtime"] == "python" else "3.12"})
    for base in ("apps", "services"):
        for directory in (root / base).iterdir():
            if directory.is_dir() and directory.relative_to(root).as_posix() not in paths:
                raise ValueError(f"Unregistered project: {directory.relative_to(root)}")
    return active, skipped

def run(root, name, phase):
    if phase not in {"install", "check", "build"}:
        raise ValueError("Unknown phase")
    active, _ = plan(root)
    project = next((p for p in active if p["name"] == name), None)
    if project is None:
        raise ValueError("Unknown or disabled project")
    for command in project[phase]:
        subprocess.run(command, cwd=root / project["path"], check=True, timeout=900)

def main():
    if len(sys.argv) == 2 and sys.argv[1] == "plan":
        active, skipped = plan(ROOT)
        matrix = {"include": [{k: p[k] for k in ("name", "runtime", "version", "python_version")} for p in active]}
        output = "matrix=" + json.dumps(matrix) + "\ncount=" + str(len(active)) + "\n"
        print(output)
        if os.getenv("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write(output)
        summary = f"## Build targets\nActive: {len(active)}\n\nSkipped (no code): {', '.join(skipped) or 'none'}\n"
        if not active:
            summary += "\nNo application build was run. Configuration validation is not application build success.\n"
        print(summary)
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
                f.write(summary)
    elif len(sys.argv) == 4 and sys.argv[1] == "run":
        run(ROOT, sys.argv[2], sys.argv[3])
    else:
        raise ValueError("Usage: ci.py plan | ci.py run PROJECT install|check|build")

if __name__ == "__main__":
    main()
