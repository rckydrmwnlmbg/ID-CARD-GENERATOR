"""
ID Card Generator - Interactive WYSIWYG Desktop Application
Modular PyQt6 Application with Drag & Drop Canvas, Dynamic Input, Batch Table,
Smart Font Fitting, Background Removal, and A4 3x3 Grid PDF Export.
"""
import sys
import os
import csv
import json
import logging
from typing import List, Dict, Any, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QProgressBar,
    QTextEdit, QSplitter, QHeaderView, QToolBar, QStatusBar,
    QCheckBox, QSpinBox, QFormLayout, QGroupBox, QListWidget,
    QListWidgetItem, QAbstractItemView, QMenu, QDialog, QFrame
)
from PyQt6.QtGui import (
    QAction, QIcon, QFont, QColor, QKeySequence, QPixmap, QImage
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize

from models import TemplateConfig, LayerConfig, resource_path
from generator_engine import (
    CardRenderer, export_single_card, build_a4_pdf_grid,
    BackgroundRemovalService, logger as engine_logger
)
from canvas_editor import TemplateCanvasView, LayerPropertyPanel, CanvasSignals


CONFIG_FILE = ".app_config.json"


class BatchExportWorker(QThread):
    """
    Background worker thread for batch rendering and exporting.
    Keeps GUI 100% responsive and emits progress/log signals.
    """
    progress = pyqtSignal(int, int, str)       # current, total, message
    log_message = pyqtSignal(str, str)         # level ("info", "success", "error"), text
    finished = pyqtSignal(str)                 # result summary message
    error = pyqtSignal(str)                    # error message

    def __init__(
        self,
        template: TemplateConfig,
        records: List[Dict[str, Any]],
        export_mode: str,                      # "pdf_grid" or "folder_images"
        output_path: str,
        enable_bg_removal: bool,
        api_key: str,
        dpi: int = 300,
        show_cut_marks: bool = True
    ):
        super().__init__()
        self.template = template
        self.records = records
        self.export_mode = export_mode
        self.output_path = output_path
        self.enable_bg_removal = enable_bg_removal
        self.api_key = api_key
        self.dpi = dpi
        self.show_cut_marks = show_cut_marks
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        total = len(self.records)
        if total == 0:
            self.error.emit("Tidak ada data untuk diekspor.")
            return

        self.log_message.emit("info", f"Memulai batch export ({total} data) - Mode: {self.export_mode}")
        bg_service = BackgroundRemovalService(self.api_key)
        renderer = CardRenderer(bg_service)
        rendered_images = []

        try:
            for idx, row in enumerate(self.records):
                if self._is_cancelled:
                    self.log_message.emit("warning", "Proses batch dibatalkan oleh pengguna.")
                    self.finished.emit("Proses dibatalkan.")
                    return

                nama_label = str(row.get("Nama") or row.get("nama") or f"Record #{idx+1}")
                self.progress.emit(idx + 1, total, f"Merender kartu ({idx + 1}/{total}): {nama_label}...")
                self.log_message.emit("info", f"[{idx + 1}/{total}] Merender kartu: {nama_label}")

                # Render individual card
                card_img = renderer.render(
                    self.template,
                    row,
                    enable_bg_removal=self.enable_bg_removal
                )

                if self.export_mode == "folder_images":
                    # Export individual image to folder
                    nik_clean = str(row.get("NIK") or row.get("nik") or idx + 1).replace("/", "_").replace("\\", "_")
                    nama_clean = str(nama_label).replace("/", "_").replace("\\", "_")
                    filename = f"ID_{nik_clean}_{nama_clean}.png"
                    file_path = os.path.join(self.output_path, filename)
                    card_img.save(file_path, "PNG", dpi=(self.dpi, self.dpi))
                    self.log_message.emit("success", f"Disimpan: {filename}")
                else:
                    # Collect for A4 PDF grid
                    rendered_images.append(card_img)

            if self.export_mode == "pdf_grid":
                self.progress.emit(total, total, "Menyusun grid A4 PDF (3x3)...")
                self.log_message.emit("info", "Menyusun halaman A4 (grid 3x3, margin simetris 300 DPI)...")

                def pdf_progress(cur_page, tot_pages, msg):
                    self.log_message.emit("info", msg)

                build_a4_pdf_grid(
                    rendered_images,
                    self.output_path,
                    dpi=self.dpi,
                    show_cut_marks=self.show_cut_marks,
                    progress_callback=pdf_progress
                )
                self.log_message.emit("success", f"Batch PDF berhasil dibuat di: {self.output_path}")
                self.finished.emit(f"Batch PDF berhasil dibuat!\nLokasi: {self.output_path}\nTotal kartu: {total}")
            else:
                self.log_message.emit("success", f"Semua gambar kartu ({total} file) berhasil disimpan di folder: {self.output_path}")
                self.finished.emit(f"Batch export gambar selesai!\nFolder: {self.output_path}\nTotal kartu: {total}")

        except Exception as e:
            self.log_message.emit("error", f"Terjadi kesalahan saat batch export: {str(e)}")
            self.error.emit(f"Error: {str(e)}")


class IDCardApp(QMainWindow):
    """Main Application Window for ID Card Generator."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ID Card Generator Pro - Visual WYSIWYG & Batch Studio")
        self.resize(1380, 880)

        # Set application icon
        icon_path = resource_path("assets/app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.signals = CanvasSignals()
        self.template_config = TemplateConfig.create_default_preset()
        self.current_preview_data: Dict[str, Any] = {}
        self.batch_worker: Optional[BatchExportWorker] = None

        self._load_app_config()
        self._init_ui()
        self._connect_signals()

        # Load initial preset into canvas
        preset_file = resource_path(os.path.join("sample_data", "sample_preset.json"))
        if os.path.exists(preset_file):
            try:
                self.template_config = TemplateConfig.load_from_json(preset_file)
            except Exception:
                pass

        self.canvas_view.set_template(self.template_config)
        self._refresh_layer_list()
        self._generate_manual_form_inputs()
        self._init_batch_table_columns()
        self.canvas_view.zoom_fit()

    # ================= UI INITIALIZATION =================
    def _init_ui(self):
        self._apply_styling()
        self._create_menu_and_toolbar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Tab 1: WYSIWYG Canvas Editor
        self.tab_editor = self._create_editor_tab()
        self.tabs.addTab(self.tab_editor, "🎨 Template Editor (WYSIWYG)")

        # Tab 2: Single Manual Form Mode
        self.tab_manual = self._create_manual_tab()
        self.tabs.addTab(self.tab_manual, "👤 Input Data Satuan")

        # Tab 3: Batch Import & Grid
        self.tab_batch = self._create_batch_tab()
        self.tabs.addTab(self.tab_batch, "📋 Batch Import & Cetak A4")

        # Tab 4: Settings & Logs
        self.tab_settings = self._create_settings_tab()
        self.tabs.addTab(self.tab_settings, "⚙️ Pengaturan & Log")

        main_layout.addWidget(self.tabs)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Siap.")

    def _create_menu_and_toolbar(self):
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")
        
        act_load_tpl = QAction("📂 Muat Gambar Template...", self)
        act_load_tpl.setShortcut("Ctrl+T")
        act_load_tpl.triggered.connect(self._browse_template_image)
        file_menu.addAction(act_load_tpl)

        act_save_preset = QAction("💾 Simpan Preset Template...", self)
        act_save_preset.setShortcut("Ctrl+S")
        act_save_preset.triggered.connect(self._save_preset_dialog)
        file_menu.addAction(act_save_preset)

        act_load_preset = QAction("📂 Buka Preset Template...", self)
        act_load_preset.setShortcut("Ctrl+O")
        act_load_preset.triggered.connect(self._load_preset_dialog)
        file_menu.addAction(act_load_preset)

        file_menu.addSeparator()
        act_exit = QAction("Keluar", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Layer Menu
        layer_menu = menubar.addMenu("&Elemen")
        act_add_text = QAction("➕ Tambah Teks Dinamis", self)
        act_add_text.setShortcut("Ctrl+Shift+T")
        act_add_text.triggered.connect(self._add_text_layer)
        layer_menu.addAction(act_add_text)

        act_add_photo = QAction("🖼️ Tambah Frame Foto", self)
        act_add_photo.setShortcut("Ctrl+Shift+P")
        act_add_photo.triggered.connect(self._add_photo_layer)
        layer_menu.addAction(act_add_photo)

        layer_menu.addSeparator()
        act_del_layer = QAction("🗑️ Hapus Elemen Terpilih", self)
        act_del_layer.setShortcut("Delete")
        act_del_layer.triggered.connect(self._delete_selected_layer)
        layer_menu.addAction(act_del_layer)

    def _create_editor_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        # Editor Toolbar
        toolbar = QToolBar("Editor Actions")
        toolbar.setIconSize(QSize(20, 20))

        btn_load_tpl = QPushButton("🖼️ Muat Template Background")
        btn_load_tpl.clicked.connect(self._browse_template_image)
        toolbar.addWidget(btn_load_tpl)
        toolbar.addSeparator()

        btn_add_text = QPushButton("➕ Teks Dinamis")
        btn_add_text.clicked.connect(self._add_text_layer)
        toolbar.addWidget(btn_add_text)

        btn_add_photo = QPushButton("📷 Frame Foto")
        btn_add_photo.clicked.connect(self._add_photo_layer)
        toolbar.addWidget(btn_add_photo)
        toolbar.addSeparator()

        btn_up = QPushButton("⬆️ Naik")
        btn_up.clicked.connect(lambda: self._move_layer(-1))
        toolbar.addWidget(btn_up)

        btn_down = QPushButton("⬇️ Turun")
        btn_down.clicked.connect(lambda: self._move_layer(1))
        toolbar.addWidget(btn_down)

        btn_del = QPushButton("🗑️ Hapus")
        btn_del.setStyleSheet("color: #ff5252;")
        btn_del.clicked.connect(self._delete_selected_layer)
        toolbar.addWidget(btn_del)
        toolbar.addSeparator()

        btn_save_pre = QPushButton("💾 Simpan Preset")
        btn_save_pre.clicked.connect(self._save_preset_dialog)
        toolbar.addWidget(btn_save_pre)

        btn_load_pre = QPushButton("📂 Muat Preset")
        btn_load_pre.clicked.connect(self._load_preset_dialog)
        toolbar.addWidget(btn_load_pre)
        toolbar.addSeparator()

        btn_zoom_fit = QPushButton("🔍 Zoom Pas")
        btn_zoom_fit.clicked.connect(lambda: self.canvas_view.zoom_fit())
        toolbar.addWidget(btn_zoom_fit)

        layout.addWidget(toolbar)

        # Main horizontal splitter: Left Canvas, Right Properties & Layer list
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Canvas View
        self.canvas_view = TemplateCanvasView(self.signals)
        splitter.addWidget(self.canvas_view)

        # Right Panel (Tabs for Properties and Layer List)
        right_panel = QWidget()
        right_panel.setMinimumWidth(340)
        right_panel.setMaximumWidth(450)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Layer List Group
        layer_group = QGroupBox("Daftar Elemen / Layer")
        layer_layout = QVBoxLayout(layer_group)
        layer_layout.setContentsMargins(4, 4, 4, 4)
        self.layer_list_widget = QListWidget()
        self.layer_list_widget.setMaximumHeight(150)
        self.layer_list_widget.itemClicked.connect(self._on_layer_list_clicked)
        layer_layout.addWidget(self.layer_list_widget)
        right_layout.addWidget(layer_group)

        # Property Panel inside a ScrollArea
        self.prop_panel = LayerPropertyPanel(self.signals)
        prop_scroll = QWidget()
        prop_scroll_layout = QVBoxLayout(prop_scroll)
        prop_scroll_layout.setContentsMargins(0, 0, 0, 0)
        prop_scroll_layout.addWidget(self.prop_panel)
        right_layout.addWidget(prop_scroll, 1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)
        return widget

    def _create_manual_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)

        # Left: Dynamic Form Controls
        left_box = QGroupBox("Form Input Data Satuan")
        left_layout = QVBoxLayout(left_box)

        guide_label = QLabel("Ketik data di bawah ini untuk live preview kartu secara instan:")
        guide_label.setStyleSheet("color: #a0a0a0; font-style: italic;")
        left_layout.addWidget(guide_label)

        self.manual_form_container = QWidget()
        self.manual_form_layout = QFormLayout(self.manual_form_container)
        left_layout.addWidget(self.manual_form_container)
        left_layout.addStretch()

        # Single Card Export Action Box
        export_box = QGroupBox("Ekspor Kartu Ini")
        exp_layout = QVBoxLayout(export_box)

        self.btn_export_single = QPushButton("💾 Export Kartu Ini ke Gambar (PNG / JPG)")
        self.btn_export_single.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.btn_export_single.clicked.connect(self._export_single_card_action)
        exp_layout.addWidget(self.btn_export_single)

        left_layout.addWidget(export_box)
        layout.addWidget(left_box, 1)

        # Right: Live High-Resolution Preview Card
        right_box = QGroupBox("Live Preview Kartu (High-DPI 300 DPI)")
        right_layout = QVBoxLayout(right_box)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.manual_preview_label = QLabel()
        self.manual_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.manual_preview_label.setStyleSheet("border: 1px dashed #555555; background-color: #1e1e1e; padding: 10px;")
        right_layout.addWidget(self.manual_preview_label, 1)

        btn_refresh_preview = QPushButton("🔄 Refresh Preview")
        btn_refresh_preview.clicked.connect(self._update_manual_live_preview)
        right_layout.addWidget(btn_refresh_preview)

        layout.addWidget(right_box, 1)
        return widget

    def _create_batch_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # Top Action Bar
        action_bar = QHBoxLayout()

        btn_paste = QPushButton("📋 Paste dari Clipboard (Excel/Sheets)")
        btn_paste.setStyleSheet("background-color: #1565c0; color: white; font-weight: bold; padding: 6px 12px;")
        btn_paste.clicked.connect(self._paste_from_clipboard)
        action_bar.addWidget(btn_paste)

        btn_import_csv = QPushButton("📂 Import CSV File...")
        btn_import_csv.clicked.connect(self._import_csv_file)
        action_bar.addWidget(btn_import_csv)

        btn_add_row = QPushButton("➕ Tambah Baris")
        btn_add_row.clicked.connect(self._add_table_row)
        action_bar.addWidget(btn_add_row)

        btn_del_row = QPushButton("➖ Hapus Baris")
        btn_del_row.clicked.connect(self._delete_table_row)
        action_bar.addWidget(btn_del_row)

        btn_clear = QPushButton("🗑️ Bersihkan Tabel")
        btn_clear.clicked.connect(self._clear_table)
        action_bar.addWidget(btn_clear)

        action_bar.addStretch()

        btn_preview_row = QPushButton("👁️ Preview Baris Terpilih di Kanvas")
        btn_preview_row.setStyleSheet("background-color: #455a64; color: white;")
        btn_preview_row.clicked.connect(self._preview_selected_table_row)
        action_bar.addWidget(btn_preview_row)

        layout.addLayout(action_bar)

        # Batch Table Widget
        self.batch_table = QTableWidget()
        self.batch_table.setAlternatingRowColors(True)
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.batch_table.itemSelectionChanged.connect(self._on_table_row_selected)
        layout.addWidget(self.batch_table, 1)

        # Batch Export Settings & Trigger Box
        exp_group = QGroupBox("Opsi Batch Export & Cetak")
        exp_layout = QVBoxLayout(exp_group)

        opts_row = QHBoxLayout()
        self.chk_cut_marks = QCheckBox("Garis Potong (Cut Marks L-Shapes) pada PDF")
        self.chk_cut_marks.setChecked(True)
        opts_row.addWidget(self.chk_cut_marks)

        self.chk_rembg_batch = QCheckBox("Gunakan remove.bg untuk Foto Batch")
        self.chk_rembg_batch.setChecked(False)
        opts_row.addWidget(self.chk_rembg_batch)

        opts_row.addStretch()

        exp_layout.addLayout(opts_row)

        btn_row = QHBoxLayout()
        self.btn_export_pdf = QPushButton("🖨️ Export Batch ke A4 PDF (Grid 3x3 Siap Cetak)")
        self.btn_export_pdf.setStyleSheet("background-color: #c62828; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.btn_export_pdf.clicked.connect(lambda: self._start_batch_export("pdf_grid"))
        btn_row.addWidget(self.btn_export_pdf)

        self.btn_export_images = QPushButton("📁 Export Batch ke Gambar Satuan (Folder PNG)")
        self.btn_export_images.setStyleSheet("background-color: #00695c; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.btn_export_images.clicked.connect(lambda: self._start_batch_export("folder_images"))
        btn_row.addWidget(self.btn_export_images)

        exp_layout.addLayout(btn_row)

        # Progress bar & Cancel
        prog_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_status_label = QLabel("Menunggu aksi batch...")
        self.btn_cancel_batch = QPushButton("Batal")
        self.btn_cancel_batch.setEnabled(False)
        self.btn_cancel_batch.clicked.connect(self._cancel_batch_export)

        prog_row.addWidget(self.progress_bar, 1)
        prog_row.addWidget(self.btn_cancel_batch)
        exp_layout.addLayout(prog_row)
        exp_layout.addWidget(self.progress_status_label)

        layout.addWidget(exp_group)
        return widget

    def _create_settings_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)

        # API & Config Settings Group
        api_group = QGroupBox("Integrasi API Background Removal (remove.bg)")
        api_layout = QFormLayout(api_group)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Masukkan remove.bg API Key Anda...")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.api_key_edit.setText(self.app_config.get("remove_bg_api_key", ""))
        api_layout.addRow("remove.bg API Key:", self.api_key_edit)

        btn_save_key = QPushButton("Simpan Pengaturan API")
        btn_save_key.clicked.connect(self._save_api_key)
        api_layout.addRow("", btn_save_key)

        info_rembg = QLabel("<i>Catatan: Foto yang sudah diproses akan dicache secara lokal sehingga tidak menguras kuota API jika dirender ulang.</i>")
        info_rembg.setStyleSheet("color: #888888;")
        api_layout.addRow("", info_rembg)
        layout.addWidget(api_group)

        # DPI Setting
        dpi_group = QGroupBox("Pengaturan Kualitas Cetak")
        dpi_layout = QFormLayout(dpi_group)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 600)
        self.dpi_spin.setValue(self.app_config.get("dpi", 300))
        dpi_layout.addRow("Resolusi Cetak (DPI):", self.dpi_spin)
        layout.addWidget(dpi_group)

        # Real-time Log Console
        log_group = QGroupBox("Status & Log Console")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #1a1a1a; color: #a9b7c6; font-family: monospace; font-size: 11px;")
        log_layout.addWidget(self.log_text)

        btn_clear_log = QPushButton("Bersihkan Log")
        btn_clear_log.clicked.connect(self.log_text.clear)
        log_layout.addWidget(btn_clear_log)
        layout.addWidget(log_group, 1)

        return widget

    def _apply_styling(self):
        dark_stylesheet = """
        QMainWindow, QWidget {
            background-color: #212121;
            color: #eeeeee;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 12px;
        }
        QGroupBox {
            border: 1px solid #3d3d3d;
            border-radius: 6px;
            margin-top: 14px;
            padding-top: 14px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 4px;
            color: #90caf9;
        }
        QLineEdit, QSpinBox, QComboBox, QTableWidget {
            background-color: #2d2d2d;
            border: 1px solid #484848;
            border-radius: 4px;
            padding: 5px;
            color: #ffffff;
            selection-background-color: #1976d2;
        }
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
            border: 1px solid #2196f3;
        }
        QPushButton {
            background-color: #383838;
            border: 1px solid #505050;
            border-radius: 4px;
            padding: 6px 12px;
            color: #ffffff;
        }
        QPushButton:hover {
            background-color: #484848;
            border: 1px solid #64b5f6;
        }
        QPushButton:pressed {
            background-color: #282828;
        }
        QTabWidget::pane {
            border: 1px solid #3c3c3c;
            background-color: #252525;
        }
        QTabBar::tab {
            background-color: #2c2c2c;
            color: #b0bec5;
            padding: 8px 16px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #1976d2;
            color: #ffffff;
            font-weight: bold;
        }
        QHeaderView::section {
            background-color: #303030;
            color: #ffffff;
            padding: 5px;
            border: 1px solid #424242;
            font-weight: bold;
        }
        QProgressBar {
            border: 1px solid #424242;
            border-radius: 4px;
            text-align: center;
            background-color: #2c2c2c;
        }
        QProgressBar::chunk {
            background-color: #4caf50;
            border-radius: 3px;
        }
        """
        self.setStyleSheet(dark_stylesheet)

    # ================= CONFIG MANAGEMENT =================
    def _load_app_config(self):
        self.app_config = {"remove_bg_api_key": "", "dpi": 300}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.app_config.update(json.load(f))
            except Exception:
                pass

    def _save_api_key(self):
        key = self.api_key_edit.text().strip()
        self.app_config["remove_bg_api_key"] = key
        self.app_config["dpi"] = self.dpi_spin.value()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.app_config, f, indent=2)
            self.log("success", "Pengaturan API Key berhasil disimpan.")
            QMessageBox.information(self, "Pengaturan Tersimpan", "API Key remove.bg berhasil disimpan.")
        except Exception as e:
            self.log("error", f"Gagal menyimpan config: {e}")

    # ================= SIGNAL CONNECTIONS =================
    def _connect_signals(self):
        self.signals.layer_selected.connect(self._on_layer_selected_on_canvas)
        self.signals.layer_modified.connect(self._on_layer_modified)
        self.signals.layer_moved.connect(self._on_layer_moved)
        self.signals.canvas_clicked_empty.connect(self._on_canvas_clicked_empty)

    def log(self, level: str, message: str):
        color_map = {
            "info": "#90caf9",
            "success": "#81c784",
            "warning": "#ffb74d",
            "error": "#e57373"
        }
        color = color_map.get(level.lower(), "#ffffff")
        html_msg = f"<span style='color: #777;'>[{level.upper()}]</span> <span style='color: {color};'>{message}</span>"
        self.log_text.append(html_msg)
        self.status_bar.showMessage(message, 5000)

    # ================= CANVAS & LAYER ACTIONS =================
    def _refresh_layer_list(self):
        self.layer_list_widget.clear()
        for layer in self.template_config.layers:
            icon = "📷" if layer.type == "photo" else "📝"
            item = QListWidgetItem(f"{icon} {layer.name} ({layer.key})")
            item.setData(Qt.ItemDataRole.UserRole, layer.id)
            self.layer_list_widget.addItem(item)

    def _on_layer_selected_on_canvas(self, layer: LayerConfig):
        self.prop_panel.set_layer(layer)
        # Select corresponding item in layer list
        for i in range(self.layer_list_widget.count()):
            item = self.layer_list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == layer.id:
                self.layer_list_widget.setCurrentItem(item)
                break

    def _on_canvas_clicked_empty(self):
        self.prop_panel.set_layer(None)
        self.layer_list_widget.clearSelection()

    def _on_layer_modified(self, layer: LayerConfig):
        self.canvas_view.update_layer_item(layer)
        self._refresh_layer_list()

    def _on_layer_moved(self, layer: LayerConfig):
        self.prop_panel.sync_coordinates(layer)

    def _on_layer_list_clicked(self, item: QListWidgetItem):
        layer_id = item.data(Qt.ItemDataRole.UserRole)
        self.canvas_view.select_layer(layer_id)

    def _add_text_layer(self):
        new_layer = LayerConfig(
            type="text",
            name=f"Teks {len(self.template_config.layers) + 1}",
            key=f"teks_{len(self.template_config.layers) + 1}",
            x=60,
            y=100 + len(self.template_config.layers) * 40,
            width=400,
            height=50,
            font_size=28,
            font_color="#0f2027",
            default_text="Teks Contoh"
        )
        self.template_config.add_layer(new_layer)
        self.canvas_view.rebuild_scene()
        self._refresh_layer_list()
        self.canvas_view.select_layer(new_layer.id)
        self._generate_manual_form_inputs()
        self._init_batch_table_columns()
        self.log("info", f"Menambahkan elemen teks baru: {new_layer.name}")

    def _add_photo_layer(self):
        new_layer = LayerConfig(
            type="photo",
            name="Foto Profil",
            key="Foto",
            x=170,
            y=250,
            width=280,
            height=340,
            fit_mode="cover",
            corner_radius=12,
            border_width=3,
            border_color="#203a43",
            placeholder_path="sample_data/sample_photo.png" if os.path.exists("sample_data/sample_photo.png") else ""
        )
        self.template_config.add_layer(new_layer)
        self.canvas_view.rebuild_scene()
        self._refresh_layer_list()
        self.canvas_view.select_layer(new_layer.id)
        self._generate_manual_form_inputs()
        self._init_batch_table_columns()
        self.log("info", "Menambahkan frame foto baru")

    def _move_layer(self, direction: int):
        cur_item = self.layer_list_widget.currentItem()
        if not cur_item:
            return
        layer_id = cur_item.data(Qt.ItemDataRole.UserRole)
        if self.template_config.move_layer(layer_id, direction):
            self.canvas_view.rebuild_scene()
            self._refresh_layer_list()
            self.canvas_view.select_layer(layer_id)

    def _delete_selected_layer(self):
        cur_item = self.layer_list_widget.currentItem()
        if not cur_item:
            return
        layer_id = cur_item.data(Qt.ItemDataRole.UserRole)
        layer = self.template_config.get_layer(layer_id)
        layer_name = layer.name if layer else "elemen"
        
        reply = QMessageBox.question(
            self, "Konfirmasi Hapus",
            f"Apakah Anda yakin ingin menghapus '{layer_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.template_config.remove_layer(layer_id)
            self.canvas_view.rebuild_scene()
            self._refresh_layer_list()
            self.prop_panel.set_layer(None)
            self._generate_manual_form_inputs()
            self._init_batch_table_columns()
            self.log("info", f"Elemen '{layer_name}' berhasil dihapus.")

    def _browse_template_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Pilih Gambar Background Template", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.template_config.template_image_path = path
            # Try to get native resolution of image
            try:
                from PIL import Image
                with Image.open(path) as img:
                    w, h = img.size
                    self.template_config.width = w
                    self.template_config.height = h
            except Exception:
                pass

            self.canvas_view.rebuild_scene()
            self.canvas_view.zoom_fit()
            self.log("success", f"Background template dimuat: {path} ({self.template_config.width}x{self.template_config.height} px)")

    def _save_preset_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Simpan Preset Template", "template_preset.json", "JSON Preset (*.json);;YAML Preset (*.yaml)")
        if path:
            try:
                if path.endswith(".yaml") or path.endswith(".yml"):
                    self.template_config.save_to_yaml(path)
                else:
                    self.template_config.save_to_json(path)
                self.log("success", f"Preset berhasil disimpan di: {path}")
                QMessageBox.information(self, "Preset Tersimpan", f"Preset template berhasil disimpan di:\n{path}")
            except Exception as e:
                self.log("error", f"Gagal menyimpan preset: {e}")
                QMessageBox.critical(self, "Error", f"Gagal menyimpan preset:\n{e}")

    def _load_preset_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Muat Preset Template", "", "Preset Files (*.json *.yaml *.yml)")
        if path:
            try:
                if path.endswith(".yaml") or path.endswith(".yml"):
                    self.template_config = TemplateConfig.load_from_yaml(path)
                else:
                    self.template_config = TemplateConfig.load_from_json(path)
                self.canvas_view.set_template(self.template_config)
                self._refresh_layer_list()
                self._generate_manual_form_inputs()
                self._init_batch_table_columns()
                self.canvas_view.zoom_fit()
                self.log("success", f"Preset dimuat: {path}")
            except Exception as e:
                self.log("error", f"Gagal memuat preset: {e}")
                QMessageBox.critical(self, "Error", f"Gagal memuat preset:\n{e}")

    # ================= MANUAL SINGLE FORM MODE =================
    def _generate_manual_form_inputs(self):
        # Clear existing layout
        while self.manual_form_layout.count() > 0:
            child = self.manual_form_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.manual_input_fields: Dict[str, QWidget] = {}

        for layer in self.template_config.layers:
            if layer.type == "text":
                line_edit = QLineEdit()
                line_edit.setText(layer.default_text)
                line_edit.textChanged.connect(self._on_manual_field_changed)
                self.manual_form_layout.addRow(f"{layer.name} ({layer.key}):", line_edit)
                self.manual_input_fields[layer.key] = line_edit
            elif layer.type == "photo":
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)

                photo_edit = QLineEdit()
                photo_edit.setText(layer.placeholder_path)
                photo_edit.textChanged.connect(self._on_manual_field_changed)

                browse_btn = QPushButton("Pilih Foto...")
                browse_btn.clicked.connect(lambda _, pe=photo_edit: self._browse_single_photo(pe))

                row_layout.addWidget(photo_edit, 1)
                row_layout.addWidget(browse_btn)

                self.manual_form_layout.addRow(f"{layer.name} ({layer.key}):", row_widget)
                self.manual_input_fields[layer.key] = photo_edit

        self._update_manual_live_preview()

    def _browse_single_photo(self, line_edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(self, "Pilih Foto Karyawan", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            line_edit.setText(path)

    def _on_manual_field_changed(self):
        self._update_manual_live_preview()

    def _get_manual_form_data(self) -> Dict[str, Any]:
        data = {}
        for key, widget in self.manual_input_fields.items():
            if isinstance(widget, QLineEdit):
                data[key] = widget.text().strip()
        return data

    def _update_manual_live_preview(self):
        data = self._get_manual_form_data()
        renderer = CardRenderer()
        img = renderer.render(self.template_config, data, enable_bg_removal=False)

        # Convert PIL RGBA to QImage
        data_bytes = img.tobytes("raw", "RGBA")
        qim = QImage(data_bytes, img.size[0], img.size[1], QImage.Format.Format_RGBA8888)
        pix = QPixmap.fromImage(qim)

        # Scale preview to fit comfortably
        target_h = 480
        scaled_pix = pix.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
        self.manual_preview_label.setPixmap(scaled_pix)

    def _export_single_card_action(self):
        path, _ = QFileDialog.getSaveFileName(self, "Simpan ID Card", "id_card.png", "PNG Image (*.png);;JPEG Image (*.jpg)")
        if not path:
            return

        data = self._get_manual_form_data()
        api_key = self.app_config.get("remove_bg_api_key", "")
        enable_bg = bool(api_key)

        try:
            bg_service = BackgroundRemovalService(api_key)
            export_single_card(
                self.template_config,
                data,
                path,
                enable_bg_removal=enable_bg,
                bg_remover=bg_service,
                dpi=self.dpi_spin.value()
            )
            self.log("success", f"Kartu berhasil diekspor ke: {path}")
            QMessageBox.information(self, "Berhasil", f"Kartu berhasil disimpan di:\n{path}")
        except Exception as e:
            self.log("error", f"Gagal mengekspor kartu: {e}")
            QMessageBox.critical(self, "Gagal Ekspor", f"Terjadi kesalahan:\n{e}")

    # ================= BATCH IMPORT & TABLE =================
    def _init_batch_table_columns(self):
        # Column headers from layer keys
        headers = []
        for l in self.template_config.layers:
            if l.key not in headers:
                headers.append(l.key)
        if not headers:
            headers = ["Nama", "NIK", "Divisi", "Foto"]

        self.batch_table.setColumnCount(len(headers))
        self.batch_table.setHorizontalHeaderLabels(headers)

    def _add_table_row(self, row_data: Optional[Dict[str, str]] = None):
        row_idx = self.batch_table.rowCount()
        self.batch_table.insertRow(row_idx)

        col_count = self.batch_table.columnCount()
        for col_idx in range(col_count):
            header = self.batch_table.horizontalHeaderItem(col_idx).text()
            val = ""
            if row_data:
                val = row_data.get(header, "")
            self.batch_table.setItem(row_idx, col_idx, QTableWidgetItem(val))

    def _delete_table_row(self):
        selected_rows = sorted(set(index.row() for index in self.batch_table.selectedIndexes()), reverse=True)
        for r in selected_rows:
            self.batch_table.removeRow(r)

    def _clear_table(self):
        self.batch_table.setRowCount(0)

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if not text:
            QMessageBox.warning(self, "Clipboard Kosong", "Tidak ada teks yang ditemukan di clipboard.")
            return

        lines = text.splitlines()
        if not lines:
            return

        # Determine delimiter (tab or comma)
        sample_line = lines[0]
        delim = "\t" if "\t" in sample_line else ","

        reader = csv.reader(lines, delimiter=delim)
        parsed_rows = list(reader)
        if not parsed_rows:
            return

        # Check if first line is header
        first_row = [c.strip() for c in parsed_rows[0]]
        existing_headers = [self.batch_table.horizontalHeaderItem(i).text() for i in range(self.batch_table.columnCount())]

        has_header = any(h.lower() in [eh.lower() for eh in existing_headers] for h in first_row)
        data_rows = parsed_rows[1:] if has_header else parsed_rows

        if has_header:
            header_map = {}
            for col_idx, col_name in enumerate(first_row):
                for eh_idx, eh in enumerate(existing_headers):
                    if col_name.strip().lower() == eh.lower():
                        header_map[col_idx] = eh_idx
                        break
        else:
            header_map = {i: i for i in range(min(len(first_row), len(existing_headers)))}

        added_count = 0
        for r in data_rows:
            if not any(r):
                continue
            row_idx = self.batch_table.rowCount()
            self.batch_table.insertRow(row_idx)
            for src_idx, cell_val in enumerate(r):
                target_col = header_map.get(src_idx)
                if target_col is not None and target_col < self.batch_table.columnCount():
                    self.batch_table.setItem(row_idx, target_col, QTableWidgetItem(cell_val.strip()))
            added_count += 1

        self.log("success", f"Berhasil menempel {added_count} baris dari clipboard!")

    def _import_csv_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Buka File CSV Data", "", "CSV Files (*.csv *.txt)")
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                self._init_batch_table_columns()
                existing_headers = [self.batch_table.horizontalHeaderItem(i).text() for i in range(self.batch_table.columnCount())]

                count = 0
                for row in reader:
                    mapped = {}
                    for h in existing_headers:
                        for rh in headers:
                            if h.lower() == rh.lower():
                                mapped[h] = row[rh]
                                break
                    self._add_table_row(mapped)
                    count += 1
            self.log("success", f"Berhasil mengimpor {count} data dari: {os.path.basename(path)}")
        except Exception as e:
            self.log("error", f"Gagal membaca file CSV: {e}")
            QMessageBox.critical(self, "Error", f"Gagal membaca CSV:\n{e}")

    def _get_batch_table_records(self) -> List[Dict[str, Any]]:
        records = []
        rows = self.batch_table.rowCount()
        cols = self.batch_table.columnCount()
        headers = [self.batch_table.horizontalHeaderItem(c).text() for c in range(cols)]

        for r in range(rows):
            rec = {}
            for c in range(cols):
                item = self.batch_table.item(r, c)
                rec[headers[c]] = item.text().strip() if item else ""
            records.append(rec)
        return records

    def _on_table_row_selected(self):
        pass

    def _preview_selected_table_row(self):
        cur_row = self.batch_table.currentRow()
        if cur_row < 0:
            QMessageBox.information(self, "Pilih Baris", "Silakan klik baris di tabel yang ingin dipreview.")
            return

        cols = self.batch_table.columnCount()
        headers = [self.batch_table.horizontalHeaderItem(c).text() for c in range(cols)]
        row_data = {}
        for c in range(cols):
            item = self.batch_table.item(cur_row, c)
            row_data[headers[c]] = item.text().strip() if item else ""

        # Switch to manual form or update preview
        for key, widget in self.manual_input_fields.items():
            if key in row_data and isinstance(widget, QLineEdit):
                widget.setText(row_data[key])

        self.tabs.setCurrentIndex(1)  # switch to manual tab to see live preview
        self.log("info", f"Menampilkan preview data baris #{cur_row + 1}")

    # ================= BATCH EXPORT & THREADING =================
    def _start_batch_export(self, export_mode: str):
        records = self._get_batch_table_records()
        if not records:
            QMessageBox.warning(self, "Data Kosong", "Tabel batch masih kosong. Masukkan data terlebih dahulu.")
            return

        if export_mode == "pdf_grid":
            output_path, _ = QFileDialog.getSaveFileName(
                self, "Simpan Batch Cetak A4 PDF (3x3 Grid)", "batch_idcard_a4_print.pdf", "PDF Document (*.pdf)"
            )
        else:
            output_path = QFileDialog.getExistingDirectory(self, "Pilih Folder Output untuk Menyimpan File PNG")

        if not output_path:
            return

        api_key = self.app_config.get("remove_bg_api_key", "")
        enable_bg = self.chk_rembg_batch.isChecked() and bool(api_key)

        self.progress_bar.setValue(0)
        self.progress_status_label.setText("Menyiapkan worker thread...")
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_images.setEnabled(False)
        self.btn_cancel_batch.setEnabled(True)

        self.batch_worker = BatchExportWorker(
            template=self.template_config,
            records=records,
            export_mode=export_mode,
            output_path=output_path,
            enable_bg_removal=enable_bg,
            api_key=api_key,
            dpi=self.dpi_spin.value(),
            show_cut_marks=self.chk_cut_marks.isChecked()
        )

        self.batch_worker.progress.connect(self._on_batch_progress)
        self.batch_worker.log_message.connect(self.log)
        self.batch_worker.finished.connect(self._on_batch_finished)
        self.batch_worker.error.connect(self._on_batch_error)
        self.batch_worker.start()

    def _on_batch_progress(self, cur: int, total: int, msg: str):
        pct = int((cur / max(1, total)) * 100)
        self.progress_bar.setValue(pct)
        self.progress_status_label.setText(f"{msg} ({pct}%)")

    def _on_batch_finished(self, summary: str):
        self.btn_export_pdf.setEnabled(True)
        self.btn_export_images.setEnabled(True)
        self.btn_cancel_batch.setEnabled(False)
        self.progress_status_label.setText("Selesai.")
        QMessageBox.information(self, "Proses Selesai", summary)

    def _on_batch_error(self, err_msg: str):
        self.btn_export_pdf.setEnabled(True)
        self.btn_export_images.setEnabled(True)
        self.btn_cancel_batch.setEnabled(False)
        self.progress_status_label.setText("Error!")
        QMessageBox.critical(self, "Error Batch Export", err_msg)

    def _cancel_batch_export(self):
        if self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.cancel()
            self.progress_status_label.setText("Membatalkan proses...")

    def _on_tab_changed(self, index: int):
        if index == 1:
            self._update_manual_live_preview()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Global Font Setup
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = IDCardApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
