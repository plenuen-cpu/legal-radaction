"""로컬 AI 모델(GGUF)을 미리 받아두는 도우미.

윈도우 배포판에서는 GUI의 '모델 다운로드' 버튼을 쓰면 되고,
개발·CI 환경에서는 이 스크립트로 models/ 폴더에 미리 받아둘 수 있다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config
from model_manager import DownloadCancelled, ModelManager


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="비식별화용 GGUF 모델 다운로드")
    parser.add_argument("--model", default=config.DEFAULT_MODEL_KEY, choices=sorted(config.MODEL_SPECS))
    parser.add_argument("--dir", help="저장 폴더(기본: exe 옆 models/)")
    parser.add_argument("--list", action="store_true", help="사용 가능한 모델 목록")
    args = parser.parse_args(argv)

    if args.list:
        for key, spec in config.MODEL_SPECS.items():
            print(f"{key:26s} {spec.name}  ({spec.size_gb} GB)  {spec.languages}")
        return 0

    manager = ModelManager(Path(args.dir) if args.dir else None)
    existing = manager.find_local(args.model)
    if existing:
        print(f"이미 있습니다: {existing}")
        return 0

    last = {"percent": -1}

    def progress(status):
        step = int(status.percent // 5)
        if step != last["percent"]:
            last["percent"] = step
            speed = status.speed_bps / (1024 * 1024)
            print(
                f"\r  {status.percent:5.1f}%  "
                f"{status.downloaded / (1024 ** 2):8.0f} / {status.total / (1024 ** 2):.0f} MB  "
                f"{speed:5.1f} MB/s",
                end="",
                flush=True,
            )

    try:
        path = manager.ensure(args.model, progress=progress)
    except DownloadCancelled:
        print("\n취소되었습니다.")
        return 130
    except Exception as exc:
        print(f"\n실패: {exc}")
        return 1
    print(f"\n완료: {path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
