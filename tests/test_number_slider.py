import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from PySide6.QtWidgets import QApplication, QDoubleSpinBox
from ui.main_window import NumberSlider


def test_number_slider_supports_dragging_and_manual_numeric_entry():
    app=QApplication.instance() or QApplication([])
    control=NumberSlider(1.5,0,10,.1,1)
    assert isinstance(control.readout,QDoubleSpinBox)
    control.readout.setValue(4.2)
    assert control.value()==4.2
    control.slider.setValue(73)
    assert control.readout.value()==7.3
    assert app is not None
