
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import main as renderer_main
from engines import merge_engine



RENDER_MODES = ("วงกลมปกติ", "มีหนาม", "วงกลมเปิด", "วงกลมหมุน", "รอยวาด", "Merge Ball LV1-8")


def mode_ui_sections(mode):
    common = {"general", "video", "output"}
    if mode == "Merge Ball LV1-8":
        return common | {"merge"}
    sections = common | {"circle_physics", "ball_appearance", "colors", "ball_images", "audio", "pattern"}
    if mode == "มีหนาม":
        sections.add("spikes")
    elif mode == "วงกลมหมุน":
        sections.add("spikes")
        sections.add("rotating")
    elif mode == "วงกลมเปิด":
        sections.add("gap")
    elif mode == "รอยวาด":
        sections.add("trail")
    return sections

def apply_render_mode(mode):
    presets = {
        "วงกลมปกติ": {"spikes_enabled": False, "gap_enabled": False, "motion_trail": False, "rotation_speed": 0.0},
        "มีหนาม": {"spikes_enabled": True, "gap_enabled": False, "motion_trail": False, "rotation_speed": 0.0},
        "วงกลมเปิด": {"spikes_enabled": False, "gap_enabled": True, "motion_trail": False, "rotation_speed": 0.0},
        "วงกลมหมุน": {"spikes_enabled": True, "gap_enabled": False, "motion_trail": False, "rotation_speed": 0.85},
        "รอยวาด": {"spikes_enabled": False, "gap_enabled": False, "motion_trail": True, "rotation_speed": 0.0},
        "Merge Ball LV1-8": {"spikes_enabled": False, "gap_enabled": False, "motion_trail": False, "rotation_speed": 0.0, "merge_mode": True},
    }
    result = dict(presets.get(mode, presets["วงกลมปกติ"]))
    result.setdefault("merge_mode", False)
    return result

APP_PROGRESS_RE = re.compile(r"APP_PROGRESS\s+([0-9]+(?:\.[0-9]+)?)\s*(.*)")
DEFAULT_BALL_COLORS = [
    "#ff4d4d",
    "#4da6ff",
    "#5cff7a",
    "#ffd84d",
    "#c77dff",
    "#ff7ad9",
    "#61e7ff",
    "#ff9f43",
]


def runtime_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def melodies_dir():
    path = runtime_base_dir() / "melodies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def patterns_dir():
    path = runtime_base_dir() / "patterns"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ball_assets_dir():
    path = runtime_base_dir() / "assets" / "balls"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_renderer_args(config):
    mode = config.get("render_mode")
    spikes_on = bool(config.get("spikes_enabled", True))
    gap_on = bool(config.get("gap_enabled", False))
    trail_on = bool(config.get("motion_trail", True))
    rot_speed = float(config.get("rotation_speed", 0.85))

    if mode == "วงกลมปกติ":
        spikes_on = False
        gap_on = False
        trail_on = False
        rot_speed = 0.0
    elif mode == "มีหนาม":
        gap_on = False
        trail_on = False
        rot_speed = 0.0
    elif mode == "วงกลมเปิด":
        spikes_on = False
        trail_on = False
        rot_speed = 0.0
    elif mode == "วงกลมหมุน":
        gap_on = False
        trail_on = False
    elif mode == "รอยวาด":
        spikes_on = False
        gap_on = False
        rot_speed = 0.0

    spike_count = int(config.get("spike_count", 3)) if spikes_on else 0
    color_mode = config.get("ball_color_mode")
    if not color_mode:
        color_mode = "random" if config.get("random_ball_color", False) else "same"
    color_mode = str(color_mode)
    ball_colors = list(config.get("ball_colors") or DEFAULT_BALL_COLORS)

    return [
        "--spike-count", str(spike_count),
        "--ball-count", str(config.get("ball_count", 1)),
        "--gravity", str(config.get("gravity", 900)),
        "--initial-angle", str(config.get("initial_angle", 35)),
        "--initial-speed", str(config.get("initial_speed", 600)),
        "--speed-growth", str(config.get("speed_growth", 1.004)),
        "--max-speed", str(config.get("max_speed", 1750)),
        "--growth", str(config.get("ball_growth", 5.0)),
        "--smooth-growth-speed", str(config.get("smooth_growth_speed", 24.0)),
        "--motion-trail", "1" if trail_on else "0",
        "--show-ball-numbers", "1" if config.get("show_ball_numbers", True) else "0",
        "--ball-number-color", str(config.get("ball_number_color", "#ffffff")),
        "--trail-rainbow-speed", str(config.get("trail_rainbow_speed", 0.11)),
        "--trail-stamp-spacing", str(config.get("trail_stamp_spacing", 0.16)),
        "--base-radius", str(config.get("base_radius", 24.0)),
        "--arena-scale", str(config.get("arena_scale", 1.0)),
        "--gap-enabled", "1" if gap_on else "0",
        "--gap-size", str(config.get("gap_size", 45.0)),
        "--gap-position", str(config.get("gap_position", -90.0)),
        "--ball-lives", ",".join(str(max(1, int(v))) for v in (config.get("ball_lives") or [10])),
        "--pattern-file", str(config.get("pattern_file", "") or ""),
        "--rotation-speed", str(rot_speed),
        "--spike-depth", str(config.get("spike_depth", 34.0)),
        "--spike-width", str(config.get("spike_width", 15.0)),
        "--wall-restitution", str(config.get("wall_restitution", 0.985)),
        "--wall-friction", str(config.get("wall_friction", 0.0006)),
        "--air-drag", str(config.get("air_drag", 0.00018)),
        "--fps", str(config.get("fps", 240)),
        "--seconds", str(config.get("seconds", 20)),
        "--width", str(config.get("width", 1080)),
        "--height", str(config.get("height", 1920)),
        "--rainbow-border", "1" if config.get("rainbow_border", True) else "0",
        "--random-ball-color", "1" if color_mode == "random" else "0",
        "--ball-color-mode", color_mode,
        "--ball-colors", ",".join(ball_colors),
        "--show-hud", "1" if config.get("show_hud", False) else "0",
        "--audio", "1" if config.get("audio", True) else "0",
        "--melody-file", str(config.get("melody_file", "") or ""),
        "--instrument", str(config.get("instrument", "piano")),
        "--note-volume", str(config.get("note_volume", 0.8)),
        "--transpose", str(config.get("transpose", 0)),
        "--melody-loop", "1" if config.get("melody_loop", True) else "0",
        "--restart-melody-on-break", "1" if config.get("restart_melody_on_break", True) else "0",
        "--seed", str(config.get("seed", 11)),
        "--out", str(config.get("output", "circle_ball_final.mp4")),
        "--ball-images", ",".join(config.get("ball_images") or []),
    ]


def build_render_command(config, python_executable="python", main_script="main.py"):
    return [python_executable, main_script] + build_renderer_args(config)


def build_merge_renderer_args(config):
    return [
        "--out", str(config.get("output", "merge_ball.mp4")),
        "--assets", str(ball_assets_dir()),
        "--width", str(config.get("width", 1080)),
        "--height", str(config.get("height", 1920)),
        "--fps", str(config.get("fps", 60)),
        "--physics-hz", str(config.get("merge_physics_hz", max(240, int(config.get("fps", 60)) * 4))),
        "--seconds", str(config.get("seconds", 30)),
        "--spawn-interval", str(config.get("merge_spawn_interval", 0.8)),
        "--gravity", str(float(config.get("merge_gravity", 980))),
        "--bounce", str(config.get("merge_bounce", 0.78)),
        "--tank-scale", str(config.get("merge_tank_scale", 1.0)),
        "--pipe-clearance", str(float(config.get("merge_pipe_clearance", 8))),
        "--level-size-percent", str(float(config.get("merge_level_size_percent", 0))),
        "--merge-volume", str(config.get("merge_sound_volume", 0.8)),
        "--merge-sound-file", str(config.get("merge_sound_file", "")),
        "--victory-sound-file", str(config.get("merge_victory_sound_file", "")),
        "--seed", str(config.get("seed", 7)),
    ] + (["--merge-sound"] if config.get("merge_sound_enabled", True) else [])


def child_command(config, log_path):
    if config.get("render_mode") == "Merge Ball LV1-8":
        args = build_merge_renderer_args(config)
        if getattr(sys, "frozen", False):
            return [sys.executable, "--merge-renderer", "--log-file", str(log_path)] + args
        return [sys.executable, str(Path(__file__).resolve()), "--merge-renderer", "--log-file", str(log_path)] + args
    args = build_renderer_args(config)
    if getattr(sys, "frozen", False):
        return [sys.executable, "--renderer", "--log-file", str(log_path)] + args
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--renderer",
        "--log-file",
        str(log_path),
    ] + args


def parse_app_progress(line):
    match = APP_PROGRESS_RE.search(line)
    if not match:
        return None, None
    value = max(0.0, min(100.0, float(match.group(1))))
    stage = match.group(2).strip() or "กำลังทำงาน"
    return value, stage


def smooth_progress_step(current, target, easing=0.18, min_step=0.012):
    current = float(current)
    target = float(target)
    if target <= current:
        return current
    gap = target - current
    step = max(float(min_step), gap * float(easing))
    return min(target, current + step)


def run_renderer_child(argv):
    log_path = None
    args = list(argv)

    if "--log-file" in args:
        idx = args.index("--log-file")
        if idx + 1 < len(args):
            log_path = Path(args[idx + 1])
            del args[idx:idx + 2]

    stream = None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(log_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = stream
        sys.stderr = stream

    try:
        renderer_main.main(args)
    finally:
        if stream:
            stream.flush()
            stream.close()


def run_merge_renderer_child(argv):
    log_path = None
    args = list(argv)
    if "--log-file" in args:
        idx = args.index("--log-file")
        if idx + 1 < len(args):
            log_path = Path(args[idx + 1])
            del args[idx:idx + 2]
    stream = None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(log_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = stream; sys.stderr = stream
    try:
        merge_engine.main(args)
    finally:
        if stream:
            stream.flush(); stream.close()


class SliderField(ttk.Frame):
    def __init__(
        self,
        parent,
        label,
        from_,
        to,
        variable,
        command=None,
        resolution=1.0,
        digits=2,
    ):
        super().__init__(parent, style="Card.TFrame")
        self.variable = variable
        self.command = command
        self.digits = digits

        ttk.Label(self, text=label, style="Card.TLabel").pack(anchor="w")
        row = ttk.Frame(self, style="Card.TFrame")
        row.pack(fill="x", pady=(4, 0))

        self.scale = tk.Scale(
            row,
            from_=from_,
            to=to,
            orient="horizontal",
            resolution=resolution,
            showvalue=False,
            command=self._on_scale,
            bg="#1a1d24",
            fg="#f2f4f8",
            troughcolor="#20242d",
            highlightthickness=0,
            activebackground="#22c55e",
            length=305,
        )
        self.scale.pack(side="left", fill="x", expand=True)
        self.scale.set(float(variable.get()))

        self.value_label = ttk.Label(
            row,
            text=self._fmt(float(variable.get())),
            width=9,
            style="Card.TLabel",
        )
        self.value_label.pack(side="left", padx=(8, 0))

    def _fmt(self, value):
        if self.digits == 0:
            return str(int(round(value)))
        return f"{value:.{self.digits}f}"

    def _on_scale(self, value):
        value = float(value)
        if self.digits == 0:
            self.variable.set(str(int(round(value))))
        else:
            self.variable.set(f"{value:.{self.digits}f}")
        self.value_label.configure(text=self._fmt(value))
        if self.command:
            self.command()


class CircleRendererThaiApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("โปรแกรมบอลเด้งในวงกลม")
        self.geometry("1240x820")
        self.minsize(1050, 680)

        self.process = None
        self.log_path = None
        self.log_offset = 0
        self.output_dir = runtime_base_dir() / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.melody_map = {}
        self.pattern_map = {}
        self.preview_after_id = None
        self.preview_image = None
        self.preview_path = runtime_base_dir() / "preview_circle.png"

        self.reported_progress = 0.0
        self.displayed_progress = 0.0
        self.progress_animation_job = None

        self._configure_style()
        self._build_vars()
        self._build_ui()
        self.refresh_melodies(select_first=True)
        self.refresh_patterns(select_first=True)
        self.update_color_ui()
        self.schedule_preview()

        self.progress_animation_job = self.after(33, self.animate_progress)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _configure_style(self):
        self.configure(bg="#111318")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#111318")
        style.configure("Card.TFrame", background="#1a1d24")
        style.configure(
            "TLabel",
            background="#111318",
            foreground="#f2f4f8",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Card.TLabel",
            background="#1a1d24",
            foreground="#f2f4f8",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            background="#111318",
            foreground="#ffffff",
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "Sub.TLabel",
            background="#111318",
            foreground="#9ca3af",
            font=("Segoe UI", 9),
        )
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=8)
        style.configure(
            "Start.TButton",
            font=("Segoe UI Semibold", 13),
            padding=(18, 12),
            background="#22c55e",
            foreground="#ffffff",
        )
        style.map(
            "Start.TButton",
            background=[("active", "#16a34a"), ("disabled", "#3f4a44")],
            foreground=[("disabled", "#b5b5b5")],
        )
        style.configure("TCheckbutton", background="#1a1d24", foreground="#f2f4f8")
        style.map(
            "TCheckbutton",
            background=[("active", "#1a1d24")],
            foreground=[("active", "#ffffff")],
        )
        style.configure(
            "Green.Horizontal.TProgressbar",
            thickness=20,
            troughcolor="#20242d",
            background="#22c55e",
        )

    def _build_vars(self):
        self.render_mode = tk.StringVar(value="รอยวาด")
        self.merge_spawn_interval = tk.StringVar(value="0.8")
        self.merge_gravity = tk.StringVar(value="980")
        self.merge_bounce = tk.StringVar(value="0.78")
        self.merge_physics_hz = tk.StringVar(value="480")
        self.merge_tank_scale = tk.StringVar(value="1.0")
        self.merge_pipe_clearance = tk.StringVar(value="8")
        self.merge_sound_enabled = tk.BooleanVar(value=True)
        self.merge_sound_volume = tk.StringVar(value="0.80")
        self.merge_sound_file = tk.StringVar(value="")
        self.merge_victory_sound_file = tk.StringVar(value="")
        self.merge_level_size_percent = tk.StringVar(value="15")
        self.show_ball_numbers = tk.BooleanVar(value=True)
        self.ball_number_color = tk.StringVar(value="#ffffff")
        self.spikes_enabled = tk.BooleanVar(value=False)
        self.spike_count = tk.StringVar(value="3")
        self.ball_count = tk.StringVar(value="1")
        self.ball_life_vars = [tk.StringVar(value="10") for _ in range(8)]
        self.ball_color_vars = [tk.StringVar(value=color) for color in DEFAULT_BALL_COLORS]
        self.color_buttons = []
        self.gap_fit_status = tk.StringVar(value="กำลังคำนวณ...")

        self.gap_enabled = tk.BooleanVar(value=False)
        self.gap_size = tk.StringVar(value="45")
        self.gap_position = tk.StringVar(value="-90")

        self.gravity = tk.StringVar(value="900")
        self.initial_angle = tk.StringVar(value="35")
        self.initial_speed = tk.StringVar(value="600")
        self.speed_growth = tk.StringVar(value="1.004")
        self.max_speed = tk.StringVar(value="1750")
        self.ball_growth = tk.StringVar(value="5.0")
        self.smooth_growth_speed = tk.StringVar(value="24.0")
        self.motion_trail = tk.BooleanVar(value=False)
        self.trail_rainbow_speed = tk.StringVar(value="0.11")
        self.trail_stamp_spacing = tk.StringVar(value="0.16")
        self.base_radius = tk.StringVar(value="24")
        self.arena_scale = tk.StringVar(value="1.0")
        self.rotation_speed = tk.StringVar(value="0.0")
        self.spike_depth = tk.StringVar(value="34")
        self.spike_width = tk.StringVar(value="15")
        self.wall_restitution = tk.StringVar(value="0.985")
        self.wall_friction = tk.StringVar(value="0.0006")
        self.air_drag = tk.StringVar(value="0.00018")

        self.fps = tk.StringVar(value="240")
        self.seconds = tk.StringVar(value="20")
        self.width = tk.StringVar(value="1080")
        self.height = tk.StringVar(value="1920")
        self.seed = tk.StringVar(value="11")

        self.rainbow_border = tk.BooleanVar(value=True)
        self.show_hud = tk.BooleanVar(value=False)

        self.ball_color_mode = tk.StringVar(value="per-ball")

        self.audio = tk.BooleanVar(value=True)
        self.melody_choice = tk.StringVar(value="ทำนองในตัว")
        self.pattern_choice = tk.StringVar(value="ไม่ใช้แพทเทิร์น")
        self.instrument = tk.StringVar(value="piano")
        self.note_volume = tk.StringVar(value="0.80")
        self.transpose = tk.StringVar(value="0")
        self.melody_loop = tk.BooleanVar(value=True)
        self.restart_melody_on_break = tk.BooleanVar(value=True)

        self.output = tk.StringVar(
            value=str((self.output_dir / "circle_ball_final.mp4").resolve())
        )

        self.ball_image_paths = [tk.StringVar(value="") for _ in range(8)]
        self.ball_image_labels = []

        self.status = tk.StringVar(value="พร้อมใช้งาน")
        self.stage = tk.StringVar(value="ยังไม่เริ่ม")
        self.progress_text = tk.StringVar(value="0.00%")
        self.progress_big_text = tk.StringVar(value="")
        self.preview_info_text = tk.StringVar(value="")

    def _build_ui(self):
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        # 1. Header (top)
        header = ttk.Frame(outer)
        header.pack(side="top", fill="x", pady=(0, 6))
        ttk.Label(
            header,
            text="โปรแกรมบอลเด้งในวงกลม",
            style="Header.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="พรีวิวภาพนิ่ง • ปรับค่าด้วยสไลเดอร์ • เสียงเด้งตามโน้ต MIDI / JSON",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # 2. Bottom dock: packed FIRST with side="bottom" so it is NEVER pushed off-screen
        bottom_dock = ttk.Frame(outer)
        bottom_dock.pack(side="bottom", fill="x", pady=(8, 0))

        # Action buttons row
        action = ttk.Frame(bottom_dock)
        action.pack(fill="x", pady=(0, 4))

        self.start_btn = ttk.Button(
            action,
            text="▶ เริ่มเรนเดอร์",
            style="Start.TButton",
            command=self.start_render,
        )
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(
            action,
            text="■ หยุด",
            command=self.stop_render,
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(8, 0))

        ttk.Button(
            action,
            text="อัปเดตพรีวิว",
            command=self.generate_preview,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            action,
            text="เปิดโฟลเดอร์ Output",
            command=self.open_output_folder,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            action,
            text="เลือกไฟล์ปลายทาง",
            command=self.browse_output,
        ).pack(side="left", padx=(8, 0))

        ttk.Label(
            action,
            textvariable=self.status,
            style="Sub.TLabel",
        ).pack(side="right")

        # Stage and progress text row
        stage_row = ttk.Frame(bottom_dock)
        stage_row.pack(fill="x", pady=(2, 2))
        ttk.Label(stage_row, textvariable=self.stage).pack(side="left")
        ttk.Label(stage_row, textvariable=self.progress_text).pack(side="right")

        # ---- Big progress display ----
        self.progress_big_label = tk.Label(
            bottom_dock,
            textvariable=self.progress_big_text,
            bg="#111318",
            fg="#22c55e",
            font=("Segoe UI Semibold", 13),
            anchor="w",
        )
        self.progress_big_label.pack(fill="x", pady=(0, 2))

        self.progress = ttk.Progressbar(
            bottom_dock,
            maximum=100.0,
            style="Green.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x")

        # Compact log area
        log_header = ttk.Frame(bottom_dock)
        log_header.pack(fill="x", pady=(4, 2))
        ttk.Label(
            log_header,
            text="บันทึกการทำงาน",
            style="Sub.TLabel",
        ).pack(side="left")

        self.log = tk.Text(
            bottom_dock,
            height=3,
            bg="#0b0d11",
            fg="#d1d5db",
            insertbackground="#ffffff",
            relief="flat",
            font=("Consolas", 9),
            wrap="word",
        )
        self.log.pack(fill="x")
        self.log.configure(state="disabled")

        # 3. Center content area (packed with side="top", fill="both", expand=True)
        content = ttk.Frame(outer)
        content.pack(side="top", fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=0)
        content.rowconfigure(0, weight=1)

        control_card = ttk.Frame(content, style="Card.TFrame", padding=14)
        control_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        preview_card = ttk.Frame(content, style="Card.TFrame", padding=14)
        preview_card.grid(row=0, column=1, sticky="nsew")

        self._build_control_panel(control_card)
        self._build_preview_panel(preview_card)

        # Apply initial mode defaults and update UI visibility
        self.apply_selected_render_mode()

    def _build_control_panel(self, parent):
        canvas = tk.Canvas(parent, bg="#1a1d24", highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas, style="Card.TFrame")

        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        def on_body_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfigure(window, width=event.width)

        body.bind("<Configure>", on_body_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        canvas.bind_all(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"),
        )

        # ---- Store body reference for section management ----
        self._ctrl_body = body

        # ============================================================
        # Section: เลือกโหมด (always visible)
        # ============================================================
        self._section(body, "เลือกรูปแบบการเรนเดอร์")
        mode_box = ttk.Frame(body, style="Card.TFrame")
        mode_box.pack(fill="x", pady=(0, 10))
        ttk.Label(mode_box, text="เลือกแบบหลักก่อน แล้วค่อยปรับกฎเสริมด้านล่าง", style="Card.TLabel").pack(anchor="w", pady=(0, 5))
        mode_combo = ttk.Combobox(mode_box, textvariable=self.render_mode, values=RENDER_MODES, state="readonly")
        mode_combo.pack(fill="x")
        mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_selected_render_mode())

        # ============================================================
        # Section: Merge Ball LV1-8
        # ============================================================
        self.sec_merge = ttk.LabelFrame(body, text="ตั้งค่า Merge Ball LV1-8", padding=8)
        merge_box = self.sec_merge
        # Don't pack yet — _update_visible_sections() will handle it
        ttk.Label(merge_box, text="รูปบอลอ่านจาก assets/balls/1.webp ถึง 8.webp", style="Card.TLabel").pack(anchor="w")
        merge_row = ttk.Frame(merge_box, style="Card.TFrame")
        merge_row.pack(fill="x", pady=(6, 2))
        ttk.Label(merge_row, text="ปล่อย LV1 ทุก (วินาที)", style="Card.TLabel").pack(side="left")
        ttk.Entry(merge_row, textvariable=self.merge_spawn_interval, width=8).pack(side="left", padx=6)
        ttk.Button(merge_row, text="เปิดโฟลเดอร์รูป LV1-8", command=lambda: self._open_folder(ball_assets_dir())).pack(side="left", padx=6)
        ttk.Button(merge_box, text="เลือกรูปให้ LV1-8", command=self.choose_merge_ball_images).pack(anchor="w", pady=(4, 6))
        mg = ttk.Frame(merge_box, style="Card.TFrame"); mg.pack(fill="x")
        self._grid_entry(mg, "Gravity Merge", self.merge_gravity, 0, 0)
        self._grid_entry(mg, "Bounce Merge", self.merge_bounce, 0, 2)
        self._grid_entry(mg, "Physics Hz", self.merge_physics_hz, 1, 0)
        self._grid_entry(mg, "ขนาดถัง", self.merge_tank_scale, 1, 2)
        self._grid_entry(mg, "ช่องเผื่อท่อ (px)", self.merge_pipe_clearance, 2, 0)
        self._grid_entry(mg, "ขนาด LV2-8 เพิ่ม (%)", self.merge_level_size_percent, 2, 2)
        snd = ttk.LabelFrame(merge_box, text="เสียงตอน Merge", padding=6); snd.pack(fill="x", pady=(8,0))
        ttk.Checkbutton(snd, text="เปิดเสียงตอน Merge", variable=self.merge_sound_enabled).pack(anchor="w")
        sr = ttk.Frame(snd, style="Card.TFrame"); sr.pack(fill="x", pady=4)
        ttk.Label(sr, text="ความดัง 0-1", style="Card.TLabel").pack(side="left")
        ttk.Entry(sr, textvariable=self.merge_sound_volume, width=7).pack(side="left", padx=5)
        ttk.Button(sr, text="เลือกเสียง Merge", command=self.choose_merge_sound).pack(side="left", padx=5)
        ttk.Button(sr, text="เลือกเสียง Victory", command=self.choose_victory_sound).pack(side="left", padx=5)
        ttk.Label(snd, textvariable=self.merge_sound_file, style="Card.TLabel").pack(anchor="w")
        ttk.Label(snd, textvariable=self.merge_victory_sound_file, style="Card.TLabel").pack(anchor="w")
        ttk.Label(merge_box, text="LV1 คงขนาดเดิมเสมอ • % ขนาดใช้เฉพาะ LV2-LV8", style="Card.TLabel").pack(anchor="w", pady=(6,0))
        ttk.Label(merge_box, text="ค่าชุดนี้ใช้เฉพาะโหมด Merge และไม่กระทบโหมดวงกลมอื่น", style="Card.TLabel").pack(anchor="w", pady=(3,0))
        self._help(body, "โหมด Merge: LV เดียวกันชนกันจะรวมเป็นระดับถัดไป และ LV8 + LV8 = Victory")

        # ============================================================
        # Section: การตั้งค่าทั่วไปและวิดีโอ (ความยาว, ความคมชัด, ตัวเลข & HUD)
        # ============================================================
        self.sec_general = ttk.Frame(body, style="Card.TFrame")
        self.sec_video = self.sec_general       # alias
        self.sec_appearance = self.sec_general  # alias
        self._section(self.sec_general, "การตั้งค่าทั่วไปและวิดีโอ (ความยาว, ความคมชัด, ตัวเลข & HUD)")

        gen_box = ttk.Frame(self.sec_general, style="Card.TFrame")
        gen_box.pack(fill="x", pady=(0, 6))

        # 1. ความยาวและ Seed
        self._grid_entry(gen_box, "เวลา (วินาที)", self.seconds, 0, 0)
        self._grid_entry(gen_box, "Seed สุ่ม", self.seed, 0, 2)

        # 2. ความคมชัด / ความละเอียด
        self._grid_entry(gen_box, "กว้าง", self.width, 1, 0)
        self._grid_entry(gen_box, "สูง", self.height, 1, 2)
        self._grid_entry(gen_box, "FPS", self.fps, 2, 0)

        preset_row = ttk.Frame(self.sec_general, style="Card.TFrame")
        preset_row.pack(fill="x", pady=(4, 8))
        ttk.Button(preset_row, text="📱 TikTok 1080×1920 (240 FPS)", command=self.apply_tiktok_preset).pack(side="left")
        ttk.Button(preset_row, text="🖥️ 1920×1080 (60 FPS)", command=lambda: self.apply_resolution_preset(1920, 1080, 60)).pack(side="left", padx=(6, 0))
        ttk.Button(preset_row, text="⏹️ 1080×1080 (60 FPS)", command=lambda: self.apply_resolution_preset(1080, 1080, 60)).pack(side="left", padx=(6, 0))

        # 3. การแสดงผลตัวเลขและ HUD
        disp_box = ttk.LabelFrame(self.sec_general, text="ตัวเลขบนลูกบอล, HUD และขอบวงกลม", padding=8)
        disp_box.pack(fill="x", pady=(4, 4))
        num_row = ttk.Frame(disp_box, style="Card.TFrame")
        num_row.pack(fill="x", pady=2)
        ttk.Checkbutton(num_row, text="แสดงตัวเลข HP บนลูกบอล", variable=self.show_ball_numbers, command=self.schedule_preview).pack(side="left")
        tk.Button(num_row, text="เลือกสีตัวเลข", command=self.pick_ball_number_color, relief="flat").pack(side="left", padx=(10, 0))

        hud_row = ttk.Frame(disp_box, style="Card.TFrame")
        hud_row.pack(fill="x", pady=2)
        ttk.Checkbutton(hud_row, text="แสดง HUD ข้อความจำนวนลูกบอล", variable=self.show_hud, command=self.schedule_preview).pack(side="left")
        ttk.Checkbutton(hud_row, text="เปิดขอบวงกลมสีรุ้ง", variable=self.rainbow_border, command=self.schedule_preview).pack(side="left", padx=(16, 0))

        # ============================================================
        # Section: ฟิสิกส์ลูกบอลและสนาม
        # ============================================================
        self.sec_physics = ttk.Frame(body, style="Card.TFrame")
        self._section(self.sec_physics, "ฟิสิกส์ลูกบอลและสนาม")
        self._slider(self.sec_physics, "จำนวนลูกบอล", 1, 8, self.ball_count, 1, 0)

        ttk.Label(
            self.sec_physics,
            text="พลังชีวิตของแต่ละลูก (HP)",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(2, 4))
        life_grid = ttk.Frame(self.sec_physics, style="Card.TFrame")
        life_grid.pack(fill="x", pady=(0, 8))
        for i, variable in enumerate(self.ball_life_vars):
            row = i // 4
            col = (i % 4) * 2
            self._grid_entry(
                life_grid,
                f"HP ลูกที่ {i + 1}",
                variable,
                row,
                col,
            )

        self._help(self.sec_physics, "มุมเริ่มต้นกำหนดทิศที่ลูกบอลพุ่งตอนเริ่ม")
        self._slider(self.sec_physics, "มุมเริ่มต้น", -180, 180, self.initial_angle, 1, 0)
        self._slider(self.sec_physics, "ความเร็วเริ่มต้น", 150, 1300, self.initial_speed, 10, 0)
        self._help(self.sec_physics, "ค่ายิ่งสูง ลูกบอลเริ่มต้นยิ่งเร็ว")
        self._slider(self.sec_physics, "แรงโน้มถ่วง", 0, 1800, self.gravity, 10, 0)
        self._help(self.sec_physics, "ค่ายิ่งสูง ลูกบอลถูกดึงลงด้านล่างแรงขึ้น")
        self._slider(self.sec_physics, "ตัวคูณความเร็วเมื่อเด้ง", 1.000, 1.020, self.speed_growth, 0.001, 3)
        self._help(self.sec_physics, "ค่ายิ่งสูง ทุกครั้งที่เด้งลูกบอลจะเร่งความเร็วมากขึ้น")
        self._slider(self.sec_physics, "ความเร็วสูงสุด", 400, 2600, self.max_speed, 10, 0)
        self._slider(self.sec_physics, "ขนาดลูกบอลเริ่มต้น", 8, 90, self.base_radius, 1, 0)
        self._slider(self.sec_physics, "โตขึ้นทุกครั้งที่เด้ง", 0, 20, self.ball_growth, 0.25, 2)
        self._help(self.sec_physics, "ค่ายิ่งสูง ขนาดเป้าหมายจะเพิ่มมากขึ้นทุกครั้งที่ชน")
        self._slider(self.sec_physics, "ความเร็วการค่อย ๆ โต", 1, 80, self.smooth_growth_speed, 1, 0)
        self._help(self.sec_physics, "ค่ายิ่งสูง ลูกบอลจะขยายเข้าหาขนาดใหม่เร็วขึ้น")
        self._slider(self.sec_physics, "ขนาดสนามวงกลม", 0.60, 1.08, self.arena_scale, 0.01, 2)

        self._slider(self.sec_physics, "แรงเด้งกำแพง", 0.80, 1.02, self.wall_restitution, 0.001, 3)
        self._help(self.sec_physics, "ค่ายิ่งสูง ลูกบอลรักษาแรงและดีดออกจากกำแพงมากขึ้น")
        self._slider(self.sec_physics, "แรงเสียดทานกำแพง", 0.0, 0.02, self.wall_friction, 0.0001, 4)
        self._slider(self.sec_physics, "แรงต้านอากาศ", 0.0, 0.01, self.air_drag, 0.0001, 4)

        # ============================================================
        # Section: รอยการเคลื่อนที่ (สำหรับโหมด รอยวาด)
        # ============================================================
        self.sec_trail = ttk.Frame(body, style="Card.TFrame")
        self._section(self.sec_trail, "การตั้งค่ารอยวาดการเคลื่อนที่")
        trail_wrap = ttk.Frame(self.sec_trail, style="Card.TFrame")
        trail_wrap.pack(fill="x", pady=(0, 4))
        ttk.Label(
            trail_wrap,
            text="รอยใช้สีและขนาดของลูกบอล ณ ขณะนั้น และจะวาดวงซ้อนถาวร",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        self._slider(self.sec_trail, "ความเร็วสีรุ้ง", 0.01, 0.40, self.trail_rainbow_speed, 0.01, 2)
        self._help(self.sec_trail, "ค่ายิ่งสูง สีของลูกบอลและรอยจะเปลี่ยนผ่านสีรุ้งเร็วขึ้น")
        self._slider(self.sec_trail, "ระยะห่างวงรอย", 0.04, 0.40, self.trail_stamp_spacing, 0.01, 2)

        # ============================================================
        # Section: ช่องว่างของวงกลม (สำหรับโหมด วงกลมเปิด)
        # ============================================================
        self.sec_gap = ttk.Frame(body, style="Card.TFrame")
        self._section(self.sec_gap, "การตั้งค่าช่องว่างของวงกลม")
        self._slider(self.sec_gap, "ขนาดช่องว่าง (องศา)", 5, 180, self.gap_size, 1, 0)
        self._slider(self.sec_gap, "ตำแหน่งช่องว่าง (องศา)", -180, 180, self.gap_position, 1, 0)

        gap_status = ttk.Frame(self.sec_gap, style="Card.TFrame")
        gap_status.pack(fill="x", pady=(2, 8))
        ttk.Label(
            gap_status,
            text="เช็กช่องว่าง / ขนาดลูกบอล",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w")
        ttk.Label(
            gap_status,
            textvariable=self.gap_fit_status,
            style="Card.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # ============================================================
        # Section: หนามของวงกลม (สำหรับโหมด มีหนาม และ วงกลมหมุน)
        # ============================================================
        self.sec_spikes = ttk.Frame(body, style="Card.TFrame")
        self._section(self.sec_spikes, "การตั้งค่าหนาม")
        self._slider(self.sec_spikes, "จำนวนหนาม", 1, 12, self.spike_count, 1, 0)
        self._help(self.sec_spikes, "ยิ่งมีหนามมาก โอกาสชนและเสีย HP ยิ่งสูง")
        self._slider(self.sec_spikes, "ความลึกหนาม", 8, 80, self.spike_depth, 1, 0)
        self._slider(self.sec_spikes, "ความกว้างหนาม", 5, 40, self.spike_width, 1, 0)

        # ============================================================
        # Section: การหมุนของวงกลม (สำหรับโหมด วงกลมหมุน)
        # ============================================================
        self.sec_rotating = ttk.Frame(body, style="Card.TFrame")
        self._section(self.sec_rotating, "การหมุนของวงกลม")
        self._slider(self.sec_rotating, "ความเร็วหมุนวงกลม/หนาม", -3.0, 3.0, self.rotation_speed, 0.05, 2)
        self._help(self.sec_rotating, "ค่าบวก = หมุนตามเข็ม, ค่าลบ = หมุนทวนเข็ม; ยิ่งสูงยิ่งหมุนเร็ว")

        # ============================================================
        # Section: รูปลักษณ์ลูกบอล (สีและรูปภาพ)
        # ============================================================
        self.sec_ball_appearance = ttk.Frame(body, style="Card.TFrame")
        self.sec_colors = self.sec_ball_appearance       # alias
        self.sec_ball_images = self.sec_ball_appearance  # alias
        self._section(self.sec_ball_appearance, "รูปลักษณ์ลูกบอล (รูปภาพ & สี)")

        # 1. รูปภาพบนลูกบอล
        img_box = ttk.LabelFrame(self.sec_ball_appearance, text="🖼️ รูปภาพบนลูกบอล (Ball Skins)", padding=8)
        img_box.pack(fill="x", pady=(0, 8))
        ttk.Label(
            img_box,
            text="ใส่รูปให้กับลูกบอลที่ต้องการ (ลูกที่ใส่รูปจะตัดขอบขาวออกอัตโนมัติ)",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        self.ball_image_labels = []
        for i in range(8):
            row_frame = ttk.Frame(img_box, style="Card.TFrame")
            row_frame.pack(fill="x", pady=2)
            ttk.Button(
                row_frame,
                text=f"เลือกรูปลูก {i + 1}",
                command=lambda idx=i: self.choose_ball_image(idx),
            ).pack(side="left")
            ttk.Button(
                row_frame,
                text="ล้าง",
                command=lambda idx=i: self.clear_ball_image(idx),
            ).pack(side="left", padx=(4, 0))
            lbl = ttk.Label(row_frame, text="ไม่มีรูป (ใช้สีปกติ)", style="Card.TLabel")
            lbl.pack(side="left", padx=(8, 0))
            self.ball_image_labels.append(lbl)

        # 2. สีลูกบอลแต่ละลูก
        color_box = ttk.LabelFrame(self.sec_ball_appearance, text="🎨 สีลูกบอลแต่ละลูก (ใช้กรณีไม่ได้ใส่รูป)", padding=8)
        color_box.pack(fill="x", pady=(0, 4))
        ttk.Label(
            color_box,
            text="กดเพื่อเปลี่ยนสีลูกบอล (แสดงเมื่อไม่มีรูปภาพ)",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        color_grid = ttk.Frame(color_box, style="Card.TFrame")
        color_grid.pack(fill="x")
        self.color_buttons = []
        for i, variable in enumerate(self.ball_color_vars):
            row = i // 4
            col = (i % 4)
            btn = tk.Button(
                color_grid,
                text=f"ลูกที่ {i + 1}",
                width=10,
                relief="flat",
                command=lambda idx=i: self.pick_ball_color(idx),
            )
            btn.grid(row=row, column=col, sticky="w", padx=(0, 6), pady=4)
            self.color_buttons.append(btn)

        # ============================================================
        # Section: เสียงเด้ง / ทำนอง
        # ============================================================
        self.sec_audio = ttk.Frame(body, style="Card.TFrame")
        self._section(self.sec_audio, "เสียงเด้ง / ทำนอง")
        audio_wrap = ttk.Frame(self.sec_audio, style="Card.TFrame")
        audio_wrap.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            audio_wrap,
            text="เปิดเสียงเด้งตามโน้ต",
            variable=self.audio,
        ).pack(anchor="w")

        ttk.Label(
            audio_wrap,
            text="ทำนอง (MIDI / JSON)",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(10, 4))

        self.melody_combo = ttk.Combobox(
            audio_wrap,
            textvariable=self.melody_choice,
            state="readonly",
            width=35,
        )
        self.melody_combo.pack(fill="x")

        melody_buttons = ttk.Frame(audio_wrap, style="Card.TFrame")
        melody_buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(
            melody_buttons,
            text="นำเข้า MIDI / JSON",
            command=self.import_melody,
        ).pack(side="left")
        ttk.Button(
            melody_buttons,
            text="รีเฟรช",
            command=self.refresh_melodies,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            melody_buttons,
            text="เปิดโฟลเดอร์ melodies",
            command=self.open_melodies_folder,
        ).pack(side="left", padx=(6, 0))

        ttk.Label(
            audio_wrap,
            text="เสียงเครื่องดนตรี",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(10, 4))

        ttk.Combobox(
            audio_wrap,
            textvariable=self.instrument,
            values=("piano", "pluck", "bell", "synth"),
            state="readonly",
            width=18,
        ).pack(anchor="w")

        audio_fields = ttk.Frame(audio_wrap, style="Card.TFrame")
        audio_fields.pack(fill="x", pady=(8, 0))
        self._grid_entry(audio_fields, "ความดังโน้ต", self.note_volume, 0, 0)
        self._grid_entry(audio_fields, "Transpose", self.transpose, 1, 0)

        ttk.Checkbutton(
            audio_wrap,
            text="เล่นวนเมื่อโน้ตหมด",
            variable=self.melody_loop,
        ).pack(anchor="w", pady=(8, 0))

        ttk.Checkbutton(
            audio_wrap,
            text="เริ่มโน้ตใหม่เมื่อบอลระเบิด",
            variable=self.restart_melody_on_break,
        ).pack(anchor="w", pady=(4, 0))

        # ============================================================
        # Section: แพทเทิร์น Timeline
        # ============================================================
        self.sec_pattern = ttk.Frame(body, style="Card.TFrame")
        self._section(self.sec_pattern, "แพทเทิร์น Timeline")
        pattern_wrap = ttk.Frame(self.sec_pattern, style="Card.TFrame")
        pattern_wrap.pack(fill="x", pady=(0, 8))
        ttk.Label(
            pattern_wrap,
            text="แพทเทิร์นจะค่อย ๆ เปลี่ยนค่าระหว่างเรนเดอร์ตามเวลา เช่น ช่องว่าง / หนาม / gravity",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, 6))
        self.pattern_combo = ttk.Combobox(
            pattern_wrap,
            textvariable=self.pattern_choice,
            state="readonly",
            width=35,
        )
        self.pattern_combo.pack(fill="x")
        pattern_buttons = ttk.Frame(pattern_wrap, style="Card.TFrame")
        pattern_buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(
            pattern_buttons,
            text="นำเข้า Pattern JSON",
            command=self.import_pattern,
        ).pack(side="left")
        ttk.Button(
            pattern_buttons,
            text="รีเฟรช",
            command=self.refresh_patterns,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            pattern_buttons,
            text="เปิดโฟลเดอร์ patterns",
            command=self.open_patterns_folder,
        ).pack(side="left", padx=(6, 0))

        # ============================================================
        # Section: ไฟล์วิดีโอปลายทาง (always visible)
        # ============================================================
        self.sec_output = ttk.Frame(body, style="Card.TFrame")
        self._section(self.sec_output, "ไฟล์วิดีโอปลายทาง")
        out_wrap = ttk.Frame(self.sec_output, style="Card.TFrame")
        out_wrap.pack(fill="x", pady=(0, 12))
        ttk.Entry(
            out_wrap,
            textvariable=self.output,
        ).pack(fill="x")

        # ---- All mode-dependent sections (order matters for display) ----
        self._mode_sections_order = [
            ("general", self.sec_general),
            ("merge", self.sec_merge),
            ("spikes", self.sec_spikes),
            ("rotating", self.sec_rotating),
            ("gap", self.sec_gap),
            ("trail", self.sec_trail),
            ("circle_physics", self.sec_physics),
            ("ball_appearance", self.sec_ball_appearance),
            ("audio", self.sec_audio),
            ("pattern", self.sec_pattern),
            ("output", self.sec_output),
        ]

        # Initial visibility
        self._update_visible_sections()

    def _get_visible_section_keys(self):
        """Return set of section keys to display for the current render mode."""
        return mode_ui_sections(self.render_mode.get())

    def _update_visible_sections(self):
        """Pack / pack_forget sections according to the current mode."""
        visible = set(self._get_visible_section_keys())
        if "video" in visible:
            visible.add("general")
        if "colors" in visible or "ball_images" in visible:
            visible.add("ball_appearance")
        seen_frames = set()
        for key, frame in self._mode_sections_order:
            frame.pack_forget()
        for key, frame in self._mode_sections_order:
            if key in visible and frame not in seen_frames:
                frame.pack(fill="x", in_=self._ctrl_body, pady=(0, 10))
                seen_frames.add(frame)

    def _build_preview_panel(self, parent):
        ttk.Label(
            parent,
            text="พรีวิวภาพ",
            style="Card.TLabel",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w")

        self.preview_label = tk.Label(
            parent,
            bg="#08090c",
            text="กำลังโหลดพรีวิว...",
            fg="#6b7280",
            font=("Segoe UI", 9),
        )
        self.preview_label.pack(pady=(4, 6))

        # Detail summary card of current configuration
        self.preview_info_card = ttk.LabelFrame(
            parent,
            text="📋 รายละเอียดการตั้งค่าปัจจุบัน",
            padding=6,
        )
        self.preview_info_card.pack(fill="x", pady=(2, 4))

        self.preview_info_label = tk.Label(
            self.preview_info_card,
            textvariable=self.preview_info_text,
            justify="left",
            anchor="nw",
            bg="#0e1117",
            fg="#cbd5e1",
            font=("Consolas", 8),
            padx=6,
            pady=4,
            relief="flat",
            wraplength=320,
        )
        self.preview_info_label.pack(fill="x")

        ttk.Label(
            parent,
            text=(
                "• พรีวิวเป็นภาพนิ่งจุดเริ่มต้นพร้อมลูกศรทิศทาง\n"
                "• เลื่อนสไลเดอร์แล้วภาพและรายละเอียดจะอัปเดตทันที"
            ),
            style="Sub.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

    def _section(self, parent, title):
        ttk.Label(
            parent,
            text=title,
            style="Card.TLabel",
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(8, 6))

    def _grid_entry(self, parent, label, variable, row, col):
        ttk.Label(
            parent,
            text=label,
            style="Card.TLabel",
        ).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=12)
        entry.grid(row=row, column=col + 1, sticky="w", padx=(0, 16), pady=4)
        entry.bind("<KeyRelease>", lambda _event: self.schedule_preview())
        return entry

    def _slider(self, parent, label, min_v, max_v, variable, resolution, digits):
        field = SliderField(
            parent,
            label,
            min_v,
            max_v,
            variable,
            command=self.schedule_preview,
            resolution=resolution,
            digits=digits,
        )
        field.pack(fill="x", pady=(0, 8))
        return field

    def _help(self, parent, text):
        ttk.Label(parent, text="↳ " + text, style="Sub.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(0, 6))

    def apply_selected_render_mode(self):
        preset = apply_render_mode(self.render_mode.get())
        self.spikes_enabled.set(preset["spikes_enabled"])
        self.gap_enabled.set(preset["gap_enabled"])
        self.motion_trail.set(preset["motion_trail"])
        self.rotation_speed.set(str(preset["rotation_speed"]))
        self._update_visible_sections()
        self.generate_preview()

    def pick_ball_number_color(self):
        selected = colorchooser.askcolor(color=self.ball_number_color.get(), title="เลือกสีตัวเลขบนลูกบอล", parent=self)
        if selected and selected[1]:
            self.ball_number_color.set(selected[1].lower())
            self.schedule_preview()

    def _text_for_bg(self, hex_color):
        value = hex_color.lstrip("#")
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return "#111111" if luminance > 155 else "#ffffff"

    def update_color_ui(self):
        if not hasattr(self, "color_buttons"):
            return
        for i, btn in enumerate(self.color_buttons):
            if i >= len(self.ball_color_vars):
                break
            color = self.ball_color_vars[i].get().lower()
            try:
                btn.configure(
                    bg=color,
                    activebackground=color,
                    fg=self._text_for_bg(color),
                    activeforeground=self._text_for_bg(color),
                )
            except tk.TclError:
                pass
        self.schedule_preview()

    def pick_ball_color(self, index):
        current = self.ball_color_vars[index].get()
        selected = colorchooser.askcolor(
            color=current,
            title=f"เลือกสีลูกที่ {index + 1}",
            parent=self,
        )
        if selected and selected[1]:
            self.ball_color_vars[index].set(selected[1].lower())
            self.update_color_ui()

    def update_gap_fit_status(self):
        if not hasattr(self, "gap_fit_status"):
            return
        try:
            width = max(1.0, float(self.width.get()))
            height = max(1.0, float(self.height.get()))
            scale = width / 1080.0
            arena_scale = max(0.55, min(1.10, float(self.arena_scale.get())))
            arena_radius = min(width * 0.42, height * 0.275) * arena_scale
            ball_radius = max(0.0, float(self.base_radius.get()) * scale)
            ball_diameter = ball_radius * 2.0
            gap_size = max(0.0, min(300.0, float(self.gap_size.get())))

            if not self.gap_enabled.get():
                self.gap_fit_status.set(
                    f"ช่องว่าง: ปิดอยู่\n"
                    f"ลูกบอลเริ่มต้น: Ø {ball_diameter:.1f} px\n"
                    "สถานะ: ✕ ผ่านออกไม่ได้ เพราะยังไม่ได้เปิดช่องว่าง"
                )
                return

            gap_width = renderer_main.gap_chord_width(arena_radius, gap_size)
            fits = renderer_main.ball_fits_gap(ball_radius, arena_radius, gap_size)
            state = "✓ ผ่านได้" if fits else "✕ ผ่านไม่ได้"
            extra = ""
            growth_px = max(0.0, float(self.ball_growth.get()) * scale)
            if fits and growth_px > 1e-9:
                max_radius = gap_width * 0.5
                remaining = max(0.0, max_radius - ball_radius)
                approx_bounces = int(remaining // growth_px)
                extra = f"\nโตต่อได้ประมาณ {approx_bounces} ครั้ง ก่อนช่องเริ่มแคบกว่าบอล"

            self.gap_fit_status.set(
                f"ช่องว่าง: {gap_size:.0f}° ≈ {gap_width:.1f} px\n"
                f"ลูกบอลเริ่มต้น: Ø {ball_diameter:.1f} px\n"
                f"ขนาดลูกสูงสุดที่ผ่านได้ ≈ Ø {gap_width:.1f} px\n"
                f"สถานะ: {state}{extra}"
            )
        except (ValueError, tk.TclError):
            self.gap_fit_status.set("กรอกค่าขนาดให้ถูกต้องเพื่อเช็กว่าบอลผ่านได้หรือไม่")

    def apply_resolution_preset(self, w, h, fps):
        self.width.set(str(w))
        self.height.set(str(h))
        self.fps.set(str(fps))
        self.schedule_preview()

    def apply_tiktok_preset(self):
        self.apply_resolution_preset(1080, 1920, 240)

    def browse_output(self):
        selected = filedialog.asksaveasfilename(
            title="เลือกไฟล์วิดีโอปลายทาง",
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4")],
            initialdir=str(self.output_dir),
            initialfile=Path(self.output.get()).name or "circle_ball_final.mp4",
        )
        if selected:
            self.output.set(selected)

    def refresh_melodies(self, select_first=False):
        folder = melodies_dir()
        old_choice = self.melody_choice.get()

        self.melody_map = {"ทำนองในตัว": ""}
        display_names = ["ทำนองในตัว"]

        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in (".json", ".mid", ".midi"):
                continue

            display = path.stem
            if path.suffix.lower() == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    display = str(data.get("name", path.stem))
                except Exception:
                    display = path.stem

            base = display
            index = 2
            while display in self.melody_map:
                display = f"{base} ({index})"
                index += 1

            self.melody_map[display] = str(path.resolve())
            display_names.append(display)

        self.melody_combo["values"] = display_names

        if old_choice in self.melody_map and not select_first:
            self.melody_choice.set(old_choice)
        elif len(display_names) > 1:
            self.melody_choice.set(display_names[1])
        else:
            self.melody_choice.set(display_names[0])

    def import_melody(self):
        selected = filedialog.askopenfilename(
            title="นำเข้าไฟล์ทำนอง",
            filetypes=[
                ("Melody files", "*.json *.mid *.midi"),
                ("JSON", "*.json"),
                ("MIDI", "*.mid *.midi"),
            ],
        )
        if not selected:
            return

        source = Path(selected)
        target = melodies_dir() / source.name

        if target.exists():
            stem = target.stem
            suffix = target.suffix
            i = 2
            while target.exists():
                target = melodies_dir() / f"{stem}_{i}{suffix}"
                i += 1

        try:
            shutil.copy2(source, target)
        except OSError as exc:
            messagebox.showerror("นำเข้าไม่สำเร็จ", str(exc))
            return

        self.refresh_melodies()
        for display, path in self.melody_map.items():
            if path and Path(path).resolve() == target.resolve():
                self.melody_choice.set(display)
                break

        messagebox.showinfo(
            "นำเข้าแล้ว",
            f"เพิ่มไฟล์ทำนองเรียบร้อย\n{target.name}",
        )

    def refresh_patterns(self, select_first=False):
        folder = patterns_dir()
        old_choice = self.pattern_choice.get()

        self.pattern_map = {"ไม่ใช้แพทเทิร์น": ""}
        display_names = ["ไม่ใช้แพทเทิร์น"]

        for path in sorted(folder.iterdir()):
            if path.suffix.lower() != ".json":
                continue

            display = path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                display = str(data.get("name", path.stem))
            except Exception:
                display = path.stem

            base = display
            index = 2
            while display in self.pattern_map:
                display = f"{base} ({index})"
                index += 1

            self.pattern_map[display] = str(path.resolve())
            display_names.append(display)

        self.pattern_combo["values"] = display_names

        if old_choice in self.pattern_map and not select_first:
            self.pattern_choice.set(old_choice)
        else:
            self.pattern_choice.set(display_names[0])

    def import_pattern(self):
        selected = filedialog.askopenfilename(
            title="นำเข้าไฟล์ Pattern JSON",
            filetypes=[
                ("Pattern JSON", "*.json"),
                ("JSON", "*.json"),
            ],
        )
        if not selected:
            return

        source = Path(selected)
        target = patterns_dir() / source.name

        if target.exists():
            stem = target.stem
            suffix = target.suffix
            i = 2
            while target.exists():
                target = patterns_dir() / f"{stem}_{i}{suffix}"
                i += 1

        try:
            shutil.copy2(source, target)
        except OSError as exc:
            messagebox.showerror("นำเข้าไม่สำเร็จ", str(exc))
            return

        self.refresh_patterns()
        for display, p in self.pattern_map.items():
            if p and Path(p).resolve() == target.resolve():
                self.pattern_choice.set(display)
                break

        messagebox.showinfo(
            "นำเข้าแล้ว",
            f"เพิ่มไฟล์ Pattern เรียบร้อย\n{target.name}",
        )

    def choose_merge_sound(self):
        path = filedialog.askopenfilename(title="เลือกเสียงตอน Merge", filetypes=[("Audio", "*.wav *.mp3 *.m4a *.aac"), ("All files", "*.*")])
        if path:
            self.merge_sound_file.set(path)

    def choose_victory_sound(self):
        path = filedialog.askopenfilename(title="เลือกเสียง Victory", filetypes=[("Audio", "*.wav *.mp3 *.m4a *.aac"), ("All files", "*.*")])
        if path:
            self.merge_victory_sound_file.set(path)

    def choose_merge_ball_images(self):
        files = filedialog.askopenfilenames(
            title="เลือกรูปบอล LV1-LV8 (เลือกได้หลายไฟล์)",
            filetypes=[("Images", "*.webp *.png *.jpg *.jpeg")],
        )
        if not files:
            return
        target_dir = ball_assets_dir()
        copied = 0
        for source in files:
            source = Path(source)
            stem = source.stem.strip()
            if stem not in {str(i) for i in range(1, 9)}:
                continue
            for ext in (".webp", ".png", ".jpg", ".jpeg"):
                old = target_dir / f"{stem}{ext}"
                if old.exists():
                    old.unlink()
            shutil.copy2(source, target_dir / f"{stem}{source.suffix.lower()}")
            copied += 1
        messagebox.showinfo("รูป Merge Ball", f"นำเข้ารูปตามชื่อ Level แล้ว {copied} ไฟล์\nใช้ชื่อ 1.webp ... 8.webp")

    def choose_ball_image(self, index):
        path = filedialog.askopenfilename(
            title=f"เลือกรูปลูกบอลที่ {index + 1}",
            filetypes=[("Images", "*.webp *.png *.jpg *.jpeg"), ("All files", "*.*")],
        )
        if path:
            self.ball_image_paths[index].set(path)
            if index < len(self.ball_image_labels):
                self.ball_image_labels[index].configure(text=Path(path).name)
            self.schedule_preview()

    def clear_ball_image(self, index):
        self.ball_image_paths[index].set("")
        if index < len(self.ball_image_labels):
            self.ball_image_labels[index].configure(text="ไม่มีรูป")
        self.schedule_preview()

    def open_patterns_folder(self):
        self._open_folder(patterns_dir())

    def collect_config(self):
        try:
            cfg = {
                "render_mode": self.render_mode.get(),
                "merge_spawn_interval": float(self.merge_spawn_interval.get()),
                "merge_gravity": float(self.merge_gravity.get()),
                "merge_bounce": float(self.merge_bounce.get()),
                "merge_physics_hz": int(float(self.merge_physics_hz.get())),
                "merge_tank_scale": float(self.merge_tank_scale.get()),
                "merge_pipe_clearance": float(self.merge_pipe_clearance.get()),
                "merge_sound_enabled": bool(self.merge_sound_enabled.get()),
                "merge_sound_volume": float(self.merge_sound_volume.get()),
                "merge_sound_file": self.merge_sound_file.get(),
                "merge_victory_sound_file": self.merge_victory_sound_file.get(),
                "merge_level_size_percent": float(self.merge_level_size_percent.get()),
                "show_ball_numbers": bool(self.show_ball_numbers.get()),
                "ball_number_color": self.ball_number_color.get(),
                "spikes_enabled": bool(self.spikes_enabled.get()),
                "spike_count": int(float(self.spike_count.get())),
                "ball_count": int(float(self.ball_count.get())),
                "ball_lives": [max(1, int(float(v.get()))) for v in self.ball_life_vars],
                "pattern_file": self.pattern_map.get(self.pattern_choice.get(), ""),
                "gap_enabled": bool(self.gap_enabled.get()),
                "gap_size": float(self.gap_size.get()),
                "gap_position": float(self.gap_position.get()),
                "gravity": float(self.gravity.get()),
                "initial_angle": float(self.initial_angle.get()),
                "initial_speed": float(self.initial_speed.get()),
                "speed_growth": float(self.speed_growth.get()),
                "max_speed": float(self.max_speed.get()),
                "ball_growth": float(self.ball_growth.get()),
                "smooth_growth_speed": float(self.smooth_growth_speed.get()),
                "motion_trail": bool(self.motion_trail.get()),
                "trail_rainbow_speed": float(self.trail_rainbow_speed.get()),
                "trail_stamp_spacing": float(self.trail_stamp_spacing.get()),
                "base_radius": float(self.base_radius.get()),
                "arena_scale": float(self.arena_scale.get()),
                "rotation_speed": float(self.rotation_speed.get()),
                "spike_depth": float(self.spike_depth.get()),
                "spike_width": float(self.spike_width.get()),
                "wall_restitution": float(self.wall_restitution.get()),
                "wall_friction": float(self.wall_friction.get()),
                "air_drag": float(self.air_drag.get()),
                "fps": int(float(self.fps.get())),
                "seconds": float(self.seconds.get()),
                "width": int(float(self.width.get())),
                "height": int(float(self.height.get())),
                "seed": int(float(self.seed.get())),
                "rainbow_border": bool(self.rainbow_border.get()),
                "show_hud": bool(self.show_hud.get()),
                "ball_color_mode": "per-ball",
                "ball_colors": [v.get().lower() for v in self.ball_color_vars],
                "audio": bool(self.audio.get()),
                "melody_file": self.melody_map.get(self.melody_choice.get(), ""),
                "instrument": self.instrument.get(),
                "note_volume": float(self.note_volume.get()),
                "transpose": int(float(self.transpose.get())),
                "melody_loop": bool(self.melody_loop.get()),
                "restart_melody_on_break": bool(self.restart_melody_on_break.get()),
                "output": str(Path(self.output.get()).expanduser()),
                "ball_images": [v.get() for v in self.ball_image_paths],
            }
        except ValueError as exc:
            raise ValueError("มีค่าบางช่องไม่ถูกต้อง") from exc

        # Enforce mode exclusivity so hidden controls never contaminate active mode
        mode = cfg.get("render_mode")
        if mode == "วงกลมปกติ":
            cfg["spikes_enabled"] = False
            cfg["spike_count"] = 0
            cfg["gap_enabled"] = False
            cfg["motion_trail"] = False
            cfg["rotation_speed"] = 0.0
        elif mode == "มีหนาม":
            cfg["gap_enabled"] = False
            cfg["motion_trail"] = False
            cfg["rotation_speed"] = 0.0
        elif mode == "วงกลมเปิด":
            cfg["spikes_enabled"] = False
            cfg["spike_count"] = 0
            cfg["motion_trail"] = False
            cfg["rotation_speed"] = 0.0
        elif mode == "วงกลมหมุน":
            cfg["gap_enabled"] = False
            cfg["motion_trail"] = False
        elif mode == "รอยวาด":
            cfg["spikes_enabled"] = False
            cfg["spike_count"] = 0
            cfg["gap_enabled"] = False
            cfg["rotation_speed"] = 0.0

        if not 1 <= cfg["ball_count"] <= 8:
            raise ValueError("จำนวนลูกบอลต้องอยู่ระหว่าง 1 ถึง 8")
        if cfg["spike_count"] < 0:
            raise ValueError("จำนวนหนามต้องไม่ติดลบ")
        if not 0 <= cfg["gap_size"] <= 300:
            raise ValueError("ขนาดช่องว่างต้องอยู่ระหว่าง 0 ถึง 300 องศา")
        cfg["ball_lives"] = cfg["ball_lives"][: cfg["ball_count"]]
        if cfg["fps"] <= 0 or cfg["seconds"] <= 0:
            raise ValueError("FPS และเวลา ต้องมากกว่า 0")
        if cfg["width"] <= 0 or cfg["height"] <= 0:
            raise ValueError("ขนาดวิดีโอต้องมากกว่า 0")
        if cfg["initial_speed"] <= 0 or cfg["max_speed"] <= 0:
            raise ValueError("ความเร็วต้องมากกว่า 0")
        if cfg["arena_scale"] <= 0:
            raise ValueError("ขนาดสนามต้องมากกว่า 0")
        if not 0 <= cfg["note_volume"] <= 1.5:
            raise ValueError("ความดังโน้ตต้องอยู่ระหว่าง 0 ถึง 1.5")

        output_path = Path(cfg["output"]).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cfg["output"] = str(output_path)
        self.output_dir = output_path.parent
        return cfg

    def schedule_preview(self):
        self.update_gap_fit_status()
        if not hasattr(self, "preview_label"):
            return
        if self.preview_after_id is not None:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
        self.preview_after_id = self.after(220, self.generate_preview)

    def update_preview_info(self, cfg):
        mode = cfg.get("render_mode", "วงกลมปกติ")
        w = cfg.get("width", 1080)
        h = cfg.get("height", 1920)
        fps = cfg.get("fps", 240)
        sec = cfg.get("seconds", 20.0)
        total_frames = int(round(fps * sec))

        lines = [
            f"🎯 โหมด: {mode}",
            f"🎬 วิดีโอ: {w}×{h} @ {fps} FPS",
            f"⏱️ ความยาว: {sec:.1f} วินาที (~{total_frames:,} เฟรม)",
        ]

        if mode == "Merge Ball LV1-8":
            interval = cfg.get("merge_spawn_interval", 0.8)
            grav = cfg.get("merge_gravity", 980)
            bounce = cfg.get("merge_bounce", 0.78)
            scale = cfg.get("merge_tank_scale", 1.0)
            lines.append(f"📦 กลไก: ปล่อยทุก {interval:.2f}s | ถัง {scale:.2f}x")
            lines.append(f"⚡ ฟิสิกส์: แรงโน้มถ่วง {grav:.0f} | เด้ง {bounce:.2f}")
            snd = "เปิด" if cfg.get("merge_sound_enabled") else "ปิด"
            lines.append(f"🔊 เสียง Merge: {snd}")
        else:
            ball_count = cfg.get("ball_count", 1)
            radius = cfg.get("base_radius", 24.0)
            speed = cfg.get("initial_speed", 600.0)
            grav = cfg.get("gravity", 900.0)
            lives = cfg.get("ball_lives", [10])[:ball_count]
            lives_str = ",".join(str(x) for x in lives)

            lines.append(f"⚽ บอล: {ball_count} ลูก (ขนาด {radius:.0f}px, เร็ว {speed:.0f}px/s)")
            lines.append(f"❤️ HP บอล: [{lives_str}] | G: {grav:.0f}")

            # Skins count
            skins = [p for p in (cfg.get("ball_images") or [])[:ball_count] if p]
            if skins:
                lines.append(f"🖼️ สกินรูปภาพ: ใส่ {len(skins)}/{ball_count} ลูก (ไร้ขอบขาว)")
            else:
                lines.append(f"🎨 สกิน: ใช้สีปกติทั้งหมด")

            # Mode-specific line
            if mode == "มีหนาม":
                cnt = cfg.get("spike_count", 3)
                depth = cfg.get("spike_depth", 34.0)
                width = cfg.get("spike_width", 15.0)
                lines.append(f"🔱 หนาม: {cnt} อัน (ลึก {depth:.0f}px, กว้าง {width:.0f}px)")
            elif mode == "วงกลมหมุน":
                cnt = cfg.get("spike_count", 3)
                rot = cfg.get("rotation_speed", 0.85)
                lines.append(f"🔄 หมุน: {rot:+.2f} rad/s | หนาม {cnt} อัน")
            elif mode == "วงกลมเปิด":
                gap_size = cfg.get("gap_size", 45.0)
                gap_pos = cfg.get("gap_position", -90.0)
                lines.append(f"🚪 ช่องว่าง: {gap_size:.0f}° ที่มุม {gap_pos:.0f}°")
            elif mode == "รอยวาด":
                rb_spd = cfg.get("trail_rainbow_speed", 0.11)
                spacing = cfg.get("trail_stamp_spacing", 0.16)
                lines.append(f"🌈 รอยวาด: สปีดสีรุ้ง {rb_spd:.2f} | ระยะ {spacing:.2f}")

            # Audio
            if cfg.get("audio"):
                inst = cfg.get("instrument", "piano")
                mel = self.melody_choice.get()
                lines.append(f"🎵 เสียง: เปิด ({inst} / {mel})")
            else:
                lines.append(f"🔇 เสียง: ปิด")

            # Numbers & HUD
            num_on = "เปิด" if cfg.get("show_ball_numbers") else "ปิด"
            hud_on = "เปิด" if cfg.get("show_hud") else "ปิด"
            rb_border = "เปิด" if cfg.get("rainbow_border") else "ปิด"
            lines.append(f"🔢 เลข HP: {num_on} | HUD: {hud_on} | ขอบรุ้ง: {rb_border}")

        lines.append(f"🎲 Seed สุ่ม: {cfg.get('seed', 11)}")
        if hasattr(self, "preview_info_text"):
            self.preview_info_text.set("\n".join(lines))

    def generate_preview(self):
        self.preview_after_id = None
        try:
            cfg = self.collect_config()
        except Exception:
            return

        self.update_preview_info(cfg)

        try:
            img = self.build_preview_image(cfg)

            view_w = 320
            view_h = 280
            h, w = img.shape[:2]
            scale = min(view_w / w, view_h / h)
            preview = cv2.resize(
                img,
                (
                    max(1, int(round(w * scale))),
                    max(1, int(round(h * scale))),
                ),
                interpolation=cv2.INTER_AREA,
            )

            cv2.imwrite(str(self.preview_path), preview)
            self.preview_image = tk.PhotoImage(file=str(self.preview_path))
            self.preview_label.configure(image=self.preview_image)
        except Exception as exc:
            self.stage.set(f"พรีวิวไม่สำเร็จ: {exc}")

    def build_merge_preview_image(self, cfg):
        target_w = 520
        ratio = cfg["height"] / max(1, cfg["width"])
        H = max(620, min(920, int(round(target_w * ratio))))
        W = target_w
        img = np.zeros((H, W, 3), dtype=np.uint8)
        cx = W // 2
        cy = int(H * 0.62)
        R = int(min(W * 0.455, H * 0.34) * cfg.get("merge_tank_scale", 1.0))
        r1 = max(10, int(24 * W / 540))
        pipe_w = r1 * 2 + int(cfg.get("merge_pipe_clearance", 8) * W / 540)
        opening_y = cy - R
        pipe_top = max(25, opening_y - int(H * 0.22))
        cv2.circle(img, (cx, cy), R, (230,230,230), 4, cv2.LINE_AA)
        cv2.rectangle(img, (cx-pipe_w//2-5, opening_y-12), (cx+pipe_w//2+5, opening_y+14), (0,0,0), -1)
        cv2.line(img, (cx-pipe_w//2, pipe_top), (cx-pipe_w//2, opening_y), (230,230,230), 4, cv2.LINE_AA)
        cv2.line(img, (cx+pipe_w//2, pipe_top), (cx+pipe_w//2, opening_y), (230,230,230), 4, cv2.LINE_AA)
        # Show representative LV1 falling through the open pipe.
        cv2.circle(img, (cx, pipe_top + max(r1+6, 36)), r1, (80,80,255), -1, cv2.LINE_AA)
        r2 = max(3, round(30 * W / 540 * (1.0 + cfg.get("merge_level_size_percent", 0) / 100.0)))
        cv2.circle(img, (cx-int(R*.32), cy+int(R*.25)), r2, (255,160,70), -1, cv2.LINE_AA)
        cv2.arrowedLine(img, (cx, pipe_top+r1*3), (cx, min(cy, pipe_top+r1*6)), (170,170,170), 2, cv2.LINE_AA, tipLength=.25)
        cv2.putText(img, "MERGE BALL  LV1 -> LV8", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, .55, (210,210,210), 1, cv2.LINE_AA)
        return img

    def build_preview_image(self, cfg):
        if cfg.get("render_mode") == "Merge Ball LV1-8":
            return self.build_merge_preview_image(cfg)
        target_w = 520
        ratio = cfg["height"] / max(1, cfg["width"])
        target_h = int(round(target_w * ratio))
        target_h = max(620, min(920, target_h))

        W = target_w
        H = target_h
        scale = W / 1080.0

        center = np.array([W * 0.5, H * 0.52], dtype=np.float64)
        arena_radius = min(W * 0.42, H * 0.275) * cfg["arena_scale"]

        rng = np.random.default_rng(cfg["seed"])
        colors = cfg["ball_colors"] or DEFAULT_BALL_COLORS
        base_radius = cfg["base_radius"] * scale
        spike_depth = cfg["spike_depth"] * scale
        spike_width = cfg["spike_width"] * scale

        img = np.zeros((H, W, 3), dtype=np.uint8)

        if cfg["rainbow_border"]:
            renderer_main.draw_rainbow_ring(
                img,
                center,
                arena_radius,
                0.10,
                max(2, int(round(5 * scale))),
                gap_position_deg=cfg["gap_position"] if cfg["gap_enabled"] else 0.0,
                gap_size_deg=cfg["gap_size"] if cfg["gap_enabled"] else 0.0,
            )
        else:
            renderer_main.draw_plain_ring(
                img,
                center,
                arena_radius,
                (242, 242, 242),
                max(2, int(round(5 * scale))),
                gap_position_deg=cfg["gap_position"] if cfg["gap_enabled"] else 0.0,
                gap_size_deg=cfg["gap_size"] if cfg["gap_enabled"] else 0.0,
            )

        spike_count = cfg["spike_count"] if cfg["spikes_enabled"] else 0
        spikes = renderer_main.get_spikes(
            center,
            arena_radius,
            0.45,
            spike_depth,
            spike_width,
            spike_count,
            gap_position_deg=cfg["gap_position"] if cfg["gap_enabled"] else 0.0,
            gap_size_deg=cfg["gap_size"] if cfg["gap_enabled"] else 0.0,
        )
        for tri in spikes:
            renderer_main.draw_triangle(img, tri, (45, 45, 245))

        # Load ball skins for preview
        preview_skins = renderer_main.load_ball_images(",".join(cfg.get("ball_images") or []))

        balls = []
        for i in range(cfg["ball_count"]):
            color = renderer_main.resolve_ball_color(
                cfg["ball_color_mode"],
                colors,
                i,
                rng,
            )
            ball = renderer_main.spawn_ball(
                center,
                arena_radius,
                base_radius,
                rng,
                i,
                cfg["ball_count"],
                color=color,
                initial_angle_deg=cfg["initial_angle"],
                initial_speed=cfg["initial_speed"] * scale,
                max_life=cfg["ball_lives"][i],
            )
            balls.append(ball)
            renderer_main.draw_ball(
                img,
                ball,
                max(2, int(round(4 * scale))),
                skin=preview_skins.get(i),
            )

        if balls:
            first = balls[0]
            direction = renderer_main.normalize(first.vel)
            arrow_len = min(arena_radius * 0.42, 95 * scale + 45)
            p0 = first.pos
            p1 = first.pos + direction * arrow_len
            cv2.arrowedLine(
                img,
                tuple(np.round(p0).astype(int)),
                tuple(np.round(p1).astype(int)),
                (255, 255, 255),
                max(1, int(round(3 * scale))),
                cv2.LINE_AA,
                tipLength=0.22,
            )

        if cfg["show_hud"]:
            cv2.putText(
                img,
                f"ANGLE {cfg['initial_angle']:.0f}",
                (18, 34),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (170, 170, 170),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                img,
                f"SPEED {cfg['initial_speed']:.0f}",
                (18, 62),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
                (150, 150, 150),
                1,
                cv2.LINE_AA,
            )

        return img

    def start_render(self):
        if self.process and self.process.poll() is None:
            return

        try:
            cfg = self.collect_config()
        except ValueError as exc:
            messagebox.showerror("ตั้งค่าไม่ถูกต้อง", str(exc))
            return

        self.reported_progress = 0.0
        self.displayed_progress = 0.0
        self.progress["value"] = 0.0
        self.progress_text.set("0.00%")
        self.status.set("กำลังเรนเดอร์...")
        self.stage.set("กำลังเริ่ม renderer")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._set_log("")

        fd, temp_name = tempfile.mkstemp(prefix="circle_renderer_", suffix=".log")
        os.close(fd)
        self.log_path = Path(temp_name)
        self.log_offset = 0

        cmd = child_command(cfg, self.log_path)
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self.process = subprocess.Popen(cmd, creationflags=creationflags)
        except Exception as exc:
            self.status.set("เริ่มไม่สำเร็จ")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            messagebox.showerror("เริ่มเรนเดอร์ไม่สำเร็จ", str(exc))
            return

        self.after(120, self.poll_render)

    def poll_render(self):
        self._consume_log()

        if not self.process:
            return

        code = self.process.poll()
        if code is None:
            self.after(120, self.poll_render)
            return

        self._consume_log()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

        if code == 0:
            self.reported_progress = 100.0
            self.stage.set("เสร็จสมบูรณ์")
            self.status.set("เสร็จแล้ว")
            self._append_log("\nเรนเดอร์เสร็จเรียบร้อย\n")
        else:
            self.status.set(f"ล้มเหลว (exit {code})")
            self.stage.set("เรนเดอร์ไม่สำเร็จ")
            self._append_log(f"\nRenderer ออกด้วยรหัส {code}\n")

        self.process = None

    def _consume_log(self):
        if not self.log_path or not self.log_path.exists():
            return

        try:
            with open(
                self.log_path,
                "r",
                encoding="utf-8",
                errors="replace",
            ) as file:
                file.seek(self.log_offset)
                chunk = file.read()
                self.log_offset = file.tell()
        except OSError:
            return

        if not chunk:
            return

        self._append_log(chunk.replace("\r", "\n"))

        for line in re.split(r"[\r\n]+", chunk):
            value, stage = parse_app_progress(line)
            if value is None:
                continue
            self.reported_progress = max(self.reported_progress, value)
            self.stage.set(stage)

    def animate_progress(self):
        target = float(self.reported_progress)

        if self.process is not None and self.process.poll() is None:
            target = min(target, 99.85)

        next_value = smooth_progress_step(
            self.displayed_progress,
            target,
            easing=0.18,
            min_step=0.012,
        )

        if target >= 100.0 and 100.0 - next_value < 0.01:
            next_value = 100.0

        self.displayed_progress = next_value
        self.progress["value"] = next_value
        self.progress_text.set(f"{next_value:.2f}%")

        # Update big progress display
        stage = self.stage.get()
        if self.process is not None and self.process.poll() is None:
            self.progress_big_text.set(f"⏳ {next_value:.2f}%  —  {stage}")
        elif next_value >= 100.0:
            self.progress_big_text.set(f"✅ 100.00%  —  เสร็จสมบูรณ์")
        elif next_value > 0.0:
            self.progress_big_text.set(f"{next_value:.2f}%  —  {stage}")
        else:
            self.progress_big_text.set("")

        self.progress_animation_job = self.after(
            33,
            self.animate_progress,
        )

    def stop_render(self):
        if not self.process or self.process.poll() is not None:
            return

        try:
            self.process.terminate()
        except Exception:
            pass

        self.status.set("กำลังหยุด...")
        self.stage.set("กำลังหยุด renderer")
        self._append_log("\nกำลังหยุด renderer...\n")

    def open_output_folder(self):
        self._open_folder(self.output_dir)

    def open_melodies_folder(self):
        self._open_folder(melodies_dir())

    def _open_folder(self, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _set_log(self, value):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        if value:
            self.log.insert("end", value)
        self.log.configure(state="disabled")

    def _append_log(self, value):
        self.log.configure(state="normal")
        self.log.insert("end", value)
        self.log.see("end")
        self.log.configure(state="disabled")

    def on_close(self):
        if self.preview_after_id is not None:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
            self.preview_after_id = None

        if self.progress_animation_job is not None:
            try:
                self.after_cancel(self.progress_animation_job)
            except Exception:
                pass
            self.progress_animation_job = None

        if self.process and self.process.poll() is None:
            if not messagebox.askyesno(
                "ยังเรนเดอร์อยู่",
                "ยังมีการเรนเดอร์อยู่ ต้องการหยุดและปิดโปรแกรมหรือไม่?",
            ):
                return
            try:
                self.process.terminate()
            except Exception:
                pass

        self.destroy()


# Backward-compatible class name for older imports.
BallRendererApp = CircleRendererThaiApp


def launch_gui():
    CircleRendererThaiApp().mainloop()


if __name__ == "__main__":
    if "--merge-renderer" in sys.argv:
        args = sys.argv[1:]
        args.remove("--merge-renderer")
        run_merge_renderer_child(args)
    elif "--renderer" in sys.argv:
        args = sys.argv[1:]
        args.remove("--renderer")
        run_renderer_child(args)
    else:
        launch_gui()
