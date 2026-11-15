"""빌드·배포 설정이 깨지지 않았는지 확인하는 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_workflow_yaml_is_valid():
    yaml = pytest.importorskip("yaml")
    for path in (ROOT / "ci" / "build-windows.yml", ROOT / ".github" / "workflows" / "build-windows.yml"):
        assert path.exists(), f"{path} 누락"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "jobs" in data and "build" in data["jobs"]
        steps = data["jobs"]["build"]["steps"]
        names = [step.get("name", "") for step in steps]
        assert any("Install dependencies" in name for name in names)
        assert any("Build portable app" in name for name in names)
        assert any("Upload artifact" in name for name in names)
        assert data["jobs"]["build"]["runs-on"] == "windows-latest"


def test_ci_and_github_workflow_identical():
    ci = (ROOT / "ci" / "build-windows.yml").read_text(encoding="utf-8")
    gh = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    assert ci == gh


def test_spec_file_exists_and_mentions_key_packages():
    spec = (ROOT / "build_windows.spec").read_text(encoding="utf-8")
    for token in ("customtkinter", "rapidocr", "llama_cpp", "models/ocr", "LegalDeid"):
        assert token in spec


def test_entrypoints_compile():
    import py_compile

    for path in [
        ROOT / "main.py",
        ROOT / "src" / "app.py",
        ROOT / "src" / "cli.py",
        ROOT / "src" / "download_model.py",
    ]:
        py_compile.compile(str(path), doraise=True)


def test_app_module_imports_when_tk_available():
    try:
        import tkinter  # noqa: F401
        import customtkinter  # noqa: F401
    except Exception as exc:  # Tk가 없는 환경(리눅스 CI 등)에서는 건너뜁니다
        pytest.skip(f"Tk 미설치: {exc}")
    sys.modules.pop("app", None)
    import app  # noqa: F401

    assert hasattr(app, "main")
    assert hasattr(app, "LegalDeidApp")
