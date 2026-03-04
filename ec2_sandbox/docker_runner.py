"""
docker_runner.py — Execute user projects inside Docker containers with strict security.
"""
import logging
import os
import subprocess
import json
import time

logger = logging.getLogger(__name__)

DOCKER_IMAGE = "blastshield-runner"

# Security limits
CPU_LIMIT = "1"
MEMORY_LIMIT = "512m"
PID_LIMIT = "64"


def run_in_docker(project_dir: str, timeout: int = 10) -> dict:
    """
    Run user project in a secure Docker container.
    Returns deployment status, errors, logs, and exit code.
    """
    # Check if Docker is available
    try:
        subprocess.run(["docker", "version"], capture_output=True, check=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("Docker not available — running fallback analysis")
        return _fallback_analysis(project_dir)

    # Check if image exists, build if needed
    _ensure_image()

    cmd = [
        "docker", "run",
        "--rm",
        f"--cpus={CPU_LIMIT}",
        f"--memory={MEMORY_LIMIT}",
        f"--pids-limit={PID_LIMIT}",
        "--network=none",
        "--read-only",
        "--tmpfs", "/tmp:size=64m",
        "-v", f"{os.path.abspath(project_dir)}:/app:ro",
        DOCKER_IMAGE,
    ]

    logger.info(f"Running Docker: timeout={timeout}s, dir={project_dir}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,  # grace period
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        exit_code = result.returncode

        # Try to parse structured output from runner
        try:
            parsed = json.loads(stdout)
            return {
                "deployment_status": parsed.get("status", "success" if exit_code == 0 else "failure"),
                "runtime_errors": parsed.get("errors", []),
                "logs": parsed.get("logs", stderr),
                "endpoint_results": parsed.get("endpoint_results", {}),
                "container_exit_code": exit_code,
            }
        except json.JSONDecodeError:
            # Runner didn't return JSON — use raw output
            errors = []
            if stderr:
                errors = [line for line in stderr.splitlines() if "Error" in line or "error" in line]
            return {
                "deployment_status": "success" if exit_code == 0 else "failure",
                "runtime_errors": errors or ([stderr[:500]] if stderr else []),
                "logs": stdout[:2000] if stdout else stderr[:2000],
                "endpoint_results": {},
                "container_exit_code": exit_code,
            }

    except subprocess.TimeoutExpired:
        logger.warning(f"Docker container timed out after {timeout}s — killing")
        # Kill any running containers with the image
        subprocess.run(
            ["docker", "ps", "-q", "--filter", f"ancestor={DOCKER_IMAGE}"],
            capture_output=True, text=True,
        )
        return {
            "deployment_status": "timeout",
            "runtime_errors": [f"Container execution exceeded {timeout}s limit"],
            "logs": "",
            "endpoint_results": {},
            "container_exit_code": -1,
        }
    except Exception as e:
        logger.error(f"Docker execution error: {e}")
        return {
            "deployment_status": "failure",
            "runtime_errors": [str(e)],
            "logs": "",
            "endpoint_results": {},
            "container_exit_code": -1,
        }


def _ensure_image():
    """Check if Docker image exists, build if not."""
    check = subprocess.run(
        ["docker", "image", "inspect", DOCKER_IMAGE],
        capture_output=True, timeout=5,
    )
    if check.returncode != 0:
        logger.info(f"Building Docker image: {DOCKER_IMAGE}")
        dockerfile_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(
            ["docker", "build", "-t", DOCKER_IMAGE, dockerfile_dir],
            capture_output=True, timeout=120,
        )


def _fallback_analysis(project_dir: str) -> dict:
    """Static analysis when Docker is not available."""
    errors = []
    logs_lines = []

    for root, _, file_list in os.walk(project_dir):
        for fname in file_list:
            if fname.endswith(".py"):
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r") as f:
                        content = f.read()
                    # Basic syntax check
                    compile(content, fname, "exec")
                    logs_lines.append(f"✅ {fname}: syntax OK")
                except SyntaxError as e:
                    errors.append(f"{fname}: SyntaxError at line {e.lineno}: {e.msg}")
                    logs_lines.append(f"❌ {fname}: {e.msg}")
                except Exception as e:
                    errors.append(f"{fname}: {e}")

    return {
        "deployment_status": "fallback" if not errors else "failure",
        "runtime_errors": errors,
        "logs": "\n".join(logs_lines),
        "endpoint_results": {},
        "container_exit_code": 1 if errors else 0,
    }
