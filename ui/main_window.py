from pathlib import Path
import json
import sys
from PySide6.QtCore import QLocale, QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QProgressBar, QSlider, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget)
from .theme import STYLESHEET
from .preview_widget import PreviewWidget
from core.config import build_arg_parser
from engines.circle.simulation import CircleSimulation
from engines.drop.simulation import DropSimulation, recommended_foam_count
from engines.drop_engine import cli as drop_cli
from engines.merge.simulation import MergeSimulation
from engines.merge_engine import cli as merge_cli

class NumberSlider(QWidget):
    """Horizontal slider synchronized with an editable numeric input."""
    def __init__(self, value, minimum, maximum, step=1.0, decimals=0, parent=None):
        super().__init__(parent); self.scale = 10 ** decimals; self.decimals = decimals
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(round(minimum*self.scale), round(maximum*self.scale)); self.slider.setSingleStep(max(1, round(step*self.scale))); self.slider.setPageStep(max(1, round(step*self.scale*5))); self.slider.setValue(round(value*self.scale))
        self.readout = QDoubleSpinBox(); self.readout.setLocale(QLocale.c()); self.readout.setRange(float(minimum),float(maximum)); self.readout.setSingleStep(float(step)); self.readout.setDecimals(decimals); self.readout.setKeyboardTracking(False); self.readout.setMinimumWidth(88)
        row = QHBoxLayout(self); row.setContentsMargins(0,0,0,0); row.addWidget(self.slider,1); row.addWidget(self.readout); self.slider.valueChanged.connect(self._update); self.readout.valueChanged.connect(self._from_input); self._update(self.slider.value())
    def _update(self, raw):
        self.readout.blockSignals(True); self.readout.setValue(raw/self.scale); self.readout.blockSignals(False)
    def _from_input(self, value): self.slider.setValue(round(float(value)*self.scale))
    def value(self): return self.slider.value() / self.scale
    def setValue(self, value): self.slider.setValue(round(float(value)*self.scale))
    def valueChanged(self, callback): self.slider.valueChanged.connect(callback)

class MainWindow(QMainWindow):
    """Complete PySide6 front end for all legacy renderer settings and engines."""
    def __init__(self):
        super().__init__(); self.setWindowTitle('BALL RENDERER — STUDIO V2'); self.resize(1500, 980); self.setStyleSheet(STYLESHEET); self.setFont(QFont('Arial', 10))
        self.mode='Circle Battle'; self.engine=None; self.process=None; self._render_cancel_requested=False; self.playing=False; self.audio_file=''; self.melody_file=''; self.merge_sound_file=''; self.victory_sound_file=''; self.merge_assets_path=str(Path(__file__).resolve().parents[1]/'assets'/'balls'); self.drop_ball_image=''; self.drop_foam_image=''; self.drop_sound_file=''; self.drop_floor_sound_file=''; self.drop_foam_color='#ffffff'
        self._build(); self._thai_ui(); self._update_mode_visibility(); self._wire_live_controls(); self._reset_engine(); self.timer=QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(16)
    def _form(self,title):
        page=QWidget(); form=QFormLayout(page); form.setContentsMargins(16,12,16,12); form.setSpacing(8); self.tabs.addTab(page,title); return form
    def _int(self,v,lo,hi,step=1): w=QSpinBox(); w.setLocale(QLocale.c()); w.setRange(lo,hi); w.setSingleStep(step); w.setValue(v); return w
    def _float(self,v,lo,hi,step=.01,dec=3): w=QDoubleSpinBox(); w.setLocale(QLocale.c()); w.setRange(lo,hi); w.setSingleStep(step); w.setDecimals(dec); w.setValue(v); return w
    def _file_row(self,callback):
        wrap=QWidget(); row=QHBoxLayout(wrap); row.setContentsMargins(0,0,0,0); edit=QLineEdit(); edit.setReadOnly(True); button=QPushButton('Choose…'); button.clicked.connect(callback); row.addWidget(edit,1); row.addWidget(button); return wrap,edit
    def _add_ball_color_button(self, layout, index):
        button=QPushButton(str(index + 1)); button.setFixedWidth(34); button.clicked.connect(lambda _checked=False,i=index:self.choose_ball_color(i)); self.ball_color_buttons.append(button); layout.addWidget(button); self._style_ball_color_button(index)
    def _style_ball_color_button(self, index):
        if index < len(self.ball_color_buttons):
            self.ball_color_buttons[index].setStyleSheet(f'QPushButton {{ background:{self.ball_colors[index]}; color:#111; border:1px solid #d5d8df; border-radius:4px; padding:4px; }}')
    def choose_ball_color(self, index):
        color=QColorDialog.getColor(QColor(self.ball_colors[index]), self, f'เลือกสีบอลลูกที่ {index + 1}')
        if color.isValid():
            self.ball_colors[index]=color.name().lower(); self._style_ball_color_button(index); self._reset_engine()
    def _build(self):
        root=QWidget(); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0)
        header=QFrame(); header.setFixedHeight(82); h=QHBoxLayout(header); h.setContentsMargins(24,10,24,10); h.addWidget(QLabel('<b style="font-size:18px">BALL RENDERER</b><br><span style="color:#949eb0;font-size:10px">STUDIO V2 · COMPLETE CONTROLS</span>')); h.addStretch(); badge=QLabel(' ENGINE SYNCED '); badge.setStyleSheet('color:#21c45e;background:#0e2e1c;border-radius:14px;padding:7px'); h.addWidget(badge); self.top_progress=QProgressBar(); self.top_progress.setRange(0,100); self.top_progress.setFormat('%p%'); self.top_progress.setFixedWidth(220); self.top_progress.setVisible(True); h.addWidget(self.top_progress); p=QPushButton('▶ Preview'); p.clicked.connect(lambda:self._set_play(True)); h.addWidget(p); r=QPushButton('Render MP4'); r.setObjectName('primary'); r.clicked.connect(self.render_mp4); h.addWidget(r); self.stop_render_btn=QPushButton('■ Stop'); self.stop_render_btn.setEnabled(False); self.stop_render_btn.clicked.connect(self.stop_render); h.addWidget(self.stop_render_btn); outer.addWidget(header)
        body=QHBoxLayout(); body.setContentsMargins(14,14,14,8); outer.addLayout(body,1)
        left=QFrame(); left.setObjectName('panel'); left.setFixedWidth(230); ll=QVBoxLayout(left); ll.addWidget(QLabel('<b>RENDER MODES</b>')); self.mode_buttons=[]
        for name in ('Circle Battle','Spikes','Open Ring','Trail Draw','Spike Multiply','Escape Split','Ball Drop Shatter','Merge Ball'):
            b=QPushButton(name); b.setCheckable(True); b.setObjectName('mode'); b.clicked.connect(lambda _checked,n=name:self.select_mode(n)); ll.addWidget(b); self.mode_buttons.append(b)
        ll.addSpacing(12); ll.addWidget(QLabel('<b>QUICK PRESETS</b>'))
        for label,v in (('TikTok 1080×1920',(1080,1920,240)),('Shorts 60 FPS',(1080,1920,60)),('Square 1080×1080',(1080,1080,60))):
            b=QPushButton(label); b.clicked.connect(lambda _checked,x=v:self._apply_video_preset(x)); ll.addWidget(b)
        ll.addStretch(); ll.addWidget(QLabel('All settings below are sent directly to the selected engine.')); body.addWidget(left)
        center=QFrame(); center.setObjectName('panel'); cl=QVBoxLayout(center); cl.addWidget(QLabel('<b>Live Preview</b>  <span style="color:#949eb0">same engine as final render</span>')); self.preview=PreviewWidget(); cl.addWidget(self.preview,1); pb=QHBoxLayout(); self.play_btn=QPushButton('▶'); self.play_btn.setObjectName('primary'); self.play_btn.clicked.connect(lambda:self._set_play(not self.playing)); pb.addWidget(self.play_btn); self.time_label=QLabel('00:00.00 / 00:30.00'); pb.addWidget(self.time_label); self.timeline=QSlider(Qt.Horizontal); pb.addWidget(self.timeline,1); restart=QPushButton('↻ Restart'); restart.clicked.connect(self._reset_engine); pb.addWidget(restart); cl.addLayout(pb); body.addWidget(center,1)
        props=QFrame(); props.setObjectName('panel'); props.setMinimumWidth(470); pl=QVBoxLayout(props); pl.addWidget(QLabel('<b style="font-size:15px">Properties</b>')); self.tabs=QTabWidget(); pl.addWidget(self.tabs,1); self._build_general(); self._build_physics(); self._build_mode_settings(); self._build_audio(); self._build_merge(); self._build_output(); self.general_form=self.tabs.widget(0).layout(); self.mode_form=self.tabs.widget(2).layout(); body.addWidget(props)
        log_frame=QFrame(); log_frame.setObjectName('panel'); log_layout=QVBoxLayout(log_frame); log_head=QHBoxLayout(); log_head.addWidget(QLabel('<b>Renderer log</b>')); log_head.addStretch(); copy_log=QPushButton('Copy log'); copy_log.clicked.connect(self.copy_log); clear_log=QPushButton('Clear'); clear_log.clicked.connect(lambda:self.log.clear()); log_head.addWidget(copy_log); log_head.addWidget(clear_log); log_layout.addLayout(log_head); self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setAcceptRichText(False); self.log.setPlaceholderText('Renderer output and errors will appear here…'); self.log.setFixedHeight(120); log_layout.addWidget(self.log); outer.addWidget(log_frame)
        status=QFrame(); status.setFixedHeight(44); sl=QHBoxLayout(status); self.status=QLabel('Ready'); self.status.setObjectName('muted'); sl.addWidget(self.status); sl.addStretch(); outer.addWidget(status)
    def _build_general(self):
        f=self._form('General'); self.mode_combo=QComboBox(); self.mode_combo.addItem('วงกลมปกติ','Circle Battle'); self.mode_combo.addItem('มีหนาม','Spikes'); self.mode_combo.addItem('วงกลมเปิด','Open Ring'); self.mode_combo.addItem('รอยวาด','Trail Draw'); self.mode_combo.addItem('หนามคูณบอล','Spike Multiply'); self.mode_combo.addItem('ออกนอกจอเกิด 2 ลูก','Escape Split'); self.mode_combo.addItem('บอลตกใส่หนาม','Ball Drop Shatter'); self.mode_combo.addItem('รวมบอล','Merge Ball'); self.mode_combo.currentIndexChanged.connect(lambda _i:self.select_mode(self.mode_combo.currentData()) if self.mode_combo.currentData()!=self.mode else None); f.addRow('โหมด',self.mode_combo); self.ball_count=self._int(1,1,8); self.seed=self._int(11,0,999999); self.seconds=self._float(30,.1,3600,1,1); self.width=self._int(1080,64,4096); self.height=self._int(1920,64,4096); self.fps=self._int(120,1,2400); f.addRow('จำนวนบอล',self.ball_count); f.addRow('Seed',self.seed); f.addRow('ความยาว (วินาที)',self.seconds); f.addRow('กว้าง',self.width); f.addRow('สูง',self.height); f.addRow('FPS',self.fps); self.color_mode=QComboBox(); self.color_mode.addItem('สีเดียว','same'); self.color_mode.addItem('สีสุ่ม','random'); self.color_mode.addItem('แยกตามบอล','per-ball'); f.addRow('โหมดสีบอล',self.color_mode); self.ball_colors=['#ff4d4d','#4da6ff','#5cff7a','#ffd84d','#c77dff','#ff7ad9','#61e7ff','#ff9f43']; self.ball_color_buttons=[]; color_wrap=QWidget(); color_layout=QHBoxLayout(color_wrap); color_layout.setContentsMargins(0,0,0,0); color_layout.setSpacing(4); [self._add_ball_color_button(color_layout,i) for i in range(8)]; f.addRow('สีบอลแต่ละลูก',color_wrap); self.show_hud=QCheckBox('แสดง HUD'); self.show_numbers=QCheckBox('แสดงตัวเลขบนบอล'); self.show_numbers.setChecked(True); self.rainbow=QCheckBox('ขอบวงกลมสีรุ้ง'); self.rainbow.setChecked(True); f.addRow(self.show_hud); f.addRow(self.show_numbers); f.addRow(self.rainbow)
    def _build_physics(self):
        f=self._form('Circle Physics'); self.initial_angle=NumberSlider(35,-180,180,1,0); self.initial_speed=NumberSlider(600,0,3000,10,0); self.gravity=NumberSlider(900,0,3000,10,0); self.speed_growth=NumberSlider(1.004,1,1.05,.001,3); self.max_speed=NumberSlider(1750,1,5000,10,0); self.base_radius=NumberSlider(24,2,200,1,0); self.ball_growth=NumberSlider(5,0,50,.25,2); self.smooth_growth=NumberSlider(24,0,200,1,0); self.arena_scale=NumberSlider(1,.5,1.2,.01,2); self.restitution=NumberSlider(.985,0,1.2,.001,3); self.bounce_growth=NumberSlider(0,0,.02,.0005,4); self.friction=NumberSlider(.0006,0,.2,.001,4); self.air_drag=NumberSlider(.00018,0,.1,.0001,5)
        for label,w in (('Initial angle',self.initial_angle),('Initial speed',self.initial_speed),('Gravity',self.gravity),('Speed growth',self.speed_growth),('Max speed',self.max_speed),('Base radius',self.base_radius),('Growth per bounce',self.ball_growth),('Smooth growth speed',self.smooth_growth),('Arena scale',self.arena_scale),('Wall restitution',self.restitution),('Bounce growth',self.bounce_growth),('Wall friction',self.friction),('Air drag',self.air_drag)): f.addRow(label,w)
    def _build_mode_settings(self):
        f=self._form('Mode Settings'); self.spike_count=NumberSlider(3,0,32,1,0); self.spike_depth=NumberSlider(34,0,300,1,0); self.spike_width=NumberSlider(15,1,180,1,0); self.rotation_speed=NumberSlider(.85,-10,10,.05,2); self.gap_enabled=QCheckBox('เปิดช่องว่าง'); self.gap_size=NumberSlider(45,0,300,1,0); self.gap_position=NumberSlider(-90,-180,180,1,0); self.escape_hud=QCheckBox('แสดงจำนวนบอลตามสี'); self.escape_countdown=QCheckBox('แสดงเวลาถอยหลัง'); self.trail=QCheckBox('รอยการเคลื่อนที่'); self.trail_speed=NumberSlider(.11,.01,1,.01,2); self.trail_spacing=NumberSlider(.16,.01,2,.01,2); self.pattern_file=''; self.pattern_row,self.pattern_label=self._file_row(self.choose_pattern)
        for label,w in (('จำนวนหนาม',self.spike_count),('ความลึกหนาม',self.spike_depth),('ความกว้างหนาม',self.spike_width),('ความเร็วหมุน',self.rotation_speed),('ช่องว่าง',self.gap_enabled),('ขนาดช่องว่าง',self.gap_size),('ตำแหน่งช่องว่าง',self.gap_position),('ตัวนับสี',self.escape_hud),('เวลาถอยหลัง',self.escape_countdown),('รอยวาด',self.trail),('ความเร็วสีรอย',self.trail_speed),('ระยะประทับรอย',self.trail_spacing)): f.addRow(label,w)
        f.addRow('แพทเทิร์น JSON',self.pattern_row); pattern_actions=QHBoxLayout(); self.pattern_refresh=QPushButton('รีเฟรชค่าจากแพทเทิร์น'); self.pattern_refresh.clicked.connect(self.refresh_from_pattern); self.pattern_delete=QPushButton('ลบแพทเทิร์นที่เลือก'); self.pattern_delete.clicked.connect(self.clear_pattern); pattern_actions.addWidget(self.pattern_refresh); pattern_actions.addWidget(self.pattern_delete); actions_widget=QWidget(); actions_widget.setLayout(pattern_actions); f.addRow(actions_widget)
        self.drop_particle_count=NumberSlider(180,1,5000,1,0); self.drop_particle_budget=NumberSlider(600,100,2000,50,0); self.drop_ball_size=NumberSlider(10,1,1000,.5,1); self.drop_gravity=NumberSlider(500,0,3000,25,0); self.drop_spawn_interval=NumberSlider(1.2,.05,10,.05,2); self.drop_particle_size=NumberSlider(8,1,40,.5,1); self.drop_particle_life=NumberSlider(6,.1,20,.1,1); self.drop_remove_on_floor=QCheckBox('ลบโฟมเมื่อถึงพื้น'); self.drop_remove_on_floor.setChecked(True); self.drop_floor_sound_chance=NumberSlider(50,0,100,5,0); self.drop_particle_speed=NumberSlider(500,20,2500,10,0); self.drop_spike_count=NumberSlider(12,1,60,1,0); self.drop_spike_height=NumberSlider(85,5,300,5,0); self.drop_image_row,self.drop_image_label=self._file_row(self.choose_drop_image); self.drop_foam_image_row,self.drop_foam_image_label=self._file_row(self.choose_drop_foam_image); self.drop_sound_row,self.drop_sound_label=self._file_row(self.choose_drop_sound); self.drop_floor_sound_row,self.drop_floor_sound_label=self._file_row(self.choose_drop_floor_sound)
        self.drop_size_row=QWidget(); size_layout=QHBoxLayout(self.drop_size_row); size_layout.setContentsMargins(0,0,0,0); self.drop_size_minus=QPushButton('-5%'); self.drop_size_plus=QPushButton('+5%'); self.drop_size_minus.clicked.connect(lambda:self._change_drop_ball_percent(-5)); self.drop_size_plus.clicked.connect(lambda:self._change_drop_ball_percent(5)); size_layout.addWidget(self.drop_size_minus); size_layout.addWidget(self.drop_ball_size,1); size_layout.addWidget(self.drop_size_plus)
        self.drop_foam_color_button=QPushButton('เลือกสีโฟม'); self.drop_foam_color_button.setStyleSheet('background:#ffffff;color:#111111'); self.drop_foam_color_button.clicked.connect(self.choose_drop_foam_color)
        self.drop_auto=QCheckBox('คำนวณจำนวนโฟมอัตโนมัติ'); self.drop_auto.setChecked(True); self.drop_auto_button=QPushButton('เซตอัตโนมัติ'); self.drop_auto_button.clicked.connect(self._force_drop_auto); self.drop_ball_size.slider.valueChanged.connect(self._apply_drop_auto); self.width.valueChanged.connect(self._apply_drop_auto)
        self.drop_script=QCheckBox('ใช้สคริปต์ 5%, 10%, 25%, 50%, 75%, 100%'); self.drop_script_button=QPushButton('ตั้งสคริปต์ 30 วินาที'); self.drop_script_button.clicked.connect(self._set_drop_size_script)
        self.drop_controls=(self.drop_particle_count,self.drop_particle_budget,self.drop_size_row,self.drop_gravity,self.drop_particle_life,self.drop_remove_on_floor,self.drop_floor_sound_chance,self.drop_image_row,self.drop_foam_image_row,self.drop_sound_row,self.drop_floor_sound_row,self.drop_foam_color_button,self.drop_auto,self.drop_auto_button,self.drop_script,self.drop_script_button)
        for label,widget in (('สคริปต์ขนาด',self.drop_script),('ตั้งค่าอัตโนมัติ',self.drop_script_button),('ขนาดบอล (% ความกว้าง)',self.drop_size_row),('โหมดอัตโนมัติ',self.drop_auto),('คำนวณใหม่',self.drop_auto_button),('จำนวนโฟมเทียบเท่า',self.drop_particle_count),('โฟมคำนวณจริงสูงสุด',self.drop_particle_budget),('แรงโน้มถ่วงบอล',self.drop_gravity),('เวลาที่โฟมอยู่ (วินาที)',self.drop_particle_life),('ถึงพื้น',self.drop_remove_on_floor),('โอกาสเสียงถึงพื้น (%)',self.drop_floor_sound_chance),('สีโฟม',self.drop_foam_color_button),('รูปภาพบนบอล',self.drop_image_row),('รูปภาพบนโฟม',self.drop_foam_image_row),('เสียงตอนแตก',self.drop_sound_row),('เสียงโฟมถึงพื้น',self.drop_floor_sound_row)): f.addRow(label,widget)
        self._apply_drop_auto()
    def _build_audio(self):
        f=self._form('Audio'); self.audio_enabled=QCheckBox('Enable audio'); self.audio_enabled.setChecked(True); f.addRow(self.audio_enabled); self.audio_mode=QComboBox(); self.audio_mode.addItem('Synth bounce','synth'); self.audio_mode.addItem('Original file','original'); self.audio_mode.addItem('Bounce samples','bounce-samples'); f.addRow('Circle audio mode',self.audio_mode); self.audio_row,self.audio_label=self._file_row(self.choose_audio); f.addRow('Source audio',self.audio_row); self.melody_row,self.melody_label=self._file_row(self.choose_melody); f.addRow('MIDI / JSON melody',self.melody_row); self.instrument=QComboBox(); self.instrument.addItem('piano','piano'); self.instrument.addItem('pluck','pluck'); self.instrument.addItem('bell','bell'); self.instrument.addItem('synth','synth'); self.note_volume=self._float(.8,0,1.5,.05,2); self.source_volume=self._float(.85,0,2,.05,2); self.transpose=self._int(0,-48,48); f.addRow('Instrument',self.instrument); f.addRow('Note volume',self.note_volume); f.addRow('Source volume',self.source_volume); f.addRow('Transpose',self.transpose); self.melody_loop=QCheckBox('Loop melody'); self.melody_loop.setChecked(True); self.restart_melody=QCheckBox('Restart melody on break'); self.restart_melody.setChecked(True); f.addRow(self.melody_loop); f.addRow(self.restart_melody)
    def _build_merge(self):
        f=self._form('Merge Ball'); self.merge_interval=NumberSlider(.8,.05,20,.05,2); self.merge_gravity=NumberSlider(980,0,3000,10,0); self.merge_bounce=NumberSlider(.78,0,1.2,.01,2); self.merge_hz=NumberSlider(240,30,1000,10,0); self.tank_scale=NumberSlider(1,.5,1.5,.01,2); self.pipe_count=NumberSlider(1,1,3,1,0); self.pipe_clearance=NumberSlider(8,0,100,1,0); self.level_percent=NumberSlider(15,-50,100,1,0); self.merge_volume=NumberSlider(.8,0,2,.05,2)
        for label,w in (('ช่วงเวลาปล่อยบอล',self.merge_interval),('แรงโน้มถ่วง',self.merge_gravity),('แรงเด้ง',self.merge_bounce),('Physics Hz',self.merge_hz),('ขนาดวง',self.tank_scale),('จำนวนท่อ',self.pipe_count),('ระยะเผื่อท่อ',self.pipe_clearance),('ขนาด LV2–LV9 (%)',self.level_percent),('ระดับเสียง',self.merge_volume)): f.addRow(label,w)
        self.merge_assets_row,self.merge_assets_label=self._file_row(self.choose_merge_assets); self.merge_assets_label.setText(self.merge_assets_path); f.addRow('รูปบอล LV1–LV9',self.merge_assets_row)
        self.merge_audio=QCheckBox('Enable merge audio'); self.merge_audio.setChecked(True); f.addRow(self.merge_audio); self.merge_row,self.merge_label=self._file_row(self.choose_merge_audio); self.victory_row,self.victory_label=self._file_row(self.choose_victory_audio); f.addRow('Merge sound',self.merge_row); f.addRow('Victory sound',self.victory_row)
    def _build_output(self):
        f=self._form('Output'); self.output_edit=QLineEdit(str(Path(__file__).resolve().parents[1]/'output'/'circle_ball_final.mp4')); f.addRow('Output MP4',self.output_edit); choose=QPushButton('Choose output file…'); choose.clicked.connect(self.choose_output); f.addRow(choose); self.progress=QProgressBar(); self.progress.setRange(0,100); f.addRow('Progress',self.progress); open_btn=QPushButton('Open output folder'); open_btn.clicked.connect(self.open_output_folder); f.addRow(open_btn)
    def _apply_video_preset(self,v): self.width.setValue(v[0]); self.height.setValue(v[1]); self.fps.setValue(v[2]); self._reset_engine()
    def _wire_live_controls(self):
        self._reset_pending=False
        controls=(self.ball_count,self.seed,self.seconds,self.width,self.height,self.fps,self.show_hud,self.show_numbers,self.rainbow,self.initial_angle,self.initial_speed,self.gravity,self.speed_growth,self.max_speed,self.base_radius,self.ball_growth,self.smooth_growth,self.arena_scale,self.restitution,self.bounce_growth,self.friction,self.air_drag,self.spike_count,self.spike_depth,self.spike_width,self.rotation_speed,self.gap_enabled,self.gap_size,self.gap_position,self.escape_hud,self.escape_countdown,self.trail,self.trail_speed,self.trail_spacing,self.audio_enabled,self.audio_mode,self.instrument,self.note_volume,self.source_volume,self.transpose,self.melody_loop,self.restart_melody,self.merge_interval,self.merge_gravity,self.merge_bounce,self.merge_hz,self.tank_scale,self.pipe_count,self.pipe_clearance,self.level_percent,self.merge_volume,self.merge_audio,self.drop_particle_count,self.drop_particle_budget,self.drop_ball_size,self.drop_gravity,self.drop_particle_life,self.drop_remove_on_floor,self.drop_floor_sound_chance,self.drop_script)
        for widget in controls:
            signal = widget.slider.valueChanged if hasattr(widget, 'slider') else (getattr(widget, 'valueChanged', None) or getattr(widget, 'stateChanged', None) or getattr(widget, 'currentIndexChanged', None))
            if signal: signal.connect(self._queue_reset)
    def _queue_reset(self, *_args):
        if self._reset_pending: return
        self._reset_pending=True
        QTimer.singleShot(100, self._finish_queued_reset)
    def _finish_queued_reset(self): self._reset_pending=False; self._reset_engine()
    def _set_control_visible(self, widget, visible, form=None):
        form=form or self.mode_form
        widget.setVisible(visible)
        label=form.labelForField(widget) if form else None
        if label: label.setVisible(visible)
    def _update_mode_visibility(self):
        merge=self.mode=='Merge Ball'; drop=self.mode=='Ball Drop Shatter'
        self.tabs.setTabVisible(1, not merge and not drop); self.tabs.setTabVisible(2, not merge); self.tabs.setTabVisible(3, not merge and not drop)
        self.tabs.setTabVisible(4, merge); self.tabs.setTabVisible(2, not merge)
        for widget in (self.ball_count,self.color_mode,self.show_numbers,self.show_hud,self.rainbow): self._set_control_visible(widget, not merge and not drop, self.tabs.widget(0).layout())
        for index,button in enumerate(self.ball_color_buttons): button.setVisible(not merge and (not drop or index==0))
        spikes=self.mode in ('Spikes','Spike Multiply'); opening=self.mode in ('Open Ring','Escape Split'); trail=self.mode=='Trail Draw'
        for widget in (self.spike_count,self.spike_depth,self.spike_width): self._set_control_visible(widget, spikes)
        for widget in (self.gap_enabled,self.gap_size,self.gap_position): self._set_control_visible(widget, opening)
        for widget in (self.escape_hud,self.escape_countdown): self._set_control_visible(widget, self.mode=='Escape Split')
        for widget in (self.trail,self.trail_speed,self.trail_spacing): self._set_control_visible(widget, trail)
        self._set_control_visible(self.rotation_speed, spikes)
        for widget in self.drop_controls: self._set_control_visible(widget, drop)
        for widget in (self.pattern_row,self.pattern_refresh,self.pattern_delete): self._set_control_visible(widget, not drop)
    def select_mode(self,name): self.mode=name; self.mode_combo.blockSignals(True); index=self.mode_combo.findData(name); self.mode_combo.setCurrentIndex(index if index >= 0 else 0); self.mode_combo.blockSignals(False); [b.setChecked(b.text()==name or (name=='Circle Battle' and b.text()=='วงกลมปกติ') or (name=='Spikes' and b.text()=='มีหนาม') or (name=='Open Ring' and b.text()=='วงกลมเปิด') or (name=='Trail Draw' and b.text()=='รอยวาด') or (name=='Spike Multiply' and b.text()=='หนามคูณบอล') or (name=='Escape Split' and b.text()=='ออกนอกจอเกิด 2 ลูก') or (name=='Ball Drop Shatter' and b.text()=='บอลตกใส่หนาม') or (name=='Merge Ball' and b.text()=='รวมบอล')) for b in self.mode_buttons]; self._update_mode_visibility(); self._reset_engine()
    def choose_audio(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose source audio','','Audio (*.wav *.mp3 *.m4a *.aac *.ogg *.flac);;All files (*)')
        if path: self.audio_file=path; self.audio_label.setText(path); self.status.setText(f'Audio selected: {Path(path).name}')
    def choose_melody(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose MIDI or JSON melody','','Melody (*.mid *.midi *.json);;All files (*)')
        if path: self.melody_file=path; self.melody_label.setText(path); self.status.setText(f'Melody selected: {Path(path).name}'); self._reset_engine()
    def choose_pattern(self):
        path,_=QFileDialog.getOpenFileName(self,'เลือกไฟล์แพทเทิร์น JSON','','แพทเทิร์น (*.json);;ทุกไฟล์ (*)')
        if path: self.pattern_file=path; self.pattern_label.setText(path); self.status.setText(f'เลือกแพทเทิร์นแล้ว: {Path(path).name}'); self._reset_engine()
    def choose_drop_image(self):
        path,_=QFileDialog.getOpenFileName(self,'เลือกรูปภาพบนบอล','','รูปภาพ (*.png *.jpg *.jpeg *.webp);;ทุกไฟล์ (*)')
        if path: self.drop_ball_image=path; self.drop_image_label.setText(path); self._reset_engine()
    def choose_drop_foam_image(self):
        path,_=QFileDialog.getOpenFileName(self,'เลือกรูปภาพบนโฟม','','รูปภาพ (*.png *.jpg *.jpeg *.webp);;ทุกไฟล์ (*)')
        if path: self.drop_foam_image=path; self.drop_foam_image_label.setText(path); self._reset_engine()
    def choose_drop_sound(self):
        path,_=QFileDialog.getOpenFileName(self,'เลือกเสียงตอนแตก','','เสียง (*.wav *.mp3 *.m4a *.aac *.ogg *.flac);;ทุกไฟล์ (*)')
        if path: self.drop_sound_file=path; self.drop_sound_label.setText(path)
    def choose_drop_floor_sound(self):
        path,_=QFileDialog.getOpenFileName(self,'เลือกเสียงโฟมถึงพื้น','','เสียง (*.wav *.mp3 *.m4a *.aac *.ogg *.flac);;ทุกไฟล์ (*)')
        if path: self.drop_floor_sound_file=path; self.drop_floor_sound_label.setText(path)
    def choose_drop_foam_color(self):
        color=QColorDialog.getColor(QColor(self.drop_foam_color),self,'เลือกสีโฟม')
        if color.isValid():
            self.drop_foam_color=color.name().lower(); self.drop_foam_color_button.setStyleSheet(f'background:{self.drop_foam_color};color:#111111'); self._reset_engine()
    def _apply_drop_auto(self,*_args):
        if not hasattr(self,'drop_auto') or not self.drop_auto.isChecked(): return
        count=recommended_foam_count(self.width.value(),self.drop_ball_size.value(),self.drop_particle_size.value()); self.drop_particle_count.setValue(count)
    def _force_drop_auto(self):
        self.drop_auto.setChecked(True); self._apply_drop_auto(); self.status.setText(f'คำนวณโฟมอัตโนมัติ: {int(self.drop_particle_count.value())} ชิ้น')
    def _change_drop_ball_percent(self,delta):
        self.drop_ball_size.setValue(max(1,min(1000,self.drop_ball_size.value()+delta))); self._apply_drop_auto()
    def _set_drop_size_script(self):
        self.drop_script.setChecked(True); self.drop_auto.setChecked(True); self.seconds.setValue(30); self.status.setText('สคริปต์พร้อม: 6 ขนาด × 5 วินาที = 30 วินาที'); self._reset_engine()
    def clear_pattern(self):
        self.pattern_file=''; self.pattern_label.clear(); self.status.setText('ล้างแพทเทิร์นที่เลือกแล้ว'); self._reset_engine()
    def refresh_from_pattern(self):
        if not self.pattern_file:
            self.status.setText('กรุณาเลือกไฟล์แพทเทิร์นก่อน'); return
        try:
            data=json.loads(Path(self.pattern_file).read_text(encoding='utf-8'))
            values=dict(data.get('defaults') or {})
            launch=dict(data.get('launch') or {})
            for event in data.get('events') or []:
                if float(event.get('time', 0)) <= 0: values.update({k:v for k,v in event.items() if k != 'time'})
            mapping={'gravity':self.gravity,'speed_growth':self.speed_growth,'max_speed':self.max_speed,'wall_restitution':self.restitution,'bounce_growth':self.bounce_growth,'wall_friction':self.friction,'air_drag':self.air_drag,'growth':self.ball_growth,'spike_count':self.spike_count,'spike_depth':self.spike_depth,'spike_width':self.spike_width,'rotation_speed':self.rotation_speed,'gap_size':self.gap_size,'gap_position':self.gap_position,'trail_rainbow_speed':self.trail_speed,'trail_stamp_spacing':self.trail_spacing}
            for key,widget in mapping.items():
                if key in values: widget.setValue(float(values[key]))
            launch_mapping={'fps':self.fps,'seconds':self.seconds,'width':self.width,'height':self.height,'initial_angle':self.initial_angle,'initial_speed':self.initial_speed,'ball_count':self.ball_count,'base_radius':self.base_radius,'arena_scale':self.arena_scale,'substeps':None}
            for key,widget in launch_mapping.items():
                if widget is not None and key in launch: widget.setValue(float(launch[key]))
            if launch.get('escape_duplicate'):
                self.select_mode('Escape Split')
            elif launch.get('spike_duplicate'):
                self.select_mode('Spike Multiply')
            if 'rainbow_border' in launch: self.rainbow.setChecked(bool(launch['rainbow_border']))
            if 'gap_enabled' in values: self.gap_enabled.setChecked(bool(values['gap_enabled']))
            if 'show_ball_numbers' in values: self.show_numbers.setChecked(bool(values['show_ball_numbers']))
            if 'ball_color_mode' in values:
                index=self.color_mode.findData(str(values['ball_color_mode']))
                if index >= 0: self.color_mode.setCurrentIndex(index)
            self.status.setText(f'อัปเดตค่าจากแพทเทิร์นแล้ว: {Path(self.pattern_file).name}'); self._reset_engine()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.status.setText(f'อ่านแพทเทิร์นไม่สำเร็จ: {exc}')
    def choose_merge_audio(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose merge sound','','Audio (*.wav *.mp3 *.m4a *.aac *.ogg *.flac);;All files (*)')
        if path: self.merge_sound_file=path; self.merge_label.setText(path)
    def choose_merge_assets(self):
        path=QFileDialog.getExistingDirectory(self,'เลือกโฟลเดอร์รูปบอล LV1–LV9',self.merge_assets_path)
        if path: self.merge_assets_path=path; self.merge_assets_label.setText(path); self.status.setText('ใช้ไฟล์ 1–9 จากโฟลเดอร์ที่เลือก'); self._reset_engine()
    def choose_victory_audio(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose victory sound','','Audio (*.wav *.mp3 *.m4a *.aac *.ogg *.flac);;All files (*)')
        if path: self.victory_sound_file=path; self.victory_label.setText(path)
    def choose_output(self):
        path,_=QFileDialog.getSaveFileName(self,'Choose output MP4',self.output_edit.text(),'MP4 (*.mp4)')
        if path: self.output_edit.setText(path)
    def _thai_ui(self):
        self.setWindowTitle('โปรแกรมบอลเด้ง — สตูดิโอ')
        button_map={'Preview':'พรีวิว','Render MP4':'เรนเดอร์ MP4','■ Stop':'หยุดเรนเดอร์','Restart':'เริ่มใหม่','Choose…':'เลือกไฟล์…','Choose output file…':'เลือกไฟล์ปลายทาง…','Open output folder':'เปิดโฟลเดอร์ผลลัพธ์','Copy log':'คัดลอก Log','Clear':'ล้าง','Circle Battle':'วงกลมปกติ','Spikes':'มีหนาม','Open Ring':'วงกลมเปิด','Trail Draw':'รอยวาด','Spike Multiply':'หนามคูณบอล','Escape Split':'ออกนอกจอเกิด 2 ลูก','Ball Drop Shatter':'บอลตกใส่หนาม','Merge Ball':'รวมบอล'}
        label_map={'All settings below are sent directly to the selected engine.':'ค่าทั้งหมดจะถูกส่งเข้าเอนจินที่เลือกโดยตรง','Ball count':'จำนวนบอล','Duration (s)':'ความยาว (วินาที)','Initial angle':'มุมเริ่มต้น','Initial speed':'ความเร็วเริ่มต้น','Gravity':'แรงโน้มถ่วง','Speed growth':'ตัวคูณความเร็วเมื่อเด้ง','Max speed':'ความเร็วสูงสุด','Base radius':'รัศมีบอลเริ่มต้น','Growth per bounce':'ขนาดเพิ่มต่อการเด้ง','Smooth growth speed':'ความเร็วการขยาย','Arena scale':'ขนาดสนาม','Wall restitution':'แรงเด้งกำแพง','Wall friction':'แรงเสียดทานกำแพง','Air drag':'แรงต้านอากาศ','Spike count':'จำนวนหนาม','Spike depth':'ความลึกหนาม','Spike width':'ความกว้างหนาม','Rotation speed':'ความเร็วหมุน','Gap size':'ขนาดช่องว่าง','Gap position':'ตำแหน่งช่องว่าง','Trail rainbow speed':'ความเร็วสีรอย','Trail stamp spacing':'ระยะประทับรอย','Circle audio mode':'โหมดเสียงวงกลม','Source audio':'ไฟล์เสียงต้นฉบับ','MIDI / JSON melody':'ทำนอง MIDI / JSON','Instrument':'เครื่องดนตรี','Note volume':'ความดังโน้ต','Source volume':'ความดังเสียงต้นฉบับ','Transpose':'เลื่อนคีย์','Spawn interval':'ช่วงเวลาปล่อยบอล','Tank scale':'ขนาดถัง','Pipe clearance':'ระยะเผื่อท่อ','LV2-8 size %':'ขนาด LV2-8 (%)','Merge sound':'เสียงตอนรวม','Victory sound':'เสียงชัยชนะ','Output MP4':'ไฟล์ MP4 ผลลัพธ์','Progress':'ความคืบหน้า'}
        for widget in self.findChildren(QPushButton):
            if widget.text() in button_map: widget.setText(button_map[widget.text()])
        for widget in self.findChildren(QLabel):
            if widget.text() in label_map: widget.setText(label_map[widget.text()])
        for widget in self.findChildren(QCheckBox):
            if widget.text() == 'Enable audio': widget.setText('เปิดเสียง')
            elif widget.text() == 'Loop melody': widget.setText('วนทำนอง')
            elif widget.text() == 'Restart melody on break': widget.setText('เริ่มทำนองใหม่เมื่อแตก')
            elif widget.text() == 'Enable merge audio': widget.setText('เปิดเสียงตอนรวมบอล')
        for index,text in enumerate(('เสียงสังเคราะห์','ไฟล์เสียงต้นฉบับ','ตัวอย่างเสียงเด้ง')):
            if index < self.audio_mode.count(): self.audio_mode.setItemText(index,text)
        for index,text in enumerate(('เปียโน','พิณดีด','ระฆัง','ซินธ์')):
            if index < self.instrument.count(): self.instrument.setItemText(index,text)
        for index,name in enumerate(('ทั่วไป','ฟิสิกส์วงกลม','ตั้งค่าโหมด','เสียง','รวมบอล','ผลลัพธ์')):
            if index < self.tabs.count(): self.tabs.setTabText(index,name)
    def _circle_args(self):
        flags={'Circle Battle':['--spike-count','0'],'Spikes':['--spike-count',str(int(self.spike_count.value()))],'Open Ring':['--spike-count','0','--gap-enabled','1'],'Trail Draw':['--spike-count','0','--motion-trail','1'],'Spike Multiply':['--spike-count',str(int(self.spike_count.value())),'--spike-duplicate','1'],'Escape Split':['--spike-count','0','--gap-enabled','1','--escape-duplicate','1']}[self.mode]
        argv=['--seed',str(self.seed.value()),'--fps',str(self.fps.value()),'--seconds',str(self.seconds.value()),'--width',str(self.width.value()),'--height',str(self.height.value()),'--ball-count',str(self.ball_count.value()),'--initial-angle',str(self.initial_angle.value()),'--initial-speed',str(self.initial_speed.value()),'--gravity',str(self.gravity.value()),'--speed-growth',str(self.speed_growth.value()),'--max-speed',str(self.max_speed.value()),'--base-radius',str(self.base_radius.value()),'--growth',str(self.ball_growth.value()),'--smooth-growth-speed',str(self.smooth_growth.value()),'--arena-scale',str(self.arena_scale.value()),'--wall-restitution',str(self.restitution.value()),'--bounce-growth',str(self.bounce_growth.value()),'--wall-friction',str(self.friction.value()),'--air-drag',str(self.air_drag.value()),'--spike-depth',str(self.spike_depth.value()),'--spike-width',str(self.spike_width.value()),'--rotation-speed',str(self.rotation_speed.value()),'--gap-size',str(self.gap_size.value()),'--gap-position',str(self.gap_position.value()),'--trail-rainbow-speed',str(self.trail_speed.value()),'--trail-stamp-spacing',str(self.trail_spacing.value()),'--ball-color-mode',str(self.color_mode.currentData()),'--audio','1' if self.audio_enabled.isChecked() else '0','--audio-mode',str(self.audio_mode.currentData()),'--instrument',str(self.instrument.currentData()),'--note-volume',str(self.note_volume.value()),'--source-volume',str(self.source_volume.value()),'--transpose',str(self.transpose.value()),'--melody-loop','1' if self.melody_loop.isChecked() else '0','--restart-melody-on-break','1' if self.restart_melody.isChecked() else '0','--rainbow-border','1' if self.rainbow.isChecked() else '0','--show-hud','1' if self.show_hud.isChecked() else '0','--show-ball-numbers','1' if self.show_numbers.isChecked() else '0']+flags
        if self.gap_enabled.isChecked(): argv+=['--gap-enabled','1']
        if self.audio_file: argv+=['--audio-file',self.audio_file]
        if self.melody_file: argv+=['--melody-file',self.melody_file]
        argv+=['--ball-colors',','.join(self.ball_colors)]
        if self.pattern_file: argv+=['--pattern-file',self.pattern_file]
        return build_arg_parser().parse_args(argv)
    def _drop_args(self):
        ball_radius=self.width.value()*self.drop_ball_size.value()/200.0
        argv=['--width',str(self.width.value()),'--height',str(self.height.value()),'--fps',str(self.fps.value()),'--seconds',str(self.seconds.value()),'--seed',str(self.seed.value()),'--one-shot','1','--gravity',str(self.drop_gravity.value()),'--ball-size',str(ball_radius),'--ball-color',self.ball_colors[0],'--foam-color',self.drop_foam_color,'--particle-count',str(int(self.drop_particle_count.value())),'--particle-budget',str(int(self.drop_particle_budget.value())),'--particle-size',str(self.drop_particle_size.value()),'--particle-life',str(self.drop_particle_life.value()),'--remove-foam-on-floor','1' if self.drop_remove_on_floor.isChecked() else '0','--floor-sound-chance',str(self.drop_floor_sound_chance.value()/100.0),'--particle-speed',str(self.drop_particle_speed.value()),'--spike-count','1','--spike-height',str(self.drop_spike_height.value())]
        if self.drop_script.isChecked(): argv+=['--size-script','5,10,25,50,75,100','--segment-seconds','5','--auto-foam-from-size','1' if self.drop_auto.isChecked() else '0']
        if self.drop_ball_image: argv+=['--ball-image',self.drop_ball_image]
        if self.drop_foam_image: argv+=['--foam-image',self.drop_foam_image]
        if self.drop_sound_file: argv+=['--shatter-sound-file',self.drop_sound_file]
        if self.drop_floor_sound_file: argv+=['--floor-sound-file',self.drop_floor_sound_file]
        return drop_cli(argv)
    def _reset_engine(self):
        if self.mode=='Merge Ball':
            out=Path(self.output_edit.text()) if hasattr(self,'output_edit') else Path('output/merge_ball_final.mp4'); self.output_edit.setText(str(out.with_name('merge_ball_final.mp4'))) if hasattr(self,'output_edit') else None
            argv=['--width',str(self.width.value()),'--height',str(self.height.value()),'--fps',str(self.fps.value()),'--physics-hz',str(int(self.merge_hz.value())),'--seconds',str(self.seconds.value()),'--seed',str(self.seed.value()),'--spawn-interval',str(self.merge_interval.value()),'--gravity',str(self.merge_gravity.value()),'--bounce',str(self.merge_bounce.value()),'--tank-scale',str(self.tank_scale.value()),'--pipe-count',str(int(self.pipe_count.value())),'--pipe-clearance',str(self.pipe_clearance.value()),'--level-size-percent',str(self.level_percent.value()),'--assets',self.merge_assets_path]; self.engine=MergeSimulation(merge_cli(argv)); self.engine.config.merge_sound_file=self.merge_sound_file; self.engine.config.victory_sound_file=self.victory_sound_file
        elif self.mode=='Ball Drop Shatter':
            out=Path(self.output_edit.text()) if hasattr(self,'output_edit') else Path('output/drop_shatter_final.mp4'); self.output_edit.setText(str(out.with_name('drop_shatter_final.mp4'))) if hasattr(self,'output_edit') else None; self.engine=DropSimulation(self._drop_args())
        else:
            out=Path(self.output_edit.text()) if hasattr(self,'output_edit') else Path('output/circle_ball_final.mp4'); self.output_edit.setText(str(out.with_name('circle_ball_final.mp4'))) if hasattr(self,'output_edit') else None; self.engine=CircleSimulation(self._circle_args())
        self.playing=False; self.timeline.setValue(0) if hasattr(self,'timeline') else None; self._paint()
    def _set_play(self,v): self.playing=v; self.play_btn.setText('⏸' if v else '▶')
    def _tick(self):
        if self.playing and self.engine and self.engine.frame_index<self.engine.total_frames: self.engine.advance_frame(); self._paint()
    def _paint(self):
        if self.engine: self.preview.set_frame(self.engine.draw_frame(360,640)); self.time_label.setText(f'{self.engine.state.elapsed_time:05.2f} / {self.seconds.value():05.2f}')
    def open_output_folder(self): p=Path(self.output_edit.text()); p.parent.mkdir(parents=True,exist_ok=True); QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))
    def _read_render_output(self):
        if not self.process:return
        lines=bytes(self.process.readAllStandardOutput()).decode(errors='replace').splitlines()
        for line in lines:
            self.log.append(line)
            if 'APP_PROGRESS' in line:
                try:
                    value=max(0,min(100,int(float(line.split('APP_PROGRESS',1)[1].strip().split(None,1)[0])))); self.progress.setValue(value); self.top_progress.setValue(value)
                except (ValueError,IndexError):pass
    def _read_render_error(self):
        raw=bytes(self.process.readAllStandardError()).decode(errors='replace').strip() if self.process else ''
        if raw:
            for line in raw.splitlines(): self.log.append('[stderr] '+line)
            self.status.setText(raw.splitlines()[-1][-180:])
    def _process_error(self,error):
        message=f'QProcess error: {error}'
        self.log.append('[process] '+message)
        self.status.setText(message)
    def copy_log(self):
        QApplication.clipboard().setText(self.log.toPlainText())
        self.status.setText('Log copied to clipboard')
    def _render_finished(self,code,_status):
        self._read_render_output(); cancelled=self._render_cancel_requested; value=100 if code==0 and not cancelled else self.progress.value(); self.progress.setValue(value); self.top_progress.setValue(value); self.status.setText('ยกเลิกการเรนเดอร์' if cancelled else ('เรนเดอร์เสร็จแล้ว' if code==0 else f'Render failed (exit {code})')); self.log.append('[process] Render cancelled by user') if cancelled else None; self.process=None; self._render_cancel_requested=False; self.stop_render_btn.setEnabled(False)
    def stop_render(self):
        if not self.process or self.process.state()==QProcess.NotRunning: return
        self._render_cancel_requested=True; self.log.append('[process] Stopping render…'); self.status.setText('กำลังหยุดเรนเดอร์…'); self.process.terminate()
        QTimer.singleShot(1200, lambda: self.process.kill() if self.process and self.process.state()!=QProcess.NotRunning else None)
    def render_mp4(self):
        if self.process and self.process.state()!=QProcess.NotRunning:return
        if self.mode not in ('Merge Ball','Ball Drop Shatter') and self.audio_enabled.isChecked() and self.audio_mode.currentData() in ('original','bounce-samples') and not self.audio_file:
            self.log.append('[validation] Choose source audio first'); self.status.setText('Choose source audio first'); return
        output=Path(self.output_edit.text()); output.parent.mkdir(parents=True,exist_ok=True); self.progress.setValue(0); self.top_progress.setValue(0); self.log.append(f'--- Starting {self.mode} render ---'); self.log.append(f'Output: {output}'); self.process=QProcess(self); self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[1])); self.process.readyReadStandardOutput.connect(self._read_render_output); self.process.readyReadStandardError.connect(self._read_render_error); self.process.errorOccurred.connect(self._process_error); self.process.finished.connect(self._render_finished)
        if self.mode=='Merge Ball':
            args=['-m','engines.merge_engine','--out',str(output),'--width',str(self.width.value()),'--height',str(self.height.value()),'--fps',str(self.fps.value()),'--physics-hz',str(int(self.merge_hz.value())),'--seconds',str(self.seconds.value()),'--seed',str(self.seed.value()),'--spawn-interval',str(self.merge_interval.value()),'--gravity',str(self.merge_gravity.value()),'--bounce',str(self.merge_bounce.value()),'--tank-scale',str(self.tank_scale.value()),'--pipe-count',str(int(self.pipe_count.value())),'--pipe-clearance',str(self.pipe_clearance.value()),'--level-size-percent',str(self.level_percent.value()),'--assets',self.merge_assets_path]
            if self.merge_audio.isChecked():
                args += ['--merge-sound','--merge-volume',str(self.merge_volume.value())]
                if self.merge_sound_file: args += ['--merge-sound-file',self.merge_sound_file]
                if self.victory_sound_file: args += ['--victory-sound-file',self.victory_sound_file]
        elif self.mode=='Ball Drop Shatter':
            a=self._drop_args(); args=['-m','engines.drop_engine']
            for key,value in vars(a).items():
                if key=='out' or value in ('',None): continue
                args += [f'--{key.replace("_","-")}',str(value)]
            args += ['--out',str(output)]
        else:
            a=self._circle_args(); args=['main.py']
            for key,value in vars(a).items():
                if key=='out' or key=='ball_images' or value in ('',None):continue
                args += [f'--{key.replace("_","-")}',str(value)]
            args += ['--out',str(output)]
        self.log.append('Command: '+sys.executable+' '+' '.join(args)); self.process.start(sys.executable,args); self.stop_render_btn.setEnabled(True); self.status.setText(f'Rendering {self.mode}…')
