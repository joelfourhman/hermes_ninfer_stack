"""Versioned, local fixtures and bounded tools for repeatable agent workloads."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

WORKLOAD_VERSION = 1
SYSTEM = "You are a careful coding and research assistant. Use the provided tools to inspect evidence, make small changes, validate them, and report concise findings. Preserve tool call order and do not invent test results."
CODING_PROMPT = """Inspect README.md, ledger.py and test_ledger.py in this small repository.
Find and fix the net-total bug, run tests, diagnose the remaining pagination failure,
make a second focused edit, rerun tests, and summarize both fixes. Use actual tools.
Do not modify tests or README.md. Work in the requested stages so failures remain observable."""
FILES = {
    "README.md": "Ledger service: refunds subtract from revenue. paginate(items, page, size) uses zero-based pages. Negative pages and nonpositive sizes must raise ValueError. Run python -m unittest -q.\n",
    "ledger.py": """def net_total(sales, refunds):
    return sum(sales) + sum(refunds)


def paginate(items, page, size):
    if page < 0 or size <= 0:
        raise ValueError("invalid page or size")
    start = page * size + 1
    return items[start:start + size]
""",
    "test_ledger.py": """import unittest
from ledger import net_total, paginate

class LedgerTests(unittest.TestCase):
    def test_refunds(self):
        self.assertEqual(net_total([20, 30], [5, 10]), 35)
        self.assertEqual(net_total([], [2]), -2)

    def test_pages(self):
        self.assertEqual(paginate(list(range(8)), 0, 3), [0, 1, 2])
        self.assertEqual(paginate(list(range(8)), 2, 3), [6, 7])
        self.assertEqual(paginate([], 0, 3), [])

    def test_validation(self):
        for page, size in [(-1, 2), (0, 0), (0, -1)]:
            with self.assertRaises(ValueError):
                paginate([], page, size)
""",
}


def tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


TOOLS = [
    tool("list_files", "List fixture files"),
    tool("read_file", "Read one fixture file", {"path": {"type": "string"}}, ["path"]),
    tool(
        "write_file",
        "Replace ledger.py with corrected Python",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    tool("run_tests", "Run the fixed acceptance tests"),
]


class Workspace:
    def __init__(self, root: Path, *, context_kib: int = 64):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name, content in FILES.items():
            (self.root / name).write_text(content, encoding="utf-8", newline="\n")
        # Unique source lines reduce trivial repetitive-prefix behavior. These are fictional records.
        for index in range(4):
            lines = [
                f"Record {index}-{n:06d}: module_{n % 97} validates tenant scope before cache lookup; risk class {n % 11}; evidence tag {n * 7919 + index}."
                for n in range(max(1, context_kib * 1024 // 4 // 120))
            ]
            lines += [
                f"Finding {index}: service shard-{index} has boundary token FIXTURE-{index}; remediation is tenant-scoped cache keys."
            ]
            (self.root / f"source-{index}.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
        self.events = []

    def path(self, name: str) -> Path:
        path = (self.root / name).resolve()
        if path.parent != self.root or path.is_symlink():
            raise ValueError("Only direct fixture files are accessible")
        return path

    def execute(self, name: str, arguments: dict) -> str:
        start = time.perf_counter()
        failed = False
        try:
            if name == "list_files":
                result = "\n".join(
                    sorted(p.name for p in self.root.iterdir() if p.is_file())
                )
            elif name == "read_file":
                result = self.path(arguments["path"]).read_text(encoding="utf-8")
            elif name == "write_file":
                path = self.path(arguments["path"])
                if path.name != "ledger.py":
                    raise ValueError("Only ledger.py may be edited")
                text = arguments["content"]
                if not isinstance(text, str) or len(text) > 32000:
                    raise ValueError("Invalid file content")
                # Benchmark-generated code runs in the test process. Restrict this toy task
                # to pure expressions/functions: no imports, attribute calls or executable hooks.
                validate_fixture_code(text)
                path.write_text(text, encoding="utf-8", newline="\n")
                result = "File written"
            elif name == "run_tests":
                validate_fixture_code(
                    (self.root / "ledger.py").read_text(encoding="utf-8")
                )
                result = self.test()
                failed = not result["passed"]
                result = json.dumps(result)
            else:
                raise ValueError("Unknown fixture tool")
        except (ValueError, KeyError, OSError, SyntaxError) as exc:
            failed = True
            result = json.dumps({"error": str(exc)})
        self.events.append(
            {
                "tool": name,
                "duration_seconds": time.perf_counter() - start,
                "failed": failed,
            }
        )
        return result

    def test(self) -> dict:
        # Restore the immutable acceptance test before every validation, including Hermes mode.
        (self.root / "test_ledger.py").write_text(
            FILES["test_ledger.py"], encoding="utf-8"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                "import sys,unittest; sys.path.insert(0, sys.argv[1]); suite=unittest.defaultTestLoader.discover(sys.argv[1]); r=unittest.TextTestRunner(verbosity=1).run(suite); sys.exit(not r.wasSuccessful())",
                str(self.root),
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return {
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr)[-12000:],
        }


def validate_fixture_code(text: str) -> None:
    import ast

    tree = ast.parse(text)
    allowed_calls = {"sum", "len", "ValueError", "max", "min", "int", "list", "range"}
    forbidden = (
        ast.Import,
        ast.ImportFrom,
        ast.Attribute,
        ast.While,
        ast.For,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.With,
        ast.Try,
        ast.Global,
        ast.Nonlocal,
    )
    if any(not isinstance(node, ast.FunctionDef) for node in tree.body):
        raise ValueError("Fixture module must contain functions only")
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise ValueError("Fixture permits pure ledger functions only")
        if isinstance(node, ast.FunctionDef) and (
            node.decorator_list or node.args.defaults or node.args.kw_defaults
        ):
            raise ValueError("Fixture forbids decorators/default expressions")
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in allowed_calls
        ):
            raise ValueError("Fixture call is outside the bounded test API")
