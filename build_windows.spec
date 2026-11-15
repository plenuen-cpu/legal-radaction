# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 설정 — 윈도우 포터블 폴더(LegalDeid/) 생성.

    pyinstaller build_windows.spec --noconfirm

결과: dist/LegalDeid/LegalDeid.exe (+ models/ocr, DLL, 사용법.txt)
GGUF 모델은 용량 때문에 묶지 않는다. exe 옆 models/ 에 직접 두거나 첫 실행 시 내려받는다.
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)

datas = []
binaries = []
hiddenimports = []


def add_package(name: str) -> None:
    try:
        package_datas, package_binaries, package_hidden = collect_all(name)
    except Exception as exc:  # 선택 패키지가 없어도 빌드는 계속
        print(f"[spec] '{name}' 수집 건너뜀: {exc}")
        return
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hidden)


for package in (
    "customtkinter",
    "rapidocr",
    "onnxruntime",
    "llama_cpp",
    "docx",
    "pymupdf",
    "PIL",
    "tkinterdnd2",
):
    add_package(package)

# 한국어 OCR 모델(약 19MB)은 함께 배포해 완전 오프라인으로 동작시킨다.
ocr_dir = ROOT / "models" / "ocr"
if ocr_dir.is_dir():
    onnx_files = sorted(ocr_dir.glob("*.onnx"))
    for path in onnx_files:
        datas.append((str(path), "models/ocr"))
    print(f"[spec] OCR 모델 {len(onnx_files)}개 포함")
else:
    print("[spec] 경고: models/ocr 가 없습니다. tools/fetch_ocr_models.py 를 먼저 실행하세요.")

for extra in (ROOT / "docs" / "사용법.txt", ROOT / "models" / "README.txt"):
    if extra.exists():
        datas.append((str(extra), "."))

icon_path = ROOT / "assets" / "icon.ico"
icon = str(icon_path) if icon_path.exists() else None

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT / "src"), str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "app",
        "cli",
        "config",
        "deidentifier",
        "exporter",
        "llm_engine",
        "model_manager",
        "ocr_pipeline",
        "paths",
        "patterns",
        "pipeline",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "pandas",
        "scipy",
        "pytest",
        "IPython",
        "notebook",
        "tkinter.test",
        "test",
        "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LegalDeid",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LegalDeid",
)
