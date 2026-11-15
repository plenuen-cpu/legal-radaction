"""llama-cpp-python 기반 로컬 LLM 래퍼.

GGUF 모델을 CPU로만 돌린다(GPU 불필요). EXAONE / Qwen(ChatML) 프롬프트 형식을 지원한다.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import config


class LlmUnavailable(RuntimeError):
    pass


_STOP_TOKENS = {
    "exaone": ["[|endofturn|]", "[|user|]", "[|system|]"],
    "chatml": ["<|im_end|>", "<|im_start|>"],
    "gemma": ["<end_of_turn>", "<start_of_turn>"],
    "llama3": ["<|eot_id|>", "<|start_header_id|>"],
}


def build_prompt(system: str, user: str, prompt_format: str = "gemma") -> str:
    if prompt_format == "chatml":
        return (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
    if prompt_format == "gemma":
        # Gemma 3는 별도 system 역할이 없어 시스템 지시를 user 턴 앞에 둔다
        return (
            f"<start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n"
            f"<start_of_turn>model\n"
        )
    if prompt_format == "llama3":
        return (
            "<|start_header_id|>system<|end_header_id|>\n\n"
            f"{system}<|eot_id|>"
            "<|start_header_id|>user<|end_header_id|>\n\n"
            f"{user}<|eot_id|>"
            "<|start_header_id|>assistant<|end_header_id|>\n\n"
        )
    # EXAONE 3.5 GGUF chat template
    return f"[|system|]{system}[|endofturn|]\n[|user|]{user}\n[|assistant|]"


def extract_json_array(raw: str) -> List[dict]:
    """모델 출력에서 JSON 배열만 뽑아낸다(설명·코드블록·깨진 쉼표 허용)."""
    if not raw:
        return []
    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    start = text.find("[")
    end = text.rfind("]")
    candidates = []
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    candidates.append(text)

    for candidate in candidates:
        for patched in (
            candidate,
            re.sub(r",\s*([\]}])", r"\1", candidate),
            candidate.replace("'", '"'),
            re.sub(r",\s*([\]}])", r"\1", candidate.replace("'", '"')),
        ):
            try:
                data = json.loads(patched)
            except Exception:
                continue
            if isinstance(data, dict):
                for key in ("entities", "results", "data", "items"):
                    if isinstance(data.get(key), list):
                        return [d for d in data[key] if isinstance(d, dict)]
                if "type" in data and "text" in data:
                    return [data]
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]

    # 마지막 수단: {"type": "...", "text": "..."} 조각을 직접 찾는다
    found = []
    for match in re.finditer(
        r"\{\s*[\"']?type[\"']?\s*:\s*[\"'](?P<type>[A-Za-z]+)[\"']\s*,\s*"
        r"[\"']?(?:text|value|name)[\"']?\s*:\s*[\"'](?P<text>[^\"']+)[\"']",
        text,
    ):
        found.append({"type": match.group("type"), "text": match.group("text")})
    return found


class LocalLlm:
    """GGUF 모델 하나를 메모리에 올려 문맥 비식별화에 사용한다."""

    def __init__(
        self,
        model_path: str | Path,
        prompt_format: str = "gemma",
        n_ctx: int = 2048,
        n_threads: Optional[int] = None,
        max_tokens: int = 512,
        verbose: bool = False,
    ):
        self.model_path = Path(model_path)
        self.prompt_format = prompt_format
        self.n_ctx = n_ctx
        self.max_tokens = max_tokens
        self.verbose = verbose
        cpu = os.cpu_count() or 4
        self.n_threads = n_threads or max(cpu - 1, 1)
        self._llm = None

    # -- 수명주기 -------------------------------------------------------
    def load(self) -> None:
        if self._llm is not None:
            return
        if not self.model_path.exists():
            raise LlmUnavailable(f"모델 파일이 없습니다: {self.model_path}")
        try:
            from llama_cpp import Llama
        except Exception as exc:  # pragma: no cover - 윈도우 배포본에는 포함
            raise LlmUnavailable(
                "llama-cpp-python이 설치되어 있지 않아 AI 문맥 분석을 쓸 수 없습니다."
            ) from exc
        try:
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_batch=256,
                verbose=self.verbose,
                use_mmap=True,
                use_mlock=False,
            )
        except Exception as exc:  # pragma: no cover
            raise LlmUnavailable(f"모델을 불러오지 못했습니다: {exc}") from exc

    def unload(self) -> None:
        self._llm = None

    @property
    def is_loaded(self) -> bool:
        return self._llm is not None

    # -- 추론 -----------------------------------------------------------
    def _complete(self, prompt: str) -> str:
        self.load()
        stops = _STOP_TOKENS.get(self.prompt_format, _STOP_TOKENS["gemma"])
        try:
            output = self._llm(
                prompt,
                max_tokens=self.max_tokens,
                temperature=0.0,
                top_p=0.9,
                repeat_penalty=1.05,
                stop=stops,
                echo=False,
            )
        except Exception as exc:  # pragma: no cover
            raise LlmUnavailable(f"AI 추론 중 오류가 발생했습니다: {exc}") from exc
        choices = output.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("text") or "").strip()

    def build_chunk_prompt(self, chunk: str) -> str:
        user = config.LLM_USER_TEMPLATE.format(chunk=chunk)
        return build_prompt(config.LLM_SYSTEM_PROMPT, user, self.prompt_format)

    def extract_entities(self, chunk: str) -> List[Dict[str, str]]:
        raw = self._complete(self.build_chunk_prompt(chunk))
        entities = extract_json_array(raw)
        if not entities and raw.strip():
            # 한 번 더 짧게 재요청(형식만 요구)
            retry_prompt = build_prompt(
                config.LLM_SYSTEM_PROMPT,
                "다음 문서에서 사람 이름·상세 주소·회사/기관 이름만 골라 "
                '[{"type":"PERSON","text":"..."}] 형식의 JSON 배열로만 출력하세요.\n\n' + chunk,
                self.prompt_format,
            )
            entities = extract_json_array(self._complete(retry_prompt))
        return entities
