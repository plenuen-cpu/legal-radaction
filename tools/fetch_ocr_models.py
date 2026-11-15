"""한국어 OCR 모델(ONNX)을 models/ocr/에 내려받는다.

배포본에는 이 파일들이 함께 들어가므로, 사용자는 OCR 모델을 따로 받을 필요가 없다.
(개발·CI에서 빌드 전에 한 번 실행)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx"

MODELS = {
    "ch_PP-OCRv5_det_mobile.onnx": (
        f"{BASE}/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx",
        "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    ),
    "korean_PP-OCRv5_rec_mobile.onnx": (
        f"{BASE}/PP-OCRv5/rec/korean_PP-OCRv5_rec_mobile.onnx",
        "cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b",
    ),
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": (
        f"{BASE}/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(target_dir: Path, force: bool = False) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename, (url, expected) in MODELS.items():
        target = target_dir / filename
        if target.exists() and not force:
            if sha256(target) == expected:
                print(f"[skip] {filename} (이미 있음)")
                continue
            print(f"[redo] {filename} (검증 실패)")
        print(f"[get ] {filename}")
        request = urllib.request.Request(url, headers={"User-Agent": "LegalDeid-build/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
            while True:
                block = response.read(1024 * 256)
                if not block:
                    break
                handle.write(block)
        actual = sha256(target)
        if actual != expected:
            target.unlink(missing_ok=True)
            print(f"[fail] {filename}: SHA-256 불일치 ({actual})")
            return 1
        print(f"[ok  ] {filename} ({target.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="한국어 OCR 모델 다운로드")
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent / "models" / "ocr"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    return fetch(Path(args.dir), args.force)


if __name__ == "__main__":
    sys.exit(main())
