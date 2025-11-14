from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt6.QtLottie import QLottieAnimation

class Window(QWidget):
    def __init__(self):
        super().__init__()

        self.anim = QLottieAnimation("rocket_progress.json")
        self.anim.setMinAndMaxFrames(0, 100)
        self.anim.setCurrentFrame(0)

        layout = QVBoxLayout(self)
        layout.addWidget(self.anim)

    def set_progress(self, percent):
        self.anim.setCurrentFrame(int(percent))

app = QApplication([])
w = Window()
w.show()
app.exec()
