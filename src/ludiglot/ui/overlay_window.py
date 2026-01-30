from __future__ import annotations

import json
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QPoint, QRect, QSize, QAbstractNativeEventFilter, QEvent, QEventLoop
from PyQt6.QtGui import QFont, QTextOption, QColor, QPalette, QAction, QActionGroup, QCursor, QPainter, QPixmap, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTextEdit, QMenu, QComboBox, QSizePolicy,
    QSlider, QSpinBox, QDoubleSpinBox, QWidgetAction, QStyle,
    QRubberBand, QSystemTrayIcon
)

from ludiglot.adapters.wuthering_waves.audio_strategy import WutheringAudioStrategy
from ludiglot.core.audio_extract import (
    convert_single_wem_to_wav,
    convert_txtp_to_wav,
    default_wwiser_path,
    find_bnk_for_event,
    find_wem_by_event_name,
    find_txtp_for_event,
    find_wem_by_hash,
    generate_txtp_for_bnk,
)
from ludiglot.core.audio_mapper import AudioCacheIndex
from ludiglot.core.audio_player import AudioPlayer
from ludiglot.core.capture import (
    CaptureError,
    CaptureRegion,
    capture_fullscreen,
    capture_region,
    capture_window,
)
from ludiglot.core.config import AppConfig, load_config
from ludiglot.core.ocr import OCREngine, group_ocr_lines
from ludiglot.core.search import FuzzySearcher
from ludiglot.core.smart_match import build_smart_candidates
from ludiglot.core.text_builder import (
    build_text_db,
    build_text_db_from_root_all,
    load_plot_audio_map,
    normalize_en,
    save_text_db,
)
from ludiglot.core.voice_map import build_voice_map_from_configdb, _resolve_events_for_text_key
from ludiglot.core.voice_event_index import VoiceEventIndex
from ludiglot.core.matcher import TextMatcher


class PersistentMenu(QMenu):
    """自定义菜单，支持在操作某些控件时保持开启。"""
    def mouseReleaseEvent(self, event):
        action = self.actionAt(event.position().toPoint())
        
        # 如果是叶子节点动作且标记为 persistent，则触发但不关闭
        if action and not action.menu() and action.property("persistent"):
            action.trigger()
            return # 关键：不调用 super() 阻止菜单关闭
            
        super().mouseReleaseEvent(event)

class UiSignals(QObject):
    status = pyqtSignal(str)
    result = pyqtSignal(dict)
    error = pyqtSignal(str)
    log = pyqtSignal(str)


class OverlayWindow(QMainWindow):
    """无边框、置顶覆盖层窗口（MVP）。"""

    capture_requested = pyqtSignal(bool)
    resources_loaded = pyqtSignal()

    def __init__(self, config: AppConfig, config_path: Path) -> None:
        super().__init__()
        self.config = config
        self._config_path = config_path
        self.signals = UiSignals()
        self.log_path = Path(__file__).resolve().parents[3] / "log" / "gui.log"
        self._install_terminal_logger()
        # self.searcher = FuzzySearcher() # TextMatcher now handles this
        self.matcher: TextMatcher | None = None
        self.audio_resolver: AudioResolver | None = None
        self.engine = OCREngine(
            lang=config.ocr_lang,
            use_gpu=config.ocr_gpu,
            mode=config.ocr_mode,
        )
        self.db: Dict[str, Any] = {}
        self.voice_map: Dict[str, list[str]] = {}
        self.voice_event_index: VoiceEventIndex | None = None
        self.audio_index: AudioCacheIndex | None = None
        self.last_match: Dict[str, Any] | None = None
        self.last_text_key: str | None = None
        self.last_hash: int | None = None
        self.last_event_name: str | None = None
        self.player = AudioPlayer()
        self._hotkey_listener = None
        self._win_hotkey_filter = None
        self._win_hotkey_ids: list[int] = []
        self._dragging = False
        self._drag_pos: QPoint | None = None
        self._resizing = False
        self._resize_edge = None  # 'left', 'right', 'top', 'bottom', 'topleft', 'topright', 'bottomleft', 'bottomright'
        self._resize_start_geometry = None
        self._resize_start_pos = None
        
        # 音频进度更新定时器
        from PyQt6.QtCore import QTimer
        self.audio_timer = QTimer(self)
        self.audio_timer.timeout.connect(self._update_audio_progress)
        self.audio_timer.setInterval(100)  # 每100ms更新一次
        
        # UI 状态
        self.current_font_size = 13
        self.current_font_weight = "SemiBold"
        self.current_letter_spacing = 0
        self.current_line_spacing = 1.2
        self.current_font_en = config.font_en
        self.current_font_cn = config.font_cn
        self._last_en_raw: str | None = None
        self._last_cn_raw: str | None = None
        self._last_en_is_html = False
        self._last_cn_is_html = False
        
        # 1. 先初始化 UI
        self._setup_ui()
        # 2. 连接所有信号（确保日志等能正常工作）
        self._connect_signals()
        # 3. 恢复配置（覆盖默认值，并调整窗口尺寸）
        self._restore_window_position()
        # 4. 最后应用样式和字体
        self._load_style()
        self._apply_font_settings()

        self.capture_requested.connect(self._capture_and_process_async)
        
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        threading.Thread(target=self._initialize_resources, daemon=True).start()
        self._start_hotkeys()
        
        # 定时同步窗口位置到外部 config
        self._sync_config_timer = QTimer(self)
        self._sync_config_timer.timeout.connect(self._persist_window_position)
        self._sync_config_timer.start(5000)  # 每 5 秒同步一次

    def closeEvent(self, event) -> None:
        print("[DEBUG] OverlayWindow closeEvent", flush=True)
        super().closeEvent(event)

    def _install_terminal_logger(self) -> None:
        """将 stdout/stderr/Qt警告 同步写入日志文件。"""
        if hasattr(sys.stdout, "_ludiglot_tee"):
            return

        class _TeeStream:
            def __init__(self, stream, log_path: Path) -> None:
                self._stream = stream
                self._log_path = log_path
                self._ludiglot_tee = True

            def write(self, data):
                try:
                    self._stream.write(data)
                except Exception:
                    pass
                try:
                    self._log_path.parent.mkdir(parents=True, exist_ok=True)
                    with self._log_path.open("a", encoding="utf-8") as f:
                        f.write(data)
                except Exception:
                    pass

            def flush(self):
                try:
                    self._stream.flush()
                except Exception:
                    pass

        sys.stdout = _TeeStream(sys.stdout, self.log_path)
        sys.stderr = _TeeStream(sys.stderr, self.log_path)
        
        # 捕获Qt警告和错误
        def qt_message_handler(mode, context, message):
            log_msg = f"[Qt {mode.name}] {message}\n"
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write(log_msg)
            except Exception:
                pass
        
        from PyQt6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(qt_message_handler)

    def _setup_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        # 启用半透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)  # 启用鼠标跟踪以便更新光标样式
        # 设置焦点策略以便接收焦点事件
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        container = QWidget(self)
        container.setObjectName("CentralWidget") # 给容器一个名字以便样式或拖拽识别
        container.setMouseTracking(True)  # 确保容器也传递鼠标事件
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self.title_label = QLabel("Ludiglot")
        self.title_label.setObjectName("Title")
        self.title_label.setFont(QFont("Segoe UI", 12))

        self.source_label = QTextEdit("等待捕获…")
        self.source_label.setObjectName("SourceText")
        self.source_label.setReadOnly(True)
        self.source_label.setAcceptRichText(True)  # 支持富文本
        self.source_label.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.source_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.source_label.setMinimumHeight(60)
        self.source_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.cn_label = QTextEdit("")
        self.cn_label.setObjectName("AccentText")
        self.cn_label.setReadOnly(True)
        self.cn_label.setAcceptRichText(True)  # 显式启用富文本支持
        self.cn_label.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.cn_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cn_label.setMinimumHeight(80)
        self.cn_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("StatusText")

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setObjectName("LogBox")
        self.log_box.setMinimumHeight(90)


        layout.addWidget(self.title_label)
        layout.addWidget(self.source_label)
        layout.addWidget(self.cn_label)
        
        # 音频控制栏（进度条 + 播放/暂停按钮 + 时间显示）
        audio_control_layout = QHBoxLayout()
        self.play_pause_btn = QPushButton("")
        self.play_pause_btn.setObjectName("AudioControl")
        self.play_pause_btn.setFixedSize(28, 28)
        self.play_pause_btn.setEnabled(False)
        self.play_pause_btn.clicked.connect(self._toggle_audio_playback)
        # 使用系统标准图标，避免彩色emoji
        style = self.style()
        if style:
            self._icon_play = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            self._icon_pause = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        else:
            self._icon_play = None
            self._icon_pause = None
        if self._icon_play:
            self.play_pause_btn.setIcon(self._icon_play)
        self.play_pause_btn.setIconSize(self.play_pause_btn.size() * 0.7)
        
        self.audio_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_slider.setObjectName("AudioSlider")
        self.audio_slider.setEnabled(False)
        self.audio_slider.setRange(0, 100)
        self.audio_slider.sliderPressed.connect(self._on_slider_pressed)
        self.audio_slider.sliderReleased.connect(self._on_slider_released)
        
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("TimeLabel")
        self.time_label.setMinimumWidth(100)
        
        audio_control_layout.addWidget(self.play_pause_btn)
        audio_control_layout.addWidget(self.audio_slider, 1)
        audio_control_layout.addWidget(self.time_label)
        layout.addLayout(audio_control_layout)
        
        layout.addWidget(self.status_label)

        container.setObjectName("OverlayRoot")
        self.setCentralWidget(container)

        
        # 创建窗口右上角菜单按钮
        self._setup_window_menu()
    
    def _setup_window_menu(self) -> None:
        """创建窗口右上角下拉菜单 and 关闭按钮"""
        # 创建顶部控制栏小部件
        self.control_bar = QWidget(self)
        self.control_bar.setFixedHeight(30)
        
        # 使用水平布局来管理按钮
        layout = QHBoxLayout(self.control_bar)
        layout.setContentsMargins(0, 0, 10, 0)  # 右边距10px
        layout.setSpacing(8)  # 按钮间距8px
        
        # 添加弹簧，将按钮推向右侧
        layout.addStretch()
        
        # 创建关闭按钮
        self.top_close_btn = QPushButton("", self.control_bar)
        self.top_close_btn.setFixedSize(26, 26)
        self.top_close_btn.setObjectName("TopCloseButton")
        self.top_close_btn.setStyleSheet("""
            QPushButton#TopCloseButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                min-width: 26px;
                max-width: 26px;
                padding: 0px;
            }
            QPushButton#TopCloseButton:hover {
                background-color: rgba(255, 100, 100, 30);
            }
        """)
        
        # 使用 Label 承载关闭图标以实现像素级对齐
        self.close_icon_label = QLabel("×", self.top_close_btn)
        self.close_icon_label.setFixedSize(26, 26)
        # y轴上移 2px
        self.close_icon_label.move(0, -2)
        self.close_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.close_icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.close_icon_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 100, 100, 200);
                font-size: 22px;
                font-weight: bold;
                background: transparent;
            }
        """)
        self.top_close_btn.clicked.connect(self.hide)
        layout.addWidget(self.top_close_btn)
        
        # 创建菜单按钮
        self.top_menu_btn = QPushButton("", self.control_bar)
        self.top_menu_btn.setFixedSize(26, 26)
        self.top_menu_btn.setObjectName("TopMenuButton")
        self.top_menu_btn.setStyleSheet("""
            QPushButton#TopMenuButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                min-width: 26px;
                max-width: 26px;
                padding: 0px;
            }
            QPushButton#TopMenuButton:hover {
                background-color: rgba(255, 255, 255, 30);
            }
            QPushButton#TopMenuButton::menu-indicator {
                image: none;
                width: 0px;
                height: 0px;
            }
        """)

        # 创建独立的图标 Label 以实现像素级位置控制
        self.menu_icon_label = QLabel("≡", self.top_menu_btn)
        self.menu_icon_label.setFixedSize(26, 26)
        # y 轴上移 3px
        self.menu_icon_label.move(0, -3)
        self.menu_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.menu_icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.menu_icon_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 200);
                font-size: 20px;
                font-weight: bold;
                background: transparent;
            }
        """)

        layout.addWidget(self.top_menu_btn)
        
        # 初始定位
        self._update_button_positions()
        
        # 创建下拉菜单
        self.window_menu = PersistentMenu(self)
        # self.top_menu_btn.setMenu(self.window_menu) # 禁用默认菜单，由 _show_window_menu 手动精确对齐
        
        # Update Database 操作
        update_action = QAction("Update Database", self)
        update_action.setToolTip("拉取 WutheringData 仓库并重建数据库")
        update_action.triggered.connect(self._update_database)
        self.window_menu.addAction(update_action)
        
        self.window_menu.addSeparator()

        # OCR 设置子菜单
        ocr_settings_menu = PersistentMenu("OCR Settings", self.window_menu)
        ocr_settings_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        ocr_settings_menu.setStyleSheet(self.window_menu.styleSheet())
        self.window_menu.addMenu(ocr_settings_menu)

        # OCR 后端选择
        ocr_backend_menu = PersistentMenu("Backend", ocr_settings_menu)
        ocr_backend_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        ocr_backend_menu.setStyleSheet(self.window_menu.styleSheet())
        ocr_settings_menu.addMenu(ocr_backend_menu)

        self.ocr_backend_group = QActionGroup(self)
        self.ocr_backend_group.setExclusive(True)
        for backend in ["auto", "paddle", "tesseract"]:
            display_name = {
                "auto": "Auto (Prefer WinOCR)",
                "paddle": "Paddle",
                "tesseract": "Tesseract"
            }.get(backend, backend)
            action = QAction(display_name, self)
            action.setCheckable(True)
            action.setChecked(backend == self.config.ocr_backend)
            action.setProperty("persistent", True)
            action.triggered.connect(lambda checked, b=backend: self._on_backend_changed(b))
            self.ocr_backend_group.addAction(action)
            ocr_backend_menu.addAction(action)

        # OCR 模式选择
        ocr_mode_menu = PersistentMenu("Mode", ocr_settings_menu)
        ocr_mode_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        ocr_mode_menu.setStyleSheet(self.window_menu.styleSheet())
        ocr_settings_menu.addMenu(ocr_mode_menu)

        self.ocr_mode_group = QActionGroup(self)
        self.ocr_mode_group.setExclusive(True)
        for mode in ["auto", "gpu", "cpu"]:
            display_name = {
                "auto": "Auto",
                "gpu": "GPU",
                "cpu": "CPU"
            }.get(mode, mode)
            action = QAction(display_name, self)
            action.setCheckable(True)
            action.setChecked(mode == self.config.ocr_mode)
            action.setProperty("persistent", True)
            action.triggered.connect(lambda checked, m=mode: self._on_mode_changed(m))
            self.ocr_mode_group.addAction(action)
            ocr_mode_menu.addAction(action)

        self.window_menu.addSeparator()
        
        # 字体设置子菜单
        font_settings_menu = PersistentMenu("Font Settings", self.window_menu)
        font_settings_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        font_settings_menu.setStyleSheet(self.window_menu.styleSheet())
        self.window_menu.addMenu(font_settings_menu)
        
        # 字号调节器
        font_size_menu = PersistentMenu("Size", font_settings_menu)
        font_size_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        font_size_menu.setStyleSheet(self.window_menu.styleSheet())
        font_settings_menu.addMenu(font_size_menu)
        
        # 共享调节器样式
        spinner_qss = """
            QSpinBox, QDoubleSpinBox { 
                background: #444; 
                color: white; 
                border: 1px solid #666; 
                border-radius: 3px; 
                padding: 2px 22px 2px 2px;
                selection-background-color: #666;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                height: 10px;
                border-left: 1px solid #666;
                background: #555;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                height: 10px;
                border-left: 1px solid #666;
                border-top: 1px solid #666;
                background: #555;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { 
                background: #666; 
            }
            /* 之前尝试使用边框三角形绘制箭头，在部分环境会退化成矩形，已确认无效 */
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 8 8'><path fill='%23cccccc' d='M4 2 L7 6 H1 Z'/></svg>");
                width: 8px;
                height: 8px;
            }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 8 8'><path fill='%23cccccc' d='M1 2 H7 L4 6 Z'/></svg>");
                width: 8px;
                height: 8px;
            }
            QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 8 8'><path fill='%23ffffff' d='M4 2 L7 6 H1 Z'/></svg>");
            }
            QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 8 8'><path fill='%23ffffff' d='M1 2 H7 L4 6 Z'/></svg>");
            }
        """

        # 字号调节器
        size_action = QWidgetAction(self)
        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(10, 2, 10, 2)
        size_layout.setSpacing(10)
        size_label = QLabel("Size")
        size_label.setStyleSheet("color: white; font-weight: normal;")
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 72)
        self.size_spin.setFixedWidth(80)
        self.size_spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        
        # 严格禁用自动获取焦点
        self.size_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        size_line_edit = self.size_spin.lineEdit()
        if size_line_edit:
            size_line_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            size_line_edit.setReadOnly(False)
            # 点击回车后确认并清除焦点（隐藏游标）
            size_line_edit.returnPressed.connect(size_line_edit.clearFocus)
            size_line_edit.editingFinished.connect(size_line_edit.clearFocus)
        
        self.size_spin.setStyleSheet(spinner_qss)
        self.size_spin.setValue(self.current_font_size)
        self.size_spin.valueChanged.connect(self._adjust_font_size_direct)
        size_layout.addWidget(size_label)
        size_layout.addStretch()
        size_layout.addWidget(self.size_spin)
        size_action.setDefaultWidget(size_widget)
        if font_size_menu:
            font_size_menu.addAction(size_action)
        
        font_weight_menu = PersistentMenu("Weight", font_settings_menu)
        font_weight_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        font_weight_menu.setStyleSheet(self.window_menu.styleSheet())
        font_settings_menu.addMenu(font_weight_menu)
        
        if font_weight_menu:

            self.font_weight_group = QActionGroup(self)
            self.font_weight_group.setExclusive(True)
        
            for weight in ["Light", "Normal", "SemiBold", "Bold", "Heavy"]:
                action = QAction(weight, self)
                action.setCheckable(True)
                action.setChecked(weight == self.current_font_weight)
                action.setProperty("persistent", True)
                action.triggered.connect(lambda checked, w=weight: self._adjust_font_weight(w))
                self.font_weight_group.addAction(action)
                font_weight_menu.addAction(action)
        
        # 字距调节器
        letter_spacing_menu = PersistentMenu("Letter Spacing", font_settings_menu)
        letter_spacing_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        letter_spacing_menu.setStyleSheet(self.window_menu.styleSheet())
        font_settings_menu.addMenu(letter_spacing_menu)
        
        spacing_action = QWidgetAction(self)
        spacing_widget = QWidget()
        spacing_layout = QHBoxLayout(spacing_widget)
        spacing_layout.setContentsMargins(10, 2, 10, 2)
        spacing_layout.setSpacing(10)
        spacing_label = QLabel("Spacing")
        spacing_label.setStyleSheet("color: white; font-weight: normal;")
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(-10, 50)
        self.spacing_spin.setSingleStep(0.5)
        self.spacing_spin.setFixedWidth(80)
        self.spacing_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        spacing_line_edit = self.spacing_spin.lineEdit()
        if spacing_line_edit:
            spacing_line_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            spacing_line_edit.setReadOnly(False)
            # 点击回车后确认并清除焦点（隐藏游标）
            spacing_line_edit.returnPressed.connect(spacing_line_edit.clearFocus)
            spacing_line_edit.editingFinished.connect(spacing_line_edit.clearFocus)
        
        self.spacing_spin.setStyleSheet(spinner_qss)
        self.spacing_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        self.spacing_spin.setValue(self.current_letter_spacing)
        self.spacing_spin.valueChanged.connect(self._adjust_letter_spacing_direct)
        spacing_layout.addWidget(spacing_label)
        spacing_layout.addStretch()
        spacing_layout.addWidget(self.spacing_spin)
        spacing_action.setDefaultWidget(spacing_widget)
        if letter_spacing_menu:
            letter_spacing_menu.addAction(spacing_action)
        
        # 行距调节器
        line_spacing_menu = PersistentMenu("Line Spacing", font_settings_menu)
        line_spacing_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        line_spacing_menu.setStyleSheet(self.window_menu.styleSheet())
        font_settings_menu.addMenu(line_spacing_menu)
        
        lh_action = QWidgetAction(self)
        lh_widget = QWidget()
        lh_layout = QHBoxLayout(lh_widget)
        lh_layout.setContentsMargins(10, 2, 10, 2)
        lh_layout.setSpacing(10)
        lh_label = QLabel("Line Spacing")
        lh_label.setStyleSheet("color: white; font-weight: normal;")
        self.lh_spin = QDoubleSpinBox()
        self.lh_spin.setRange(0.5, 5.0)
        self.lh_spin.setSingleStep(0.1)
        self.lh_spin.setFixedWidth(80)
        self.lh_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        lh_line_edit = self.lh_spin.lineEdit()
        if lh_line_edit:
            lh_line_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            lh_line_edit.setReadOnly(False)
            # 点击回车后确认并清除焦点（隐藏游标）
            lh_line_edit.returnPressed.connect(lh_line_edit.clearFocus)
            lh_line_edit.editingFinished.connect(lh_line_edit.clearFocus)
        
        self.lh_spin.setStyleSheet(spinner_qss)
        self.lh_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        self.lh_spin.setValue(self.current_line_spacing)
        self.lh_spin.valueChanged.connect(self._adjust_line_spacing_direct)
        lh_layout.addWidget(lh_label)
        lh_layout.addStretch()
        lh_layout.addWidget(self.lh_spin)
        lh_action.setDefaultWidget(lh_widget)
        if line_spacing_menu:
            line_spacing_menu.addAction(lh_action)

        # 字体选择菜单
        font_family_menu = PersistentMenu("Font Family", font_settings_menu)
        font_family_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        font_family_menu.setStyleSheet(self.window_menu.styleSheet())
        if font_settings_menu:
            font_settings_menu.addMenu(font_family_menu)
            
            # 英文字体
            en_font_menu = PersistentMenu("English", font_family_menu)
            en_font_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            en_font_menu.setStyleSheet(self.window_menu.styleSheet())
            font_family_menu.addMenu(en_font_menu)
            self._setup_font_selection_menu(en_font_menu, "en")
            
            # 中文字体
            cn_font_menu = PersistentMenu("Chinese", font_family_menu)
            cn_font_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            cn_font_menu.setStyleSheet(self.window_menu.styleSheet())
            font_family_menu.addMenu(cn_font_menu)
            self._setup_font_selection_menu(cn_font_menu, "cn")

        self.window_menu.addSeparator()
        
        # 菜单展开方向 - 作为一个标准菜单，保持普通关闭行为
        direction_menu = self.window_menu.addMenu("Menu Direction")
        if direction_menu:
            direction_menu.setStyleSheet(self.window_menu.styleSheet())
            left_action = QAction("← Left", self)
            left_action.triggered.connect(lambda: self._set_menu_direction("left"))
            direction_menu.addAction(left_action)
            right_action = QAction("Right →", self)
            right_action.triggered.connect(lambda: self._set_menu_direction("right"))
            direction_menu.addAction(right_action)
        
        self.top_menu_btn.clicked.connect(self._show_window_menu)
        
        # 初始化菜单样式（默认左展开）
        self._initialize_menu_style()

    def _show_window_menu(self):
        """显示窗口菜单，实现右边缘对齐"""
        # 核心：必须先获取 sizeHint，因为 exec() 之前 width() 可能还是旧值
        self.window_menu.ensurePolished()
        self.window_menu.adjustSize()
        menu_w = self.window_menu.sizeHint().width()
        
        # 获取按钮右边缘的全局 X 坐标
        btn_topleft = self.top_menu_btn.mapToGlobal(QPoint(0, 0))
        btn_right_x = btn_topleft.x() + self.top_menu_btn.width()
        btn_bottom_y = btn_topleft.y() + self.top_menu_btn.height()
        
        direction = getattr(self, "_menu_direction", "left")
        
        if direction == "left":
            # 强制右边缘对齐：菜单左 X = 按钮右 X - 菜单宽度
            target_x = btn_right_x - menu_w
            self.window_menu.exec(QPoint(target_x, btn_bottom_y))
        else:
            # 向右展开：左边缘对齐 (默认行为)
            self.window_menu.exec(QPoint(btn_topleft.x(), btn_bottom_y))
    
    def _initialize_menu_style(self):
        """初始化菜单样式，确保所有用户都能看到正确的样式"""
        direction = getattr(self, "_menu_direction", "left")
        layout_dir = Qt.LayoutDirection.RightToLeft if direction == "left" else Qt.LayoutDirection.LeftToRight
        item_align = "right" if direction == "left" else "left"
        
        menu_style = f"""
            QMenu {{
                background-color: rgba(40, 40, 40, 240);
                color: white;
                font-family: "Source Han Serif SC", "思源宋体", serif;
                font-size: 13px;
                border: 1px solid rgba(255, 255, 255, 30);
            }}
            QMenu::item {{
                padding: 6px 16px 6px 16px;
                border-radius: 4px;
                text-align: {item_align};
                border-left: 2px solid transparent; /* 始终占用空间，防止选中时宽度抖动 */
            }}
            QMenu::item:checked {{
                background-color: rgba(201, 166, 74, 45);
                border-left: 2px solid #c9a64a;
            }}
            QMenu::item:selected {{
                background-color: rgba(60, 60, 60, 200);
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #555;
                margin: 4px 8px;
            }}
            QMenu::right-arrow {{
                width: 0px;
                height: 0px;
                image: none;
            }}
            QMenu::indicator {{
                width: 0px;
                height: 0px;
                image: none;
            }}
        """
        
        # 递归设置所有菜单的方向和样式
        menus = [self.window_menu]
        while menus:
            m = menus.pop(0)
            m.setLayoutDirection(layout_dir)
            m.setStyleSheet(menu_style)
            for action in m.actions():
                if action.menu():
                    menus.append(action.menu())

    def _show_window_menu_old(self):
        """显示窗口菜单，实现右边缘对齐"""
        # 核心：必须先获取 sizeHint，因为 exec() 之前 width() 可能还是旧值
        self.window_menu.ensurePolished()
        self.window_menu.adjustSize()
        menu_w = self.window_menu.sizeHint().width()
        
        # 获取按钮右边缘的全局 X 坐标
        btn_topleft = self.top_menu_btn.mapToGlobal(QPoint(0, 0))
        btn_right_x = btn_topleft.x() + self.top_menu_btn.width()
        btn_bottom_y = btn_topleft.y() + self.top_menu_btn.height()
        
        direction = getattr(self, "_menu_direction", "left")
        
        if direction == "left":
            # 强制右边缘对齐：菜单左 X = 按钮右 X - 菜单宽度
            target_x = btn_right_x - menu_w
            self.window_menu.exec(QPoint(target_x, btn_bottom_y))
        else:
            # 向右展开：左边缘对齐 (默认行为)
            self.window_menu.exec(QPoint(btn_topleft.x(), btn_bottom_y))

    def _set_menu_direction(self, direction: str):
        """设置菜单展开方向"""
        self._menu_direction = direction
        layout_dir = Qt.LayoutDirection.RightToLeft if direction == "left" else Qt.LayoutDirection.LeftToRight
        
        # 根据方向更新菜单样式（统一左侧高亮条）
        item_align = "right" if direction == "left" else "left"
        menu_style = f"""
            QMenu {{
                background-color: rgba(40, 40, 40, 240);
                color: white;
                font-family: \"Source Han Serif SC\", \"思源宋体\", serif;
                font-size: 13px;
                border: 1px solid rgba(255, 255, 255, 30);
            }}
            QMenu::item {{
                padding: 6px 16px 6px 16px;
                border-radius: 4px;
                text-align: {item_align};
                border-left: 2px solid transparent; /* 始终占用空间，防止选中时宽度抖动 */
            }}
            QMenu::item:checked {{
                background-color: rgba(201, 166, 74, 45);
                border-left: 2px solid #c9a64a;
            }}
            QMenu::item:selected {{
                background-color: rgba(60, 60, 60, 200);
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #555;
                margin: 4px 8px;
            }}
            QMenu::right-arrow {{
                width: 0px;
                height: 0px;
                image: none;
            }}
            QMenu::indicator {{
                width: 0px;
                height: 0px;
                image: none;
            }}
        """
        
        # 递归设置所有菜单的方向和样式
        menus = [self.window_menu]
        while menus:
            m = menus.pop(0)
            m.setLayoutDirection(layout_dir)
            m.setStyleSheet(menu_style)
            for action in m.actions():
                if action.menu():
                    menus.append(action.menu())
        self.signals.log.emit(f"[UI] 菜单方向设置为: {direction}")
        self._persist_window_position()

    def _adjust_font_size_direct(self, value: int):
        """直接通过 SpinBox 调节字号"""
        self.current_font_size = value
        self._apply_font_settings()
        self.signals.log.emit(f"[UI] 字号设置为: {value}pt")
        self._persist_window_position()

    def _adjust_letter_spacing_direct(self, value: float):
        """直接调节字距"""
        self.current_letter_spacing = value
        self._apply_font_settings()
        self.signals.log.emit(f"[UI] 字距设置为: {value}px")
        self._persist_window_position()

    def _adjust_line_spacing_direct(self, value: float):
        """直接调节行距"""
        self.current_line_spacing = value
        self._apply_font_settings()
        self.signals.log.emit(f"[UI] 行距设置为: {value:.1f}x")
        self._persist_window_position()

    def _adjust_font_size(self, delta: int):
        """调整字体大小，并更新菜单标签"""
        self.current_font_size = max(8, min(72, self.current_font_size + delta))
        if hasattr(self, 'font_size_label_action'):
            self.font_size_label_action.setText(f"{self.current_font_size}pt")
        self._apply_font_settings()


    def _on_size_click(self):
        """当点击字号数值时，弹出输入框"""
        from ludiglot.ui.dialogs import StyledInputDialog
        val, ok = StyledInputDialog.get_int(self, "Font Size", "Enter Size (8-72):", 
                                          self.current_font_size, 8, 72)
        if ok:
            self.current_font_size = val
            self._apply_font_settings()
            if hasattr(self, 'font_size_label_action'):
                self.font_size_label_action.setText(f"{val}pt")

    def _on_spacing_click(self):
        """点击字距数值直接输入"""
        from ludiglot.ui.dialogs import StyledInputDialog
        val, ok = StyledInputDialog.get_double(self, "Letter Spacing", "Enter (px):", 
                                             self.current_letter_spacing, -10, 50, 1)
        if ok:
            self.current_letter_spacing = val
            self._apply_font_settings()
            if hasattr(self, 'letter_spacing_label'):
                self.letter_spacing_label.setText(f"{val}px")

    def _on_line_spacing_click(self):
        """点击行距数值直接输入"""
        from ludiglot.ui.dialogs import StyledInputDialog
        val, ok = StyledInputDialog.get_double(self, "Line Spacing", "Enter (x):", 
                                             self.current_line_spacing, 0.5, 5.0, 1)
        if ok:
            self.current_line_spacing = val
            self._apply_font_settings()
            if hasattr(self, 'line_spacing_label'):
                self.line_spacing_label.setText(f"{val:.1f}x")

    def _update_button_positions(self):
        """更新按钮位置"""
        if hasattr(self, 'control_bar'):
            self.control_bar.setGeometry(0, 5, self.width(), 30)

    def _get_available_fonts(self) -> list[str]:
        """获取系统和data/fonts目录下的可用字体"""
        from PyQt6.QtGui import QFontDatabase
        
        fonts = []
        
        # 添加常用字体（系统自带）
        default_fonts = [
            "Source Han Serif SC, 思源宋体, serif",
            "Microsoft YaHei, 微软雅黑, sans-serif",
            "SimSun, 宋体, serif",
            "SimHei, 黑体, sans-serif",
            "KaiTi, 楷体, serif",
            "Arial, sans-serif",
            "Times New Roman, serif",
            "Courier New, monospace",
        ]
        fonts.extend(default_fonts)
        
        # 扫描 Fonts 目录
        font_dir = self.config.fonts_root
        if font_dir.exists():
            for font_file in font_dir.glob("*.[tT][tT][fF]"):
                try:
                    font_id = QFontDatabase.addApplicationFont(str(font_file))
                    if font_id != -1:
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        for family in families:
                            fonts.append(family)
                            self.signals.log.emit(f"[FONT] Loaded: {family} from {font_file.name}")
                except Exception as e:
                    self.signals.log.emit(f"[FONT] Failed to load {font_file.name}: {e}")
            
            for font_file in font_dir.glob("*.[oO][tT][fF]"):
                try:
                    font_id = QFontDatabase.addApplicationFont(str(font_file))
                    if font_id != -1:
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        for family in families:
                            fonts.append(family)
                            self.signals.log.emit(f"[FONT] Loaded: {family} from {font_file.name}")
                except Exception as e:
                    self.signals.log.emit(f"[FONT] Failed to load {font_file.name}: {e}")
        
        return fonts

    def _setup_font_selection_menu(self, menu: QMenu, lang: str) -> None:
        """设置字体选择菜单"""
        fonts = self._get_available_fonts()
        current_font = self.current_font_en if lang == "en" else self.current_font_cn
        
        font_group = QActionGroup(self)
        font_group.setExclusive(True)
        
        for font in fonts:
            action = QAction(font, self)
            action.setCheckable(True)
            action.setChecked(font == current_font)
            action.setProperty("persistent", True)
            action.triggered.connect(lambda checked, f=font, l=lang: self._change_font(f, l))
            font_group.addAction(action)
            menu.addAction(action)

    def _change_font(self, font: str, lang: str) -> None:
        """切换字体"""
        if lang == "en":
            self.current_font_en = font
            self.signals.log.emit(f"[UI] English font: {font}")
        else:
            self.current_font_cn = font
            self.signals.log.emit(f"[UI] Chinese font: {font}")
        
        self._apply_font_settings()
        self._persist_window_position()

    def _font_weight_css(self) -> str:
        weight_map = {
            "Light": "300",
            "Normal": "400",
            "SemiBold": "600",
            "Bold": "700",
            "Heavy": "900",
        }
        return weight_map.get(self.current_font_weight, "600")
    
    def _apply_font_settings(self):
        """应用字体设置到所有UI元素"""
        from PyQt6.QtGui import QFont, QTextCursor
        
        # 内容字体（原文和翻译）
        en_font = QFont()
        en_font.setFamily(self.current_font_en)
        # 确保字号合法（避免Qt警告）- 处理所有边界情况
        try:
            size_val = int(self.current_font_size) if self.current_font_size else 13
        except (ValueError, TypeError):
            size_val = 13
        valid_size = max(8, min(72, size_val))
        en_font.setPointSize(valid_size)
        
        # 设置字重
        weight_map = {
            "Light": QFont.Weight.Light,
            "Normal": QFont.Weight.Normal,
            "SemiBold": QFont.Weight.DemiBold,
            "Bold": QFont.Weight.Bold,
            "Heavy": QFont.Weight.Black
        }
        en_font.setWeight(weight_map.get(self.current_font_weight, QFont.Weight.DemiBold))
        
        # 设置字距
        en_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.current_letter_spacing)
        
        # 中文字体
        cn_font = QFont()
        cn_font.setFamily(self.current_font_cn)
        cn_font.setPointSize(valid_size)
        cn_font.setWeight(weight_map.get(self.current_font_weight, QFont.Weight.DemiBold))
        cn_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.current_letter_spacing)
        
        # 应用到标签
        self.source_label.setFont(en_font)
        self.cn_label.setFont(cn_font)
        
        # 设置行距（通过CSS）
        line_height_percent = int(self.current_line_spacing * 100)
        text_edit_style = f"""
            QTextEdit {{
                line-height: {line_height_percent}%;
            }}
        """
        self.source_label.setStyleSheet(text_edit_style)
        self.cn_label.setStyleSheet(text_edit_style)

        # 重新渲染富文本以应用字号/字重/行距
        self._refresh_text_display()
        
        self.signals.log.emit(f"[UI] 字体设置：{self.current_font_size}pt, {self.current_font_weight}, 字距{self.current_letter_spacing}px, 行距{self.current_line_spacing:.1f}x")

    def _refresh_text_display(self) -> None:
        if self._last_en_raw is not None:
            if self._last_en_is_html:
                self.source_label.setHtml(self._convert_game_html(self._last_en_raw, lang="en"))
            else:
                self.source_label.setPlainText(self._last_en_raw)
        if self._last_cn_raw is not None:
            if self._last_cn_is_html:
                self.cn_label.setHtml(self._convert_game_html(self._last_cn_raw, lang="cn"))
            else:
                self.cn_label.setPlainText(self._last_cn_raw)
    
    def _sync_menu_states(self):
        """显示菜单前强制同步状态并清除焦点"""
        # 同步字重勾选状态
        for action in self.window_menu.findChildren(QAction):
            if action.text() in ["Light", "Normal", "SemiBold", "Bold", "Heavy"]:
                action.setChecked(action.text() == self.current_font_weight)
        
        # 强制清除输入框焦点（防止游标再次出现）
        if hasattr(self, 'size_spin'): self.size_spin.lineEdit().clearFocus()
        if hasattr(self, 'spacing_spin'): self.spacing_spin.lineEdit().clearFocus()
        if hasattr(self, 'lh_spin'): self.lh_spin.lineEdit().clearFocus()

    def _adjust_font_weight(self, weight: str):
        """调整字体粗细"""
        self.current_font_weight = weight
        # 更新菜单项的勾选状态
        for action in self.window_menu.findChildren(QAction):
            if action.text() in ["Light", "Normal", "SemiBold", "Bold", "Heavy"]:
                action.setChecked(action.text() == weight)
        self._apply_font_settings()
        self._persist_window_position()
    
    def _adjust_letter_spacing(self, delta: float):
        """调整字距"""
        self.current_letter_spacing = max(-2, min(10, self.current_letter_spacing + delta))
        self._apply_font_settings()
        if hasattr(self, 'letter_spacing_label'):
            self.letter_spacing_label.setText(f"{self.current_letter_spacing}px")
    
    def _adjust_line_spacing(self, delta: float):
        """调整行距"""
        self.current_line_spacing = max(0.8, min(3.0, self.current_line_spacing + delta))
        self._apply_font_settings()
        if hasattr(self, 'line_spacing_label'):
            self.line_spacing_label.setText(f"{self.current_line_spacing:.1f}x")

    def _adjust_font_size(self, delta: int) -> None:
        """调整字体大小
        
        Args:
            delta: 增量（+1 或 -1）
        """
        self.current_font_size = max(8, min(24, self.current_font_size + delta))
        
        # 应用字体设置
        self._apply_font_settings()
        
        # 更新菜单显示
        if hasattr(self, 'font_size_label_action'):
            self.font_size_label_action.setText(f"{self.current_font_size}pt")
        
        self.signals.log.emit(f"[UI] 字体大小调整为 {self.current_font_size}pt")
    
    def _update_database(self) -> None:
        """更新数据库：拉取 WutheringData 并重建"""
        from ludiglot.ui.dialogs import StyledDialog, StyledProgressDialog
        from ludiglot.ui.db_updater import DatabaseUpdateThread
        
        # 检查data_root配置
        if not self.config.data_root:
            StyledDialog.warning(
                self,
                "配置错误",
                "未设置 data_root 路径。\n请在 config/settings.json 中配置 WutheringData 路径。"
            )
            return
        
        # 确认对话框
        reply = StyledDialog.question(
            self,
            "更新数据库",
            f"即将从 GitHub 拉取 WutheringData 并重建数据库。\n\n"
            f"数据路径: {self.config.data_root}\n"
            f"输出文件: {self.config.db_path}\n\n"
            f"此操作可能需要几分钟。是否继续？"
        )
        
        from PyQt6.QtWidgets import QDialog
        if reply != QDialog.DialogCode.Accepted:
            return
        
        # 创建进度对话框
        progress = StyledProgressDialog("Database Update", "正在更新数据库...", self)
        progress.show()
        
        # 启动更新线程
        self.update_thread = DatabaseUpdateThread(self._config_path, self.config.db_path)
        
        def on_progress(msg: str):
            progress.setLabelText(msg)
            self.signals.log.emit(f"[DB UPDATE] {msg}")
        
        def on_finished(success: bool, message: str):
            progress.close()
            if success:
                # 重新加载数据库
                try:
                    self.db = json.loads(self.config.db_path.read_text(encoding="utf-8"))
                    StyledDialog.information(self, "成功", message)
                    self.signals.log.emit(f"[DB UPDATE] 成功：{message}")
                except Exception as e:
                    StyledDialog.warning(self, "警告", f"数据库更新成功，但重新加载失败：{e}")
            else:
                StyledDialog.critical(self, "失败", f"数据库更新失败：\n{message}")
                self.signals.log.emit(f"[DB UPDATE] 失败：{message}")
        
        self.update_thread.progress.connect(on_progress)
        self.update_thread.finished.connect(on_finished)
        self.update_thread.start()

    def _load_style(self) -> None:
        style_path = Path(__file__).parent / "style.qss"
        if style_path.exists():
            self.setStyleSheet(style_path.read_text(encoding="utf-8"))

    def _connect_signals(self) -> None:
        self.signals.status.connect(self.status_label.setText)
        self.signals.error.connect(self._show_error)
        self.signals.result.connect(self._show_result)
        self.signals.log.connect(self._append_log)

    def _initialize_resources(self) -> None:
        try:
            # 只有在设置了自动重建且路径有效，或者 DB 不存在时才构建
            should_rebuild = self.config.auto_rebuild_db or not self.config.db_path.exists()
            
            if should_rebuild:
                # 如果要构建但没有源数据路径，则尝试报错
                if not (self.config.data_root or (self.config.en_json and self.config.zh_json)):
                    if not self.config.db_path.exists():
                        raise FileNotFoundError("找不到数据库文件，且没有指定源数据路径 (data_root) 来生成它。")
                    else:
                        should_rebuild = False # 无法重建就跳过

            if should_rebuild:
                self.signals.status.emit("构建文本数据库…")
                if self.config.data_root and self.config.data_root.exists():
                    db = build_text_db_from_root_all(self.config.data_root)
                elif self.config.en_json and Path(self.config.en_json).exists():
                    db = build_text_db(Path(self.config.en_json), Path(self.config.zh_json))
                else:
                    # 最后的兜底：如果本该重建但没数据，且 DB 已经存在，就降级使用现有 DB
                    if self.config.db_path.exists():
                        self.signals.log.emit("[DB] 缺少源数据，跳过重建，使用现有数据库")
                        should_rebuild = False
                    else:
                        raise FileNotFoundError("找不到数据库文件，且没有有效的源数据路径来生成它。")

            if should_rebuild:
                save_text_db(db, self.config.db_path)
            
            if self.config.db_path.exists():
                with open(self.config.db_path, "r", encoding="utf-8") as f:
                    self.db = json.load(f)
            else:
                self.db = {}
        except Exception as exc:
            self.signals.error.emit(f"DB 初始化失败: {exc}")
            return

        if self.config.data_root:
            try:
                cache_path = Path(__file__).resolve().parents[3] / "cache" / "voice_map.json"
                self.voice_map = build_voice_map_from_configdb(self.config.data_root, cache_path=cache_path)
                if self.voice_map:
                    self.signals.log.emit(f"[VOICE] 映射加载: {len(self.voice_map)} 项")
            except Exception as exc:
                self.signals.log.emit(f"[VOICE] 映射加载失败: {exc}")

        try:
            self._build_voice_event_index()
        except Exception as exc:
            self.signals.log.emit(f"[VOICE] 事件索引加载失败: {exc}")

        try:
            self.signals.status.emit("预加载 OCR 模型…")
            self.engine.initialize()
            self.signals.log.emit("[OCR] 模型已预加载")
        except Exception as exc:
            self.signals.log.emit(f"[OCR] 预加载失败: {exc}")

        if self.config.audio_cache_path and self.config.scan_audio_on_start:
            try:
                self.signals.status.emit("扫描音频缓存…")
                self.audio_index = AudioCacheIndex(
                    self.config.audio_cache_path,
                    index_path=self.config.audio_cache_index_path,
                    max_mb=self.config.audio_cache_max_mb,
                )
                self.audio_index.load()
                self.audio_index.scan()
                self.signals.log.emit(f"[AUDIO] 缓存条目: {len(self.audio_index.entries)}")
            except Exception as exc:
                self.signals.error.emit(f"音频缓存扫描失败: {exc}")

        self._external_wem_root = self._resolve_external_wem_root()

        self._init_matcher()

        self.signals.status.emit("就绪")
        self.resources_loaded.emit()

    def _resolve_external_wem_root(self) -> Path | None:
        if not self.config.audio_wem_root:
            return None
        try:
            base = self.config.audio_wem_root.parents[1]  # Media/zh -> WwiseAudio_Generated
            candidate = base / "WwiseExternalSource"
            if candidate.exists():
                return candidate
            candidate = base / "WwiseExternalSource" / "zh"
            if candidate.exists():
                return candidate
        except Exception:
            return None
        return None

    def _collect_voice_event_names(self) -> list[str]:
        events: list[str] = []
        if self.config.data_root:
            try:
                plot_audio = load_plot_audio_map(self.config.data_root)
                events.extend([str(v) for v in plot_audio.values() if v])
            except Exception:
                pass
        for items in self.voice_map.values():
            if isinstance(items, list):
                events.extend([str(v) for v in items if v])
        dedup: list[str] = []
        seen = set()
        for ev in events:
            if ev in seen:
                continue
            seen.add(ev)
            dedup.append(ev)
        return dedup

    def _build_voice_event_index(self) -> None:
        if not self.config.audio_bnk_root and not self.config.audio_txtp_cache:
            return
        cache_path = None
        if self.config.audio_cache_path:
            cache_path = self.config.audio_cache_path / "voice_event_index.json"
        extra_names = self._collect_voice_event_names()
        index = VoiceEventIndex(
            bnk_root=self.config.audio_bnk_root,
            txtp_root=self.config.audio_txtp_cache,
            cache_path=cache_path,
            extra_names=extra_names,
        )
        index.load_or_build()
        self.voice_event_index = index
        if index.names:
            self.signals.log.emit(f"[VOICE] 事件索引: {len(index.names)} 项")

    def _init_matcher(self) -> None:
        if self.db:
            from ludiglot.core.matcher import TextMatcher
            from ludiglot.core.audio_resolver import AudioResolver

            self.matcher = TextMatcher(self.db, self.voice_map, self.voice_event_index)
            self.matcher.set_logger(self.signals.log.emit)
            self.signals.log.emit("[MATCHER] 匹配服务已初始化")

            self.audio_resolver = AudioResolver(self.config, self.voice_event_index)
            self.signals.log.emit("[AUDIO] 解析服务已初始化")

    def _should_rebuild_db(self) -> bool:
        if not self.config.auto_rebuild_db:
            return not self.config.db_path.exists()
        if not self.config.db_path.exists():
            return True
        try:
            db_mtime = self.config.db_path.stat().st_mtime
            if self.config.data_root:
                textmap_root = self.config.data_root / "TextMap"
                if textmap_root.exists():
                    latest = max((p.stat().st_mtime for p in textmap_root.rglob("*.json")), default=db_mtime)
                    if latest > db_mtime:
                        return True
            if self.config.en_json.exists() and self.config.en_json.stat().st_mtime > db_mtime:
                return True
            if self.config.zh_json.exists() and self.config.zh_json.stat().st_mtime > db_mtime:
                return True
        except Exception:
            pass
        try:
            raw = json.loads(self.config.db_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return True
            if len(raw) < self.config.min_db_entries:
                return True
            # demo 数据库识别
            for value in raw.values():
                matches = value.get("matches") if isinstance(value, dict) else None
                if matches and matches[0].get("source_json") == "demo.json":
                    return True
                break
        except Exception:
            return True
        return False

    def _start_hotkeys(self) -> None:
        if not self.config.hotkey_capture:
            return
        if self._register_windows_hotkeys():
            msg = f"[HOTKEY] 已注册(WinAPI): {self.config.hotkey_capture}"
            if self.config.hotkey_toggle:
                msg += f" / {self.config.hotkey_toggle}"
            self.signals.log.emit(msg)
            return
        try:
            from pynput import keyboard
        except Exception as exc:
            self.signals.error.emit(f"全局热键不可用: {exc}")
            return

        hotkey = self._convert_hotkey(self.config.hotkey_capture)
        bindings = {hotkey: lambda: self.capture_requested.emit(True)}
        if self.config.hotkey_toggle:
            toggle_hotkey = self._convert_hotkey(self.config.hotkey_toggle)
            bindings[toggle_hotkey] = self._toggle_visibility

        self._hotkey_listener = keyboard.GlobalHotKeys(bindings)
        threading.Thread(target=self._hotkey_listener.run, daemon=True).start()
        
        msg = f"[HOTKEY] 已注册: {self.config.hotkey_capture}"
        if self.config.hotkey_toggle:
            msg += f" / {self.config.hotkey_toggle}"
        self.signals.log.emit(msg)

    def _register_windows_hotkeys(self) -> bool:
        try:
            import ctypes
            import ctypes.wintypes
        except Exception:
            return False
        hotkey = self._parse_win_hotkey(self.config.hotkey_capture)
        if hotkey is None:
            return False
        hotkeys: list[tuple[int, int, int]] = [(1, hotkey[0], hotkey[1])]
        if self.config.hotkey_toggle:
            toggle = self._parse_win_hotkey(self.config.hotkey_toggle)
            if toggle is not None:
                hotkeys.append((2, toggle[0], toggle[1]))
        user32 = ctypes.windll.user32
        registered: list[int] = []
        for hotkey_id, modifiers, vk in hotkeys:
            if user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
                registered.append(hotkey_id)
        if not registered:
            return False

        class _WinHotkeyFilter(QAbstractNativeEventFilter):
            def __init__(self, callback_map: dict[int, Any]):
                super().__init__()
                self._callback_map = callback_map

            def nativeEventFilter(self, eventType, message):
                if eventType != "windows_generic_MSG":
                    return False, 0
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312:
                    hotkey_id = int(msg.wParam)
                    callback = self._callback_map.get(hotkey_id)
                    if callback:
                        callback()
                        return True, 1
                return False, 0

        callback_map = {1: lambda: self.capture_requested.emit(True)}
        if self.config.hotkey_toggle:
            callback_map[2] = self._toggle_visibility
        self._win_hotkey_filter = _WinHotkeyFilter(callback_map)
        app = QApplication.instance()
        if app:
            app.installNativeEventFilter(self._win_hotkey_filter)
        self._win_hotkey_ids = registered
        return True

    def _parse_win_hotkey(self, hotkey: str) -> tuple[int, int] | None:
        parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
        if not parts:
            return None
        modifiers = 0
        vk = None
        for part in parts:
            if part in {"ctrl", "control"}:
                modifiers |= 0x0002
            elif part == "alt":
                modifiers |= 0x0001
            elif part == "shift":
                modifiers |= 0x0004
            elif part in {"win", "cmd"}:
                modifiers |= 0x0008
            else:
                if len(part) == 1:
                    vk = ord(part.upper())
        if vk is None:
            return None
        return modifiers, vk

    def _convert_hotkey(self, hotkey: str) -> str:
        key = hotkey.lower().replace("ctrl", "<ctrl>").replace("shift", "<shift>")
        key = key.replace("alt", "<alt>").replace("win", "<cmd>")
        return key

    def _toggle_visibility(self) -> None:
        """切换窗口显示/隐藏状态，使用isHidden()避免状态不同步问题。"""
        if self.isHidden():
            self.show_and_activate()
        else:
            self.hide()
    
    def _toggle_audio_playback(self) -> None:
        """切换音频播放/暂停。"""
        if self.player.is_playing():
            self.player.pause()
            if self._icon_play:
                self.play_pause_btn.setIcon(self._icon_play)
            self.audio_timer.stop()
        else:
            self.player.resume()
            if self._icon_pause:
                self.play_pause_btn.setIcon(self._icon_pause)
            self.audio_timer.start()
    
    def _on_slider_pressed(self) -> None:
        """滑动条按下时暂停播放，避免跳动。"""
        if hasattr(self, '_slider_was_playing'):
            return
        self._slider_was_playing = self.player.is_playing()
        if self._slider_was_playing:
            self.player.pause()
            self.audio_timer.stop()
    
    def _on_slider_released(self) -> None:
        """滑动条释放时跳转到新位置并恢复播放。"""
        position = self.audio_slider.value() / 100.0
        self.player.seek(position)
        if hasattr(self, '_slider_was_playing') and self._slider_was_playing:
            self.player.resume()
            if self._icon_pause:
                self.play_pause_btn.setIcon(self._icon_pause)
            self.audio_timer.start()
            del self._slider_was_playing
    
    def _update_audio_progress(self) -> None:
        """定时更新音频进度条和时间标签。"""
        if not self.player.is_playing():
            self.audio_timer.stop()
            return
        
        position = self.player.get_position()
        duration = self.player.get_duration()
        
        # 更新进度条（但不在拖动时更新）
        if not self.audio_slider.isSliderDown():
            self.audio_slider.setValue(int(position * 100))
        
        # 更新时间标签
        if duration > 0:
            current_ms = int(position * duration)
            current_sec = current_ms // 1000
            duration_sec = duration // 1000
            self.time_label.setText(f"{current_sec//60:02d}:{current_sec%60:02d} / {duration_sec//60:02d}:{duration_sec%60:02d}")

    def _translate_title(self, title: str) -> str:
        """尝试将标题（如角色名、招式名）翻译为中文。"""
        if not self.matcher:
            return ""
        try:
            cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in title).strip()
            key = normalize_en(cleaned)
            if not key:
                return ""
            result, score = self.matcher.search_key(key)
            if isinstance(result, dict):
                # 1. 尝试直接获取
                cn = result.get("official_cn") or result.get("cn")
                # 2. 尝试从 matches 列表中获取
                if not cn:
                    matches = result.get("matches", [])
                    if matches:
                        cn = matches[0].get("official_cn") or matches[0].get("cn")
                
                if cn and score >= 0.7:
                    return str(cn)
        except Exception:
            pass
        return ""

    def _on_mode_changed(self, mode: str) -> None:
        self.engine.set_mode(mode)
        self.config.ocr_mode = mode
        self.signals.status.emit(f"OCR 模式: {mode}")
        self._persist_window_position()

    def _on_backend_changed(self, backend: str) -> None:
        self.config.ocr_backend = backend
        self.signals.status.emit(f"OCR 后端: {backend}")
        self._persist_window_position()

    def trigger_capture(self) -> None:
        self.stop_audio()
        self.capture_requested.emit(True)

    def _capture_and_process_async(self, force_select: bool = False) -> None:
        selected_region: CaptureRegion | None = None
        self.signals.log.emit("[HOTKEY] 触发捕获")
        if force_select or self.config.capture_mode == "select":
            self.signals.status.emit("请选择 OCR 区域…")
            selected_region = self._select_region()
            if selected_region is None:
                self.signals.status.emit("已取消")
                return
        threading.Thread(
            target=self._capture_and_process,
            args=(selected_region,),
            daemon=True,
        ).start()

    def _capture_and_process(self, selected_region: CaptureRegion | None) -> None:
        self.signals.status.emit("捕获中…")
        try:
            self._capture_image(selected_region)
        except Exception as exc:
            self.signals.error.emit(f"截图失败: {exc}")
            return

        # 过小截图会触发 OCR 底层异常，直接跳过并提示
        try:
            from PIL import Image

            img = Image.open(self.config.image_path)
            if img.width < 8 or img.height < 8:
                self.signals.log.emit(
                    f"[CAPTURE] 选区过小({img.width}x{img.height})，已跳过"
                )
                self.signals.status.emit("选区过小，已取消")
                return
        except Exception:
            pass

        try:
            image_path = self._preprocess_image(self.config.image_path)
            if self.config.ocr_backend == "windows":
                box_lines = self.engine.recognize_with_boxes(image_path)
            elif self.config.ocr_backend == "tesseract":
                tess_path = getattr(self, "_tesseract_image_path", image_path)
                box_lines = self.engine.recognize_with_boxes(tess_path, prefer_tesseract=True)
            else:
                box_lines = self.engine.recognize_with_boxes(image_path)
            backend = getattr(self.engine, "last_backend", None) or "paddle"
            backend_label = {
                "windows": "WindowsOCR",
                "tesseract": "Tesseract",
                "paddle": "PaddleOCR",
            }.get(backend, backend)
            self.signals.log.emit(f"[OCR] 后端: {backend_label}")
        except Exception as exc:
            self.signals.error.emit(f"OCR 失败: {exc}")
            return

        if not box_lines:
            self.signals.status.emit("OCR 未识别到文本")
            self.signals.log.emit("[OCR] 未识别到文本")
            return

        lines = group_ocr_lines(box_lines)
        if self.config.ocr_backend == "auto" and self._needs_tesseract(lines):
            self.signals.log.emit("[OCR] 质量较差，切换 Tesseract")
            tess_path = getattr(self, "_tesseract_image_path", image_path)
            box_lines = self.engine.recognize_with_boxes(tess_path, prefer_tesseract=True)
            lines = group_ocr_lines(box_lines)

        self.signals.log.emit("[OCR] 识别结果:")
        for text, conf in lines:
            self.signals.log.emit(f"  - {text} (conf={conf:.3f})")

        if not self.matcher:
             self.signals.error.emit("匹配服务未就绪")
             return

        result = self.matcher.match(lines)
        if result is None:
            self.signals.status.emit("未提取到可用文本")
            self.signals.log.emit("[OCR] 归一化后为空，跳过")
            return
        
        print(f"[DEBUG] _capture_and_process: Got result. Keys: {list(result.keys())}", flush=True)
        
        # Deepcopy to ensure thread safety and detach from DB
        try:
             import copy
             safe_result = copy.deepcopy(result)
             print("[DEBUG] _capture_and_process: Emitting safe_result...", flush=True)
             self.signals.result.emit(safe_result)
             print("[DEBUG] _capture_and_process: Result emitted.", flush=True)
        except Exception as e:
             print(f"[ERROR] CRITICAL: Failed to emit result signal: {e}", flush=True)
             self.signals.error.emit(f"Internal Error: Signal Emission Failed: {e}")
             return

        self.signals.status.emit("就绪")
        print("[DEBUG] _capture_and_process: Status emitted. Done.", flush=True)


    def _capture_image(self, selected_region: CaptureRegion | None) -> None:
        try:
            if selected_region is not None:
                # 手动框选时严格使用用户选择区域
                capture_region(selected_region, self.config.image_path)
                return
            if self.config.capture_mode == "window":
                if not self.config.window_title:
                    raise RuntimeError("capture_mode=window 需要 window_title")
                capture_window(self.config.window_title, self.config.image_path)
                return
            if self.config.capture_mode == "region":
                if not self.config.capture_region:
                    raise RuntimeError("capture_mode=region 需要 capture_region")
                region = CaptureRegion(
                    left=int(self.config.capture_region["left"]),
                    top=int(self.config.capture_region["top"]),
                    width=int(self.config.capture_region["width"]),
                    height=int(self.config.capture_region["height"]),
                )
                capture_region(region, self.config.image_path)
                return
            if self.config.capture_mode == "image":
                if self.config.image_path.exists():
                    return
                capture_fullscreen(self.config.image_path)
                return
            if self.config.capture_mode == "select":
                region = self._select_region()
                if region is None:
                    raise RuntimeError("未选择区域")
                capture_region(region, self.config.image_path)
                return
            raise RuntimeError(f"未知 capture_mode: {self.config.capture_mode}")
        except CaptureError:
            capture_fullscreen(self.config.image_path)
        self._validate_capture(self.config.image_path)

    def _expand_region(self, region: CaptureRegion) -> CaptureRegion:
        try:
            import mss
        except Exception:
            return region
        margin_x = 40
        margin_y = 30
        with mss.mss() as sct:
            monitor = sct.monitors[1]
        left = max(monitor["left"], region.left - margin_x)
        top = max(monitor["top"], region.top - margin_y)
        right = min(monitor["left"] + monitor["width"], region.left + region.width + margin_x)
        bottom = min(monitor["top"] + monitor["height"], region.top + region.height + margin_y)
        width = max(right - left, region.width)
        height = max(bottom - top, region.height)
        if width < 600:
            extra = (600 - width) // 2
            left = max(monitor["left"], left - extra)
            right = min(monitor["left"] + monitor["width"], right + extra)
            width = right - left
        if height < 120:
            extra = (120 - height) // 2
            top = max(monitor["top"], top - extra)
            bottom = min(monitor["top"] + monitor["height"], bottom + extra)
            height = bottom - top
        return CaptureRegion(left=int(left), top=int(top), width=int(width), height=int(height))

    def _preprocess_image(self, image_path: Path) -> Path:
        return image_path

    def _validate_capture(self, image_path: Path) -> None:
        try:
            from PIL import Image
        except Exception:
            return
        try:
            if not image_path.exists():
                return
            if image_path.stat().st_size < 20000:
                self.signals.log.emit("[CAPTURE] 图片过小，回退全屏截图")
                capture_fullscreen(image_path)
            img = Image.open(image_path)
            if img.width < 300 or img.height < 60:
                self.signals.log.emit("[CAPTURE] 尺寸异常，回退全屏截图")
                capture_fullscreen(image_path)
        except Exception as exc:
            self.signals.log.emit(f"[CAPTURE] 校验失败: {exc}")


    def _build_candidates(self, lines: list[tuple[str, float]]) -> list[tuple[str, float]]:
        texts = [text.strip() for text, _ in lines if text and text.strip()]
        if not texts:
            return []
        # 丢弃明显低质量行，减少断章取义
        filtered = [(text, conf) for text, conf in lines if conf >= 0.45 or len(text) >= 20]
        if not filtered:
            filtered = lines
        joined = " ".join(text for text, _ in filtered)
        joined_words = [w for w in joined.split() if w]
        joined_len = len(normalize_en(joined))
        high_conf_tokens: list[str] = []
        for text, conf in filtered:
            if conf < 0.6 or not text:
                continue
            cleaned = text.strip()
            if not cleaned:
                continue
            if len(cleaned) == 1 and cleaned.lower() not in {"a", "i"}:
                continue
            high_conf_tokens.append(cleaned)
        joined_high = " ".join(high_conf_tokens) if high_conf_tokens else joined
        best = max(lines, key=lambda item: item[1])
        longest = max(texts, key=len)
        avg_conf = sum(conf for _, conf in lines) / max(len(lines), 1)
        candidates: list[tuple[str, float]] = [
            (joined_high, avg_conf),
            (joined, avg_conf),
        ]
        # 从整段文本生成滑动窗口候选，增强长句匹配
        candidates.extend(self._window_candidates(joined, avg_conf))
        # 仅在置信度足够且非长文本场景时才引入单行候选，避免噪声行支配结果
        if best[1] >= 0.6 and (len(joined_words) < 6 and joined_len < 40):
            candidates.append(best)
        if best[1] >= 0.6 and len(longest) >= 8 and (len(joined_words) < 6 and joined_len < 40):
            candidates.append((longest, best[1]))

        # 单行短文本：拆词与重排，提升“角色名/属性名”命中
        if len(lines) == 1:
            raw = lines[0][0]
            cleaned = self._clean_ocr_line(raw)
            if cleaned:
                tokens = cleaned.split()
                if tokens:
                    # 长文本不拆分单词，避免单词误命中
                    if len(tokens) > 3 or len(cleaned) >= 24:
                        tokens = []
                    # 单词候选
                    for token in tokens:
                        if len(token) >= 3:
                            candidates.append((token, lines[0][1]))
                    # 两词组合
                    if len(tokens) >= 2:
                        pair = f"{tokens[0]} {tokens[1]}"
                        candidates.append((pair, lines[0][1]))
                        candidates.append((f"{tokens[1]} {tokens[0]}", lines[0][1]))
                    # 全部清洗后的文本
                    candidates.append((cleaned, lines[0][1]))
        # 去重
        seen = set()
        unique: list[tuple[str, float]] = []
        for text, conf in candidates:
            if text in seen:
                continue
            seen.add(text)
            unique.append((text, conf))
        return unique

    def _clean_ocr_line(self, text: str) -> str:
        # 去掉图标/分隔符噪声，保留字母数字与空格
        cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
        cleaned = " ".join(cleaned.split())
        return cleaned.strip()

    def _is_list_mode(self, lines: list[tuple[str, float]]) -> bool:
        if len(lines) < 4:
            return False
        cleaned = [self._clean_ocr_line(text) for text, _ in lines if text]
        cleaned = [c for c in cleaned if c]
        # 忽略明显非列表项的长行/数字行
        filtered = []
        for c in cleaned:
            if not c:
                continue
            if len(c.split()) > 3 or len(c) > 20:
                continue
            digit_ratio = sum(ch.isdigit() for ch in c) / max(len(c), 1)
            if digit_ratio > 0.4:
                continue
            filtered.append(c)
        if len(filtered) < 3:
            return False
        lengths = [len(c) for c in filtered]
        max_len = max(lengths)
        avg_words = sum(len(c.split()) for c in filtered) / max(len(filtered), 1)
        return max_len <= 16 and avg_words <= 2.2

    def _has_voice_match(self, result: dict) -> bool:
        """检查匹配结果是否有对应的语音文件。"""
        if not isinstance(result, dict):
            return False
        matches = result.get('matches', [])
        if not matches:
            return False
        text_key = matches[0].get('text_key', '')
        if not text_key:
            return False
        # 检查语音映射或缓存
        event_name = f"vo_{text_key}"
        if self.voice_map and event_name in self.voice_map:
            return True
        if self.voice_event_index:
            events = self.voice_event_index.find_candidates(text_key=text_key, voice_event=event_name, limit=1)
            if events:
                return True
        return False
    
    def _result_has_voice(self, result: dict) -> bool:
        """_has_voice_match 的别名，保持兼容性"""
        return self._has_voice_match(result)

    def _stat_alias_map(self) -> dict[str, str]:
        return {
            "hp": "mainhp",
            "atk": "mainatk",
            "def": "maindef",
            "energyregen": "mainenergyregen",
            "critrate": "maincritrate",
            "critdmg": "maincritdmg",
            "critdamage": "maincritdmg",
            "critdmgbonus": "maincritdmg",
        }

    def _needs_tesseract(self, lines: list[tuple[str, float]]) -> bool:
        if len(lines) < 3:
            return False
        for text, conf in lines:
            if conf < 0.35 and len(text) >= 15:
                return True
        low_conf = [conf for _, conf in lines if conf < 0.4]
        if low_conf and (len(low_conf) / len(lines)) >= 0.4:
            return True
        avg_conf = sum(conf for _, conf in lines) / max(len(lines), 1)
        if avg_conf < 0.7:
            return True
        # 文本质量检测：字母/空格比例过低
        joined = " ".join(text for text, _ in lines)
        if not joined:
            return False
        alpha = sum(ch.isalpha() or ch.isspace() for ch in joined)
        ratio = alpha / max(len(joined), 1)
        return ratio < 0.65

    def _lookup_best(self, lines: list[tuple[str, float]]) -> Dict[str, Any] | None:
        """智能匹配算法：支持混合单行标题和多行长文本的场景。
        
        策略：
        1. 检测每行是否为短标题（单行单条目）
        2. 检测是否为长文本（多行描述）
        3. 如果混合：分段匹配，第一行返回标题，后续行返回长文本
        4. 优先返回有语音的条目
        """
        best_result: Dict[str, Any] | None = None
        best_score = -1.0
        best_text = ""
        best_conf = 0.0

        context_text = " ".join(self._clean_ocr_line(text) for text, _ in lines if text)
        context_words = [w for w in context_text.split() if w]
        context_len = len(normalize_en(context_text))

        # 先评估每一行的匹配置信度和特征
        alias_map = self._stat_alias_map()
        line_info: list[dict] = []
        for idx, (text, conf) in enumerate(lines):
            cleaned = self._clean_ocr_line(text)
            if not cleaned:
                continue
            key = normalize_en(cleaned)
            if not key:
                continue
            key = alias_map.get(key, key)
            result, score = self._search_db(key)
            
            # 判断行特征
            word_count = len(cleaned.split())
            is_short = word_count <= 3 and len(cleaned) <= 20
            is_title_like = is_short and not any(ch in cleaned for ch in [',', '.', '!', '?'])
            
            line_info.append({
                'idx': idx,
                'text': text,
                'cleaned': cleaned,
                'key': key,
                'conf': conf,
                'score': score,
                'result': result,
                'word_count': word_count,
                'is_short': is_short,
                'is_title_like': is_title_like,
            })
        
        if not line_info:
            return None
        
        # 检测多独立条目：如果有多行且每行都有较好的独立匹配，返回多条目
        multi_items = []
        
        for idx, line in enumerate(line_info):
            cleaned = line['cleaned']
            
            # 检测是否为时间格式（如 "8d 8h", "3h 45m", "2d" 等）
            import re
            time_pattern = r'^\d+[dhms](\s+\d+[dhms])*$'
            is_time_format = bool(re.match(time_pattern, cleaned.lower().strip()))
            
            if is_time_format:
                # 时间数字附加到上一个条目
                if multi_items:
                    multi_items[-1]['time_suffix'] = cleaned
                    self.signals.log.emit(f"[FILTER] 时间格式附加到上一条目: {cleaned}")
                else:
                    self.signals.log.emit(f"[FILTER] 时间格式但无前置条目，跳过: {cleaned}")
                continue
            
            # 跳过纯数字行
            digit_ratio = sum(ch.isdigit() for ch in cleaned) / max(len(cleaned), 1)
            if digit_ratio > 0.8:  # 纯数字
                self.signals.log.emit(f"[FILTER] 跳过纯数字行: {cleaned} (digit_ratio={digit_ratio:.2f})")
                continue
            
            # 检查是否有高质量的独立匹配
            matched_key = line['result'].get('_matched_key', '') if isinstance(line['result'], dict) else ''
            key_len = len(line['key'])
            matched_len = len(matched_key)
            
            # 检测特殊字符污染（如 Bésides, we' e 包含特殊字符）
            import re
            special_char_count = len(re.findall(r'[^\w\s\-]', cleaned))  # 非字母数字空格连字符
            special_char_ratio = special_char_count / max(len(cleaned), 1)
            has_special_pollution = special_char_ratio > 0.15  # 超过15%特殊字符视为污染
            
            # 高质量匹配标准：
            # 1. 分数足够高 (>0.75) 且无特殊字符污染 或
            # 2. 匹配长度相近（50%-200%范围）且分数中等 (>0.55)
            # 3. 长文本（>50字符）且分数>0.60（提高长文本阈值避免误匹配）
            # 4. 短文本（<15字符）需要更高分数 (>0.85) 避免误匹配
            is_high_score = line['score'] >= 0.75 and not has_special_pollution
            is_length_match = matched_len >= key_len * 0.5 and matched_len <= key_len * 2.0
            is_long_text = key_len > 50 and line['score'] >= 0.60  # 长文本也需要较高分数
            is_short_text_strict = key_len < 15 and line['score'] >= 0.85  # 短文本严格要求
            is_good_match = is_high_score or (is_length_match and line['score'] >= 0.55) or is_long_text or is_short_text_strict
            
            if has_special_pollution and line['score'] < 0.85:
                self.signals.log.emit(f"[FILTER] 跳过特殊字符污染: {cleaned} (special_ratio={special_char_ratio:.2f}, score={line['score']:.3f})")
                continue
            
            if is_good_match:
                multi_items.append(line)
                self.signals.log.emit(f"[FILTER] 保留条目: {cleaned} (score={line['score']:.3f}, len={key_len})")
            else:
                self.signals.log.emit(f"[FILTER] 跳过低质量匹配: {cleaned} (score={line['score']:.3f}, matched_len={matched_len}, key_len={key_len})")
        
        # 如果有3+个独立的高质量匹配，返回多条目模式
        if len(multi_items) >= 3:
            self.signals.log.emit(f"[MATCH] 检测到 {len(multi_items)} 个独立条目")
            items = []
            for line in multi_items:
                matches = line['result'].get("matches") if isinstance(line['result'], dict) else None
                match = matches[0] if matches else {}
                
                # 获取官方原文和译文，如果有时间后缀则直接附加
                official_en = match.get("official_en") or ""
                official_cn = match.get("official_cn") or ""
                time_suffix = line.get('time_suffix')
                if time_suffix:
                    # 如果原文末尾是冒号，直接附加时间；否则用空格隔开
                    if official_en:
                        if official_en.rstrip().endswith(':'):
                            official_en = f"{official_en} {time_suffix}"
                        else:
                            official_en = f"{official_en}: {time_suffix}"
                    if official_cn:
                        if official_cn.rstrip().endswith('：'):
                            official_cn = f"{official_cn}{time_suffix}"
                        else:
                            official_cn = f"{official_cn}：{time_suffix}"
                
                items.append({
                    "ocr": line['cleaned'],
                    "query_key": line['key'],
                    "score": round(line['score'], 3),
                    "text_key": match.get("text_key"),
                    "official_en": official_en,
                    "official_cn": official_cn,
                })
            return {
                "_multi": True,
                "items": items,
                # 使用官方原文而非OCR文本或query_key
                "_official_en": " / ".join([i.get("official_en") or i.get("ocr") or "" for i in items if i.get("official_en") or i.get("ocr")]),
                "_official_cn": " / ".join([i.get("official_cn") or "" for i in items if i.get("official_cn")]),
                "_query_key": " / ".join([i["query_key"] for i in items if i.get("query_key")]),
                "_ocr_text": " / ".join([i["ocr"] for i in items if i.get("ocr")]),
            }
        
        # 智能分段：检测混合内容（第一行是标题，后续行是长文本）
        # 只在没有多个独立匹配时使用，避免误判
        if len(line_info) >= 2 and len(multi_items) < 3:
            first_line = line_info[0]
            rest_lines = line_info[1:]
            
            # 如果第一行是短标题且后续行构成长文本
            if first_line['is_title_like']:
                rest_text = " ".join(l['cleaned'] for l in rest_lines)
                rest_key = normalize_en(rest_text)
                rest_result, rest_score = self._search_db(rest_key)
                
                # 如果后续行形成了高分匹配的长文本
                if rest_score >= 0.5 and len(rest_text.split()) >= 5:
                    # 检查是否有语音
                    rest_has_voice = self._has_voice_match(rest_result)
                    first_has_voice = self._has_voice_match(first_line['result'])
                    
                    # 验证匹配质量：长文本应该有足够长度的matched_key
                    matched_key = rest_result.get('_matched_key', '')
                    is_good_match = len(matched_key) >= len(rest_key) * 0.6  # 匹配项应至少是查询的60%长度
                    
                    # 优先返回有语音的内容或高质量长文本匹配
                    should_use_rest = (
                        is_good_match and (
                            len(rest_key) > 100 
                            or rest_has_voice 
                            or (not first_has_voice and rest_score > first_line['score'])
                        )
                    )
                    
                    if should_use_rest:
                        self.signals.log.emit(
                            f"[MATCH] 混合内容：第一行=标题({first_line['cleaned']}), "
                            f"后续行=长文本(score={rest_score:.3f}, matched_len={len(matched_key)}, 有语音={rest_has_voice})"
                        )
                        rest_result['_score'] = round(rest_score, 3)
                        rest_result['_query_key'] = rest_key
                        rest_result['_ocr_text'] = rest_text
                        rest_result['_ocr_conf'] = sum(l['conf'] for l in rest_lines) / len(rest_lines)
                        rest_result['_first_line'] = first_line['cleaned']  # 保留标题信息
                        return rest_result
        
        # 原有逻辑：处理列表模式和其他场景
        line_scores: list[tuple[str, float, dict]] = [
            (l['cleaned'], l['score'], l['result']) for l in line_info
        ]

        # 列表模式：多数行高分时返回多条，避免只命中一行
        if self._is_list_mode(lines) and line_scores:
            short_line_scores = []
            for cleaned, score, result in line_scores:
                if len(cleaned.split()) > 3 or len(cleaned) > 20:
                    continue
                digit_ratio = sum(ch.isdigit() for ch in cleaned) / max(len(cleaned), 1)
                if digit_ratio > 0.4:
                    continue
                short_line_scores.append((cleaned, score, result))
            strong_lines = [(c, s, r) for c, s, r in short_line_scores if s >= 0.9]
            if len(strong_lines) >= 3:
                items = []
                for cleaned, score, result in strong_lines:
                    matches = result.get("matches") if isinstance(result, dict) else None
                    match = matches[0] if matches else {}
                    items.append(
                        {
                            "ocr": cleaned,
                            "query_key": normalize_en(cleaned),
                            "score": round(score, 3),
                            "text_key": match.get("text_key"),
                            "official_cn": match.get("official_cn"),
                        }
                    )
                return {
                    "_multi": True,
                    "items": items,
                    "_query_key": " / ".join([i["query_key"] for i in items if i.get("query_key")]),
                    "_ocr_text": " / ".join([i["ocr"] for i in items if i.get("ocr")]),
                }

        if self._is_list_mode(lines) and line_scores and all(s >= 0.95 for _, s, _ in line_scores):
            items = []
            for cleaned, score, result in line_scores:
                matches = result.get("matches") if isinstance(result, dict) else None
                match = matches[0] if matches else {}
                items.append(
                    {
                        "ocr": cleaned,
                        "query_key": normalize_en(cleaned),
                        "score": round(score, 3),
                        "text_key": match.get("text_key"),
                        "official_cn": match.get("official_cn"),
                    }
                )
            return {
                "_multi": True,
                "items": items,
                "_query_key": " / ".join([i["query_key"] for i in items if i.get("query_key")]),
                "_ocr_text": " / ".join([i["ocr"] for i in items if i.get("ocr")]),
            }

        # 否则优先进行“行拼接”候选（处理标题+描述等混合情况）
        stitched_lines: list[tuple[str, float]] = []
        idx = 0
        while idx < len(lines):
            text, conf = lines[idx]
            cleaned = self._clean_ocr_line(text)
            if not cleaned:
                idx += 1
                continue
            key = normalize_en(cleaned)
            score = 0.0
            if key:
                _, score = self._search_db(alias_map.get(key, key))
            if score >= 0.95:
                stitched_lines.append((cleaned, conf))
                idx += 1
                continue
            # 低置信度行，优先与下一行拼接
            if idx + 1 < len(lines):
                next_clean = self._clean_ocr_line(lines[idx + 1][0])
                if next_clean:
                    stitched_lines.append((f"{cleaned} {next_clean}", (conf + lines[idx + 1][1]) / 2.0))
                    idx += 2
                    continue
            stitched_lines.append((cleaned, conf))
            idx += 1

        smart_result = build_smart_candidates(lines)
        candidates = smart_result.get('candidates', [])
        strategy = smart_result.get('strategy', 'unknown')
        self.signals.log.emit(f"[SEARCH] 智能匹配策略={strategy}, 评估 {len(candidates)} 个候选...")

        import time
        start_time = time.time()

        for text, conf in candidates:
            # 如果已经找到高度匹配的结果，且文本长度适中，提前结束
            if best_score > 0.96 and len(best_text.split()) > 5:
                break

            key = normalize_en(text)
            if not key:
                continue

            # 长文本场景：过滤过短候选，避免命中单词/短语
            # 严格的长度匹配约束：如果OCR文本很长，不应该匹配到很短的数据库条目
            if (context_words and len(context_words) >= 6) or (context_len >= 40):
                # 过滤掉词数太少的候选
                if len(text.split()) <= 3:
                    continue
                # 过滤掉字符长度太短的候选
                if len(key) < 20:
                    continue
            
            result, score = self._search_db(key)
            matched_key = result.get("_matched_key") if isinstance(result, dict) else None
            
            # 基础分逻辑：综合考虑相似度、长度和词数
            word_count = max(len(text.split()), 1)
            length_bonus = min(len(key) / 100.0, 1.0)
            word_bonus = min(word_count / 8.0, 1.0)
            weighted_score = score * (0.6 + 0.2 * length_bonus + 0.2 * word_bonus)

            # 避免长文本误命中短条目 - 改进版
            # 使用绝对长度差和比例相结合的方式判断
            if matched_key:
                key_len = len(key)
                matched_len = len(matched_key)
                length_diff = abs(key_len - matched_len)
                length_ratio = matched_len / max(key_len, 1)  # 匹配条目长度 / 查询长度
                
                # 场景1: 长查询(>25字符) 匹配到 短条目(<20字符) → 严重不匹配
                if key_len > 25 and matched_len < 20:
                    weighted_score *= 0.2  # 严厉惩罚
                    self.signals.log.emit(f"[MATCH] 长查询匹配短条目惩罚: query_len={key_len}, matched_len={matched_len}, ratio={length_ratio:.2f}")
                
                # 场景2: 长度差异过大（>15字符 且 比例<0.6）
                elif length_diff > 15 and length_ratio < 0.6:
                    weighted_score *= 0.4
                    self.signals.log.emit(f"[MATCH] 长度差异惩罚: diff={length_diff}, ratio={length_ratio:.2f}")
                
                # 场景3: 查询长度是匹配的2倍以上
                elif key_len > matched_len * 2:
                    weighted_score *= 0.5
                    self.signals.log.emit(f"[MATCH] 长度比例惩罚: query_len={key_len}, matched_len={matched_len}")
                
                # 场景4: 轻度长度不匹配
                elif key_len > matched_len * 1.5 and score < 0.97:
                    weighted_score *= 0.75
            
            # 新增：优先匹配有语音的条目（对话优先于任务名/角色名）
            matches = result.get("matches") if isinstance(result, dict) else []
            has_audio = False
            if matches:
                first_match = matches[0]
                audio_hash = first_match.get("audio_hash")
                audio_event = first_match.get("audio_event")
                has_audio = bool(audio_hash or audio_event)
            
            # 如果有语音，给予加分（在相似度接近时优先选择有语音的条目）
            if has_audio:
                weighted_score *= 1.15  # 给有语音的条目加15%的权重
                self.signals.log.emit(f"[MATCH] 语音条目加成: has_audio=True, weighted={weighted_score:.3f}")
            
            if weighted_score > best_score:
                best_score = weighted_score
                best_result = result
                best_text = text
                best_conf = conf
                best_result["_score"] = round(score, 3)
                best_result["_query_key"] = key
                best_result["_ocr_text"] = best_text
                best_result["_ocr_conf"] = round(best_conf, 3)
                best_result["_weighted"] = round(weighted_score, 3)
        
        elapsed = time.time() - start_time
        if best_result:
            self.signals.log.emit(f"[SEARCH] 耗时: {elapsed:.2f}s, 最佳匹配: {best_result.get('_query_key')} (score={best_result.get('_score')})")
        else:
            self.signals.log.emit(f"[SEARCH] 耗时: {elapsed:.2f}s, 未找到合适匹配")

        return best_result

    def _window_candidates(self, text: str, conf: float) -> list[tuple[str, float]]:
        words = [w for w in text.split() if w]
        if len(words) < 10:
            return []
        windows: list[tuple[str, float]] = []
        min_len = 8
        max_len = 24
        step = 4
        for start in range(0, max(len(words) - min_len + 1, 1), step):
            for length in (min_len, 12, 16, 20, max_len):
                if start + length > len(words):
                    continue
                segment = " ".join(words[start : start + length])
                windows.append((segment, conf))
            if len(windows) >= 60:
                break
        return windows

    def _search_db(self, key: str) -> tuple[Dict[str, Any], float]:
        # 1. 直接匹配
        if key in self.db:
            result = dict(self.db[key])
            result["_matched_key"] = key
            return result, 1.0

        # 1.5 子串匹配优化：处理标题+描述混合，或截屏不全导致的匹配失败
        if len(key) >= 10:
            # 1.5.1 前缀匹配 (OCR 是库文本的前半部分)
            prefix_hits = [k for k in self.db.keys() if k.startswith(key)]
            if prefix_hits:
                best_prefix = min(prefix_hits, key=len)
                result = dict(self.db.get(best_prefix, {}))
                result["_matched_key"] = best_prefix
                return result, 0.99
            
            # 1.5.2 包含匹配 (OCR 包含了整个库项)
            # 例如 OCR: "The quick brown fox jumps..." 包含了库项 "brown fox"
            # 但要避免长查询匹配到短语：query_len=408, matched="ensemblesylph"(13) ❌
            contain_in_ocr = [k for k in self.db.keys() if len(k) >= 10 and k in key]
            if contain_in_ocr:
                best_k = max(contain_in_ocr, key=len) # 取包含的最具体(最长)项
                # 关键修复：长查询(>100)不允许匹配到短语(<50)
                # 新增：匹配项长度应至少是查询的40%，避免部分词组误匹配
                length_ratio = len(best_k) / len(key)
                if not (len(key) > 100 and len(best_k) < 50) and length_ratio >= 0.4:
                    result = dict(self.db.get(best_k, {}))
                    result["_matched_key"] = best_k
                    self.signals.log.emit(
                        f"[MATCH] 包含匹配：query_len={len(key)}, matched_len={len(best_k)}, ratio={length_ratio:.2f}"
                    )
                    return result, 0.95  # 降低评分以反映不完整匹配
                else:
                    self.signals.log.emit(
                        f"[MATCH] 跳过短语匹配：query_len={len(key)}, matched_len={len(best_k)}, ratio={length_ratio:.2f}"
                    )

            # 1.5.3 被包含匹配 (库文本包含了 OCR 内容 - **部分截屏核心场景**)
            # 用户场景：截取了极长文本的一部分 → 应匹配包含该部分的完整库文本
            # 限制条件：只对足够长的查询启用（避免短文本误匹配）
            # 例如："Signs of a Silent Star" (20字符) 不应该匹配到包含它的长描述文本
            if len(key) >= 50:  # 只对50+字符的查询启用被包含匹配
                contain_hits = [k for k in self.db.keys() if key in k]
                if contain_hits:
                    # 优先选择最短的包含项（最精确的匹配）
                    best_contain = min(contain_hits, key=len)
                    # 额外检查：匹配项不应该太长（避免误匹配到无关长文本）
                    if len(best_contain) <= len(key) * 3:
                        result = dict(self.db.get(best_contain, {}))
                        result["_matched_key"] = best_contain
                        self.signals.log.emit(
                            f"[MATCH] 部分截屏匹配成功：query_len={len(key)}, matched_len={len(best_contain)}"
                        )
                        return result, 0.98
            
            # 1.5.4 长查询松散匹配（处理文本版本差异）
            # 场景：OCR识别"标题+描述"拆分后，或数据库/游戏文本版本不一致
            # 例如 query="press basicattack...", db_key="basicattack..."（略有差异）
            if len(key) >= 100:  # 只对长查询执行此检查
                try:
                    from rapidfuzz import fuzz
                    # 查找长度相近且内容相关的候选
                    min_len = int(len(key) * 0.7)
                    max_len = int(len(key) * 5.0)  # 放宽上限，允许更长的完整描述
                    # 使用query中间50字符作为锚点（避免开头可能缺失的问题）
                    anchor_fragment = key[50:100] if len(key) >= 100 else key[:50]
                    loose_candidates = [k for k in self.db.keys() if min_len <= len(k) <= max_len and anchor_fragment in k]
                    
                    self.signals.log.emit(f"[MATCH] 松散匹配：query_len={len(key)}, 候选数量={len(loose_candidates)}")
                    
                    if loose_candidates:
                        # 使用token_set_ratio找最相似的
                        best_loose = max(loose_candidates, key=lambda k: fuzz.token_set_ratio(key, k))
                        similarity = fuzz.token_set_ratio(key, best_loose) / 100.0
                        
                        self.signals.log.emit(f"[MATCH] 最佳候选：key_len={len(best_loose)}, similarity={similarity:.3f}")
                        
                        if similarity >= 0.45:  # 降低到45%以处理文本版本差异
                            result = dict(self.db.get(best_loose, {}))
                            result["_matched_key"] = best_loose
                            self.signals.log.emit(
                                f"[MATCH] 松散匹配成功：query_len={len(key)}, matched_len={len(best_loose)}, similarity={similarity:.3f}"
                            )
                            return result, similarity
                except Exception as e:
                    self.signals.log.emit(f"[MATCH] 松散匹配失败: {e}")
        
        try:
            from rapidfuzz import fuzz, process
        except Exception:
            best, score = self.searcher.search(key, self.db.keys())
            result = dict(self.db.get(best, {}))
            result["_matched_key"] = best
            return result, score

        key_len = len(key)
        
        # 2. 短查询优先精确匹配策略
        # 对于短文本（<20字符），优先在长度接近的条目中查找，避免误匹配到长条目
        if key_len < 20:
            # 严格的长度过滤：±40%
            min_len = int(key_len * 0.6)
            max_len = int(key_len * 1.4)
            strict_candidates = [k for k in self.db.keys() if min_len <= len(k) <= max_len]
            
            if strict_candidates:
                hit = process.extractOne(key, strict_candidates, scorer=fuzz.ratio)
                if hit:
                    best_item, fuzzy_score, _ = hit
                    score = fuzzy_score / 100.0
                    # 如果在严格范围内找到高分匹配，直接返回
                    if score >= 0.85:
                        result = dict(self.db.get(str(best_item), {}))
                        result["_matched_key"] = str(best_item)
                        self.signals.log.emit(
                            f"[MATCH] 短查询精确匹配：query_len={key_len}, matched_len={len(best_item)}, score={score:.3f}"
                        )
                        return result, float(score)
        
        # 3. 常规长度过滤候选集
        min_len = int(key_len * 0.5)
        max_len = int(key_len * 1.5)
        candidates = [k for k in self.db.keys() if min_len <= len(k) <= max_len]
        if not candidates:
            candidates = list(self.db.keys())

        def _extract(cands: list[str]) -> tuple[str, float]:
            if key_len < 20:
                hit = process.extractOne(key, cands, scorer=fuzz.ratio)
            else:
                hit = process.extractOne(key, cands, scorer=fuzz.token_set_ratio)
            if hit is None:
                return "", 0.0
            best_item, score, _ = hit
            return str(best_item), float(score) / 100.0

        best_item, score = _extract(candidates)

        # 3. 若得分偏低，放宽长度限制再次搜索（适配“标题+长描述”场景）
        if score < 0.85:
            wide_max = int(key_len * 3.0)
            wide_candidates = [k for k in self.db.keys() if len(k) >= min_len and len(k) <= wide_max]
            if not wide_candidates:
                wide_candidates = list(self.db.keys())
            wide_item, wide_score = _extract(wide_candidates)
            if wide_score > score:
                best_item, score = wide_item, wide_score

        result = dict(self.db.get(str(best_item), {}))
        result["_matched_key"] = str(best_item)
        return result, float(score)

    def _is_voice_eligible(self, text_key: str | None) -> bool:
        if not text_key:
            return False
        prefixes = (
            "Term",  # UI/术语
            "SkillInput_",
            "SkillTag_",
            "WeaponConf_",
            "ComboTeaching_",
            "ItemInfo_",
            "RogueRes_",
            "Flow_",
            "POI_",
        )
        return not text_key.startswith(prefixes)

    def _show_result(self, result: Dict[str, Any]) -> None:
        print("[DEBUG] _show_result called", flush=True)
        try:
            self.last_match = result
            self.last_hash = None
            self.last_event_name = None
            if result.get("_multi"):
                items = result.get("items", [])
                left = []
                right = []
                for item in items:
                    # 使用数据库官方原文，如果不存在则fallback到OCR
                    en = item.get("official_en") or item.get("ocr") or ""
                    cn = item.get("official_cn") or item.get("text_key") or ""
                    if en:
                        left.append(en)
                    if cn:
                        right.append(cn)
                    self.signals.log.emit(
                        f"[ITEM] {item.get('ocr')} -> {item.get('text_key')} (score={item.get('score')})"
                    )
                # 使用换行分隔多个条目，检测是否包含HTML标签
                en_joined = "\n".join(left)
                cn_joined = "\n".join(right) if right else "（未找到中文匹配）"
                
                self.signals.log.emit("[WINDOW] 设置文本内容")
                # 检测英文文本是否包含HTML标签
                if '<' in en_joined and '>' in en_joined or '【' in en_joined:
                    html_en = self._convert_game_html(en_joined, lang="en")
                    self.source_label.setHtml(html_en)
                    self._last_en_is_html = True
                else:
                    self.source_label.setPlainText(en_joined)
                    self._last_en_is_html = False
                self._last_en_raw = en_joined
                
                # 检测中文文本是否包含HTML标签
                if '<' in cn_joined and '>' in cn_joined or '【' in cn_joined:
                    html_cn = self._convert_game_html(cn_joined, lang="cn")
                    self.cn_label.setHtml(html_cn)
                    self._last_cn_is_html = True
                else:
                    self.cn_label.setPlainText(cn_joined)
                    self._last_cn_is_html = False
                self._last_cn_raw = cn_joined
                
                # 显示官方原文而非OCR文本
                official_en = result.get('_official_en') or result.get('_ocr_text') or ''
                official_cn = result.get('_official_cn') or ''
                self.signals.log.emit(f"[MATCH] 官方原文: {official_en}")
                self.signals.log.emit(f"[MATCH] 官方译文: {official_cn}")
                self.signals.log.emit(f"[QUERY] OCR识别: {result.get('_ocr_text')} -> {result.get('_query_key')}")
                self.signals.log.emit("[WINDOW] 禁用音频控件（多条目模式）")
                # 多条目模式不支持音频播放
                self.play_pause_btn.setEnabled(False)
                self.audio_slider.setEnabled(False)
                self.signals.log.emit("[WINDOW] 准备显示多条目结果")
                self.show()
                self.signals.log.emit("[WINDOW] 已调用show()")
                self.raise_()
                self.signals.log.emit("[WINDOW] 已调用raise_()")
                self.activateWindow()
                self.signals.log.emit("[WINDOW] 窗口激活完成")
                return
        except Exception as e:
            self.signals.error.emit(f"显示结果失败: {e}")
            import traceback
            self.signals.log.emit(f"[ERROR] {traceback.format_exc()}")
            return
        query_key = result.get("_query_key", "")
        score = result.get("_score")
        matches = result.get("matches") or []
        
        # 提取显示内容（英文原文 + 中文翻译）
        en_text = ""
        cn_text = ""
        text_key = None
        audio_hash = None
        audio_event = None
        
        # 检查是否有标题信息（混合内容场景）
        first_line = result.get("_first_line")
        
        if matches:
            # 使用数据库官方英文原文（保留HTML标记）
            en_text = matches[0].get("official_en", "")
            cn_text = matches[0].get("official_cn", "")
            text_key = matches[0].get("text_key")
            audio_hash = matches[0].get("audio_hash")
            audio_event = matches[0].get("audio_event")
            
            # 如果有标题，添加到显示开头（不加【】）
            if first_line:
                title_cn = self._translate_title(first_line)
                display_title = title_cn or first_line
                # 标题样式：加粗、暗金色（和游戏原生一致）
                en_text = f"<span style='color: #d4af37; font-weight: bold;'>{first_line}</span>\n{en_text}"
                cn_text = f"<span style='color: #d4af37; font-weight: bold;'>{display_title}</span>\n{cn_text}"
                self.signals.log.emit(f"[DISPLAY] 标题: {first_line} -> {display_title}, 内容: {text_key}")

        # 音频识别逻辑：委托给 AudioResolver
        self.last_text_key = text_key
        if text_key and self.audio_resolver:
            res = self.audio_resolver.resolve(text_key, db_event=audio_event, db_hash=audio_hash)
            if res:
                self.last_hash = res.hash_value
                self.last_event_name = res.event_name
                self.signals.log.emit(f"[MATCH] text_key={text_key} hash={self.last_hash} ({res.source_type})")
            else:
                self.signals.log.emit(f"[MATCH] text_key={text_key} 未找到对应音频")
        elif text_key:
             # 回退到数据库原始哈希
             if audio_hash:
                 try: self.last_hash = int(audio_hash)
                 except: pass
             self.last_event_name = audio_event
             if self.last_hash:
                 self.signals.log.emit(f"[MATCH] text_key={text_key} 使用数据库哈希={self.last_hash}")
        
        # 显示数据库英文原文（保留HTML标记）
        if en_text:
            # 检测是否包含HTML标记
            if '<' in en_text and '>' in en_text or '【' in en_text:
                html_en = self._convert_game_html(en_text, lang="en")
                self.source_label.setHtml(html_en)
                self._last_en_raw = en_text
                self._last_en_is_html = True
            else:
                score_info = f"\nscore={score}" if score is not None else ""
                self.source_label.setPlainText(f"{en_text}{score_info}")
                self._last_en_raw = f"{en_text}{score_info}"
                self._last_en_is_html = False
        else:
            # 兜底：使用OCR文本
            ocr_original = result.get('_ocr_text', query_key)
            score_info = f" score={score}" if score is not None else ""
            self.source_label.setPlainText(f"{ocr_original}{score_info}")
            self._last_en_raw = f"{ocr_original}{score_info}"
            self._last_en_is_html = False
        
        # 渲染中文文本（支持HTML标记）
        if cn_text:
            # 检测是否包含HTML标记
            if '<' in cn_text and '>' in cn_text or '【' in cn_text:
                html_cn = self._convert_game_html(cn_text, lang="cn")
                self.cn_label.setHtml(html_cn)
                self._last_cn_raw = cn_text
                self._last_cn_is_html = True
            else:
                self.cn_label.setPlainText(cn_text)
                self._last_cn_raw = cn_text
                self._last_cn_is_html = False
            self.signals.log.emit(f"[CN] {cn_text[:100]}..." if len(cn_text) > 100 else f"[CN] {cn_text}")
        else:
            self.cn_label.setPlainText("（未找到中文匹配）")
            self._last_cn_raw = "（未找到中文匹配）"
            self._last_cn_is_html = False
        
        # 设置音频控件状态
        has_audio = self.last_hash is not None
        self.play_pause_btn.setEnabled(has_audio)
        self.audio_slider.setEnabled(has_audio)
        
        self.signals.log.emit(f"[QUERY] {result.get('_ocr_text')} -> {query_key}")
        
        # 确保窗口显示并置顶
        self.signals.log.emit("[DEBUG] Calling show_and_activate...")
        self.show_and_activate()
        self.signals.log.emit("[DEBUG] show_and_activate returned.")
        
        # 自动播放逻辑
        if self.config.play_audio and has_audio:
            self.signals.log.emit("[DEBUG] Calling play_audio...")
            self.play_audio()
            self.signals.log.emit("[DEBUG] play_audio returned.")
    
    def _convert_game_html(self, text: str, lang: str = "cn") -> str:
        """将游戏的自定义HTML标记转换为标准HTML格式，并包装为完整HTML文档。
        
        支持的游戏标记：
        - <color=#RRGGBB>文本</color>、<color=Name>文本</color>：颜色
        - <te href=xxx>文本</te>：下划线+黄色
        - <size=xx>文本</size>：字号
        - 【文本】：黄色高亮括号
        
        Args:
            text: 游戏文本
            lang: "en" 或 "cn"，用于选择对应语言的字体
        """
        import re
        
        # 游戏预设颜色名映射
        color_names = {
            "Highlight": "#fbbf24",  # 黄色高亮
            "Title": "#a79969",      # 暗金色标题（技能名称）
            "Wind": "#55ffb5",       # 气动-青蓝色
            "Fire": "#ef4444",       # 热熔-红色
            "Thunder": "#8b5cf6",    # 导电-紫色
            "Ice": "#06b6d4",        # 冷凝-青色
            "Light": "#fbbf24",      # 衍射-黄色
            "Dark": "#8b5cf6",       # 湮灭-紫色
        }
        
        # 替换 <color=Name>...</color>（预设颜色）
        for name, hex_color in color_names.items():
            text = re.sub(
                rf'<color={name}>(.*?)</color>',
                rf'<span style="color: {hex_color}">\1</span>',
                text,
                flags=re.DOTALL | re.IGNORECASE
            )
        
        # 替换 <color=#RRGGBB>...</color>（十六进制颜色）
        text = re.sub(
            r'<color=(#[0-9a-fA-F]{6,8})>(.*?)</color>',
            r'<span style="color: \1">\2</span>',
            text,
            flags=re.DOTALL
        )
        
        # 替换 <te href=xxx>...</te>（游戏术语链接 → 下划线+黄色）
        text = re.sub(
            r'<te\s+href=\d+>(.*?)</te>',
            r'<span style="color: #fbbf24; text-decoration: underline;">\1</span>',
            text,
            flags=re.DOTALL
        )
        
        # 替换 <size=xx>...</size>（字号）
        text = re.sub(
            r'<size=(\d+)>(.*?)</size>',
            r'<span style="font-size: \1pt">\2</span>',
            text,
            flags=re.DOTALL
        )
        
        # 替换 【...】（中文括号 → 黄色高亮）
        text = re.sub(
            r'【(.*?)】',
            r'<span style="color: #fbbf24; font-weight: bold;">【\1】</span>',
            text,
            flags=re.DOTALL
        )
        
        # 根据语言选择字体
        font_family = self.current_font_en if lang == "en" else self.current_font_cn
        # 包装为完整HTML文档
        font_size_pt = int(self.current_font_size) if self.current_font_size else 13
        line_height = float(self.current_line_spacing) if self.current_line_spacing else 1.2
        letter_spacing = float(self.current_letter_spacing) if self.current_letter_spacing else 0.0
        font_weight = self._font_weight_css()

        html = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: "{font_family}";
            color: #e2e8f0;
            line-height: {line_height};
            margin: 8px;
            padding: 0;
            font-size: {font_size_pt}pt;
            font-weight: {font_weight};
            letter-spacing: {letter_spacing}px;
        }}
    </style>
</head>
<body>
{text.replace(chr(10), '<br>')}
</body>
</html>
'''
        return html


    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        self._append_log(f"[ERROR] {message}")

    def _append_log(self, message: str) -> None:
        print(message, flush=True)  # 直接输出到终端，满足用户需求
        self.log_box.append(message)
        # 若 stdout 已被 Tee，避免重复写入文件
        if hasattr(sys.stdout, "_ludiglot_tee"):
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception:
            pass

    def show_and_activate(self) -> None:
        """显示并激活窗口，确保焦点。"""
        self.show()
        self.raise_()
        self.activateWindow()
        # 确保获得焦点以便检测焦点丢失
        self.setFocus()
        # 强制窗口置顶并获得键盘焦点
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        QApplication.processEvents()  # 立即处理事件

    def stop_audio(self) -> None:
        if hasattr(self, "player"):
            self.player.stop()
            self.signals.status.emit("已停止播放")
            
            # 重置音频控制UI
            if hasattr(self, 'audio_timer'):
                self.audio_timer.stop()
            if hasattr(self, 'play_pause_btn'):
                if self._icon_play:
                    self.play_pause_btn.setIcon(self._icon_play)
                self.play_pause_btn.setEnabled(False)
            if hasattr(self, 'audio_slider'):
                self.audio_slider.setValue(0)
                self.audio_slider.setEnabled(False)
            if hasattr(self, 'time_label'):
                self.time_label.setText("00:00 / 00:00")

    def play_audio(self) -> None:
        if self.last_hash is None or not self.config.audio_cache_path:
            return
        if self.audio_index is None:
            self.audio_index = AudioCacheIndex(
                self.config.audio_cache_path,
                index_path=self.config.audio_cache_index_path,
                max_mb=self.config.audio_cache_max_mb,
            )
            self.audio_index.load()
            self.audio_index.scan()
        
        path = None
        if self.audio_resolver:
            # 重新尝试定位物理文件 (处理可能的延迟加载)
            res = self.audio_resolver.resolve(self.last_text_key, db_event=self.last_event_name, db_hash=self.last_hash)
            if res:
                self.last_hash = res.hash_value
                self.last_event_name = res.event_name
                
                # 如果是 cache，直接获取路径
                if res.source_type == 'cache':
                    path = self.audio_resolver.audio_index.find(res.hash_value)
                elif res.source_type == 'wem' or res.source_type == 'bnk':
                    # 需要触发提取逻辑
                    path = self._ensure_audio_from_event()
        
        # 兜底：如果 resolver 没搞定，尝试原始 index
        if path is None and self.last_hash:
            if self.audio_index:
                path = self.audio_index.find(self.last_hash)
        
        if path is None:
            path = self._ensure_audio_from_event()
        
        if path is None:
            self.signals.status.emit("未找到对应音频文件")
            return

        self.signals.status.emit(f"正在播放: {path.name}")
        self.player.play(str(path), block=False)
        
        # 启用音频控制UI
        self.play_pause_btn.setEnabled(True)
        if self._icon_pause:
            self.play_pause_btn.setIcon(self._icon_pause)
        self.audio_slider.setEnabled(True)
        self.audio_slider.setValue(0)
        self.audio_timer.start()

    def _ensure_audio_from_event(self) -> Path | None:
        if self.last_hash is None:
            return None
        if not self.config.audio_cache_path:
            return None
        if not self.config.audio_wem_root or not self.config.audio_bnk_root:
            return None
        if not self.config.vgmstream_path:
            return None
        txtp_cache = self.config.audio_txtp_cache
        if not txtp_cache:
            return None
        wwiser_path = self.config.wwiser_path or default_wwiser_path()
        text_key = self.last_text_key

        event_candidates = []
        if self.audio_resolver:
            event_candidates = self.audio_resolver.get_candidates(text_key, self.last_event_name)
        
        if not event_candidates and self.last_event_name:
            event_candidates = [self.last_event_name]
            
        event_candidates = event_candidates[:8]

        for event_name in event_candidates:
            # 0. 尝试直接从 ExternalSource/WEM 命中（剧情常见）
            direct_wem = None
            if self.config.audio_wem_root:
                direct_wem = find_wem_by_event_name(
                    self.config.audio_wem_root,
                    event_name,
                    external_root=self.config.audio_external_root,
                )
            if direct_wem is not None:
                try:
                    path = convert_single_wem_to_wav(
                        direct_wem,
                        self.config.vgmstream_path,
                        self.config.audio_cache_path,
                    )
                    # 若有 hash，额外生成 hash 命名副本，方便缓存索引命中
                    if self.last_hash is not None:
                        target = self.config.audio_cache_path / f"{self.last_hash}.wav"
                        if path != target and not target.exists():
                            try:
                                shutil.copyfile(path, target)
                                path = target
                            except Exception:
                                pass
                    if self.audio_index:
                        self.audio_index.add_file(path)
                    return path
                except Exception as exc:
                    self.signals.log.emit(f"[VOICE] WEM 转码失败: {exc}")
            
            bnk_path = find_bnk_for_event(self.config.audio_bnk_root, event_name)
            if bnk_path is None:
                self.signals.log.emit(f"[VOICE] 未找到 BNK: {event_name}")
                continue
            try:
                txtp_files = generate_txtp_for_bnk(
                    bnk_path,
                    self.config.audio_wem_root,
                    txtp_cache,
                    wwiser_path,
                    log_callback=self.signals.log.emit,
                )
            except Exception as exc:
                self.signals.log.emit(f"[VOICE] TXTP 生成失败: {exc}")
                continue
            if not txtp_files:
                self.signals.log.emit(f"[VOICE] TXTP 为空: {bnk_path.name}")
                continue
            txtp_dir = txtp_cache / bnk_path.stem
            # 传入 hash 以便在没有命名的 TXTP 中寻找 (例如 3157737296.txtp)
            txtp_path = find_txtp_for_event(txtp_dir, event_name, self.last_hash) or txtp_files[0]
            output_path = self.config.audio_cache_path / f"{self.last_hash}.wav"
            try:
                path = convert_txtp_to_wav(txtp_path, self.config.vgmstream_path, output_path)
                if self.audio_index:
                    self.audio_index.add_file(path)
                return path
            except Exception as exc:
                self.signals.log.emit(f"[VOICE] TXTP 转码失败: {exc}")
                continue
        return None

    def closeEvent(self, event) -> None:
        """关闭前保存所有状态"""
        try:
            self._persist_window_position()
        except:
            pass
        self._unregister_windows_hotkeys()
        super().closeEvent(event)
    
    def hideEvent(self, event) -> None:
        """窗口隐藏事件，记录日志以便调试快捷键问题。"""
        self.signals.log.emit("[WINDOW] 隐藏")
        super().hideEvent(event)
    
    def showEvent(self, event) -> None:
        """窗口显示事件。"""
        self.signals.log.emit("[WINDOW] 显示")
        super().showEvent(event)
        # 确保窗口获得焦点，以便接收focusOutEvent
        self.setFocus()

    def eventFilter(self, obj, event) -> bool:
        """全局事件过滤器：检测窗口失焦+鼠标点击窗口外 → 隐藏窗口"""
        if self.isVisible():
            # 方案1: 检测失焦事件（窗口失去活动状态）
            if event.type() == QEvent.Type.WindowDeactivate:
                # 检查是否是菜单或子菜单导致的失焦
                if hasattr(self, 'window_menu'):
                    # 递归检查主菜单及其所有子菜单
                    menus_to_check = [self.window_menu]
                    while menus_to_check:
                        current_menu = menus_to_check.pop(0)
                        if current_menu.isVisible():
                            return False
                        for action in current_menu.actions():
                            if action.menu():
                                menus_to_check.append(action.menu())
                self.hide()
                return False
            # 方案2: 鼠标点击时检查是否在窗口外（双重保险）
            if event.type() == QEvent.Type.MouseButtonPress:
                try:
                    if hasattr(event, "globalPosition"):
                        pos = event.globalPosition().toPoint()
                    else:
                        pos = QCursor.pos()
                    
                    # 检查是否点击在菜单或其关联子菜单内
                    if hasattr(self, 'window_menu'):
                        menus_to_check = [self.window_menu]
                        while menus_to_check:
                            current_menu = menus_to_check.pop(0)
                            if current_menu.isVisible() and current_menu.frameGeometry().contains(pos):
                                return False
                            for action in current_menu.actions():
                                if action.menu():
                                    menus_to_check.append(action.menu())
                    
                    # 只有点击在窗口外且不在菜单内才隐藏
                    if not self.frameGeometry().contains(pos):
                        self.hide()
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            
            # 解决粘连问题：如果点击在按钮等控件上，不触发窗口拖拽或缩放
            child = self.childAt(pos)
            # 如果点击的是按钮（包括其内部的图标 Label）或下拉框，则直接返回
            if isinstance(child, (QPushButton, QComboBox, QLabel)) and child.parent() in {self.control_bar, self.centralWidget()}:
                # 特殊处理：如果是标题或状态栏等非交互 Label，允许拖拽
                if child not in {self.title_label, self.status_label}:
                    super().mousePressEvent(event)
                    return

            edge = self._get_resize_edge(pos)
            if edge:
                # 开始调整大小
                self._resizing = True
                self._resize_edge = edge
                self._resize_start_geometry = self.geometry()
                self._resize_start_pos = event.globalPosition().toPoint()
            else:
                # 开始拖拽窗口
                if child is None or child in {self.centralWidget(), self.title_label, self.status_label, self.control_bar}:
                    self._dragging = True
                    self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        
        if self._resizing and self._resize_edge and self._resize_start_geometry:
            # 调整窗口大小
            current_pos = event.globalPosition().toPoint()
            delta_x = current_pos.x() - self._resize_start_pos.x()
            delta_y = current_pos.y() - self._resize_start_pos.y()
            
            geo = QRect(self._resize_start_geometry)
            min_width, min_height = 300, 200  # 最小窗口尺寸
            
            # 根据边缘类型调整几何
            if 'left' in self._resize_edge:
                new_width = max(geo.width() - delta_x, min_width)
                geo.setLeft(geo.right() - new_width)
            if 'right' in self._resize_edge:
                new_width = max(geo.width() + delta_x, min_width)
                geo.setWidth(new_width)
            if 'top' in self._resize_edge:
                new_height = max(geo.height() - delta_y, min_height)
                geo.setTop(geo.bottom() - new_height)
            if 'bottom' in self._resize_edge:
                new_height = max(geo.height() + delta_y, min_height)
                geo.setHeight(new_height)
            
            self.setGeometry(geo)
        elif self._dragging and self._drag_pos is not None:
            # 拖拽窗口
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        else:
            # 鼠标悬停时更新光标样式（未按下时）
            edge = self._get_resize_edge(pos)
            self._update_cursor_for_edge(edge)
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self._dragging = False
                self._drag_pos = None
                self._persist_window_position()
            elif self._resizing:
                self._resizing = False
                self._resize_edge = None
                self._resize_start_geometry = None
                self._resize_start_pos = None
                self._persist_window_position()  # 也保存窗口位置
                # 保存窗口大小
                try:
                    pos = self.pos()
                    size = self.size()
                    raw = json.loads(self._config_path.read_text(encoding="utf-8"))
                    raw["window_pos"] = {"x": int(pos.x()), "y": int(pos.y())}
                    raw["window_size"] = {"width": int(size.width()), "height": int(size.height())}
                    self._config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            self._persist_window_position()
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        """窗口大小改变事件：更新按钮位置"""
        super().resizeEvent(event)
        self._update_button_positions()

    def _restore_window_position(self) -> None:
        # 恢复窗口大小和 UI 设置
        raw = {}
        try:
            if self._config_path.exists():
                raw = json.loads(self._config_path.read_text(encoding="utf-8"))
                
                # 恢复窗口尺寸
                window_size = raw.get("window_size")
                if window_size and isinstance(window_size, dict):
                    width = int(window_size.get("width", 620))
                    height = int(window_size.get("height", 260))
                    self.resize(width, height)
                    self.signals.log.emit(f"[RECOVERY] 恢复窗口尺寸: {width}x{height}")
                
                # 恢复 UI 设置
                if "ui_settings" in raw:
                    ui = raw["ui_settings"]
                    self.current_font_size = ui.get("font_size", self.current_font_size)
                    self.current_font_weight = ui.get("font_weight", self.current_font_weight)
                    self.current_letter_spacing = ui.get("letter_spacing", self.current_letter_spacing)
                    self.current_line_spacing = ui.get("line_spacing", self.current_line_spacing)
                    self._menu_direction = ui.get("menu_direction", "right") # 默认为右
                   
                    # 更新控制器数值
                    if hasattr(self, 'size_spin'):
                        self.size_spin.blockSignals(True)
                        self.size_spin.setValue(self.current_font_size)
                        self.size_spin.blockSignals(False)
                    if hasattr(self, 'spacing_spin'):
                        self.spacing_spin.blockSignals(True)
                        self.spacing_spin.setValue(self.current_letter_spacing)
                        self.spacing_spin.blockSignals(False)
                    if hasattr(self, 'lh_spin'):
                        self.lh_spin.blockSignals(True)
                        self.lh_spin.setValue(self.current_line_spacing)
                        self.lh_spin.blockSignals(False)

                    # 应用菜单方向
                    from PyQt6.QtCore import QTimer
                    direction = self._menu_direction
                    QTimer.singleShot(150, lambda d=direction: self._set_menu_direction(d))
                    self.signals.log.emit(f"[RECOVERY] 恢复 UI 设置: {self.current_font_size}pt, 字距{self.current_letter_spacing}px, 行距{self.current_line_spacing}x")
        except Exception as e:
            self.signals.log.emit(f"[RECOVERY] 恢复配置失败: {e}")
        
        # 恢复窗口位置 (优先使用 raw 中的位置，否则回退到 config)
        window_pos = raw.get("window_pos")
        if window_pos and isinstance(window_pos, dict):
            x = window_pos.get("x")
            y = window_pos.get("y")
        elif self.config.window_pos:
            x, y = self.config.window_pos
        else:
            return

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = max(geo.left(), min(x, geo.right() - self.width()))
        y = max(geo.top(), min(y, geo.bottom() - self.height()))
        self.move(x, y)
        self.signals.log.emit(f"[RECOVERY] 恢复窗口位置: {x}, {y}")
        
        # 强制应用一次字体设置以同步 UI
        self._apply_font_settings()

    def _get_resize_edge(self, pos: QPoint) -> str | None:
        """检测鼠标位置是否在窗口边缘，返回边缘类型。"""
        margin = 8  # 边缘检测区域宽度（像素）
        rect = self.rect()
        x, y = pos.x(), pos.y()
        
        at_left = x <= margin
        at_right = x >= rect.width() - margin
        at_top = y <= margin
        at_bottom = y >= rect.height() - margin
        
        # 角落优先
        if at_top and at_left:
            return 'topleft'
        elif at_top and at_right:
            return 'topright'
        elif at_bottom and at_left:
            return 'bottomleft'
        elif at_bottom and at_right:
            return 'bottomright'
        # 边缘
        elif at_left:
            return 'left'
        elif at_right:
            return 'right'
        elif at_top:
            return 'top'
        elif at_bottom:
            return 'bottom'
        
        return None
    
    def _update_cursor_for_edge(self, edge: str | None) -> None:
        """根据边缘类型更新鼠标光标。"""
        if edge == 'left' or edge == 'right':
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge == 'top' or edge == 'bottom':
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge == 'topleft' or edge == 'bottomright':
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge == 'topright' or edge == 'bottomleft':
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _persist_window_position(self) -> None:
        try:
            # 如果窗口已被销毁或不可见，不进行同步保存（防止保存初始坐标）
            if not self.isVisible():
                return
                
            pos = self.pos()
            size = self.size()
            raw = {}
            if self._config_path.exists():
                try:
                    raw = json.loads(self._config_path.read_text(encoding="utf-8"))
                except Exception:
                    raw = {}
            
            # 保存关键窗口状态
            raw["window_pos"] = {"x": int(pos.x()), "y": int(pos.y())}
            raw["window_size"] = {"width": int(size.width()), "height": int(size.height())}
            
            # 保存所有 UI 偏好设置
            raw["ui_settings"] = {
                "font_size": self.current_font_size,
                "font_weight": self.current_font_weight,
                "letter_spacing": self.current_letter_spacing,
                "line_spacing": self.current_line_spacing,
                "menu_direction": getattr(self, "_menu_direction", "left"),
                "font_en": self.current_font_en,
                "font_cn": self.current_font_cn
            }
            
            # 同时也更新顶层字段以保持兼容性
            raw["font_en"] = self.current_font_en
            raw["font_cn"] = self.current_font_cn
            
            # 立即写入文件
            self._config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            # 静默失败，或打印调试
            pass

    def reset_window_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.left() + max((geo.width() - self.width()) // 2, 0)
        y = geo.top() + max((geo.height() - self.height()) // 2, 0)
        self.move(x, y)
        self._persist_window_position()

    def _unregister_windows_hotkeys(self) -> None:
        if not self._win_hotkey_ids:
            return
        try:
            import ctypes
        except Exception:
            return
        user32 = ctypes.windll.user32
        for hotkey_id in self._win_hotkey_ids:
            try:
                user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
        self._win_hotkey_ids = []

    def _select_region(self) -> CaptureRegion | None:
        """选择屏幕区域并转换为物理像素坐标。"""
        selector = ScreenSelector()
        rect = selector.get_region()
        
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return None
        
        # ScreenSelector 返回的是逻辑坐标
        # 对于截图操作（mss等库），需要物理像素坐标
        screen = QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        
        # 转换为物理坐标
        physical_left = int(rect.x() * dpr)
        physical_top = int(rect.y() * dpr)
        physical_width = int(rect.width() * dpr)
        physical_height = int(rect.height() * dpr)
        
        print(f"[框选] 逻辑坐标: ({rect.x()}, {rect.y()}, {rect.width()}, {rect.height()})")
        print(f"[框选] 物理坐标: ({physical_left}, {physical_top}, {physical_width}, {physical_height})")
        print(f"[框选] DPI缩放比: {dpr}")
        
        return CaptureRegion(
            left=physical_left,
            top=physical_top,
            width=physical_width,
            height=physical_height,
        )


def run_gui(config_path: Path) -> None:
    app = QApplication([])
    app.setFont(QFont("Segoe UI", 10))
    app.setQuitOnLastWindowClosed(False)
    
    try:
        config = load_config(config_path)
    except Exception as e:
        # 在终端显示错误信息，不使用GUI窗口
        print("\n" + "="*70)
        print("❌ Ludiglot 启动失败")
        print("="*70)
        print("\n加载配置或数据失败：")
        print(f"\n{e}")
        print("\n" + "="*70 + "\n")
        return

    window = OverlayWindow(config, config_path)
    window.hide()

    tray = QSystemTrayIcon(app)
    style = app.style()
    if style:
        tray.setIcon(style.standardIcon(style.StandardPixmap.SP_ComputerIcon))
    
    menu = QMenu()
    # 修复：明确 Show/Hide 的职责，不再使用 toggle，解决状态不一致导致的“双击才能显示”问题
    show_action = menu.addAction("Show")
    hide_action = menu.addAction("Hide")
    menu.addSeparator()
    capture_action = menu.addAction("Capture")
    reset_action = menu.addAction("Reset Window Position")
    quit_action = menu.addAction("Quit")

    if show_action:
        show_action.triggered.connect(window.show_and_activate)
    if hide_action:
        hide_action.triggered.connect(window.hide)
    if capture_action:
        capture_action.triggered.connect(lambda: window.capture_requested.emit(True))
    if reset_action:
        reset_action.triggered.connect(window.reset_window_position)
    if quit_action:
        quit_action.triggered.connect(app.quit)

    tray.setContextMenu(menu)
    # 单击图标切换显示/隐藏
    tray.activated.connect(lambda reason: window._toggle_visibility() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    # 双击图标触发捕获
    tray.activated.connect(lambda reason: window.capture_requested.emit(True) if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray.show()

    print("[DEBUG] Entering app.exec()", flush=True)
    try:
        ret = app.exec()
        print(f"[DEBUG] app.exec() returned with {ret}", flush=True)
    except Exception as e:
        print(f"[ERROR] Exception in app.exec(): {e}", flush=True)
    finally:
        print("[DEBUG] Application exiting.", flush=True)


class ScreenSelector(QWidget):
    """全屏选区控件，返回用户选定的区域（全局坐标）。
    
    修复高DPI屏幕下的坐标偏移问题：
    - 考虑设备像素比（devicePixelRatio）
    - 使用物理像素进行截图和显示
    - 在返回坐标时转换回逻辑坐标
    """

    region_selected = pyqtSignal(QRect)

    def __init__(self) -> None:
        super().__init__()
        screen = QGuiApplication.primaryScreen()
        self._screen = screen
        
        # 获取设备像素比（High DPI 缩放比例）
        self._device_pixel_ratio = screen.devicePixelRatio() if screen else 1.0
        
        # 使用虚拟几何作为逻辑坐标系
        self._virtual_rect = screen.virtualGeometry() if screen else QRect(0, 0, 1920, 1080)
        
        # 设置窗口几何（逻辑坐标）
        self.setGeometry(self._virtual_rect)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        
        self.rubber_band: QRubberBand | None = None
        self.origin: QPoint | None = None
        self._selected_rect: QRect | None = None
        self._background = self._capture_background()
        
        # 调试信息
        print(f"[ScreenSelector] 设备像素比: {self._device_pixel_ratio}")
        print(f"[ScreenSelector] 虚拟几何(逻辑): {self._virtual_rect}")
        print(f"[ScreenSelector] 物理分辨率: {screen.geometry() if screen else 'N/A'}")

    def get_region(self) -> QRect | None:
        try:
            loop = QEventLoop()
            self.region_selected.connect(loop.quit)
            self.show()
            self.raise_()
            self.activateWindow()
            loop.exec()
            self.hide()
            return self._selected_rect
        except Exception as e:
            print(f"[ScreenSelector ERROR] {e}")
            import traceback
            traceback.print_exc()
            self.hide()
            return None

    def _capture_background(self) -> QPixmap:
        """捕获屏幕背景，考虑高DPI缩放。"""
        # 创建逻辑尺寸的背景pixmap
        background = QPixmap(self._virtual_rect.size())
        if background.isNull():
            # 如果pixmap创建失败，返回最小有效pixmap
            background = QPixmap(1920, 1080)
        background.fill(Qt.GlobalColor.black)
        
        painter = QPainter(background)
        if not painter.isActive():
            return background
        
        # 遍历所有屏幕并捕获
        for screen in QGuiApplication.screens():
            # grabWindow(0) 返回整个屏幕的截图
            # 返回的pixmap已经包含了正确的devicePixelRatio信息
            pix = screen.grabWindow(0)
            
            # 获取屏幕的逻辑几何（Qt自动处理DPI）
            screen_geom = screen.geometry()
            
            # 计算屏幕在虚拟桌面中的偏移量（逻辑坐标）
            offset = screen_geom.topLeft() - self._virtual_rect.topLeft()
            
            # Qt的drawPixmap会自动处理DPI缩放
            # 如果pix有devicePixelRatio，会按逻辑尺寸绘制
            painter.drawPixmap(offset, pix)
        
        painter.end()
        
        # 调试信息
        print(f"[ScreenSelector] 背景Pixmap尺寸: {background.size()}, DPR: {background.devicePixelRatio()}")
        return background

        return background

    def closeEvent(self, event) -> None:
        print("[DEBUG] ScreenSelector closeEvent", flush=True)
        super().closeEvent(event)

    def paintEvent(self, event) -> None:
        """绘制背景和半透明遮罩。"""
        if self._background is None or self._background.isNull():
            return
        
        painter = QPainter(self)
        if not painter.isActive():
            return
        
        # 绘制背景截图，Qt会自动处理DPI缩放
        painter.drawPixmap(self.rect(), self._background, self._background.rect())
        
        # 添加半透明深色遮罩以便看清框选区域
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        
        painter.end()

    def mousePressEvent(self, event) -> None:
        self.origin = event.pos()
        if self.rubber_band is None:
            self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        if self.origin:
            self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())
        self.rubber_band.show()

    def mouseMoveEvent(self, event) -> None:
        if self.rubber_band and self.origin:
            self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event) -> None:
        """鼠标释放时，转换坐标到全局物理像素坐标。"""
        if self.rubber_band is None or not self.origin:
            self._selected_rect = None
        else:
            # 获取选区的窗口本地坐标（逻辑坐标）
            rect = self.rubber_band.geometry().normalized()
            
            # 转换到全局坐标（逻辑坐标系）
            # 窗口本地坐标 + 窗口全局位置
            global_top_left = self.mapToGlobal(rect.topLeft())
            
            # 创建全局坐标的矩形（逻辑坐标）
            self._selected_rect = QRect(global_top_left, rect.size())
            
            # 调试输出
            print(f"[ScreenSelector] 选中区域(逻辑): x={global_top_left.x()}, y={global_top_left.y()}, w={rect.width()}, h={rect.height()}")
            print(f"[ScreenSelector] 物理坐标预估: x={int(global_top_left.x()*self._device_pixel_ratio)}, y={int(global_top_left.y()*self._device_pixel_ratio)}, w={int(rect.width()*self._device_pixel_ratio)}, h={int(rect.height()*self._device_pixel_ratio)}")
        
        self.region_selected.emit(self._selected_rect or QRect())
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._selected_rect = None
            self.region_selected.emit(QRect())
            self.close()
            return
        super().keyPressEvent(event)
