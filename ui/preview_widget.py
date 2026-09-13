from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget
import cv2

class PreviewWidget(QWidget):
    timeChanged = Signal(float)
    def __init__(self, parent=None):
        super().__init__(parent); self.image = None; self.setMinimumSize(360, 520)
    def set_frame(self, frame):
        if frame is None: return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888).copy()
        self.update()
    def paintEvent(self, event):
        p = QPainter(self); p.fillRect(self.rect(), '#060709')
        if self.image:
            pix = QPixmap.fromImage(self.image).scaled(self.size(),  Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap((self.width()-pix.width())//2, (self.height()-pix.height())//2, pix)
