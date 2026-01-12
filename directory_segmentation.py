import os
import yaml
from pathlib import Path

from PyQt5.QtCore import Qt, QPoint, QEvent
from PyQt5.QtGui import QPixmap, QCursor, QPen
from PyQt5.QtWidgets import (
    QAction,
    QFrame,
    QLabel,
    QMainWindow,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QPushButton, QFileDialog, QMessageBox
from PyQt5.QtWidgets import QColorDialog
from PyQt5.QtWidgets import QSpinBox, QLabel, QRadioButton, QButtonGroup, QHBoxLayout, QWidget

from output_manager import OutputManager
from workspace_config import WorkspaceConfig

class DirectorySegmentation(QMainWindow):
    def __init__(self, directory_path, parent=None, workspace_mode="create"):
        super().__init__(parent)
        self._mask = None  # Mask overlay as QImage
        self._overlay_color = QColor(255, 0, 0)
        self._overlay_alpha = 128
        self.workspace_mode = workspace_mode  # "create" or "open"
        self.workspace_path = None
        
        if workspace_mode == "open":
            # Opening existing workspace
            self.workspace_path = directory_path
            self.directory_path = self._load_input_directory_from_config(directory_path)
            self.image_files = self._discover_images_from_workspace(directory_path)
        else:
            # Creating new workspace from source directory
            self.directory_path = directory_path
            self.image_files = self._discover_images(directory_path)
        
        self.current_index = 0

        # Initialize undo/redo stacks
        self._undo_stack = []
        self._redo_stack = []

        # Initialize tool radio buttons and group early to avoid AttributeError
        self.pen_radio = QRadioButton("Pen")
        self.cursor_radio = QRadioButton("Cursor")
        self.erase_radio = QRadioButton("Erase")
        self.pen_radio.setChecked(True)
        self.tool_group = QButtonGroup()
        self.tool_group.addButton(self.pen_radio)
        self.tool_group.addButton(self.cursor_radio)
        self.tool_group.addButton(self.erase_radio)

        if workspace_mode == "open":
            window_title = f"Workspace: {os.path.basename(os.path.normpath(directory_path))}"
        else:
            window_title = os.path.basename(os.path.normpath(directory_path)) or directory_path
        self.setWindowTitle(window_title)
        self.resize(960, 720)

        # Initialize output manager for workspace structure
        if workspace_mode == "open":
            # Use existing workspace path
            self.output_manager = None  # Not creating new workspace
            self.original_dir = os.path.join(directory_path, "OriginalImage")
            self.mask_dir = os.path.join(directory_path, "Mask")
        else:
            # Create new workspace
            self.output_manager = OutputManager(self.directory_path)
            try:
                self.original_dir, self.mask_dir = self.output_manager.initialize_structure()
                self.workspace_path = self.output_manager.get_workspace_path()
            except OSError as e:
                QMessageBox.critical(self, "Workspace Error", f"Failed to create workspace: {e}")
                self.original_dir = None
                self.mask_dir = None

        self._setup_central_frame()
        self._setup_upper_toolbar()
        self._setup_info_bar()
        self._setup_lower_toolbar()
        self._load_current_image()
        self._update_info_bar()

    def _ensure_mask(self):
        if self._mask is None:
            self._init_mask()

    def _init_mask(self):
        if hasattr(self, '_original_pixmap') and self._original_pixmap is not None:
            size = self._original_pixmap.size()
            self._mask = QImage(size, QImage.Format_ARGB32_Premultiplied)
            self._mask.fill(0)
        else:
            self._mask = None
    
    def _load_existing_mask(self, image_path):
        """Load saved mask for current image if it exists in workspace"""
        # Get the base filename without extension
        image_filename = os.path.basename(image_path)
        image_basename = os.path.splitext(image_filename)[0]
        
        # Construct mask filename using naming pattern
        mask_filename = f"{image_basename}_mask.png"
        mask_path = os.path.join(self.mask_dir, mask_filename)
        
        # Try to load the mask
        if os.path.exists(mask_path):
            loaded_mask = QImage(mask_path)
            if not loaded_mask.isNull():
                # Ensure mask matches image size
                if hasattr(self, '_original_pixmap') and self._original_pixmap is not None:
                    size = self._original_pixmap.size()
                    if loaded_mask.size() != size:
                        # Scale mask to match image size
                        loaded_mask = loaded_mask.scaled(size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    
                    # Convert to ARGB32_Premultiplied format
                    self._mask = loaded_mask.convertToFormat(QImage.Format_ARGB32_Premultiplied)
                    return
        
        # If no mask found or loading failed, create empty mask
        self._init_mask()

    def _render_mask_overlay(self, base_pixmap, scaled_width, scaled_height, pan_x, pan_y):
        if self._mask is None or base_pixmap.isNull():
            return base_pixmap
        mask_scaled = self._mask.scaled(scaled_width, scaled_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        mask_region = mask_scaled.copy(pan_x, pan_y, base_pixmap.width(), base_pixmap.height())
        tinted = self._tint_mask_fragment(mask_region)
        painter = QPainter(base_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawImage(0, 0, tinted)
        painter.end()
        return base_pixmap

    def _map_label_pos_to_image(self, event_pos):
        if not hasattr(self, '_original_pixmap') or self._original_pixmap is None:
            return None
        if self.image_label.pixmap() is None:
            return None
        label_pos = self.image_label.mapFrom(self, event_pos)
        label_rect = self.image_label.rect()
        pixmap = self.image_label.pixmap()
        offset_x = (label_rect.width() - pixmap.width()) // 2
        offset_y = (label_rect.height() - pixmap.height()) // 2
        local_x = label_pos.x() - offset_x
        local_y = label_pos.y() - offset_y
        if local_x < 0 or local_y < 0 or local_x >= pixmap.width() or local_y >= pixmap.height():
            return None
        zoom = self.zoom_spin.value() / 100.0 if hasattr(self, 'zoom_spin') else 1.0
        pan_x, pan_y = getattr(self, '_pan_offset', (0, 0))
        image_x = int((local_x + pan_x) / zoom)
        image_y = int((local_y + pan_y) / zoom)
        if image_x < 0 or image_y < 0 or image_x >= self._original_pixmap.width() or image_y >= self._original_pixmap.height():
            return None
        return image_x, image_y

    def _load_input_directory_from_config(self, workspace_path):
        """Load the original input directory path from config.yml"""
        config_file = os.path.join(workspace_path, "config.yml")
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('input_directory', workspace_path)
        except Exception as e:
            print(f"Warning: Could not load config.yml: {e}")
            return workspace_path
    
    def _discover_images_from_workspace(self, workspace_path):
        """Discover images from OriginalImage folder in workspace"""
        original_image_dir = os.path.join(workspace_path, "OriginalImage")
        if not os.path.exists(original_image_dir):
            return []
        return self._discover_images(original_image_dir)
    
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

        prev_action = QAction("Prev", self)
        prev_action.triggered.connect(self._go_previous)
        toolbar.addAction(prev_action)

        next_action = QAction("Next", self)
        next_action.triggered.connect(self._go_next)
        toolbar.addAction(next_action)
        
        # Add spacer
        spacer = QWidget()
        spacer.setSizePolicy(QWidget().sizePolicy().Expanding, QWidget().sizePolicy().Preferred)
        toolbar.addWidget(spacer)
        
        # Add Settings action
        settings_action = QAction("⚙ Workspace Settings", self)
        settings_action.triggered.connect(self._configure_workspace)
        toolbar.addAction(settings_action)

        self.addToolBar(Qt.TopToolBarArea, toolbar)

    def _setup_info_bar(self):
        """Create info bar showing workspace path, current image, and mask progress"""
        info_frame = QFrame(self)
        info_frame.setFrameShape(QFrame.StyledPanel)
        info_frame.setStyleSheet("QFrame { background-color: #f0f0f0; padding: 4px; }")
        
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 4, 8, 4)
        info_layout.setSpacing(2)
        
        # Workspace path label
        self.workspace_label = QLabel()
        self.workspace_label.setStyleSheet("font-weight: bold; color: #333;")
        info_layout.addWidget(self.workspace_label)
        
        # Current image label
        self.current_image_label = QLabel()
        self.current_image_label.setStyleSheet("color: #555;")
        info_layout.addWidget(self.current_image_label)
        
        # Mask progress label
        self.mask_progress_label = QLabel()
        self.mask_progress_label.setStyleSheet("color: #555;")
        info_layout.addWidget(self.mask_progress_label)
        
        # Add to main window as a toolbar
        toolbar = QToolBar("Info Bar", self)
        toolbar.setMovable(False)
        toolbar.setAllowedAreas(Qt.TopToolBarArea)
        toolbar.addWidget(info_frame)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

    def _update_info_bar(self):
        """Update the info bar with current workspace, image, and mask statistics"""
        # Update workspace path
        if self.workspace_path:
            self.workspace_label.setText(f"Workspace: {self.workspace_path}")
        else:
            self.workspace_label.setText(f"Source Directory: {self.directory_path}")
        
        # Update current image
        if self.image_files and 0 <= self.current_index < len(self.image_files):
            current_image = os.path.basename(self.image_files[self.current_index])
            self.current_image_label.setText(f"Current Image: {current_image} ({self.current_index + 1}/{len(self.image_files)})")
        else:
            self.current_image_label.setText("Current Image: None")
        
        # Update mask progress (count existing masks)
        masked_count = self._count_masked_images()
        total_count = len(self.image_files) if self.image_files else 0
        self.mask_progress_label.setText(f"Masked Images: {masked_count}/{total_count}")

    def _count_masked_images(self):
        """Count how many images have corresponding mask files"""
        if not self.mask_dir or not os.path.exists(self.mask_dir):
            return 0
        
        count = 0
        for image_path in self.image_files:
            image_filename = os.path.basename(image_path)
            image_basename = os.path.splitext(image_filename)[0]
            mask_filename = f"{image_basename}_mask.png"
            mask_path = os.path.join(self.mask_dir, mask_filename)
            
            if os.path.exists(mask_path):
                count += 1
        
        return count

    def _setup_lower_toolbar(self):
        toolbar = QToolBar("Manual Segmentation", self)
        toolbar.setMovable(False)
        toolbar.setAllowedAreas(Qt.BottomToolBarArea)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        
        # --- Undo/Redo buttons ---
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setFixedWidth(60)
        self.undo_btn.clicked.connect(self._undo)
        self.undo_btn.setEnabled(False)
        self.redo_btn = QPushButton("Redo")
        self.redo_btn.setFixedWidth(60)
        self.redo_btn.clicked.connect(self._redo)
        self.redo_btn.setEnabled(False)
        
        # --- Zoom control ---
        zoom_label = QLabel("Zoom:")
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(10, 400)
        self.zoom_spin.setValue(100)
        self.zoom_spin.setSuffix(" %")
        self.zoom_spin.setSingleStep(10)
        self.zoom_spin.valueChanged.connect(self._on_zoom_changed)
        self.zoom_spin.setFocusPolicy(Qt.StrongFocus)

        # --- Tool selection (Pen/Cursor/Erase) ---
        tool_label = QLabel("Tool:")
        # Radio buttons and group are already initialized in __init__
        self.tool_group.buttonClicked.connect(self._on_tool_changed)

        # --- Pen radius control ---
        radius_label = QLabel("Radius:")
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(1, 100)
        self.radius_spin.setValue(10)
        self.radius_spin.setSingleStep(1)
        self.radius_spin.valueChanged.connect(self._on_radius_changed)
        self.radius_spin.setFocusPolicy(Qt.StrongFocus)

        overlay_label = QLabel("Overlay:")
        self.color_button = QPushButton()
        self.color_button.setFixedSize(36, 20)
        self.color_button.clicked.connect(self._choose_overlay_color)
        opacity_label = QLabel("Opacity:")
        self.alpha_spin = QSpinBox()
        self.alpha_spin.setRange(0, 255)
        self.alpha_spin.setValue(self._overlay_alpha)
        self.alpha_spin.setSingleStep(5)
        self.alpha_spin.valueChanged.connect(self._on_alpha_changed)
        self.alpha_spin.setFocusPolicy(Qt.StrongFocus)
        self._update_color_button()
         # --- Save button ---
        save_btn = QPushButton("Save Mask")
        save_btn.clicked.connect(self._save_mask)

        # Layout for controls
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(self.undo_btn)
        controls_layout.addWidget(self.redo_btn)
        controls_layout.addSpacing(16)
        controls_layout.addWidget(zoom_label)
        controls_layout.addWidget(self.zoom_spin)
        controls_layout.addSpacing(16)
        controls_layout.addWidget(tool_label)
        controls_layout.addWidget(self.pen_radio)
        controls_layout.addWidget(self.cursor_radio)
        controls_layout.addWidget(self.erase_radio)
        controls_layout.addSpacing(16)
        controls_layout.addWidget(radius_label)
        controls_layout.addWidget(self.radius_spin)
        controls_layout.addSpacing(16)
        controls_layout.addWidget(overlay_label)
        controls_layout.addWidget(self.color_button)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(opacity_label)
        controls_layout.addWidget(self.alpha_spin)
        controls_layout.addStretch()
        
        controls_layout.addSpacing(16)
        controls_layout.addWidget(save_btn)
        toolbar.addWidget(controls_widget)
        self.addToolBar(Qt.BottomToolBarArea, toolbar)
        self._update_tool_cursor()

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
        self._update_tool_cursor()  # Update cursor size when zoom changes

    def _on_tool_changed(self, button):
        self._update_tool_cursor()

    def _on_radius_changed(self, value):
        self._update_tool_cursor()

    def _update_tool_cursor(self):
        if not hasattr(self, 'image_label'):
            return
        if self.cursor_radio.isChecked():
            self.image_label.setCursor(Qt.OpenHandCursor)
        elif self.pen_radio.isChecked() or self.erase_radio.isChecked():
            zoom = self.zoom_spin.value() / 100.0 if hasattr(self, 'zoom_spin') else 1.0
            cursor = self._make_brush_cursor(self.radius_spin.value(), zoom)
            self.image_label.setCursor(cursor)
        else:
            self.image_label.setCursor(Qt.ArrowCursor)

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
            visible_width = min(label_size.width(), scaled_pixmap.width() - pan_x)
            visible_height = min(label_size.height(), scaled_pixmap.height() - pan_y)
            cropped = scaled_pixmap.copy(pan_x, pan_y, visible_width, visible_height)
            composed = self._render_mask_overlay(cropped, scaled_width, scaled_height, pan_x, pan_y)
            self.image_label.setPixmap(composed)
        else:
            composed = self._render_mask_overlay(scaled_pixmap, scaled_width, scaled_height, pan_x, pan_y)
            self.image_label.setPixmap(composed)

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
        
        # Load existing mask if in "open" mode
        if self.workspace_mode == "open" and self.mask_dir:
            self._load_existing_mask(image_path)
        else:
            self._init_mask()
        
        # Clear undo/redo stacks when loading a new image
        self._undo_stack.clear()
        self._redo_stack.clear()
        if hasattr(self, 'undo_btn'):
            self._update_undo_redo_buttons()
        
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
        elif (self.pen_radio.isChecked() or self.erase_radio.isChecked()) and event.button() == Qt.LeftButton:
            target = self._map_label_pos_to_image(event.pos())
            if target is not None:
                self._ensure_mask()
                self._save_mask_state()  # Save state before drawing
                self._drawing = True
                self._last_draw_point = target
                self._apply_stroke(target, target)
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
        elif getattr(self, '_drawing', False) and (self.pen_radio.isChecked() or self.erase_radio.isChecked()):
            target = self._map_label_pos_to_image(event.pos())
            if target is not None:
                self._apply_stroke(self._last_draw_point, target)
                self._last_draw_point = target
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, '_dragging', False) and event.button() == Qt.LeftButton:
            self._dragging = False
        if getattr(self, '_drawing', False) and event.button() == Qt.LeftButton:
            self._drawing = False
            self._last_draw_point = None
        super().mouseReleaseEvent(event)

    def _apply_stroke(self, start_point, end_point):
        if self._mask is None or start_point is None or end_point is None:
            return
        radius = self.radius_spin.value()
        painter = QPainter(self._mask)
        painter.setRenderHint(QPainter.Antialiasing)
        pen_width = max(1, radius * 2)
        if self.erase_radio.isChecked():
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.setPen(QColor(0, 0, 0, 0))
        else:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QColor(255, 255, 255, 255))
        painter.setBrush(Qt.NoBrush)
        pen = painter.pen()
        pen.setWidth(pen_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(start_point[0], start_point[1], end_point[0], end_point[1])
        painter.end()
        self._update_image_display()

    #TODO: use it from a picture resource
    def _make_brush_cursor(self, radius, zoom=1.0):
        # Scale radius by zoom factor for visual feedback
        scaled_radius = max(1, int(radius * zoom))
        padding = 6
        diameter = scaled_radius * 2
        size = diameter + padding * 2
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(Qt.white)
        pen.setWidth(2)
        painter.setPen(pen)
        center = QPoint(size // 2, size // 2)
        painter.drawEllipse(center, scaled_radius, scaled_radius)
        cross_half = min(scaled_radius, max(2, scaled_radius - 2))
        painter.drawLine(center.x() - cross_half, center.y(), center.x() + cross_half, center.y())
        painter.drawLine(center.x(), center.y() - cross_half, center.x(), center.y() + cross_half)
        painter.end()
        hotspot = QPoint(center.x(), center.y())
        return QCursor(pixmap, hotspot.x(), hotspot.y())

    def _choose_overlay_color(self):
        chosen = QColorDialog.getColor(self._overlay_color, self, "Select Overlay Color")
        if chosen.isValid():
            self._overlay_color = QColor(chosen.red(), chosen.green(), chosen.blue())
            self._update_color_button()
            self._update_image_display()

    def _on_alpha_changed(self, value):
        self._overlay_alpha = value
        self._update_image_display()

    def _update_color_button(self):
        self.color_button.setStyleSheet(
            "background-color: rgb({0}, {1}, {2}); border: 1px solid #444;".format(
                self._overlay_color.red(),
                self._overlay_color.green(),
                self._overlay_color.blue()
            )
        )

    def _tint_mask_fragment(self, fragment):
        if fragment.isNull():
            return fragment
        source = fragment.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        tinted = QImage(source.size(), QImage.Format_ARGB32_Premultiplied)
        color = QColor(self._overlay_color)
        color.setAlpha(self._overlay_alpha)
        tinted.fill(color)
        painter = QPainter(tinted)
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.drawImage(0, 0, source)
        painter.end()
        return tinted

    def _save_mask_state(self):
        """Save current mask state to undo stack before modification"""
        if self._mask is not None:
            # Create a deep copy of the mask
            mask_copy = self._mask.copy()
            self._undo_stack.append(mask_copy)
            # Clear redo stack when new action is performed
            self._redo_stack.clear()
            self._update_undo_redo_buttons()

    def _undo(self):
        """Undo the last mask operation"""
        if not self._undo_stack:
            return
        # Save current state to redo stack
        if self._mask is not None:
            self._redo_stack.append(self._mask.copy())
        # Restore previous state
        self._mask = self._undo_stack.pop()
        self._update_undo_redo_buttons()
        self._update_image_display()

    def _redo(self):
        """Redo the last undone operation"""
        if not self._redo_stack:
            return
        # Save current state to undo stack
        if self._mask is not None:
            self._undo_stack.append(self._mask.copy())
        # Restore next state
        self._mask = self._redo_stack.pop()
        self._update_undo_redo_buttons()
        self._update_image_display()

    def _update_undo_redo_buttons(self):
        """Update enabled state of undo/redo buttons"""
        self.undo_btn.setEnabled(len(self._undo_stack) > 0)
        self.redo_btn.setEnabled(len(self._redo_stack) > 0)

    def _save_mask(self):
        """Save mask using OutputManager - automatically organizes files in workspace."""
        if self._mask is None:
            QMessageBox.warning(self, "Save Mask", "No mask to save.")
            return
        
        if self.mask_dir is None:
            QMessageBox.critical(self, "Save Error", "Workspace not initialized.")
            return
        
        # Get current image path
        current_image_path = self.image_files[self.current_index]
        
        try:
            if self.workspace_mode == "create" and self.output_manager:
                # Use OutputManager for new workspaces
                orig_path, mask_path = self.output_manager.save_mask_with_original(
                    current_image_path,
                    self._mask
                )
            else:
                # Save directly to workspace for opened workspaces
                image_filename = os.path.basename(current_image_path)
                image_basename = os.path.splitext(image_filename)[0]
                mask_filename = f"{image_basename}_mask.png"
                mask_path = os.path.join(self.mask_dir, mask_filename)
                
                # Save mask
                success = self._mask.save(mask_path, "PNG")
                if not success:
                    raise IOError(f"Failed to save mask to {mask_path}")
                
                # Copy original if it doesn't exist
                orig_path = os.path.join(self.original_dir, image_filename)
                if not os.path.exists(orig_path):
                    import shutil
                    shutil.copy2(current_image_path, orig_path)
            
            # Show success message with paths
            QMessageBox.information(
                self, 
                "Mask Saved",
                f"Files saved successfully:\\n\\nMask: {mask_path}"
            )
            
            # Update info bar to reflect new mask count
            self._update_info_bar()
        except (IOError, OSError, ValueError, RuntimeError) as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save mask: {e}")
    
    def _configure_workspace(self):
        """Show dialog to configure workspace output folder."""
        WorkspaceConfig.show_folder_selection_dialog(self)

    def _go_previous(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self._load_current_image()
        self._update_info_bar()

    def _go_next(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self._load_current_image()
        self._update_info_bar()

    def wheelEvent(self, event):
        """Handle wheel events anywhere in the window to change focused spinbox"""
        # Check which spinbox has focus
        focused_widget = self.focusWidget()
        if focused_widget in [self.zoom_spin, self.radius_spin, self.alpha_spin]:
            # Get the wheel delta
            delta = event.angleDelta().y()
            if delta > 0:
                focused_widget.stepUp()
            elif delta < 0:
                focused_widget.stepDown()
            event.accept()
            return
        # If no spinbox has focus, pass event to base class
        super().wheelEvent(event)
