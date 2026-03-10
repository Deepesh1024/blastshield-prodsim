"""
runner.py — Runs INSIDE the Docker container.
Detects entry point, installs deps, executes the project, captures errors.
Outputs structured JSON to stdout.
"""
import json
import os
import subprocess
import sys
import traceback

APP_DIR = "/app"
ENTRY_FILES = ["app.py", "main.py", "server.py", "run.py", "index.py", "__main__.py"]


def find_entry_point():
    """Find the main Python file to execute."""
    for name in ENTRY_FILES:
        path = os.path.join(APP_DIR, name)
        if os.path.isfile(path):
            return path

    # Look for any .py file with FastAPI/Flask or if __name__
    py_files = sorted([f for f in os.listdir(APP_DIR) if f.endswith(".py")])
    for f in py_files:
        path = os.path.join(APP_DIR, f)
        try:
            with open(path) as fp:
                content = fp.read()
            if "if __name__" in content or "FastAPI" in content or "Flask" in content:
                return path
        except Exception:
            continue

    # Just return the first .py file
    if py_files:
        return os.path.join(APP_DIR, py_files[0])

    return None


def install_requirements():
    """Install requirements.txt if present."""
    req_path = os.path.join(APP_DIR, "requirements.txt")
    if os.path.isfile(req_path):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_path,
                 "--target", "/tmp/deps", "--quiet", "--no-cache-dir"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                sys.path.insert(0, "/tmp/deps")
                return True, "Dependencies installed"
            return False, result.stderr[:200]
        except subprocess.TimeoutExpired:
            return False, "pip install timed out"
    return True, "No requirements.txt"


def run_project(entry_path: str) -> dict:
    """Execute the project and capture results."""
    errors = []
    logs = []

    # Try syntax check first
    try:
        with open(entry_path) as f:
            source = f.read()
        compile(source, os.path.basename(entry_path), "exec")
        logs.append(f"✅ Syntax check passed: {os.path.basename(entry_path)}")
    except SyntaxError as e:
        errors.append(f"SyntaxError at line {e.lineno}: {e.msg}")
        return {"status": "failure", "errors": errors, "logs": "\n".join(logs)}

    # Try importing the module
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import importlib.util; spec = importlib.util.spec_from_file_location('mod', '{entry_path}'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "PYTHONPATH": f"{APP_DIR}:/tmp/deps"},
        )

        if result.returncode == 0:
            logs.append(f"✅ Import successful: {os.path.basename(entry_path)}")
            if result.stdout.strip():
                logs.append(result.stdout.strip()[:500])
        else:
            stderr = result.stderr.strip()
            # Extract the actual error
            err_lines = [l for l in stderr.splitlines() if l.strip() and not l.startswith(" ")]
            for line in err_lines[-3:]:
                errors.append(line[:200])
            logs.append(f"❌ Import failed: {os.path.basename(entry_path)}")

    except subprocess.TimeoutExpired:
        errors.append("Module import timed out (>10s)")
    except Exception as e:
        errors.append(str(e))

    # Check all .py files for syntax
    for fname in os.listdir(APP_DIR):
        if fname.endswith(".py") and fname != os.path.basename(entry_path):
            fpath = os.path.join(APP_DIR, fname)
            try:
                with open(fpath) as f:
                    compile(f.read(), fname, "exec")
                logs.append(f"✅ Syntax OK: {fname}")
            except SyntaxError as e:
                errors.append(f"{fname}: SyntaxError line {e.lineno}: {e.msg}")
                logs.append(f"❌ Syntax error: {fname}")

    status = "success" if not errors else "failure"
    return {
        "status": status,
        "errors": errors,
        "logs": "\n".join(logs),
        "endpoint_results": {},
    }


def main():
    result = {
        "status": "unknown",
        "errors": [],
        "logs": "",
        "endpoint_results": {},
    }

    try:
        # Find entry point
        entry = find_entry_point()
        if not entry:
            result["status"] = "failure"
            result["errors"] = ["No Python entry point found in /app"]
            print(json.dumps(result))
            return

        # Install deps
        dep_ok, dep_msg = install_requirements()
        if not dep_ok:
            result["errors"].append(f"Dependency install failed: {dep_msg}")

        # Run project
        result = run_project(entry)

    except Exception as e:
        result["status"] = "failure"
        result["errors"] = [traceback.format_exc()[:500]]

    # Output JSON to stdout
    print(json.dumps(result))


if __name__ == "__main__":
    main()

# Documented code

# Documented code
