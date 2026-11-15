"""모델 다운로드 관리자 테스트(로컬 HTTP 서버로 이어받기·검증 확인)."""
from __future__ import annotations

import hashlib
import http.server
import os
import socketserver
import threading
from pathlib import Path

import pytest

import config
from model_manager import DownloadCancelled, ModelError, ModelManager


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    payload = b""
    support_range = True

    def log_message(self, *args):
        pass

    def do_GET(self):
        total = len(self.payload)
        start = 0
        header = self.headers.get("Range")
        if header and self.support_range and header.startswith("bytes="):
            start = int(header.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{total - 1}/{total}")
        else:
            self.send_response(200)
        body = self.payload[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def http_server():
    servers = []

    def factory(payload: bytes, support_range: bool = True):
        handler = type(
            "Handler", (_RangeHandler,), {"payload": payload, "support_range": support_range}
        )
        server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}/model.gguf"

    yield factory
    for server in servers:
        server.shutdown()
        server.server_close()


def make_spec(url: str, payload: bytes, key: str = "test-model") -> dict:
    return {
        key: config.ModelSpec(
            key=key,
            name="테스트 모델",
            repo="test/repo",
            filename="test.gguf",
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            prompt_format="exaone",
            params_b=0.1,
            languages="ko",
            license_name="test",
            license_url="",
            commercial_ok=True,
        )
    }


def patch_url(monkeypatch, spec, url):
    monkeypatch.setattr(type(spec), "url", property(lambda self: url))


def test_download_and_verify(tmp_path, http_server, monkeypatch):
    payload = b"x" * (300 * 1024)
    spec = make_spec("", payload)["test-model"]
    patch_url(monkeypatch, spec, http_server(payload))
    manager = ModelManager(tmp_path, {"test-model": spec})

    events = []
    path = manager.ensure("test-model", progress=events.append)
    assert path.exists()
    assert path.read_bytes() == payload
    assert events and events[-1].percent == 100.0
    assert manager.is_ready("test-model")


def test_resume_partial_download(tmp_path, http_server, monkeypatch):
    payload = b"y" * (200 * 1024)
    spec = make_spec("", payload)["test-model"]
    patch_url(monkeypatch, spec, http_server(payload))
    part = tmp_path / "test.gguf.part"
    part.write_bytes(payload[: 80 * 1024])

    manager = ModelManager(tmp_path, {"test-model": spec})
    path = manager.ensure("test-model")
    assert path.read_bytes() == payload


def test_checksum_mismatch_raises(tmp_path, http_server, monkeypatch):
    payload = b"z" * (120 * 1024)
    spec = make_spec("", payload)["test-model"]
    spec = config.ModelSpec(**{**spec.__dict__, "sha256": "0" * 64})
    patch_url(monkeypatch, spec, http_server(payload))
    manager = ModelManager(tmp_path, {"test-model": spec})
    with pytest.raises(ModelError):
        manager.ensure("test-model")


def test_cancel_stops_download(tmp_path, http_server, monkeypatch):
    payload = b"q" * (400 * 1024)
    spec = make_spec("", payload)["test-model"]
    patch_url(monkeypatch, spec, http_server(payload))
    manager = ModelManager(tmp_path, {"test-model": spec})
    with pytest.raises(DownloadCancelled):
        manager.ensure("test-model", cancel_check=lambda: True)


def test_find_local_accepts_renamed_gguf(tmp_path):
    manager = ModelManager(tmp_path)
    target = tmp_path / "직접넣은모델.gguf"
    with target.open("wb") as handle:
        handle.truncate(150 * 1024 * 1024)  # 희소 파일
    assert manager.find_local("exaone-3.5-2.4b-q4km") == target
    assert manager.is_ready("exaone-3.5-2.4b-q4km")


def test_unknown_model_key(tmp_path):
    manager = ModelManager(tmp_path)
    with pytest.raises(ModelError):
        manager.ensure("없는모델")


def test_model_specs_match_brief():
    gemma = config.MODEL_SPECS["gemma-3-4b-it-q4km"]
    llama = config.MODEL_SPECS["llama-3.2-3b-instruct-q4km"]
    exaone = config.MODEL_SPECS["exaone-3.5-2.4b-q4km"]
    qwen = config.MODEL_SPECS["qwen2.5-3b-instruct-q4km"]
    # 기본은 사용자가 고른 EXAONE(연구·개인용), 업무용은 Gemma/Llama 선택
    assert config.DEFAULT_MODEL_KEY == exaone.key
    assert exaone.prompt_format == "exaone"
    assert exaone.size_gb < 2.0
    assert exaone.recommended
    assert gemma.commercial_ok and llama.commercial_ok
    assert gemma.prompt_format == "gemma"
    assert not qwen.commercial_ok
    assert "q4_k_m" in qwen.filename
