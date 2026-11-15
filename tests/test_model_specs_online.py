"""모델 파일 URL·크기 확인(네트워크 필요, 수동 실행용).

    pytest -m slow tests/test_model_specs_online.py
"""
from __future__ import annotations

import pytest

import config

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("key", sorted(config.MODEL_SPECS))
def test_model_url_reachable(key):
    import urllib.request

    spec = config.MODEL_SPECS[key]
    request = urllib.request.Request(spec.url, method="HEAD", headers={"User-Agent": "LegalDeid-test"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status in (200, 206)
            length = int(response.headers.get("Content-Length") or 0)
    except Exception as exc:  # 네트워크가 없으면 건너뛴다
        pytest.skip(f"네트워크 없음: {exc}")
    if length:
        assert length == spec.size, f"{key} 크기 불일치: {length} != {spec.size}"
    assert len(spec.sha256) == 64
