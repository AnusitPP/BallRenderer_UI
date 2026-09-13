COLORS = {
    "canvas": "#0a0c10", "panel": "#101319", "panel2": "#15181f",
    "border": "#212630", "text": "#f0f2f7", "muted": "#949eb0",
    "green": "#21c45e", "green_dark": "#0e2e1c", "cyan": "#33c7eb",
}

STYLESHEET = """
QMainWindow, QWidget { background: #0a0c10; color: #f0f2f7; font-family: Arial, 'Segoe UI'; }
QFrame#panel, QGroupBox { background: #101319; border: 1px solid #212630; border-radius: 12px; }
QLabel#muted { color: #949eb0; }
QLabel#section { color: #949eb0; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QPushButton { background: #15181f; border: 1px solid #212630; border-radius: 9px; color: #f0f2f7; padding: 9px 13px; }
QPushButton:hover { border-color: #21c45e; }
QPushButton#primary { background: #21c45e; border: none; font-weight: 700; }
QPushButton#primary:hover { background: #28d66b; }
QPushButton#mode { text-align: left; }
QPushButton#mode:checked { background: #1a2b24; border: 1px solid #21c45e; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #15181f; border: none; border-radius: 8px; padding: 8px; color: #f0f2f7; }
QSlider::groove:horizontal { height: 5px; background: #212630; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #21c45e; border-radius: 3px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #f0f2f7; border-radius: 7px; }
QProgressBar { height: 5px; border: none; background: #212630; border-radius: 2px; }
QProgressBar::chunk { background: #21c45e; border-radius: 2px; }
QTabBar::tab { color: #949eb0; padding: 10px 18px; }
QTabBar::tab:selected { color: #f0f2f7; border-bottom: 3px solid #21c45e; }
"""
