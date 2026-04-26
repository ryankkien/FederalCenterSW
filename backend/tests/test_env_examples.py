import ast
from pathlib import Path
from typing import List, Set


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLES = [
    REPO_ROOT / "backend" / ".env.example",
    REPO_ROOT / "backend" / ".env.local.example",
    REPO_ROOT / "feature_extractor" / ".env.example",
]


def test_env_examples_share_the_same_ordered_contract() -> None:
    parsed = [_parse_env_example(path) for path in ENV_EXAMPLES]
    expected = parsed[0]

    assert expected
    assert parsed[1] == expected
    assert parsed[2] == expected


def test_literal_env_consumers_are_documented_in_examples() -> None:
    documented = set(_parse_env_example(ENV_EXAMPLES[0]))
    consumed = set()
    for source_path in (
        REPO_ROOT / "backend" / "app",
        REPO_ROOT / "backend" / "function_app.py",
        REPO_ROOT / "feature_extractor" / "app",
    ):
        paths = source_path.rglob("*.py") if source_path.is_dir() else [source_path]
        for path in paths:
            consumed.update(_literal_env_names(path))

    assert consumed - documented == set()


def _parse_env_example(path: Path) -> List[str]:
    names = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name = stripped.split("=", 1)[0]
        assert name not in seen, f"{path} defines {name} more than once"
        seen.add(name)
        names.append(name)
    return names


def _literal_env_names(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first_arg = node.args[0]
        if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
            continue
        if _is_env_lookup(node.func):
            names.add(first_arg.value)
    return names


def _is_env_lookup(func: ast.expr) -> bool:
    if isinstance(func, ast.Attribute):
        return (
            func.attr == "getenv"
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
        )
    if isinstance(func, ast.Name):
        return func.id in {"_csv_env", "_env_bool", "_require_env"}
    return False
