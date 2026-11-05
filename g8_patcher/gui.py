"""Small desktop interface; all firmware and network work runs off the UI thread."""

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .core import PatcherError, build_package, list_profiles
from .network import download_original


class PatcherWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.busy = False
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.profiles = list_profiles()
        self.result_folder: Path | None = None
        self.archive_path: str | None = None
        self.source_mode = tk.StringVar(value="download")
        self.source_path = tk.StringVar()
        self.output_path = tk.StringVar(value=str(Path.home() / "Downloads" / "G8-Compat"))
        self.profile_label = tk.StringVar(value=self.profiles[0]["label"])
        self.description = tk.StringVar(value=self.profiles[0]["description"])
        self.status = tk.StringVar(value="원본 준비 방법과 프로필을 선택하세요.")
        self.controls: list[ttk.Widget] = []
        root.title(f"G8 Compat Patcher {__version__}")
        root.geometry("820x710")
        root.minsize(720, 650)
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.option_add("*Font", ("Segoe UI", 10))
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Action.TButton", padding=(16, 8))
        outer = ttk.Frame(root, padding=22)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(6, weight=1)
        ttk.Label(outer, text="G8 Compat Patcher", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="G8 Galileo USB-C · 원본 129.60-1.5 기반 업데이트 ZIP 생성", wraplength=740).grid(
            row=1, column=0, sticky="w", pady=(3, 16)
        )

        source = ttk.LabelFrame(outer, text="1. 공식 원본 준비", padding=12)
        source.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        source.columnconfigure(0, weight=1)
        automatic = ttk.Radiobutton(source, text="GameSir 공식 서버에서 자동 다운로드", variable=self.source_mode,
                                    value="download", command=self._source_changed)
        automatic.grid(row=0, column=0, columnspan=2, sticky="w")
        local = ttk.Radiobutton(source, text="이미 받은 공식 ZIP 선택", variable=self.source_mode,
                                value="local", command=self._source_changed)
        local.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 4))
        self.source_entry = ttk.Entry(source, textvariable=self.source_path)
        self.source_entry.grid(row=2, column=0, sticky="ew", padx=(0, 8))
        self.source_button = ttk.Button(source, text="파일 선택", command=self._choose_source)
        self.source_button.grid(row=2, column=1)
        self.controls.extend((automatic, local, self.source_entry, self.source_button))

        options = ttk.LabelFrame(outer, text="2. 프로필과 저장 폴더", padding=12)
        options.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        options.columnconfigure(1, weight=1)
        ttk.Label(options, text="프로필").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.profile_box = ttk.Combobox(options, textvariable=self.profile_label, state="readonly",
                                      values=[profile["label"] for profile in self.profiles])
        self.profile_box.grid(row=0, column=1, columnspan=2, sticky="ew")
        self.profile_box.bind("<<ComboboxSelected>>", self._profile_changed)
        ttk.Label(options, textvariable=self.description, wraplength=630).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(6, 12)
        )
        ttk.Label(options, text="저장 폴더").grid(row=2, column=0, sticky="w", padx=(0, 12))
        output_entry = ttk.Entry(options, textvariable=self.output_path)
        output_entry.grid(row=2, column=1, sticky="ew", padx=(0, 8))
        output_button = ttk.Button(options, text="폴더 선택", command=self._choose_output)
        output_button.grid(row=2, column=2)
        self.controls.extend((self.profile_box, output_entry, output_button))

        action = ttk.Frame(outer)
        action.grid(row=4, column=0, sticky="ew")
        action.columnconfigure(1, weight=1)
        self.build_button = ttk.Button(action, text="업데이트 ZIP 만들기", style="Action.TButton", command=self._start)
        self.build_button.grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.progress = ttk.Progressbar(action, mode="indeterminate")
        self.progress.grid(row=0, column=1, sticky="ew")
        self.controls.append(self.build_button)
        ttk.Label(outer, textvariable=self.status, wraplength=740).grid(row=5, column=0, sticky="w", pady=(10, 8))

        result_frame = ttk.Frame(outer)
        result_frame.grid(row=6, column=0, sticky="nsew")
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        self.result_text = tk.Text(result_frame, height=10, wrap="word", relief="solid", borderwidth=1,
                                   padx=10, pady=10, state="disabled")
        self.result_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(result_frame, command=self.result_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.result_text.configure(yscrollcommand=scrollbar.set)
        buttons = ttk.Frame(outer)
        buttons.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        self.open_button = ttk.Button(buttons, text="결과 폴더 열기", state="disabled", command=self._open_result)
        self.open_button.pack(side="left")
        self.copy_button = ttk.Button(buttons, text="ZIP 경로 복사", state="disabled", command=self._copy_path)
        self.copy_button.pack(side="left", padx=(8, 0))
        self._set_result("원본의 해시를 확인한 뒤 새 ZIP을 생성합니다.\n생성된 ZIP은 GameSir 앱의 로컬 펌웨어 기능으로 설치합니다.")
        self._source_changed()
        self.root.after(100, self._poll)

    def _profile(self) -> dict:
        return next(profile for profile in self.profiles if profile["label"] == self.profile_label.get())

    def _profile_changed(self, _event=None):
        self.description.set(self._profile()["description"])

    def _source_changed(self):
        state = "normal" if not self.busy and self.source_mode.get() == "local" else "disabled"
        self.source_entry.configure(state=state)
        self.source_button.configure(state=state)

    def _choose_source(self):
        path = filedialog.askopenfilename(parent=self.root, title="공식 G8 원본 ZIP 선택",
                                         filetypes=[("ZIP 파일", "*.zip"), ("모든 파일", "*.*")])
        if path:
            self.source_path.set(path)

    def _choose_output(self):
        path = filedialog.askdirectory(parent=self.root, title="결과 저장 폴더 선택", mustexist=False)
        if path:
            self.output_path.set(path)

    def _set_result(self, text: str):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")

    def _set_busy(self, busy: bool):
        self.busy = busy
        for control in self.controls:
            control.configure(state="disabled" if busy else "normal")
        if not busy:
            self.profile_box.configure(state="readonly")
        self._source_changed()
        self.open_button.configure(state="normal" if not busy and self.result_folder else "disabled")
        self.copy_button.configure(state="normal" if not busy and self.archive_path else "disabled")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _start(self):
        if self.busy:
            return
        mode = self.source_mode.get()
        raw_source, raw_output = self.source_path.get().strip(), self.output_path.get().strip()
        if mode == "local" and not raw_source:
            messagebox.showerror("원본 파일 선택", "공식 원본 ZIP 파일을 선택해 주세요.", parent=self.root)
            return
        if not raw_output:
            messagebox.showerror("저장 폴더 선택", "결과를 저장할 폴더를 선택해 주세요.", parent=self.root)
            return
        try:
            output = Path(raw_output).expanduser().resolve()
            source = Path(raw_source).expanduser().resolve() if mode == "local" else None
        except (OSError, RuntimeError) as error:
            messagebox.showerror("경로 확인", str(error), parent=self.root)
            return
        profile = self._profile()["id"]
        self.result_folder = None
        self.archive_path = None
        self._set_result("")
        self._set_busy(True)
        self.status.set("작업을 시작합니다…")
        threading.Thread(target=self._worker, args=(source, output, profile), daemon=True).start()

    def _worker(self, source: Path | None, output: Path, profile: str):
        try:
            if source is None:
                self.events.put(("status", "GameSir 공식 원본을 내려받고 확인합니다…"))
                source = download_original(output / "originals")
            self.events.put(("status", "원본을 검증하고 업데이트 ZIP을 생성합니다…"))
            self.events.put(("complete", build_package(source, output, profile)))
        except (PatcherError, OSError) as error:
            self.events.put(("error", str(error)))
        except Exception as error:
            self.events.put(("error", f"예기치 않은 오류 ({type(error).__name__}): {error}"))

    def _poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "status":
                    self.status.set(str(value))
                elif event == "error":
                    self._set_result(str(value))
                    self.status.set("ZIP을 만들지 못했습니다. 아래 내용을 확인해 주세요.")
                    self._set_busy(False)
                elif event == "complete":
                    self._complete(value)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _complete(self, result: dict):
        self.archive_path = result["archive"]
        self.result_folder = Path(self.archive_path).parent
        profile = next(item for item in self.profiles if item["id"] == result["profile"])
        self.status.set(f"완료 · {profile['label']} · 펌웨어 해시 검증 통과")
        self._set_result(
            f"생성된 ZIP\n{self.archive_path}\n\n"
            "설치 방법\n"
            "1. ZIP을 휴대폰에 복사합니다. 파일명을 변경하거나 압축을 풀지 마세요.\n"
            "2. G8를 매핑 모드로 연결하고 GameSir 앱의 로컬 펌웨어 선택에서 ZIP을 선택합니다.\n"
            "3. 설치가 끝나면 G8를 분리했다 다시 연결하고 원하는 모드로 전환합니다.\n\n"
            f"{profile['description']}\n\n"
            "내부 펌웨어 버전은 129.60-1.5로 유지됩니다. ZIP 파일명의 버전은 업데이트 선택용입니다.\n\n"
            f"펌웨어 SHA-256\n{result['main_sha256']}\n\n"
            f"검증 기록\n{result['report']}"
        )
        self._set_busy(False)

    def _open_result(self):
        if self.result_folder is None:
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(self.result_folder))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.result_folder)])
        except OSError as error:
            messagebox.showerror("폴더 열기", str(error), parent=self.root)

    def _copy_path(self):
        if self.archive_path is not None:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.archive_path)
            self.status.set("ZIP 경로를 복사했습니다.")

    def _close(self):
        if self.busy:
            messagebox.showinfo("작업 진행 중", "현재 파일을 처리하고 있습니다. 작업이 끝나면 창을 닫아 주세요.", parent=self.root)
            return
        self.root.destroy()


def run():
    root = tk.Tk()
    PatcherWindow(root)
    root.mainloop()
