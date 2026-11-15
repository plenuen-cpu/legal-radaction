"""로컬 LLM(GGUF) 다운로드·검증 관리.

인터넷이 없는 환경에서도 동작하도록, exe 옆 `models/` 폴더에 GGUF 파일을 두면
그대로 사용한다. 없을 때만 Hugging Face에서 내려받는다(이어받기·SHA-256 검증).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import config
from paths import models_dir as default_models_dir

CHUNK = 1024 * 256
USER_AGENT = f"{config.APP_NAME}/{config.APP_VERSION} (+local de-identification tool)"


class ModelError(RuntimeError):
    pass


class DownloadCancelled(ModelError):
    pass


@dataclass
class DownloadStatus:
    key: str
    path: Path
    total: int
    downloaded: int
    percent: float
    speed_bps: float


def _emit(callback, status: DownloadStatus) -> None:
    if callback:
        try:
            callback(status)
        except Exception:
            pass


def _sha256(path: Path, cancel_check=None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            if cancel_check and cancel_check():
                raise DownloadCancelled("다운로드가 취소되었습니다.")
            block = handle.read(CHUNK * 4)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class ModelManager:
    def __init__(self, directory: Optional[Path] = None, specs: Optional[Dict] = None):
        self._dir = Path(directory) if directory else default_models_dir()
        self.specs = specs or config.MODEL_SPECS

    @property
    def directory(self) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        return self._dir

    # -- 로컬 모델 찾기 -------------------------------------------------
    def list_local(self) -> List[Path]:
        try:
            return sorted(p for p in self.directory.glob("*.gguf") if p.is_file())
        except OSError:
            return []

    def find_local(self, key: Optional[str]) -> Optional[Path]:
        spec = self.specs.get(key or "")
        if spec is not None:
            candidate = self.directory / spec.filename
            if candidate.exists():
                size = candidate.stat().st_size
                if size == spec.size or size > 100 * 1024 * 1024:
                    return candidate
        # 사용자가 파일명을 바꿔 넣은 경우: 모델 폴더의 첫 GGUF를 사용
        for path in self.list_local():
            if path.stat().st_size > 100 * 1024 * 1024:
                return path
        return None

    def is_ready(self, key: Optional[str]) -> bool:
        return self.find_local(key) is not None

    def local_size_gb(self, path: Path) -> float:
        try:
            return round(path.stat().st_size / (1024 ** 3), 2)
        except OSError:
            return 0.0

    # -- 다운로드 -------------------------------------------------------
    def ensure(
        self,
        key: Optional[str],
        progress: Optional[Callable[[DownloadStatus], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Path:
        key = key or config.DEFAULT_MODEL_KEY
        spec = self.specs.get(key)
        if spec is None:
            raise ModelError(f"알 수 없는 모델입니다: {key}")
        existing = self.find_local(key)
        if existing:
            return existing

        target = self.directory / spec.filename
        part = target.with_suffix(target.suffix + ".part")
        resume_from = part.stat().st_size if part.exists() else 0

        request = urllib.request.Request(spec.url, headers={"User-Agent": USER_AGENT})
        if resume_from:
            request.add_header("Range", f"bytes={resume_from}-")

        started = time.time()
        downloaded = resume_from
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if resume_from and getattr(response, "status", 200) != 206:
                    # 서버가 이어받기를 지원하지 않으면 처음부터
                    resume_from = 0
                    downloaded = 0
                    part.unlink(missing_ok=True)
                total = int(response.headers.get("Content-Length") or 0) + resume_from
                if not total:
                    total = spec.size
                mode = "ab" if resume_from else "wb"
                try:
                    with part.open(mode) as handle:
                        while True:
                            if cancel_check and cancel_check():
                                raise DownloadCancelled("다운로드가 취소되었습니다.")
                            block = response.read(CHUNK)
                            if not block:
                                break
                            handle.write(block)
                            downloaded += len(block)
                            elapsed = max(time.time() - started, 0.001)
                            _emit(
                                progress,
                                DownloadStatus(
                                    key=key,
                                    path=part,
                                    total=total,
                                    downloaded=downloaded,
                                    percent=round(min(downloaded / total * 100, 100.0), 1) if total else 0.0,
                                    speed_bps=downloaded / elapsed,
                                ),
                            )
                except OSError as exc:
                    raise ModelError(
                        "모델 파일을 저장하지 못했습니다. 디스크 공간과 폴더 쓰기 권한을 확인하세요. "
                        f"({exc})"
                    ) from exc
        except urllib.error.HTTPError as exc:
            raise ModelError(f"모델 다운로드에 실패했습니다(HTTP {exc.code}). 네트워크를 확인하세요.") from exc
        except urllib.error.URLError as exc:
            raise ModelError(f"모델 다운로드에 실패했습니다: {exc.reason}") from exc

        if part.stat().st_size < spec.size * 0.95:
            raise ModelError(
                f"모델 파일이 완전하지 않습니다({part.stat().st_size:,} / {spec.size:,} bytes). 다시 시도하세요."
            )
        if cancel_check and cancel_check():
            raise DownloadCancelled("다운로드가 취소되었습니다.")

        _emit(
            progress,
            DownloadStatus(key, part, spec.size, downloaded, 100.0, 0.0),
        )
        actual = _sha256(part, cancel_check)
        if actual.lower() != spec.sha256.lower():
            broken = part.with_suffix(part.suffix + ".bad")
            shutil.move(str(part), str(broken))
            raise ModelError(
                "모델 파일 검증(SHA-256)에 실패했습니다. 파일이 손상되었을 수 있습니다. 다시 다운로드하세요."
            )
        part.replace(target)
        return target

    # -- 상태 -----------------------------------------------------------
    def describe(self, key: Optional[str]) -> dict:
        key = key or config.DEFAULT_MODEL_KEY
        spec = self.specs.get(key)
        path = self.find_local(key)
        return {
            "key": key,
            "name": spec.name if spec else key,
            "size_gb": spec.size_gb if spec else (self.local_size_gb(path) if path else 0),
            "ready": path is not None,
            "path": str(path) if path else "",
            "directory": str(self.directory),
        }
