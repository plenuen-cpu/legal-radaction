"""법률문서 비식별화 — 윈도우용 GUI (CustomTkinter).

비개발자도 쓸 수 있게 PDF 선택 → 방식 선택 → 실행 → 결과 폴더 열기 흐름만 노출한다.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

import config
import pipeline
from model_manager import DownloadStatus, ModelError, ModelManager
from paths import app_dir, log_dir, settings_path

try:  # 선택 기능: 끌어다 놓기
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_IMPORTED = True
except Exception:  # pragma: no cover
    _DND_IMPORTED = False

APP_ICON = app_dir() / "assets" / "icon.ico"

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


class _BaseWindow(ctk.CTk):
    """tkinterdnd2가 있으면 끌어다 놓기를 함께 지원하는 창."""

    dnd_enabled = False

    def __init__(self):
        super().__init__()
        if _DND_IMPORTED:
            try:
                self.TkdndVersion = TkinterDnD._require(self)  # type: ignore[attr-defined]
                self.dnd_enabled = True
            except Exception:
                self.dnd_enabled = False


class LegalDeidApp(_BaseWindow):
    def __init__(self):
        super().__init__()
        self.title(f"{config.APP_TITLE}  ·  {config.APP_NAME}")
        self.geometry("900x760")
        self.minsize(820, 680)
        if APP_ICON.exists():
            try:
                self.iconbitmap(str(APP_ICON))
            except Exception:
                pass

        self.settings = self._load_settings()
        self.manager = ModelManager()
        self.files: List[Path] = []
        self.output_dir = ctk.StringVar(value=self.settings.output_dir)
        self.style_var = ctk.StringVar(value=self.settings.style)
        self.use_llm_var = ctk.BooleanVar(value=self.settings.use_llm)
        self.save_mapping_var = ctk.BooleanVar(value=self.settings.save_mapping)
        self.force_ocr_var = ctk.BooleanVar(value=False)
        self.model_var = ctk.StringVar(value=self._model_label(self.settings.model_key))
        self.status_var = ctk.StringVar(value="대기 중")
        self.model_status_var = ctk.StringVar(value="")
        self.queue: "queue.Queue" = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.last_output_dir: Optional[Path] = None
        self._model_labels = {
            self._model_label(key): key for key in config.MODEL_SPECS
        }

        self._build_ui()
        self._refresh_model_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._poll_queue)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("#1f4e79", "#12324d"))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="🛡️  법률문서 비식별화",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="white",
        ).grid(row=0, column=0, padx=20, pady=(16, 0), sticky="w")
        ctk.CTkLabel(
            header,
            text="PDF를 넣으면 로컬에서 OCR · AI 분석으로 개인정보를 가리고 TXT·워드로 저장합니다. 파일은 인터넷으로 나가지 않습니다.",
            font=ctk.CTkFont(size=12),
            text_color="#d6e4f0",
        ).grid(row=1, column=0, padx=20, pady=(2, 16), sticky="w")

        # 파일 선택
        files_frame = ctk.CTkFrame(self)
        files_frame.grid(row=1, column=0, padx=16, pady=(12, 6), sticky="nsew")
        files_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            files_frame, text="1. PDF 파일", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, padx=14, pady=(10, 2), sticky="w")

        list_wrap = ctk.CTkFrame(files_frame)
        list_wrap.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="nsew")
        list_wrap.grid_columnconfigure(0, weight=1)
        files_frame.grid_rowconfigure(1, weight=1)
        self.file_list = tk.Listbox(
            list_wrap,
            height=5,
            selectmode=tk.EXTENDED,
            font=("Malgun Gothic", 10),
            activestyle="none",
        )
        self.file_list.grid(row=0, column=0, padx=(0, 6), pady=6, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(list_wrap, command=self.file_list.yview)
        scrollbar.grid(row=0, column=1, padx=(0, 6), pady=6, sticky="ns")
        self.file_list.configure(yscrollcommand=scrollbar.set)

        buttons = ctk.CTkFrame(files_frame, fg_color="transparent")
        buttons.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="w")
        ctk.CTkButton(buttons, text="PDF 파일 선택", width=130, command=self._choose_files).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            buttons, text="선택 제거", width=100, fg_color="#5a5a5a", hover_color="#444444",
            command=self._remove_selected,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            buttons, text="모두 지우기", width=100, fg_color="#5a5a5a", hover_color="#444444",
            command=self._clear_files,
        ).pack(side="left", padx=4)
        hint = "여러 개를 한 번에 넣을 수 있습니다. " + (
            "파일을 창에 끌어다 놓아도 됩니다." if self.dnd_enabled else ""
        )
        ctk.CTkLabel(
            files_frame, text=hint, font=ctk.CTkFont(size=11), text_color=("#666666", "#9aa5b1")
        ).grid(row=3, column=0, padx=16, pady=(0, 8), sticky="w")

        if self.dnd_enabled:
            try:
                self.file_list.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
                self.file_list.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
            except Exception:
                pass

        # 본문: 옵션 + 로그
        body = ctk.CTkFrame(self)
        body.grid(row=2, column=0, padx=16, pady=6, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        options = ctk.CTkFrame(body)
        options.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")
        options.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            options, text="2. 비식별화 방식", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 4), sticky="w")

        radios = ctk.CTkFrame(options, fg_color="transparent")
        radios.grid(row=1, column=0, columnspan=2, padx=10, sticky="w")
        ctk.CTkRadioButton(
            radios, text="가명화  [이름1] [주소1] [회사1]", variable=self.style_var,
            value=config.STYLE_PSEUDONYM,
        ).pack(side="left", padx=8)
        ctk.CTkRadioButton(
            radios, text="마스킹  ***", variable=self.style_var, value=config.STYLE_MASK
        ).pack(side="left", padx=8)

        checks = ctk.CTkFrame(options, fg_color="transparent")
        checks.grid(row=2, column=0, columnspan=2, padx=10, pady=(4, 2), sticky="w")
        ctk.CTkCheckBox(
            checks, text="AI 문맥 분석 사용 (이름·주소 정확도 향상)",
            variable=self.use_llm_var, command=self._refresh_model_status,
        ).pack(side="left", padx=8)
        ctk.CTkCheckBox(
            checks, text="치환 대조표(CSV) 저장", variable=self.save_mapping_var
        ).pack(side="left", padx=8)
        ctk.CTkCheckBox(
            checks, text="스캔 PDF 강제 OCR", variable=self.force_ocr_var
        ).pack(side="left", padx=8)

        ctk.CTkLabel(options, text="로컬 AI 모델", font=ctk.CTkFont(size=12)).grid(
            row=3, column=0, padx=16, pady=(8, 0), sticky="w"
        )
        model_row = ctk.CTkFrame(options, fg_color="transparent")
        model_row.grid(row=3, column=1, padx=8, pady=(8, 0), sticky="ew")
        model_row.grid_columnconfigure(0, weight=1)
        self.model_combo = ctk.CTkComboBox(
            model_row,
            values=list(self._model_labels.keys()),
            variable=self.model_var,
            command=lambda _value: self._refresh_model_status(),
            state="readonly",
        )
        self.model_combo.grid(row=0, column=0, padx=4, sticky="ew")
        self.download_btn = ctk.CTkButton(
            model_row, text="모델 다운로드", width=120, command=self._download_model
        )
        self.download_btn.grid(row=0, column=1, padx=4)

        ctk.CTkLabel(
            options, textvariable=self.model_status_var, font=ctk.CTkFont(size=11),
            text_color=("#666666", "#9aa5b1"), anchor="w", justify="left",
        ).grid(row=4, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="w")

        ctk.CTkLabel(options, text="3. 저장 폴더", font=ctk.CTkFont(size=12)).grid(
            row=5, column=0, padx=16, pady=(2, 0), sticky="w"
        )
        out_row = ctk.CTkFrame(options, fg_color="transparent")
        out_row.grid(row=5, column=1, padx=8, pady=(2, 0), sticky="ew")
        out_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            out_row, textvariable=self.output_dir, placeholder_text="비워두면 원본 PDF와 같은 폴더에 저장"
        ).grid(row=0, column=0, padx=4, sticky="ew")
        ctk.CTkButton(out_row, text="찾아보기", width=90, command=self._choose_output).grid(
            row=0, column=1, padx=4
        )
        ctk.CTkLabel(
            options, text="", height=4
        ).grid(row=6, column=0)

        # 진행 + 로그
        progress_frame = ctk.CTkFrame(body)
        progress_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        progress_frame.grid_columnconfigure(0, weight=1)
        progress_frame.grid_rowconfigure(3, weight=1)

        self.progress = ctk.CTkProgressBar(progress_frame)
        self.progress.grid(row=0, column=0, columnspan=3, padx=12, pady=(12, 4), sticky="ew")
        self.progress.set(0)
        ctk.CTkLabel(
            progress_frame, textvariable=self.status_var, anchor="w",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, columnspan=3, padx=14, sticky="w")

        actions = ctk.CTkFrame(progress_frame, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=3, padx=10, pady=6, sticky="ew")
        self.start_btn = ctk.CTkButton(
            actions, text="비식별화 시작", width=160, height=38,
            font=ctk.CTkFont(size=14, weight="bold"), command=self._start,
        )
        self.start_btn.pack(side="left", padx=6)
        self.cancel_btn = ctk.CTkButton(
            actions, text="취소", width=90, height=38, fg_color="#8b2f2f",
            hover_color="#6d2424", command=self._cancel, state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=6)
        self.open_btn = ctk.CTkButton(
            actions, text="결과 폴더 열기", width=130, height=38,
            fg_color="#2f6b3a", hover_color="#24552d", command=self._open_output,
            state="disabled",
        )
        self.open_btn.pack(side="left", padx=6)

        self.log_box = ctk.CTkTextbox(progress_frame, height=170, font=ctk.CTkFont(size=12))
        self.log_box.grid(row=3, column=0, columnspan=3, padx=12, pady=(4, 12), sticky="nsew")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _model_label(key: str) -> str:
        spec = config.MODEL_SPECS.get(key)
        if not spec:
            return key
        mark = " · 기본" if key == config.DEFAULT_MODEL_KEY else ""
        return f"{spec.name} · {spec.size_gb}GB · {spec.license_label}{mark}"

    def _current_model_key(self) -> str:
        label = self.model_var.get()
        return self._model_labels.get(label, self.settings.model_key)

    def _log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message.rstrip() + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, message: str, progress: Optional[float] = None) -> None:
        self.status_var.set(message)
        if progress is not None:
            self.progress.set(max(0.0, min(progress, 1.0)))

    def _load_settings(self) -> config.Settings:
        try:
            data = json.loads(settings_path().read_text(encoding="utf-8"))
            return config.Settings.from_dict(data)
        except Exception:
            return config.Settings()

    def _save_settings(self) -> None:
        try:
            self.settings.output_dir = self.output_dir.get().strip()
            self.settings.style = self.style_var.get()
            self.settings.use_llm = bool(self.use_llm_var.get())
            self.settings.save_mapping = bool(self.save_mapping_var.get())
            self.settings.model_key = self._current_model_key()
            settings_path().write_text(
                json.dumps(self.settings.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _refresh_model_status(self) -> None:
        if not self.use_llm_var.get():
            self.model_status_var.set("AI 문맥 분석을 사용하지 않습니다(정규식만). 이름 일부가 남을 수 있습니다.")
            return
        key = self._current_model_key()
        info = self.manager.describe(key)
        spec = config.MODEL_SPECS.get(key)
        license_note = ""
        if spec:
            license_note = f" · 모델 라이선스: {spec.license_name}"
            if not spec.commercial_ok:
                license_note += " (연구·개인용, 업무용 사용 불가)"
        if info["ready"]:
            self.model_status_var.set(
                f"준비됨: {info['name']} ({info['size_gb']}GB){license_note} · {info['path']}"
            )
            self.download_btn.configure(state="disabled", text="모델 준비됨")
        else:
            self.model_status_var.set(
                f"모델이 없습니다. '모델 다운로드'를 누르면 {info['size_gb']}GB를 받습니다(1회만). "
                f"지금 실행하면 정규식만으로 처리됩니다.{license_note}"
            )
            self.download_btn.configure(state="normal", text="모델 다운로드")

    # ------------------------------------------------------------- actions
    def _choose_files(self) -> None:
        initial = self.settings.last_input_dir or str(Path.home())
        paths = filedialog.askopenfilenames(
            title="비식별화할 PDF 선택",
            initialdir=initial,
            filetypes=[("PDF 문서", "*.pdf"), ("모든 파일", "*.*")],
        )
        if paths:
            self._add_files([Path(p) for p in paths])
            self.settings.last_input_dir = str(Path(paths[0]).parent)

    def _on_drop(self, event) -> None:  # pragma: no cover - GUI 전용
        try:
            raw = self.tk.splitlist(event.data)
        except Exception:
            raw = str(event.data).split()
        self._add_files([Path(item) for item in raw if str(item).lower().endswith(".pdf")])

    def _add_files(self, paths: List[Path]) -> None:
        for path in paths:
            if path.suffix.lower() != ".pdf":
                continue
            if path in self.files:
                continue
            self.files.append(path)
            self.file_list.insert("end", f"{path.name}   —   {path.parent}")
        if self.files and not self.output_dir.get().strip():
            self.output_dir.set(str(self.files[0].resolve().parent))

    def _remove_selected(self) -> None:
        for index in reversed(self.file_list.curselection()):
            self.file_list.delete(index)
            del self.files[index]

    def _clear_files(self) -> None:
        self.file_list.delete(0, "end")
        self.files.clear()

    def _choose_output(self) -> None:
        initial = self.output_dir.get().strip() or str(Path.home())
        folder = filedialog.askdirectory(title="결과를 저장할 폴더", initialdir=initial)
        if folder:
            self.output_dir.set(folder)

    def _open_output(self) -> None:
        target = self.last_output_dir or Path(self.output_dir.get().strip() or Path.home())
        try:
            if os.name == "nt":
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            messagebox.showwarning("폴더 열기 실패", f"폴더를 열 수 없습니다.\n{target}\n\n{exc}")

    # --------------------------------------------------------------- run
    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self.files:
            messagebox.showinfo("파일 없음", "PDF 파일을 먼저 선택하세요.")
            return
        out_text = self.output_dir.get().strip()
        if out_text:
            out_dir = Path(out_text)
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("저장 폴더", f"저장 폴더를 사용할 수 없습니다.\n{exc}")
                return

        use_llm = bool(self.use_llm_var.get())
        model_key = self._current_model_key()
        if use_llm and not self.manager.is_ready(model_key):
            answer = messagebox.askyesnocancel(
                "AI 모델 없음",
                "로컬 AI 모델이 아직 없습니다.\n\n"
                "예: 정규식만으로 지금 처리 (이름 일부가 남을 수 있음)\n"
                "아니오: 모델 다운로드 (약 2.5GB, 1회)\n"
                "취소: 그만두기",
            )
            if answer is None:
                return
            if answer is False:
                self._download_model()
                return
            use_llm = False

        cfg = config.PipelineConfig(
            style=self.style_var.get(),
            use_llm=use_llm,
            model_key=model_key,
            force_ocr=bool(self.force_ocr_var.get()),
            save_mapping=bool(self.save_mapping_var.get()),
        )
        target_dir = Path(out_text) if out_text else None

        self.cancel_event.clear()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.open_btn.configure(state="disabled")
        self.progress.set(0)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self._save_settings()

        files = list(self.files)
        self.worker = threading.Thread(
            target=self._worker, args=(files, cfg, target_dir), daemon=True
        )
        self.worker.start()

    def _worker(self, files: List[Path], cfg: config.PipelineConfig, out_dir: Optional[Path]) -> None:
        ok_count = 0
        last_dir = out_dir
        for index, path in enumerate(files, start=1):
            if self.cancel_event.is_set():
                break
            self.queue.put(("log", f"[{index}/{len(files)}] {path.name}"))
            base = (index - 1) / len(files)

            def progress(message, current=0, total=100, _base=base, _n=len(files)):
                fraction = _base + (_n and (current / total) / _n or 0)
                self.queue.put(("progress", message, fraction))

            result = pipeline.process_pdf(
                path,
                cfg,
                output_dir=out_dir,
                progress=progress,
                cancel_check=self.cancel_event.is_set,
            )
            if result.error:
                self.queue.put(("log", f"    ✗ {result.error}"))
                continue
            ok_count += 1
            last_dir = result.txt_path.parent if result.txt_path else out_dir
            self.queue.put(("log", f"    ✓ {pipeline.summarize(result)}"))
            if result.txt_path:
                self.queue.put(("log", f"      TXT  : {result.txt_path}"))
            if result.docx_path:
                self.queue.put(("log", f"      DOCX : {result.docx_path}"))
            if result.mapping_path:
                self.queue.put(("log", f"      대조표: {result.mapping_path}"))
            for warning in result.warnings:
                self.queue.put(("log", f"      · {warning}"))
        self.queue.put(("done", ok_count, len(files), last_dir))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                if item[0] == "log":
                    self._log(item[1])
                elif item[0] == "progress":
                    self._set_status(item[1], item[2])
                elif item[0] == "done":
                    self._finish(item[1], item[2], item[3])
                elif item[0] == "download":
                    self._download_progress(item[1])
                elif item[0] == "download_done":
                    self._download_finished(item[1], item[2])
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _finish(self, ok_count: int, total: int, last_dir: Optional[Path]) -> None:
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        if last_dir:
            self.last_output_dir = Path(last_dir)
            self.open_btn.configure(state="normal")
        if ok_count:
            self._set_status(f"완료: {ok_count}/{total}건", 1.0)
        else:
            self._set_status("완료된 파일이 없습니다.", 0.0)
        self._save_settings()

    def _cancel(self) -> None:
        self.cancel_event.set()
        self._set_status("취소 중…")
        self._log("취소 요청됨. 현재 단계가 끝나면 중단합니다.")

    # ----------------------------------------------------------- download
    def _download_model(self) -> None:
        key = self._current_model_key()
        info = self.manager.describe(key)
        if info["ready"]:
            self._refresh_model_status()
            return
        if not messagebox.askyesno(
            "모델 다운로드",
            f"{info['name']} ({info['size_gb']}GB)를 지금 받을까요?\n\n"
            f"저장 위치: {info['directory']}\n"
            "한 번만 받으면 이후에는 인터넷 없이도 동작합니다.",
        ):
            return
        self.download_btn.configure(state="disabled", text="다운로드 중…")
        self.progress.set(0)
        self._set_status("모델 다운로드 준비 중…")
        threading.Thread(target=self._download_worker, args=(key,), daemon=True).start()

    def _download_worker(self, key: str) -> None:
        try:
            path = self.manager.ensure(
                key,
                progress=lambda status: self.queue.put(("download", status)),
                cancel_check=self.cancel_event.is_set,
            )
            self.queue.put(("download_done", path, None))
        except Exception as exc:
            self.queue.put(("download_done", None, str(exc)))

    def _download_progress(self, status: DownloadStatus) -> None:
        speed = status.speed_bps / (1024 * 1024)
        self._set_status(
            f"모델 다운로드 {status.percent:.1f}%  "
            f"({status.downloaded / (1024 ** 2):.0f}/{status.total / (1024 ** 2):.0f} MB, {speed:.1f} MB/s)",
            status.percent / 100,
        )

    def _download_finished(self, path, error) -> None:
        if error:
            self._set_status("모델 다운로드 실패", 0)
            self._log(f"모델 다운로드 실패: {error}")
            messagebox.showerror("모델 다운로드", str(error))
        else:
            self._set_status("모델 준비 완료", 1.0)
            self._log(f"모델 준비 완료: {path}")
        self._refresh_model_status()

    # --------------------------------------------------------------- exit
    def _on_close(self) -> None:
        self._save_settings()
        self.cancel_event.set()
        self.destroy()


def _enable_windows_dpi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass


def main() -> int:
    _enable_windows_dpi()
    try:
        app = LegalDeidApp()
    except Exception:
        log_dir().joinpath("gui_error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
