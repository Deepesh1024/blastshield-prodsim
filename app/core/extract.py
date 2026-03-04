"""
extract.py — Unpack zip / raw code, extract file contents, detect FastAPI/Flask endpoints.
"""
import io
import re
import zipfile
from typing import Optional


def extract_files_from_code(code: str) -> list[dict]:
    """Wrap a raw code string into the standard file-list format."""
    return [{"file": "main.py", "content": code}]


def extract_files_from_zip(zip_bytes: bytes) -> list[dict]:
    """Read up to 6 .py files from an in-memory zip archive."""
    files: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        py_names = [n for n in zf.namelist() if n.endswith(".py")][:6]
        for name in py_names:
            content = zf.read(name).decode("utf-8", errors="replace")
            files.append({"file": name, "content": content})
    return files


# Regex patterns for FastAPI / Flask route decorators
_ROUTE_RE = re.compile(
    r"""@\w+\.(get|post|put|delete|patch)\(\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
# Also match the function defined right after the decorator
_FUNC_RE = re.compile(r"def\s+(\w+)\s*\(")


def detect_endpoints(files: list[dict]) -> list[dict]:
    """Scan all files for route decorators and return structured endpoint list."""
    endpoints: list[dict] = []
    for f in files:
        lines = f["content"].splitlines()
        for i, line in enumerate(lines):
            m = _ROUTE_RE.search(line)
            if m:
                method = m.group(1).upper()
                path = m.group(2)
                func_name = _find_next_function(lines, i)
                endpoints.append(
                    {
                        "file": f["file"],
                        "method": method,
                        "path": path,
                        "function": func_name,
                    }
                )
    return endpoints


def _find_next_function(lines: list[str], start: int) -> str:
    """Look ahead from a decorator line to find the function name."""
    for j in range(start + 1, min(start + 5, len(lines))):
        fm = _FUNC_RE.search(lines[j])
        if fm:
            return fm.group(1)
    return "unknown"


def detect_functions(files: list[dict]) -> list[dict]:
    """Return all top-level function definitions across files."""
    funcs: list[dict] = []
    for f in files:
        for m in re.finditer(r"def\s+(\w+)\s*\(", f["content"]):
            funcs.append({"file": f["file"], "function": m.group(1)})
    return funcs


def detect_io_functions(files: list[dict]) -> list[dict]:
    """Heuristically find functions that likely perform I/O."""
    io_keywords = [
        "request", "fetch", "query", "read", "write", "send",
        "get", "post", "put", "delete", "connect", "open",
        "download", "upload", "execute", "call", "invoke",
    ]
    results: list[dict] = []
    for f in files:
        for m in re.finditer(
            r"(?:async\s+)?def\s+(\w+)\s*\([^)]*\)\s*:", f["content"]
        ):
            name = m.group(1)
            if any(kw in name.lower() for kw in io_keywords):
                results.append({"file": f["file"], "function": name})
    return results
