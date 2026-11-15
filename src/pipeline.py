"""PDF 한 건을 받아 OCR → 비식별화 → TXT/DOCX/대조표까지 처리하는 오케스트레이터."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import config
import exporter
import ocr_pipeline
from deidentifier import Deidentifier, DeidResult
from model_manager import ModelManager
from paths import bundled_ocr_models_dir, models_dir

ProgressFn = Callable[[str, int, int], None]
CancelFn = Callable[[], bool]


@dataclass
class ProcessResult:
    source: Path
    txt_path: Optional[Path] = None
    docx_path: Optional[Path] = None
    mapping_path: Optional[Path] = None
    deid: Optional[DeidResult] = None
    page_count: int = 0
    ocr_pages: int = 0
    elapsed_seconds: float = 0.0
    warnings: list = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.txt_path is not None


def build_llm(cfg: config.PipelineConfig, manager: Optional[ModelManager] = None):
    """설정에 따라 로컬 LLM 객체를 만든다(모델이 없으면 None)."""
    if not cfg.use_llm:
        return None
    manager = manager or ModelManager()
    if cfg.model_path:
        path = Path(cfg.model_path)
    else:
        path = manager.find_local(cfg.resolved_model_key())
    if not path or not Path(path).exists():
        return None
    from llm_engine import LocalLlm

    spec = config.MODEL_SPECS.get(cfg.resolved_model_key())
    prompt_format = spec.prompt_format if spec else "gemma"
    return LocalLlm(
        path,
        prompt_format=prompt_format,
        n_ctx=cfg.n_ctx,
        n_threads=cfg.n_threads,
        max_tokens=cfg.max_llm_tokens,
    )


def process_pdf(
    pdf_path: str | Path,
    cfg: Optional[config.PipelineConfig] = None,
    output_dir: Optional[str | Path] = None,
    llm=None,
    progress: Optional[ProgressFn] = None,
    cancel_check: Optional[CancelFn] = None,
    ocr_engine: Optional[ocr_pipeline.OcrEngine] = None,
) -> ProcessResult:
    cfg = cfg or config.PipelineConfig()
    source = Path(pdf_path)
    out_dir = Path(output_dir) if output_dir else source.resolve().parent
    result = ProcessResult(source=source)
    started = time.time()

    def report(message: str, current: int = 0, total: int = 0) -> None:
        if progress:
            try:
                progress(message, current, total)
            except TypeError:
                progress(message)  # type: ignore[misc]

    if not source.exists():
        result.error = f"파일을 찾을 수 없습니다: {source}"
        return result
    if source.suffix.lower() != ".pdf":
        result.error = "PDF 파일만 처리할 수 있습니다."
        return result
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.error = f"출력 폴더를 만들 수 없습니다: {exc}"
        return result

    # 1) 텍스트 추출 / OCR
    report("PDF 여는 중", 0, 100)
    ocr_cfg = ocr_pipeline.OcrConfig(dpi=cfg.dpi, force_ocr=cfg.force_ocr)
    if ocr_engine is None:
        ocr_engine = ocr_pipeline.OcrEngine(
            models_dir=bundled_ocr_models_dir(), config=ocr_cfg
        )
    try:
        pages = ocr_pipeline.extract_pages(
            source,
            config=ocr_cfg,
            progress=lambda message, current, total: report(
                message,
                int(5 + (current / max(total, 1)) * 40),
                100,
            ),
            cancel_check=cancel_check,
            ocr_engine=ocr_engine,
            models_dir=bundled_ocr_models_dir(),
        )
    except Exception as exc:
        result.error = f"PDF 텍스트 추출/OCR 실패: {exc}"
        return result

    result.page_count = len(pages)
    result.ocr_pages = sum(1 for page in pages if page.used_ocr)
    if not pages:
        result.error = "처리할 페이지가 없습니다."
        return result
    if cancel_check and cancel_check():
        result.error = "사용자가 취소했습니다."
        return result

    # AI 모델을 올리기 전에 OCR 엔진을 내려 메모리를 확보한다(8GB PC 배려)
    if ocr_engine is not None:
        try:
            ocr_engine.unload()
        except Exception:
            pass

    full_text = ocr_pipeline.pages_to_text(pages)
    if not full_text.strip():
        result.error = (
            "PDF에서 글자를 찾지 못했습니다. 스캔 상태가 매우 나쁘거나 암호가 걸린 PDF일 수 있습니다."
        )
        return result

    # 2) 비식별화
    report("AI 모델 준비 중", 50, 100)
    if cfg.use_llm and llm is None:
        llm = build_llm(cfg)
    deidentifier = Deidentifier(
        style=cfg.style,
        mask_text=cfg.mask_text,
        llm=llm,
        chunk_size=cfg.chunk_size,
        use_llm=cfg.use_llm,
        progress=lambda message: report(message, 50, 100),
        cancel_check=cancel_check,
    )
    try:
        deid = deidentifier.process(full_text)
    except Exception as exc:
        result.error = f"비식별화 처리 실패: {exc}"
        return result
    result.deid = deid
    result.warnings.extend(deid.warnings)
    if cancel_check and cancel_check():
        result.error = "사용자가 취소했습니다."
        return result

    # 3) 저장
    report("파일 저장 중", 90, 100)
    paths = exporter.build_output_paths(source, out_dir)
    try:
        result.txt_path = exporter.export_txt(deid.text, paths["txt"])
        result.docx_path = exporter.export_docx(
            deid.text,
            paths["docx"],
            add_notice=cfg.add_docx_notice,
        )
        if cfg.save_mapping:
            result.mapping_path = exporter.export_mapping_csv(deid.table.rows(), paths["mapping"])
    except Exception as exc:
        result.error = f"파일 저장 실패: {exc}"
        return result

    result.elapsed_seconds = round(time.time() - started, 1)
    report("완료", 100, 100)
    return result


def summarize(result: ProcessResult) -> str:
    if result.error:
        return result.error
    deid = result.deid
    assert deid is not None
    from deidentifier import LABEL_NAMES

    counts = deid.stats
    parts = [f"{LABEL_NAMES.get(label, label)} {count}건" for label, count in counts.items()]
    detail = ", ".join(parts) if parts else "치환 없음"
    return (
        f"{result.page_count}쪽(OCR {result.ocr_pages}쪽) · {detail} · "
        f"{result.elapsed_seconds}초"
    )
