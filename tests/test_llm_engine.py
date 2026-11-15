"""로컬 LLM 프롬프트·출력 파싱 테스트(모델 없이 동작)."""
from __future__ import annotations

import pytest

import config
import llm_engine
from llm_engine import LocalLlm, LlmUnavailable, build_prompt, extract_json_array


def test_gemma_prompt_format():
    prompt = build_prompt("시스템", "사용자", "gemma")
    assert prompt.startswith("<start_of_turn>user\n")
    assert prompt.endswith("<start_of_turn>model\n")
    assert "<end_of_turn>" in prompt


def test_llama3_prompt_format():
    prompt = build_prompt("시스템", "사용자", "llama3")
    assert prompt.startswith("<|start_header_id|>system<|end_header_id|>")
    assert prompt.endswith("<|start_header_id|>assistant<|end_header_id|>\n\n")


def test_exaone_prompt_format():
    prompt = build_prompt("시스템", "사용자", "exaone")
    assert prompt.startswith("[|system|]시스템[|endofturn|]")
    assert "[|user|]사용자" in prompt
    assert prompt.endswith("[|assistant|]")


def test_chatml_prompt_format():
    prompt = build_prompt("시스템", "사용자", "chatml")
    assert "<|im_start|>system" in prompt
    assert "<|im_start|>assistant" in prompt
    assert prompt.endswith("\n")


def test_chunk_prompt_contains_rules(tmp_path):
    model = tmp_path / "fake.gguf"
    model.write_bytes(b"x")
    llm = LocalLlm(model, prompt_format="exaone")
    prompt = llm.build_chunk_prompt("원고 김민수는 출석했다.")
    assert "원고 김민수는 출석했다." in prompt
    assert "법원명" in prompt
    assert "JSON" in prompt


def test_parse_plain_json():
    raw = '[{"type":"PERSON","text":"김민수"}]'
    assert extract_json_array(raw) == [{"type": "PERSON", "text": "김민수"}]


def test_parse_fenced_json():
    raw = '```json\n[{"type":"ADDRESS","text":"서울 강남구"}]\n```'
    assert extract_json_array(raw)[0]["text"] == "서울 강남구"


def test_parse_with_preamble_and_trailing_text():
    raw = '찾았습니다:\n[{"type":"ORG","text":"한빛테크"}]\n이상입니다.'
    assert extract_json_array(raw)[0]["type"] == "ORG"


def test_parse_trailing_comma_and_single_quotes():
    raw = "[{'type':'PERSON','text':'이재훈'},]"
    parsed = extract_json_array(raw)
    assert parsed and parsed[0]["text"] == "이재훈"


def test_parse_empty_array():
    assert extract_json_array("[]") == []


def test_parse_garbage_returns_empty():
    assert extract_json_array("죄송합니다. 찾을 수 없습니다.") == []


def test_parse_dict_wrapper():
    raw = '{"entities":[{"type":"PERSON","text":"김민수"}]}'
    assert extract_json_array(raw)[0]["text"] == "김민수"


def test_missing_model_raises(tmp_path):
    llm = LocalLlm(tmp_path / "없는모델.gguf")
    with pytest.raises(LlmUnavailable):
        llm.load()


def test_model_spec_in_prompt_uses_config():
    assert "{chunk}" in config.LLM_USER_TEMPLATE
    assert "PERSON" in config.LLM_USER_TEMPLATE
