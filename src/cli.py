"""명령줄 실행기(테스트·자동화용).

예)
    python src/cli.py 문서.pdf -o 결과폴더
    python src/cli.py *.pdf --style mask --no-llm
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config
import pipeline
from model_manager import ModelManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="한국어 법률문서 PDF를 로컬에서 비식별화합니다.",
    )
    parser.add_argument("inputs", nargs="+", help="PDF 파일 경로(여러 개 가능)")
    parser.add_argument("-o", "--output", help="출력 폴더(기본: 원본과 같은 폴더)")
    parser.add_argument(
        "--style", choices=["pseudonym", "mask"], default="pseudonym",
        help="pseudonym=[이름1] 가명화(기본), mask=*** 마스킹",
    )
    parser.add_argument("--no-llm", action="store_true", help="로컬 AI 문맥 분석 없이 정규식만 사용")
    parser.add_argument("--model", default=config.DEFAULT_MODEL_KEY, help="사용할 GGUF 모델 키")
    parser.add_argument("--model-path", help="GGUF 파일 직접 지정")
    parser.add_argument("--dpi", type=int, default=config.DEFAULT_DPI, help="스캔 PDF 렌더링 DPI")
    parser.add_argument("--force-ocr", action="store_true", help="텍스트 PDF도 강제로 OCR")
    parser.add_argument("--no-mapping", action="store_true", help="치환 대조표를 저장하지 않음")
    parser.add_argument("--chunk-size", type=int, default=1200, help="AI 분석 구간 길이(글자)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    manager = ModelManager()
    cfg = config.PipelineConfig(
        style=args.style,
        use_llm=not args.no_llm,
        model_key=args.model,
        model_path=args.model_path,
        dpi=args.dpi,
        force_ocr=args.force_ocr,
        save_mapping=not args.no_mapping,
        chunk_size=args.chunk_size,
    )

    if cfg.use_llm and not args.model_path and not manager.is_ready(cfg.model_key):
        print("[안내] 로컬 AI 모델이 없어 정규식만으로 진행합니다.")
        print(f"       모델을 받으려면: python src/download_model.py --model {cfg.model_key}")
        cfg.use_llm = False

    exit_code = 0
    for raw in args.inputs:
        path = Path(raw)
        print(f"\n=== {path.name} ===")
        result = pipeline.process_pdf(
            path,
            cfg,
            output_dir=args.output,
            progress=lambda message, current, total: print(f"  … {message}", flush=True),
        )
        if result.error:
            print(f"  [실패] {result.error}")
            exit_code = 1
            continue
        print(f"  [완료] {pipeline.summarize(result)}")
        print(f"  TXT : {result.txt_path}")
        print(f"  DOCX: {result.docx_path}")
        if result.mapping_path:
            print(f"  대조표: {result.mapping_path}")
        for warning in result.warnings:
            print(f"  - {warning}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
