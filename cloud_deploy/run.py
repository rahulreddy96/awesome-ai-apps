"""
Cloud runner — launches any project from the repo with optimized settings.

Usage:
    python -m cloud_deploy.run <category>/<project>
    python -m cloud_deploy.run starter_ai_agents/agno_starter
    python -m cloud_deploy.run --list  # show available projects

Environment:
    CLOUD_TIER=minimal|balanced   (default: minimal)
    NEBIUS_API_KEY=...            (required)
"""

import os
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = [
    "starter_ai_agents",
    "simple_ai_agents",
    "mcp_ai_agents",
    "memory_agents",
    "rag_apps",
    "advance_ai_agents",
    "course",
    "voice_agents",
]


def find_projects():
    projects = []
    for cat in CATEGORIES:
        cat_path = REPO_ROOT / cat
        if not cat_path.is_dir():
            continue
        for entry in sorted(cat_path.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            has_python = any(entry.glob("*.py")) or any(entry.glob("**/*.py"))
            if has_python:
                projects.append(f"{cat}/{entry.name}")
    return projects


def find_entrypoint(project_dir: Path) -> Path | None:
    for name in ["main.py", "app.py", "run.py", "agent.py"]:
        candidate = project_dir / name
        if candidate.exists():
            return candidate
    py_files = list(project_dir.glob("*.py"))
    if py_files:
        return py_files[0]
    return None


def install_deps(project_dir: Path):
    req = project_dir / "requirements.txt"
    pyproject = project_dir / "pyproject.toml"
    if req.exists():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", "-r", str(req)],
            check=False,
        )
    elif pyproject.exists():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", "-e", str(project_dir)],
            check=False,
        )


def run_project(project_path: str):
    project_dir = REPO_ROOT / project_path
    if not project_dir.is_dir():
        print(f"Error: project '{project_path}' not found at {project_dir}")
        sys.exit(1)

    tier = os.getenv("CLOUD_TIER", "minimal")
    print(f"[cloud_deploy] Running {project_path} with tier={tier}")

    install_deps(project_dir)

    entrypoint = find_entrypoint(project_dir)
    if entrypoint is None:
        print(f"Error: no Python entrypoint found in {project_dir}")
        sys.exit(1)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CLOUD_TIER"] = tier

    if entrypoint.name == "app.py" and _uses_streamlit(entrypoint):
        cmd = [sys.executable, "-m", "streamlit", "run", str(entrypoint),
               "--server.port=8501", "--server.address=0.0.0.0",
               "--server.headless=true",
               "--browser.gatherUsageStats=false"]
    else:
        cmd = [sys.executable, str(entrypoint)]

    print(f"[cloud_deploy] Command: {' '.join(cmd)}")
    os.execvpe(cmd[0], cmd, env)


def _uses_streamlit(path: Path) -> bool:
    try:
        text = path.read_text(errors="replace")[:2000]
        return "streamlit" in text or "import st" in text
    except Exception:
        return False


def main():
    args = sys.argv[1:]
    if not args or args[0] == "--list":
        projects = find_projects()
        print(f"Available projects ({len(projects)}):\n")
        for p in projects:
            print(f"  {p}")
        return

    run_project(args[0])


if __name__ == "__main__":
    main()
