import os

from PyQt5.QtWidgets import QMainWindow, QWidget


class DirectorySegmentation(QMainWindow):
    def __init__(self, directory_path, parent=None):
        super().__init__(parent)
        self.directory_path = directory_path

        window_title = os.path.basename(os.path.normpath(directory_path)) or directory_path
        self.setWindowTitle(window_title)
        self.resize(600, 400)

        placeholder = QWidget(self)
        self.setCentralWidget(placeholder)
