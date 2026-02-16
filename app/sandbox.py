"""Sandbox utilities for AI-created MCP servers.

Provides AST-based code validation, a runtime import hook template,
and environment builder for sandboxed subprocess execution.
"""

import ast
import os
import sys
import textwrap
from pathlib import Path

# Modules the AI server code is allowed to import.
ALLOWED_MODULES: set[str] = {
    # MCP framework
    "mcp",
    # Safe stdlib
    "json",
    "datetime",
    "math",
    "re",
    "collections",
    "typing",
    "dataclasses",
    "enum",
    "time",
    "string",
    "random",
    "itertools",
    "functools",
    "hashlib",
    "base64",
    "textwrap",
    "uuid",
    "decimal",
    "fractions",
    "statistics",
    "operator",
    "copy",
    "pprint",
    "io",
    "struct",
    "abc",
    "contextlib",
    "logging",
}

# Modules that require allow_network=true.
NETWORK_MODULES: set[str] = {
    "socket",
    "urllib",
    "http",
    "requests",
    "httpx",
    "aiohttp",
    "ssl",
    "ftplib",
    "smtplib",
    "imaplib",
    "poplib",
    "xmlrpc",
}

# Dangerous function names that must never be called.
DANGEROUS_CALLS: set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "breakpoint",
    "exit",
    "quit",
}

# Dangerous dunder attributes.
DANGEROUS_ATTRS: set[str] = {
    "__class__",
    "__bases__",
    "__subclasses__",
    "__mro__",
    "__globals__",
    "__code__",
    "__builtins__",
}


def validate_code(code: str, *, allow_network: bool = False) -> tuple[bool, str]:
    """Validate MCP server code via AST analysis.

    Returns (ok, error_message). error_message is empty when ok=True.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error on line {e.lineno}: {e.msg}"

    errors: list[str] = []

    for node in ast.walk(tree):
        # --- Check imports ---
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, allow_network, errors, node.lineno)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _check_module(node.module, allow_network, errors, node.lineno)

        # --- Check dangerous calls ---
        elif isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name and name in DANGEROUS_CALLS:
                errors.append(f"Line {node.lineno}: call to '{name}()' is forbidden")

        # --- Check dangerous attribute access ---
        elif isinstance(node, ast.Attribute):
            if node.attr in DANGEROUS_ATTRS:
                errors.append(
                    f"Line {node.lineno}: access to '{node.attr}' is forbidden"
                )

    if errors:
        return False, "; ".join(errors)
    return True, ""


def _check_module(
    module: str, allow_network: bool, errors: list[str], lineno: int
) -> None:
    """Check whether a module import is allowed."""
    base = module.split(".")[0]

    # Always allowed
    if base in ALLOWED_MODULES:
        return

    # Network modules need explicit permission
    if base in NETWORK_MODULES:
        if not allow_network:
            errors.append(
                f"Line {lineno}: import '{module}' requires allow_network=true"
            )
        return

    # Everything else is forbidden
    errors.append(f"Line {lineno}: import '{module}' is not allowed")


def build_sandbox_env(
    server_dir: Path, *, allow_network: bool = False
) -> dict[str, str]:
    """Build a restricted environment dict for the sandboxed subprocess."""
    env: dict[str, str] = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "MCP_SANDBOX_DIR": str(server_dir / "sandbox"),
    }
    # Need PATH so python can find shared libraries / the interpreter itself
    if "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    # Need VIRTUAL_ENV and related paths so the mcp package can be found
    if "VIRTUAL_ENV" in os.environ:
        env["VIRTUAL_ENV"] = os.environ["VIRTUAL_ENV"]
    # LD_LIBRARY_PATH may be needed for native libs
    if "LD_LIBRARY_PATH" in os.environ:
        env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
    # HOME is sometimes needed
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    return env


def build_wrapper_script(server_py: Path, *, allow_network: bool = False) -> str:
    """Build a Python wrapper script that installs the import hook then runs the server."""
    forbidden = ALLOWED_MODULES.copy()  # We'll invert — compute forbidden set
    # Actually, the hook blocks everything NOT in allowed (+ optionally network)
    allowed = ALLOWED_MODULES.copy()
    if allow_network:
        allowed |= NETWORK_MODULES

    allowed_repr = repr(sorted(allowed))

    return textwrap.dedent(f"""\
        import sys
        import importlib.abc
        import importlib.machinery
        import os

        # --- Sandbox import hook ---
        _ALLOWED = set({allowed_repr})
        # Also allow any submodules of allowed packages
        _ALLOWED_BASES = _ALLOWED.copy()

        class _SandboxImporter(importlib.abc.MetaPathFinder):
            def find_module(self, fullname, path=None):
                base = fullname.split(".")[0]
                if base in _ALLOWED_BASES:
                    return None  # allow normal import
                # Block everything else
                raise ImportError(
                    f"Import of '{{fullname}}' is not allowed in sandbox. "
                    f"Allowed top-level modules: {{', '.join(sorted(_ALLOWED_BASES))}}"
                )

        sys.meta_path.insert(0, _SandboxImporter())

        # Provide sandbox dir via env (already set, but make sure it's accessible)
        _sandbox_dir = os.environ.get("MCP_SANDBOX_DIR", "sandbox")
        os.makedirs(_sandbox_dir, exist_ok=True)

        # Run the actual server
        _server_path = {str(server_py)!r}
        with open(_server_path, "r") as _f:
            _code = _f.read()
        exec(compile(_code, _server_path, "exec"))
    """)
