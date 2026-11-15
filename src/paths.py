"""앱 실행 위치에 따른 경로 계산.

포터블(.exe) 배포를 전제로 하므로, 모델·설정은 exe 옆 폴더를 우선 사용한다.
쓰기 권한이 없는 곳(예: Program Files)에 설치된 경우에만 사용자 데이터 폴더로 물러난다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """PyInstaller 등으로 묶인 실행 파일인지 여부."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """실행 파일(또는 소스 실행 시 프로젝트 루트)이 있는 폴더."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """PyInstaller onefile 임시 해제 폴더(_MEIPASS) 또는 앱 폴더."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else app_dir()


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def user_data_dir() -> Path:
    """설정·로그·모델 다운로드용 사용자 폴더."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = root / "LegalDeid"
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    """GGUF 모델을 두는 폴더. exe 옆 `models/` 우선, 없으면 사용자 폴더."""
    portable = app_dir() / "models"
    if portable.exists() and _writable(portable):
        return portable
    if _writable(portable):
        return portable
    fallback = user_data_dir() / "models"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def bundled_ocr_models_dir() -> Path | None:
    """함께 배포된 OCR 모델 폴더(models/ocr). 없으면 None."""
    for base in (app_dir(), resource_dir()):
        candidate = base / "models" / "ocr"
        if candidate.is_dir() and any(candidate.glob("*.onnx")):
            return candidate
    return None


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def log_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
