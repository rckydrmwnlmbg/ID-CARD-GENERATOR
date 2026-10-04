"""
Interactive WYSIWYG Template Canvas and Drag & Drop Editor for ID Card Generator.
Provides QGraphicsScene/QGraphicsView based visual editor with real-time property synchronization.
"""
import os
from typing import Optional, List, Dict, Any, Callable
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QPushButton, QColorDialog, QFileDialog, QComboBox, QCheckBox,
    QGroupBox, QFormLayout, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem, QToolBar,
    QButtonGroup, QRadioButton, QMessageBox, QFrame, QScrollArea, QSplitter
)
from PyQt6.QtGui import (
    QColor, QPen, QBrush, QFont, QPixmap, QImage, QPainter, QAction,
    QCursor, QFontDatabase, QPainterPath
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject

from models import LayerConfig, TemplateConfig, resource_path


class CanvasSignals(QObject):
    layer_selected = pyqtSignal(object)       # LayerConfig or None
    layer_modified = pyqtSignal(object)       # LayerConfig
    layer_moved = pyqtSignal(object)          # LayerConfig
    canvas_clicked_empty = pyqtSignal()
    request_render = pyqtSignal()


class DraggableLayerItem(QGraphicsItem):
    """
    Interactive QGraphicsItem representing either a text layer or a photo frame.
    Supports clicking, selection, dragging, and visual bounding box handles.
    """
    
    def __init__(self, layer: LayerConfig, signals: CanvasSignals, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.signals = signals
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setPos(QPointF(float(layer.x), float(layer.y)))
        self._is_resizing = False
        self._resize_handle_size = 10.0

    def boundingRect(self) -> QRectF:
        pad = 6.0
        return QRectF(-pad, -pad, float(self.layer.width) + 2 * pad, float(self.layer.height) + 2 * pad)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        
        w = float(self.layer.width)
        h = float(self.layer.height)
        rect = QRectF(0, 0, w, h)

        if self.layer.type == "photo":
            # Photo Frame Preview
            path = QPainterPath()
            rad = float(min(self.layer.corner_radius, w / 2, h / 2))
            path.addRoundedRect(rect, rad, rad)
            
            # Draw placeholder / sample photo
            photo_path = self.layer.placeholder_path
            loaded_pix = None
            if photo_path and os.path.exists(photo_path):
                loaded_pix = QPixmap(photo_path)
            
            if loaded_pix and not loaded_pix.isNull():
                painter.save()
                painter.setClipPath(path)
                scaled_pix = loaded_pix.scaled(
                    int(w), int(h),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding if self.layer.fit_mode in ["cover", "crop"]
                    else Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                # Center crop / draw
                sx = (scaled_pix.width() - int(w)) // 2
                sy = (scaled_pix.height() - int(h)) // 2
                painter.drawPixmap(0, 0, scaled_pix, sx, sy, int(w), int(h))
                painter.restore()
            else:
                painter.fillPath(path, QBrush(QColor(230, 235, 245, 230)))
                # Draw subtle photo icon / text
                painter.setPen(QPen(QColor(140, 155, 175), 1.5))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"📷 {self.layer.name}")

            # Draw frame border if configured
            if self.layer.border_width > 0:
                pen = QPen(QColor(self.layer.border_color), float(self.layer.border_width))
                painter.setPen(pen)
                painter.drawPath(path)

        else:
            # Text Layer Preview
            # Background hover/subtle frame
            painter.setPen(QPen(QColor(180, 200, 220, 80), 1, Qt.PenStyle.DotLine))
            painter.setBrush(QBrush(QColor(240, 245, 255, 30)))
            painter.drawRect(rect)

            # Determine text to show
            text_str = self.layer.default_text or self.layer.name
            if self.layer.uppercase:
                text_str = text_str.upper()

            # Font setup
            qfont = QFont("DejaVu Sans", self.layer.font_size)
            if self.layer.font_path and os.path.exists(self.layer.font_path):
                font_id = QFontDatabase.addApplicationFont(self.layer.font_path)
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    qfont = QFont(families[0], self.layer.font_size)
            
            qfont.setBold(self.layer.bold)
            qfont.setItalic(self.layer.italic)
            painter.setFont(qfont)
            painter.setPen(QColor(self.layer.font_color))

            # Alignment
            align_flags = Qt.AlignmentFlag.AlignVCenter
            if self.layer.alignment == "center":
                align_flags |= Qt.AlignmentFlag.AlignHCenter
            elif self.layer.alignment == "right":
                align_flags |= Qt.AlignmentFlag.AlignRight
            else:
                align_flags |= Qt.AlignmentFlag.AlignLeft

            painter.drawText(rect, int(align_flags), text_str)

        # Draw Selection Highlighting and Resize Handles
        if self.isSelected():
            painter.setPen(QPen(QColor(33, 150, 243), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(rect)

            # Small resize handle indicator at bottom-right corner
            handle_size = self._resize_handle_size
            handle_rect = QRectF(w - handle_size, h - handle_size, handle_size, handle_size)
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.setBrush(QBrush(QColor(33, 150, 243)))
            painter.drawRect(handle_rect)

            # Top label badge
            badge_rect = QRectF(0, -22, min(140, max(80, len(self.layer.name) * 8 + 10)), 18)
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(QColor(33, 150, 243)))
            painter.drawRoundedRect(badge_rect, 3, 3)
            painter.setPen(QColor(255, 255, 255))
            badge_font = QFont("Arial", 8, QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.layer.name[:18])

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            # Snap to bounds / update layer coordinates
            self.layer.x = int(round(new_pos.x()))
            self.layer.y = int(round(new_pos.y()))
            self.signals.layer_moved.emit(self.layer)
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:
                self.signals.layer_selected.emit(self.layer)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        pos = event.pos()
        w = float(self.layer.width)
        h = float(self.layer.height)
        hs = self._resize_handle_size
        if QRectF(w - hs, h - hs, hs, hs).contains(pos):
            self._is_resizing = True
            event.accept()
            return
        self._is_resizing = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing:
            pos = event.pos()
            new_w = max(20, int(pos.x()))
            new_h = max(20, int(pos.y()))
            self.prepareGeometryChange()
            self.layer.width = new_w
            self.layer.height = new_h
            self.update()
            self.signals.layer_modified.emit(self.layer)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_resizing:
            self._is_resizing = False
            self.signals.layer_modified.emit(self.layer)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TemplateCanvasView(QGraphicsView):
    """
    QGraphicsView that holds the ID Card Scene with smooth zooming, panning, and background rendering.
    """
    
    def __init__(self, signals: CanvasSignals, parent=None):
        super().__init__(parent)
        self.signals = signals
        self.scene_ref = QGraphicsScene(self)
        self.setScene(self.scene_ref)

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.bg_item: Optional[QGraphicsPixmapItem] = None
        self.card_outline_item: Optional[QGraphicsRectItem] = None
        self.layer_items: Dict[str, DraggableLayerItem] = {}
        self.template_config: Optional[TemplateConfig] = None

        self.setStyleSheet("background-color: #2b2d30; border: 1px solid #3c3f41;")

    def set_template(self, config: TemplateConfig):
        self.template_config = config
        self.rebuild_scene()

    def rebuild_scene(self):
        self.scene_ref.clear()
        self.layer_items.clear()

        if not self.template_config:
            return

        w = float(self.template_config.width)
        h = float(self.template_config.height)

        # Set Scene Bounding Rect with comfortable margins
        margin = 100.0
        self.scene_ref.setSceneRect(-margin, -margin, w + 2 * margin, h + 2 * margin)

        # Card Drop Shadow & Background
        shadow = QGraphicsRectItem(4, 4, w, h)
        shadow.setBrush(QBrush(QColor(0, 0, 0, 80)))
        shadow.setPen(QPen(Qt.PenStyle.NoPen))
        self.scene_ref.addItem(shadow)

        bg_rect = QGraphicsRectItem(0, 0, w, h)
        bg_rect.setBrush(QBrush(QColor(255, 255, 255)))
        bg_rect.setPen(QPen(QColor(200, 200, 200), 1))
        self.scene_ref.addItem(bg_rect)

        # Background Template Image
        img_path = self.template_config.template_image_path
        if img_path and os.path.exists(img_path):
            pix = QPixmap(img_path)
            if not pix.isNull():
                if pix.width() != int(w) or pix.height() != int(h):
                    pix = pix.scaled(int(w), int(h), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.bg_item = self.scene_ref.addPixmap(pix)
                self.bg_item.setPos(0, 0)
                self.bg_item.setZValue(0)

        # Add Layer Items
        for z_idx, layer in enumerate(self.template_config.layers):
            item = DraggableLayerItem(layer, self.signals)
            item.setZValue(z_idx + 1)
            self.scene_ref.addItem(item)
            self.layer_items[layer.id] = item

    def update_layer_item(self, layer: LayerConfig):
        """Updates position and visual state of an existing layer item."""
        if layer.id in self.layer_items:
            item = self.layer_items[layer.id]
            item.prepareGeometryChange()
            item.setPos(QPointF(float(layer.x), float(layer.y)))
            item.update()

    def select_layer(self, layer_id: str):
        self.scene_ref.clearSelection()
        if layer_id in self.layer_items:
            item = self.layer_items[layer_id]
            item.setSelected(True)
            self.signals.layer_selected.emit(item.layer)

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if not item or isinstance(item, (QGraphicsRectItem, QGraphicsPixmapItem)):
            self.signals.canvas_clicked_empty.emit()
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        """Smooth zoom in/out with Ctrl + Wheel or Wheel alone."""
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(zoom_factor, zoom_factor)
        else:
            self.scale(1.0 / zoom_factor, 1.0 / zoom_factor)

    def zoom_fit(self):
        if self.template_config:
            w = float(self.template_config.width)
            h = float(self.template_config.height)
            self.fitInView(QRectF(0, 0, w, h), Qt.AspectRatioMode.KeepAspectRatio)


class LayerPropertyPanel(QWidget):
    """
    Side panel displaying and editing properties of the currently active layer.
    """
    
    def __init__(self, signals: CanvasSignals, parent=None):
        super().__init__(parent)
        self.signals = signals
        self.current_layer: Optional[LayerConfig] = None
        self._updating_ui = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Header Info
        self.title_label = QLabel("<b>Properti Elemen</b>")
        self.title_label.setStyleSheet("font-size: 14px; color: #e0e0e0;")
        layout.addWidget(self.title_label)

        self.empty_label = QLabel("<i>Pilih elemen di kanvas untuk mengedit properti.</i>")
        self.empty_label.setStyleSheet("color: #888888; padding: 20px 0;")
        layout.addWidget(self.empty_label)

        self.prop_container = QWidget()
        prop_layout = QVBoxLayout(self.prop_container)
        prop_layout.setContentsMargins(0, 0, 0, 0)
        prop_layout.setSpacing(8)

        # 1. Identity & Data Key Group
        id_group = QGroupBox("Identitas & Kunci Data")
        id_layout = QFormLayout(id_group)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Misal: Nama Lengkap")
        self.name_edit.textChanged.connect(self._on_name_changed)
        id_layout.addRow("Nama Layer:", self.name_edit)

        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("Kunci data (misal: Nama, NIK)")
        self.key_edit.textChanged.connect(self._on_key_changed)
        id_layout.addRow("Data Key:", self.key_edit)
        prop_layout.addWidget(id_group)

        # 2. Position & Size Group
        pos_group = QGroupBox("Posisi & Ukuran (Pixel)")
        pos_layout = QFormLayout(pos_group)

        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 5000)
        self.x_spin.valueChanged.connect(self._on_coord_changed)
        pos_layout.addRow("Posisi X:", self.x_spin)

        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 5000)
        self.y_spin.valueChanged.connect(self._on_coord_changed)
        pos_layout.addRow("Posisi Y:", self.y_spin)

        self.w_spin = QSpinBox()
        self.w_spin.setRange(10, 5000)
        self.w_spin.valueChanged.connect(self._on_coord_changed)
        pos_layout.addRow("Lebar (W):", self.w_spin)

        self.h_spin = QSpinBox()
        self.h_spin.setRange(10, 5000)
        self.h_spin.valueChanged.connect(self._on_coord_changed)
        pos_layout.addRow("Tinggi (H):", self.h_spin)
        prop_layout.addWidget(pos_group)

        # 3. Text Properties Group
        self.text_group = QGroupBox("Properti Teks")
        text_layout = QFormLayout(self.text_group)

        self.default_text_edit = QLineEdit()
        self.default_text_edit.setPlaceholderText("Teks contoh...")
        self.default_text_edit.textChanged.connect(self._on_default_text_changed)
        text_layout.addRow("Teks Preview:", self.default_text_edit)

        font_row = QHBoxLayout()
        self.font_path_label = QLabel("Font Default (DejaVu)")
        self.font_path_label.setStyleSheet("color: #bbbbbb; font-size: 11px;")
        font_browse_btn = QPushButton("Pilih Font...")
        font_browse_btn.clicked.connect(self._browse_custom_font)
        font_row.addWidget(self.font_path_label, 1)
        font_row.addWidget(font_browse_btn)
        text_layout.addRow("Font File:", font_row)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 200)
        self.font_size_spin.setValue(24)
        self.font_size_spin.valueChanged.connect(self._on_text_style_changed)
        text_layout.addRow("Ukuran Font:", self.font_size_spin)

        # Smart Auto-fit width controls
        self.autofit_check = QCheckBox("Aktifkan Smart Auto-fit Width")
        self.autofit_check.setChecked(True)
        self.autofit_check.toggled.connect(self._on_text_style_changed)
        text_layout.addRow("", self.autofit_check)

        self.min_font_spin = QSpinBox()
        self.min_font_spin.setRange(6, 100)
        self.min_font_spin.setValue(12)
        self.min_font_spin.valueChanged.connect(self._on_text_style_changed)
        text_layout.addRow("Min Font Size:", self.min_font_spin)

        color_row = QHBoxLayout()
        self.color_btn = QPushButton("#000000")
        self.color_btn.setStyleSheet("background-color: #000000; color: white; font-weight: bold; border-radius: 3px;")
        self.color_btn.clicked.connect(self._pick_font_color)
        color_row.addWidget(self.color_btn)
        text_layout.addRow("Warna Teks:", color_row)

        align_row = QHBoxLayout()
        self.align_left_rb = QRadioButton("Kiri")
        self.align_center_rb = QRadioButton("Tengah")
        self.align_right_rb = QRadioButton("Kanan")
        self.align_group = QButtonGroup(self)
        self.align_group.addButton(self.align_left_rb, 0)
        self.align_group.addButton(self.align_center_rb, 1)
        self.align_group.addButton(self.align_right_rb, 2)
        self.align_group.idClicked.connect(self._on_alignment_changed)
        align_row.addWidget(self.align_left_rb)
        align_row.addWidget(self.align_center_rb)
        align_row.addWidget(self.align_right_rb)
        text_layout.addRow("Alignment:", align_row)

        style_row = QHBoxLayout()
        self.bold_check = QCheckBox("Bold")
        self.bold_check.toggled.connect(self._on_text_style_changed)
        self.italic_check = QCheckBox("Italic")
        self.italic_check.toggled.connect(self._on_text_style_changed)
        self.upper_check = QCheckBox("Huruf Kapital (ALL CAPS)")
        self.upper_check.toggled.connect(self._on_text_style_changed)
        style_row.addWidget(self.bold_check)
        style_row.addWidget(self.italic_check)
        style_row.addWidget(self.upper_check)
        text_layout.addRow("Gaya:", style_row)
        prop_layout.addWidget(self.text_group)

        # 4. Photo Properties Group
        self.photo_group = QGroupBox("Properti Frame Foto")
        photo_layout = QFormLayout(self.photo_group)

        self.fit_mode_cb = QComboBox()
        self.fit_mode_cb.addItems(["cover (Isi & Crop Presisi)", "contain (Muat Penuh)", "stretch"])
        self.fit_mode_cb.currentIndexChanged.connect(self._on_photo_prop_changed)
        photo_layout.addRow("Mode Fit:", self.fit_mode_cb)

        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(0, 300)
        self.radius_spin.setValue(12)
        self.radius_spin.valueChanged.connect(self._on_photo_prop_changed)
        photo_layout.addRow("Sudut Membulat (Radius):", self.radius_spin)

        self.border_w_spin = QSpinBox()
        self.border_w_spin.setRange(0, 50)
        self.border_w_spin.setValue(2)
        self.border_w_spin.valueChanged.connect(self._on_photo_prop_changed)
        photo_layout.addRow("Tebal Garis Border:", self.border_w_spin)

        border_color_row = QHBoxLayout()
        self.border_color_btn = QPushButton("#203a43")
        self.border_color_btn.setStyleSheet("background-color: #203a43; color: white; border-radius: 3px;")
        self.border_color_btn.clicked.connect(self._pick_border_color)
        border_color_row.addWidget(self.border_color_btn)
        photo_layout.addRow("Warna Border:", border_color_row)

        self.rembg_check = QCheckBox("Hapus Background Foto Otomatis (remove.bg)")
        self.rembg_check.toggled.connect(self._on_photo_prop_changed)
        photo_layout.addRow("", self.rembg_check)

        photo_pick_row = QHBoxLayout()
        self.photo_path_edit = QLineEdit()
        self.photo_path_edit.setPlaceholderText("Path foto placeholder...")
        self.photo_path_edit.textChanged.connect(self._on_placeholder_changed)
        photo_pick_btn = QPushButton("Pilih...")
        photo_pick_btn.clicked.connect(self._browse_placeholder_photo)
        photo_pick_row.addWidget(self.photo_path_edit, 1)
        photo_pick_row.addWidget(photo_pick_btn)
        photo_layout.addRow("Foto Placeholder:", photo_pick_row)
        prop_layout.addWidget(self.photo_group)

        layout.addWidget(self.prop_container)
        layout.addStretch()

        self.prop_container.hide()

    def set_layer(self, layer: Optional[LayerConfig]):
        self.current_layer = layer
        if not layer:
            self.empty_label.show()
            self.prop_container.hide()
            self.title_label.setText("<b>Properti Elemen</b>")
            return

        self._updating_ui = True
        self.empty_label.hide()
        self.prop_container.show()
        self.title_label.setText(f"<b>Properti: {layer.name} ({layer.type.upper()})</b>")

        # Identity
        self.name_edit.setText(layer.name)
        self.key_edit.setText(layer.key)

        # Coordinates
        self.x_spin.setValue(layer.x)
        self.y_spin.setValue(layer.y)
        self.w_spin.setValue(layer.width)
        self.h_spin.setValue(layer.height)

        if layer.type == "text":
            self.text_group.show()
            self.photo_group.hide()
            self.default_text_edit.setText(layer.default_text)
            self.font_size_spin.setValue(layer.font_size)
            self.autofit_check.setChecked(layer.auto_fit)
            self.min_font_spin.setValue(layer.min_font_size)
            self.font_path_label.setText(os.path.basename(layer.font_path) if layer.font_path else "Default (DejaVu)")
            self.color_btn.setText(layer.font_color)
            self.color_btn.setStyleSheet(f"background-color: {layer.font_color}; color: {'#000' if QColor(layer.font_color).lightness() > 128 else '#fff'}; border-radius: 3px;")
            
            if layer.alignment == "center":
                self.align_center_rb.setChecked(True)
            elif layer.alignment == "right":
                self.align_right_rb.setChecked(True)
            else:
                self.align_left_rb.setChecked(True)

            self.bold_check.setChecked(layer.bold)
            self.italic_check.setChecked(layer.italic)
            self.upper_check.setChecked(layer.uppercase)
        else:
            self.text_group.hide()
            self.photo_group.show()
            fit_idx = 0
            if layer.fit_mode == "contain":
                fit_idx = 1
            elif layer.fit_mode == "stretch":
                fit_idx = 2
            self.fit_mode_cb.setCurrentIndex(fit_idx)
            self.radius_spin.setValue(layer.corner_radius)
            self.border_w_spin.setValue(layer.border_width)
            self.border_color_btn.setText(layer.border_color)
            self.border_color_btn.setStyleSheet(f"background-color: {layer.border_color}; color: {'#000' if QColor(layer.border_color).lightness() > 128 else '#fff'}; border-radius: 3px;")
            self.rembg_check.setChecked(layer.remove_bg)
            self.photo_path_edit.setText(layer.placeholder_path)

        self._updating_ui = False

    def sync_coordinates(self, layer: LayerConfig):
        """Called when layer is dragged on canvas to update position spinboxes."""
        if self.current_layer and self.current_layer.id == layer.id:
            self._updating_ui = True
            self.x_spin.setValue(layer.x)
            self.y_spin.setValue(layer.y)
            self.w_spin.setValue(layer.width)
            self.h_spin.setValue(layer.height)
            self._updating_ui = False

    def _on_name_changed(self, text: str):
        if self._updating_ui or not self.current_layer:
            return
        self.current_layer.name = text
        self.signals.layer_modified.emit(self.current_layer)

    def _on_key_changed(self, text: str):
        if self._updating_ui or not self.current_layer:
            return
        self.current_layer.key = text
        self.signals.layer_modified.emit(self.current_layer)

    def _on_coord_changed(self):
        if self._updating_ui or not self.current_layer:
            return
        self.current_layer.x = self.x_spin.value()
        self.current_layer.y = self.y_spin.value()
        self.current_layer.width = self.w_spin.value()
        self.current_layer.height = self.h_spin.value()
        self.signals.layer_modified.emit(self.current_layer)

    def _on_default_text_changed(self, text: str):
        if self._updating_ui or not self.current_layer:
            return
        self.current_layer.default_text = text
        self.signals.layer_modified.emit(self.current_layer)

    def _on_text_style_changed(self):
        if self._updating_ui or not self.current_layer:
            return
        self.current_layer.font_size = self.font_size_spin.value()
        self.current_layer.auto_fit = self.autofit_check.isChecked()
        self.current_layer.min_font_size = self.min_font_spin.value()
        self.current_layer.bold = self.bold_check.isChecked()
        self.current_layer.italic = self.italic_check.isChecked()
        self.current_layer.uppercase = self.upper_check.isChecked()
        self.signals.layer_modified.emit(self.current_layer)

    def _on_alignment_changed(self, btn_id: int):
        if self._updating_ui or not self.current_layer:
            return
        if btn_id == 1:
            self.current_layer.alignment = "center"
        elif btn_id == 2:
            self.current_layer.alignment = "right"
        else:
            self.current_layer.alignment = "left"
        self.signals.layer_modified.emit(self.current_layer)

    def _pick_font_color(self):
        if not self.current_layer:
            return
        init_color = QColor(self.current_layer.font_color)
        col = QColorDialog.getColor(init_color, self, "Pilih Warna Font")
        if col.isValid():
            hex_color = col.name()
            self.current_layer.font_color = hex_color
            self.color_btn.setText(hex_color)
            self.color_btn.setStyleSheet(f"background-color: {hex_color}; color: {'#000' if col.lightness() > 128 else '#fff'}; border-radius: 3px;")
            self.signals.layer_modified.emit(self.current_layer)

    def _browse_custom_font(self):
        if not self.current_layer:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Pilih File Font Kustom", "", "Font Files (*.ttf *.otf)")
        if path:
            self.current_layer.font_path = path
            self.font_path_label.setText(os.path.basename(path))
            self.signals.layer_modified.emit(self.current_layer)

    def _on_photo_prop_changed(self):
        if self._updating_ui or not self.current_layer:
            return
        idx = self.fit_mode_cb.currentIndex()
        modes = ["cover", "contain", "stretch"]
        self.current_layer.fit_mode = modes[idx]
        self.current_layer.corner_radius = self.radius_spin.value()
        self.current_layer.border_width = self.border_w_spin.value()
        self.current_layer.remove_bg = self.rembg_check.isChecked()
        self.signals.layer_modified.emit(self.current_layer)

    def _pick_border_color(self):
        if not self.current_layer:
            return
        init_color = QColor(self.current_layer.border_color)
        col = QColorDialog.getColor(init_color, self, "Pilih Warna Border")
        if col.isValid():
            hex_color = col.name()
            self.current_layer.border_color = hex_color
            self.border_color_btn.setText(hex_color)
            self.border_color_btn.setStyleSheet(f"background-color: {hex_color}; color: {'#000' if col.lightness() > 128 else '#fff'}; border-radius: 3px;")
            self.signals.layer_modified.emit(self.current_layer)

    def _on_placeholder_changed(self, path: str):
        if self._updating_ui or not self.current_layer:
            return
        self.current_layer.placeholder_path = path
        self.signals.layer_modified.emit(self.current_layer)

    def _browse_placeholder_photo(self):
        if not self.current_layer:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Pilih Foto Placeholder", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.photo_path_edit.setText(path)
            self.current_layer.placeholder_path = path
            self.signals.layer_modified.emit(self.current_layer)
