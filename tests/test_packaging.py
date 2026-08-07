from pathlib import Path


def test_python_package_manifest_declares_server_entrypoint():
    text = Path(__file__).parents[1].joinpath("pyproject.toml").read_text()
    assert 'name = "my-virtual-office-free"' in text
    assert 'virtual-office-server = "server:main"' in text
