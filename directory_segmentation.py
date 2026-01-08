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
from PyQt5.QtGui import QColor, QImage


class DirectorySegmentation(QMainWindow):
    self._mask = None  # Mask overlay as QImage
    self._mask_color = QColor(255, 0, 0, 128)  # Semi-transparent red
    
    def _init_mask(self):
        if hasattr(self, '_original_pixmap') and self._original_pixmap is not None:
            size = self._original_pixmap.size()
            self._mask = QImage(size, QImage.Format_ARGB32_Premultiplied)
            self._mask.fill(0)
        else:
            self._mask = None
    
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
        # Update zoom and reset pan if needed
        prev_zoom = getattr(self, '_zoom_factor', 1.0)
        self._zoom_factor = value / 100.0
        # Optionally, keep pan center
        if hasattr(self, '_original_pixmap') and self._original_pixmap is not None:
            if prev_zoom != self._zoom_factor:
                # Adjust pan to keep center
                label_size = self.image_label.size()
                pan_x, pan_y = getattr(self, '_pan_offset', (0, 0))
                center_x = pan_x + label_size.width() // 2
                center_y = pan_y + label_size.height() // 2
                new_scaled_width = int(self._original_pixmap.width() * self._zoom_factor)
                new_scaled_height = int(self._original_pixmap.height() * self._zoom_factor)
                new_pan_x = max(0, center_x - label_size.width() // 2)
                new_pan_y = max(0, center_y - label_size.height() // 2)
                max_x = max(0, new_scaled_width - label_size.width())
                max_y = max(0, new_scaled_height - label_size.height())
                self._pan_offset = (min(new_pan_x, max_x), min(new_pan_y, max_y))
        self._update_image_display()

    def _on_tool_changed(self, button):
        # Switch between pen and cursor (pan) tool
        if self.cursor_radio.isChecked():
            self.image_label.setCursor(Qt.OpenHandCursor)
        else:
            self.image_label.setCursor(Qt.CrossCursor)

    def _on_radius_changed(self, value):
        # Placeholder: implement pen radius logic if needed
        pass

    def _update_image_display(self):
        if not hasattr(self, '_original_pixmap') or self._original_pixmap is None:
            return
        label_size = self.image_label.size()
        zoom = self.zoom_spin.value() / 100.0 if hasattr(self, 'zoom_spin') else 1.0
        orig_pixmap = self._original_pixmap
        # Calculate scaled size
        scaled_width = int(orig_pixmap.width() * zoom)
        scaled_height = int(orig_pixmap.height() * zoom)
        scaled_pixmap = orig_pixmap.scaled(scaled_width, scaled_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Pan logic: show a region of the scaled image if zoomed in
        pan_x, pan_y = getattr(self, '_pan_offset', (0, 0))
        # Ensure pan offset is within bounds
        max_x = max(0, scaled_pixmap.width() - label_size.width())
        max_y = max(0, scaled_pixmap.height() - label_size.height())
        pan_x = min(max(pan_x, 0), max_x)
        pan_y = min(max(pan_y, 0), max_y)
        self._pan_offset = (pan_x, pan_y)

        if scaled_pixmap.width() > label_size.width() or scaled_pixmap.height() > label_size.height():
            # Crop the visible region
            cropped = scaled_pixmap.copy(pan_x, pan_y, min(label_size.width(), scaled_pixmap.width()-pan_x), min(label_size.height(), scaled_pixmap.height()-pan_y))
            self.image_label.setPixmap(cropped)
        else:
            self.image_label.setPixmap(scaled_pixmap)

    def _load_current_image(self):
        if not self.image_files:
            self.image_label.setText("No image available")
            self.image_label.setPixmap(QPixmap())
            self._original_pixmap = None
                self._mask = None
                return

        image_path = self.image_files[self.current_index]
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.image_label.setText("Unable to load image")
            self.image_label.setPixmap(QPixmap())
            self._original_pixmap = None
                self._mask = None
                return

        self._original_pixmap = pixmap
        self._zoom_factor = self.zoom_spin.value() / 100.0 if hasattr(self, 'zoom_spin') else 1.0
        self._pan_offset = getattr(self, '_pan_offset', (0, 0))
            self._init_mask()
        self._update_image_display()

    def _set_pixmap_scaled(self, pixmap):
        # Deprecated: replaced by _update_image_display
        self._update_image_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_image_display()
    def mousePressEvent(self, event):
        if self.cursor_radio.isChecked() and event.button() == Qt.LeftButton:
            if self.image_label.underMouse():
                self._dragging = True
                self._drag_start = event.pos()
                self._pan_start = getattr(self, '_pan_offset', (0, 0))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, '_dragging', False) and self.cursor_radio.isChecked():
            delta = event.pos() - self._drag_start
            pan_x, pan_y = self._pan_start
            new_pan_x = pan_x - delta.x()
            new_pan_y = pan_y - delta.y()
            # Clamp pan
            if hasattr(self, '_original_pixmap') and self._original_pixmap is not None:
                zoom = self.zoom_spin.value() / 100.0
                scaled_width = int(self._original_pixmap.width() * zoom)
                scaled_height = int(self._original_pixmap.height() * zoom)
                label_size = self.image_label.size()
                max_x = max(0, scaled_width - label_size.width())
                max_y = max(0, scaled_height - label_size.height())
                new_pan_x = min(max(new_pan_x, 0), max_x)
                new_pan_y = min(max(new_pan_y, 0), max_y)
            self._pan_offset = (new_pan_x, new_pan_y)
            self._update_image_display()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, '_dragging', False) and event.button() == Qt.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(event)

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
