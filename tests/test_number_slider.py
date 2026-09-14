import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QFileDialog
from ui.main_window import MainWindow, NumberSlider


def test_number_slider_supports_dragging_and_manual_numeric_entry():
    app=QApplication.instance() or QApplication([])
    control=NumberSlider(1.5,0,10,.1,1)
    assert isinstance(control.readout,QDoubleSpinBox)
    control.readout.setValue(4.2)
    assert control.value()==4.2
    control.slider.setValue(73)
    assert control.readout.value()==7.3
    assert app is not None


def test_merge_image_folder_picker_updates_preview_engine(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args: str(tmp_path))
    window=MainWindow(); window.select_mode('Merge Ball'); window.choose_merge_assets()
    assert window.merge_assets_path==str(tmp_path)
    assert window.engine.config.assets==str(tmp_path)
    window.close(); assert app is not None
