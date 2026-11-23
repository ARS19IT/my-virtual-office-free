import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP = ROOT / "app"


def _pyproject():
    return tomllib.loads(ROOT.joinpath("pyproject.toml").read_text())


def test_python_package_manifest_declares_server_entrypoint():
    project = _pyproject()["project"]
    assert project["name"] == "my-virtual-office-free"
    assert project["scripts"]["virtual-office-server"] == "server:main"


def test_every_local_module_the_server_imports_is_packaged():
    declared = set(_pyproject()["tool"]["setuptools"]["py-modules"])
    pending, seen = ["server"], set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        for node in ast.walk(ast.parse(APP.joinpath(f"{name}.py").read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module.split(".")[0]]
            pending += [n for n in names if APP.joinpath(f"{n}.py").exists()]
    assert seen <= declared, sorted(seen - declared)


def test_office_ui_is_shipped_with_the_package():
    shipped = _pyproject()["tool"]["setuptools"]["data-files"]["share/my-virtual-office-free/app"]
    files = {p.name for pattern in shipped for p in ROOT.glob(pattern)}
    for name in ("index.html", "game.js", "setup.html", "default-office-config.json"):
        assert name in files, name
