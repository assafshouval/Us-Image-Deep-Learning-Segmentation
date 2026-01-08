import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QFrame,
    QLabel,
    QMainWindow,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


class DirectorySegmentation(QMainWindow):
    def __init__(self, directory_path, parent=None):
        super().__init__(parent)
        self.directory_path = directory_path
        self.image_files = self._discover_images(directory_path)
        self.current_index = 0

        window_title = os.path.basename(os.path.normpath(directory_path)) or directory_path
        self.setWindowTitle(window_title)
        self.resize(960, 720)

        self._setup_central_frame()
        self._setup_upper_toolbar()
        self._setup_lower_toolbar()
        self._load_current_image()

    def _discover_images(self, directory_path):
        supported = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
        items = os.listdir(directory_path) if os.path.isdir(directory_path) else []
        images = [
            os.path.join(directory_path, item)
            for item in sorted(items)
            if os.path.splitext(item)[1].lower() in supported
        ]
        return images

    def _setup_central_frame(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)

        frame = QFrame(container)
        frame.setFrameShape(QFrame.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel(frame)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setText("No image available")
        frame_layout.addWidget(self.image_label)

        layout.addWidget(frame)
        self.setCentralWidget(container)

    def _setup_upper_toolbar(self):
        toolbar = QToolBar("Navigation", self)
        toolbar.setMovable(False)
        toolbar.setAllowedAreas(Qt.TopToolBarArea)

        back_action = QAction("Back", self)
        back_action.triggered.connect(self.close)
        toolbar.addAction(back_action)

        prev_action = QAction("Prev", self)
        prev_action.triggered.connect(self._go_previous)
        toolbar.addAction(prev_action)

        next_action = QAction("Next", self)
        next_action.triggered.connect(self._go_next)
        toolbar.addAction(next_action)

        self.addToolBar(Qt.TopToolBarArea, toolbar)

    def _setup_lower_toolbar(self):
        toolbar = QToolBar("Manual Segmentation", self)
        toolbar.setMovable(False)
        toolbar.setAllowedAreas(Qt.BottomToolBarArea)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)

        # --- Zoom control ---
        from PyQt5.QtWidgets import QSpinBox, QLabel, QRadioButton, QButtonGroup, QHBoxLayout, QWidget

        zoom_label = QLabel("Zoom:")
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(10, 400)
        self.zoom_spin.setValue(100)
        self.zoom_spin.setSuffix(" %")
        self.zoom_spin.setSingleStep(10)
        self.zoom_spin.valueChanged.connect(self._on_zoom_changed)

        # --- Tool selection (Pen/Cursor) ---
        tool_label = QLabel("Tool:")
        self.pen_radio = QRadioButton("Pen")
        self.cursor_radio = QRadioButton("Cursor")
        self.pen_radio.setChecked(True)
        self.tool_group = QButtonGroup(toolbar)
        self.tool_group.addButton(self.pen_radio)
        self.tool_group.addButton(self.cursor_radio)
        self.tool_group.buttonClicked.connect(self._on_tool_changed)

        # --- Pen radius control ---
        radius_label = QLabel("Radius:")
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(1, 100)
        self.radius_spin.setValue(10)
        self.radius_spin.setSingleStep(1)
        self.radius_spin.valueChanged.connect(self._on_radius_changed)

        # Layout for controls
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(zoom_label)
        controls_layout.addWidget(self.zoom_spin)
        controls_layout.addSpacing(16)
        controls_layout.addWidget(tool_label)
        controls_layout.addWidget(self.pen_radio)
        controls_layout.addWidget(self.cursor_radio)
        controls_layout.addSpacing(16)
        controls_layout.addWidget(radius_label)
        controls_layout.addWidget(self.radius_spin)
        controls_layout.addStretch()

        toolbar.addWidget(controls_widget)
        self.addToolBar(Qt.BottomToolBarArea, toolbar)

    def _on_zoom_changed(self, value):
        # Placeholder: implement zoom logic if needed
        self._load_current_image()

    def _on_tool_changed(self, button):
        # Placeholder: implement tool switching logic if needed
        pass

    def _on_radius_changed(self, value):
        # Placeholder: implement pen radius logic if needed
        pass

    def _load_current_image(self):
        if not self.image_files:
            self.image_label.setText("No image available")
            self.image_label.setPixmap(QPixmap())
            return

        image_path = self.image_files[self.current_index]
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.image_label.setText("Unable to load image")
            self.image_label.setPixmap(QPixmap())
            return

        self._set_pixmap_scaled(pixmap)

    def _set_pixmap_scaled(self, pixmap):
        if self.image_label.width() <= 0 or self.image_label.height() <= 0:
            self.image_label.setPixmap(pixmap)
            return
        scaled = pixmap.scaled(
            self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        pixmap = self.image_label.pixmap()
        if pixmap:
            self._set_pixmap_scaled(pixmap)

    def _go_previous(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self._load_current_image()

    def _go_next(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self._load_current_image()
