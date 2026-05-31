from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QPoint, QPointF, QRect, QRectF, QSize, QAbstractNativeEventFilter, QEvent, QEventLoop
from PyQt6.QtGui import QFont, QTextOption, QColor, QPalette, QAction, QActionGroup, QCursor, QPainter, QPixmap, QGuiApplication, QImage
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTextEdit, QMenu, QComboBox, QSizePolicy,
    QSlider, QSpinBox, QDoubleSpinBox, QWidgetAction, QStyle,
    QRubberBand, QSystemTrayIcon, QFrame
)

from ludiglot.core.audio_player import AudioPlayer
from ludiglot.core.capture import CaptureRegion
from ludiglot.core.capture_input import (
    CaptureInputAdapters,
    capture_input_to_memory,
    capture_options_from_config,
)
from ludiglot.core.config import AppConfig, load_config
from ludiglot.core.overlay_runtime import (
    OverlayRuntimeCallbacks,
    create_overlay_ocr_engine,
    initialize_overlay_runtime,
)
from ludiglot.core.overlay_audio_runtime import OverlayAudioRuntime
from ludiglot.core.display_shaper import (
    DisplayPreferences,
    convert_game_html,
    extract_numeric_values_from_context,
    resolve_display_placeholders,
    shape_translation_display,
)
from ludiglot.core.preferences import (
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    ConfigJsonStore,
    OverlayPreferences,
    WindowBounds,
    WindowPoint,
    WindowSize,
    clamp_window_position,
)
from ludiglot.core.selection_geometry import (
    MonitorGeometry,
    Rect,
    ScreenGeometry,
    crop_box_for_snapshot_region,
    expand_region_within_monitor,
    map_selection_to_capture_region,
    normalize_monitors_to_image_size,
)
from ludiglot.core.audio_playback_orchestrator import AudioIntent, AudioPlaybackIdentity
from ludiglot.core.capture_match_workflow import (
    CaptureProcessCallbacks,
    CaptureProcessRequest,
    needs_tesseract,
    run_capture_match_workflow,
)
from ludiglot.ui.waveform_progress_bar import AudioWaveformProgressBar


class PersistentMenu(QMenu):
    """自定义菜单，支持在操作某些控件时保持开启。"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 启用半透明背景，去除系统默认白色底框
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # 启用无边框窗口标记，彻底剥离 Windows 11 等操作系统的 native 强行大圆角和原生阴影，使 2px border-radius 生效
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)

    def showEvent(self, event):
        super().showEvent(event)
        parent_menu = self.parent()
        # 如果当前是一个嵌套子菜单，我们强制重新计算它的弹出坐标，让它完美贴合在母菜单边界之外，绝不覆盖
        if isinstance(parent_menu, QMenu):
            # 获取母菜单的物理屏幕坐标和宽度
            p_geom = parent_menu.geometry()
            my_geom = self.geometry()
            
            # 检测当前的展开方向是向左还是向右，并做高精度对齐
            direction = "left" if parent_menu.layoutDirection() == Qt.LayoutDirection.RightToLeft else "right"
            if direction == "left":
                # 向左展开：子选单的右边界对齐母选单的左边界
                new_x = p_geom.x() - my_geom.width()
            else:
                # 向右展开：子选单的左边界对齐母选单的右边界
                new_x = p_geom.x() + p_geom.width()
                
            self.move(new_x, my_geom.y())

    def mouseReleaseEvent(self, event):
        action = self.actionAt(event.position().toPoint())
        
        # 如果是叶子节点动作且标记为 persistent，则触发但不关闭
        if action and not action.menu() and action.property("persistent"):
            action.trigger()
            return # 关键：不调用 super() 阻止菜单关闭
            
        super().mouseReleaseEvent(event)


class GoldSpinBox(QSpinBox):
    """自绘制箭头的金铜色微调输入框，确保在任何布局和渲染引擎下100%显示完美的矢量三角形图标"""
    def paintEvent(self, event):
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        from PyQt6.QtWidgets import QStyle, QStyleOptionSpinBox
        from PyQt6.QtGui import QPolygonF
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        
        # 获取向上和向下按钮的物理区域
        up_rect = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxUp, self)
        down_rect = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxDown, self)
        
        # 获取鼠标相对于控件的全局位置
        mouse_pos = self.mapFromGlobal(QCursor.pos())
        
        # 绘制向上箭头
        if not up_rect.isEmpty():
            painter.save()
            is_hover = self.underMouse() and up_rect.contains(mouse_pos)
            color = QColor(255, 255, 255, 255) if is_hover else QColor(170, 155, 106, 220)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            
            cx = up_rect.x() + up_rect.width() / 2.0
            cy = up_rect.y() + up_rect.height() / 2.0
            poly = QPolygonF([QPointF(cx, cy - 2.5), QPointF(cx + 3.5, cy + 1.5), QPointF(cx - 3.5, cy + 1.5)])
            painter.drawPolygon(poly)
            painter.restore()

        # 绘制向下箭头
        if not down_rect.isEmpty():
            painter.save()
            is_hover = self.underMouse() and down_rect.contains(mouse_pos)
            color = QColor(255, 255, 255, 255) if is_hover else QColor(170, 155, 106, 220)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            
            cx = down_rect.x() + down_rect.width() / 2.0
            cy = down_rect.y() + down_rect.height() / 2.0
            poly = QPolygonF([QPointF(cx - 3.5, cy - 1.5), QPointF(cx + 3.5, cy - 1.5), QPointF(cx, cy + 2.5)])
            painter.drawPolygon(poly)
            painter.restore()


class GoldDoubleSpinBox(QDoubleSpinBox):
    """自绘制箭头的金铜色双精度微调输入框，确保在任何布局和渲染引擎下100%显示完美的矢量三角形图标"""
    def paintEvent(self, event):
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        from PyQt6.QtWidgets import QStyle, QStyleOptionSpinBox
        from PyQt6.QtGui import QPolygonF
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        
        # 获取向上和向下按钮的物理区域
        up_rect = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxUp, self)
        down_rect = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxDown, self)
        
        # 获取鼠标相对于控件的全局位置
        mouse_pos = self.mapFromGlobal(QCursor.pos())
        
        # 绘制向上箭头
        if not up_rect.isEmpty():
            painter.save()
            is_hover = self.underMouse() and up_rect.contains(mouse_pos)
            color = QColor(255, 255, 255, 255) if is_hover else QColor(170, 155, 106, 220)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            
            cx = up_rect.x() + up_rect.width() / 2.0
            cy = up_rect.y() + up_rect.height() / 2.0
            poly = QPolygonF([QPointF(cx, cy - 2.5), QPointF(cx + 3.5, cy + 1.5), QPointF(cx - 3.5, cy + 1.5)])
            painter.drawPolygon(poly)
            painter.restore()

        # 绘制向下箭头
        if not down_rect.isEmpty():
            painter.save()
            is_hover = self.underMouse() and down_rect.contains(mouse_pos)
            color = QColor(255, 255, 255, 255) if is_hover else QColor(170, 155, 106, 220)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            
            cx = down_rect.x() + down_rect.width() / 2.0
            cy = down_rect.y() + down_rect.height() / 2.0
            poly = QPolygonF([QPointF(cx - 3.5, cy - 1.5), QPointF(cx + 3.5, cy - 1.5), QPointF(cx, cy + 2.5)])
            painter.drawPolygon(poly)
            painter.restore()


class PlayPauseButton(QPushButton):
    """自绘制的播放/暂停按钮，保证图标完美居中和颜色可调，并带有精致的悬浮和状态切换动效。"""
    def __init__(self, parent=None):
        super().__init__("", parent)
        self._is_playing = False
        self._hover_val = 0.0
        self._press_val = 0.0
        self._state_val = 0.0  # 0.0 = Play, 1.0 = Pause
        
        # 强制覆盖全局 QSS，防止受到全局 QPushButton 的影响
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 0px;
            }
        """)
        
        from PyQt6.QtCore import QVariantAnimation, QEasingCurve
        
        # 悬浮动画：0.0 -> 1.0
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._handle_hover_anim)
        
        # 播放/暂停状态切换动画：0.0 -> 1.0，OutBack 带有微弹回感，尽显灵动
        self._state_anim = QVariantAnimation(self)
        self._state_anim.setDuration(300)
        self._state_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._state_anim.valueChanged.connect(self._handle_state_anim)

    def _handle_hover_anim(self, value):
        self._hover_val = value
        self.update()

    def _handle_state_anim(self, value):
        self._state_val = value
        self.update()

    def set_playing(self, playing: bool):
        if self._is_playing != playing:
            self._is_playing = playing
            self._state_anim.stop()
            self._state_anim.setStartValue(self._state_val)
            self._state_anim.setEndValue(1.0 if playing else 0.0)
            self._state_anim.start()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_val)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_val)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_val = 1.0
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_val = 0.0
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        
        # 禁用或各类状态的颜色和微动效融合计算
        if not self.isEnabled():
            bg_color = QColor(255, 255, 255, 12)
            border_color = QColor(255, 255, 255, 25)
            icon_color = QColor(255, 255, 255, 76)
        else:
            h = self._hover_val
            p = self._press_val
            
            # 背景色：透明灰 -> 雅致金黄微亮
            bg_r = int(255 * (1.0 - h) + 170 * h)
            bg_g = int(255 * (1.0 - h) + 155 * h)
            bg_b = int(255 * (1.0 - h) + 106 * h)
            bg_a = int((38 * (1.0 - h) + 60 * h) * (1.0 - p * 0.2))
            bg_color = QColor(bg_r, bg_g, bg_b, bg_a)
            
            # 边框色：透白 -> 明亮金黄 #c9a64a
            border_r = int(255 * (1.0 - h) + 201 * h)
            border_g = int(255 * (1.0 - h) + 166 * h)
            border_b = int(255 * (1.0 - h) + 74 * h)
            border_a = int(76 * (1.0 - h) + 180 * h)
            border_color = QColor(border_r, border_g, border_b, border_a)
            
            # 图标颜色
            icon_r = int(200 * (1.0 - h) + 255 * h)
            icon_g = int(200 * (1.0 - h) + 255 * h)
            icon_b = int(200 * (1.0 - h) + 255 * h)
            icon_a = int(200 * (1.0 - h) + 255 * h)
            icon_color = QColor(icon_r, icon_g, icon_b, icon_a)

        # 1. 绘制背景菱形
        from PyQt6.QtGui import QPolygonF
        cx = rect.width() / 2.0
        cy = rect.height() / 2.0
        margin = 1.5
        w = rect.width() - 2.0 * margin
        h = rect.height() - 2.0 * margin
        p_top = QPointF(cx, cy - h / 2.0)
        p_right = QPointF(cx + w / 2.0, cy)
        p_bottom = QPointF(cx, cy + h / 2.0)
        p_left = QPointF(cx - w / 2.0, cy)
        diamond = QPolygonF([p_top, p_right, p_bottom, p_left])

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawPolygon(diamond)
        
        # 2. 绘制边框菱形
        from PyQt6.QtGui import QPen
        pen = QPen(border_color, 1.0 + self._hover_val * 0.4)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(diamond)

        # 3. 绘制图标（以中心为锚点应用变换）
        cx = rect.width() / 2.0
        cy = rect.height() / 2.0
        
        # 播放三角形（在 state_val 趋向 1.0 时顺时针旋转 90 度并淡出）
        if self._state_val < 0.99:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(self._state_val * 90.0)
            
            opacity = 1.0 - self._state_val
            c_play = QColor(icon_color)
            c_play.setAlpha(int(icon_color.alpha() * opacity))
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c_play)
            
            from PyQt6.QtGui import QPolygonF
            size = 10.0
            half_size = size / 2.0
            offset = 0.5  # 视觉微调中心偏移
            p1 = QPointF(-half_size * 0.7 + offset, -half_size)
            p2 = QPointF(-half_size * 0.7 + offset, half_size)
            p3 = QPointF(half_size * 1.1 + offset, 0.0)
            poly = QPolygonF([p1, p2, p3])
            painter.drawPolygon(poly)
            painter.restore()
            
        # 暂停双线（从 -90 度逆时针转回 0 度并淡入）
        if self._state_val > 0.01:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate((1.0 - self._state_val) * -90.0)
            
            opacity = self._state_val
            c_pause = QColor(icon_color)
            c_pause.setAlpha(int(icon_color.alpha() * opacity))
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c_pause)
            
            w = 3.0
            h = 10.0
            gap = 4.0
            
            # 左竖线
            x1 = -gap / 2.0 - w
            y1 = -h / 2.0
            painter.drawRect(QRectF(x1, y1, w, h))
            
            # 右竖线
            x2 = gap / 2.0
            painter.drawRect(QRectF(x2, y1, w, h))
            painter.restore()

        painter.end()


class CloseIconButton(QPushButton):
    """自绘制的关闭按钮，鸣潮风格的四片利刃组成的交叉图标。
    Hover 态为微动效：四片利刃平滑地朝外侧对角线方向扩张（无颜色和背景变化）。
    """
    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(32, 32)
        self._current_offset = 2.5  # 基础偏移，稍微移大，增加常规状态下的比例感
        
        # 强制覆盖全局 QSS，防止受到全局 QPushButton 的边框、底色和内边距影响
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 0px;
            }
        """)
        
        # 导入动画所需类
        from PyQt6.QtCore import QVariantAnimation, QEasingCurve
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(120)  # 120ms 灵动响应
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._handle_anim)
        
    def _handle_anim(self, value):
        self._current_offset = value
        self.update()
        
    def enterEvent(self, event):
        super().enterEvent(event)
        self._anim.stop()
        self._anim.setStartValue(self._current_offset)
        self._anim.setEndValue(6.0)  # 悬浮时利刃向外舒展 6.0px，展现出强烈的张力
        self._anim.start()
        
    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._anim.stop()
        self._anim.setStartValue(self._current_offset)
        self._anim.setEndValue(2.5)  # 移开时平滑缩回到 2.5px
        self._anim.start()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        cx = rect.width() / 2.0
        cy = rect.height() / 2.0
        
        # 纯净的白色/亮灰，无任何底色和彩色变幻
        if self.underMouse():
            icon_color = QColor(255, 255, 255, 230)  # 略微明亮以示交互
        else:
            icon_color = QColor(255, 255, 255, 180)  # 默认柔和白色
            
        # 绘制四瓣鸣潮风格利刃交叉
        painter.save()
        painter.translate(cx, cy)
        
        L = 12.5  # 增大：利刃整体长度为 12.5
        
        # 每次旋转 90 度画一片利刃，倾斜 45 度开始第一片
        painter.rotate(45)
        
        from PyQt6.QtGui import QPainterPath
        for _ in range(4):
            painter.save()
            # 沿着当前旋转方向 of X 轴平移，实现完美且极其平滑的向外舒展动画
            painter.translate(self._current_offset, 0)
            
            path = QPainterPath()
            # 刀刃起点移动至 0.0 开始绘制，基础宽度微增到 1.6 以适应比例
            path.moveTo(0.0, -1.6)
            # 绘制上弧线到刀尖
            path.quadTo(L * 0.4, -0.7, L - 1.8, 0.0)
            # 绘制下弧线到终点
            path.quadTo(L * 0.4, 0.7, 0.0, 1.6)
            path.closeSubpath()
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(icon_color)
            painter.drawPath(path)
            
            # 绘制中间细微的利刃脊线
            from PyQt6.QtGui import QPen
            pen = QPen(QColor(0, 0, 0, 45), 0.8)
            painter.setPen(pen)
            painter.drawLine(QPointF(0.0, 0), QPointF(L - 3.0, 0))
            
            painter.restore()
            painter.rotate(90)
            
        painter.restore()
        painter.end()


class MenuIconButton(QPushButton):
    """自绘制的菜单/设置按钮，外部是六边形（无齿轮），内部是圆，内部的圆内有个直径稍小的圆形弧线。
    Hover 态为旋转与微放大动画：外部图标旋转 60 度，内部圆形弧线保持静止，整体放大 12%。
    """
    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(32, 32)
        self._anim_progress = 0.0
        
        # 强制覆盖全局 QSS，防止受到全局 QPushButton 的边框、底色和内边距影响
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 0px;
            }
        """)
        
        # 导入动画所需类
        from PyQt6.QtCore import QVariantAnimation, QEasingCurve
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(350)  # 350ms 顺滑旋转与放大
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._handle_anim)
        
    def _handle_anim(self, value):
        self._anim_progress = value
        self.update()
        
    def enterEvent(self, event):
        super().enterEvent(event)
        self._anim.stop()
        self._anim.setStartValue(self._anim_progress)
        self._anim.setEndValue(1.0)  # 悬浮态达到最大值
        self._anim.start()
        
    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._anim.stop()
        self._anim.setStartValue(self._anim_progress)
        self._anim.setEndValue(0.0)  # 恢复
        self._anim.start()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        cx = rect.width() / 2.0
        cy = rect.height() / 2.0
        
        # 悬停时仅高亮图标自身，不绘制任何背景色
        if self.underMouse() and self.isDown():
            icon_color = QColor(255, 255, 255, 255)
            arc_color = QColor(170, 155, 106, 250)  # 主金黄色
        elif self.underMouse():
            icon_color = QColor(255, 255, 255, 230)
            arc_color = QColor(170, 155, 106, 220)
        else:
            icon_color = QColor(255, 255, 255, 180)  # 默认淡白
            arc_color = QColor(150, 150, 150, 160)  # 默认灰色圆弧
            
        # 整体应用微放大（1.0 -> 1.2），创造高级的物理升起感
        painter.save()
        painter.translate(cx, cy)
        total_scale = 1.0 + self._anim_progress * 0.2
        painter.scale(total_scale, total_scale)
        
        # 1. 绘制会旋转的外部六边形与内部圆
        painter.save()
        angle = self._anim_progress * 60.0
        painter.rotate(angle)
        painter.scale(0.95, 0.95)  # 基础微调缩放以维持视觉精致度
        
        # 绘制六边形
        import math
        from PyQt6.QtGui import QPolygonF
        
        hexagon = QPolygonF()
        R = 9.5  # 六边形外接圆半径
        for i in range(6):
            # i * 60 + 30 使得平顶朝上，极其规整精美
            angle_rad = math.radians(i * 60 + 30)
            x = R * math.cos(angle_rad)
            y = R * math.sin(angle_rad)
            hexagon.append(QPointF(x, y))
            
        from PyQt6.QtGui import QPen
        hex_pen = QPen(icon_color, 1.5)
        painter.setPen(hex_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(hexagon)
        
        # 绘制内部圆
        r_inner = 4.5
        painter.drawEllipse(QPointF(0, 0), r_inner, r_inner)
        
        painter.restore()
        
        # 2. 绘制不旋转的内部圆形弧线（但参与整体的放大效果）
        painter.save()
        
        arc_pen = QPen(arc_color, 1.2)
        painter.setPen(arc_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        r_arc = 4.0  # 直径稍小的圆形弧线半径
        arc_rect = QRectF(-r_arc, -r_arc, r_arc * 2, r_arc * 2)
        start_angle = 45 * 16  # 起始角度
        span_angle = 270 * 16  # 跨越角度，留出优雅缺口
        painter.drawArc(arc_rect, start_angle, span_angle)
        
        painter.restore()
        painter.restore()
        painter.end()


class StarDivider(QWidget):
    """中间带四角星的分界线"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        cx = rect.width() / 2.0
        cy = rect.height() / 2.0
        
        # 绘制四角星
        painter.save()
        painter.translate(cx, cy)
        
        star_color = QColor(170, 155, 106, 220)  # 经典金黄色 #aa9b6a
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(star_color)
        
        # 绘制四角星的路径
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        R = 8.0  # 外半径
        r = 2.5  # 内半径
        
        path.moveTo(0, -R)
        path.lineTo(r, -r)
        path.lineTo(R, 0)
        path.lineTo(r, r)
        path.lineTo(0, R)
        path.lineTo(-r, r)
        path.lineTo(-R, 0)
        path.lineTo(-r, -r)
        path.closeSubpath()
        painter.drawPath(path)
        
        # 绘制四角星中心的微小亮核
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.drawEllipse(QPointF(0, 0), 1.2, 1.2)
        
        painter.restore()
        
        # 绘制两侧的渐变线条
        from PyQt6.QtGui import QLinearGradient, QPen
        
        # 左侧渐变线
        left_grad = QLinearGradient(0, cy, cx - 12, cy)
        left_grad.setColorAt(0.0, QColor(170, 155, 106, 0))
        left_grad.setColorAt(0.7, QColor(170, 155, 106, 120))
        left_grad.setColorAt(1.0, QColor(170, 155, 106, 200))
        
        pen_left = QPen(left_grad, 1.0)
        painter.setPen(pen_left)
        painter.drawLine(QPointF(10, cy), QPointF(cx - 12, cy))
        
        # 右侧渐变线
        right_grad = QLinearGradient(cx + 12, cy, rect.width(), cy)
        right_grad.setColorAt(0.0, QColor(170, 155, 106, 200))
        right_grad.setColorAt(0.3, QColor(170, 155, 106, 120))
        right_grad.setColorAt(1.0, QColor(170, 155, 106, 0))
        
        pen_right = QPen(right_grad, 1.0)
        painter.setPen(pen_right)
        painter.drawLine(QPointF(cx + 12, cy), QPointF(rect.width() - 10, cy))
        
        painter.end()


class UiSignals(QObject):
    status = pyqtSignal(str)
    result = pyqtSignal(dict)
    error = pyqtSignal(str)
    log = pyqtSignal(str)


@dataclass
class DesktopSnapshot:
    image: Any
    left: int
    top: int
    monitors: list[MonitorGeometry]
    screen_pixmaps: list[QPixmap]


class OverlayWindow(QMainWindow):
    """无边框、置顶覆盖层窗口（MVP）。"""

    capture_requested = pyqtSignal(bool)
    resources_initialized = pyqtSignal(object)
    resources_loaded = pyqtSignal()

    def __init__(self, config: AppConfig, config_path: Path) -> None:
        super().__init__()
        self.config = config
        self._config_path = config_path
        self.signals = UiSignals()
        self.log_path = Path(__file__).resolve().parents[3] / "log" / "gui.log"
        self._install_terminal_logger()
        self.matcher = None
        self.audio_resolver = None
        self.skill_param_resolver = None
        runtime_callbacks = OverlayRuntimeCallbacks(
            status=self.signals.status.emit,
            log=self.signals.log.emit,
            error=self.signals.error.emit,
        )
        self.engine = create_overlay_ocr_engine(config, runtime_callbacks)
        self.db: Dict[str, Any] = {}
        self.voice_map: Dict[str, list[str]] = {}
        self.voice_event_index = None
        self.audio_index = None
        self.audio_runtime: OverlayAudioRuntime | None = None
        self.last_match: Dict[str, Any] | None = None
        self.last_text_key: str | None = None
        self.last_hash: int | None = None
        self.last_event_name: str | None = None
        self.player = AudioPlayer()
        self._hotkey_listener = None
        self._win_hotkey_filter = None
        self._win_hotkey_ids: list[int] = []
        self._capture_in_progress = False  # 防止快捷键重复触发捕获
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
        self.resources_initialized.connect(self._on_runtime_resources_initialized)
        
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        threading.Thread(target=self._initialize_resources, daemon=True).start()
        self._start_hotkeys()
        
        # 定时同步窗口位置到外部 config
        self._sync_config_timer = QTimer(self)
        self._sync_config_timer.timeout.connect(self._persist_window_position)
        self._sync_config_timer.start(5000)  # 每 5 秒同步一次

    def _install_terminal_logger(self) -> None:
        """将 stdout/stderr/Qt警告 同步写入日志文件。"""
        if hasattr(sys.stdout, "_ludiglot_tee"):
            return

        stream_lock = threading.Lock()

        class _TeeStream:
            def __init__(self, stream, log_path: Path) -> None:
                self._stream = stream
                self._log_path = log_path
                self._ludiglot_tee = True

            def write(self, data):
                if not data:
                    return
                with stream_lock:
                    try:
                        self._stream.write(data)
                    except Exception:
                        # Best-effort output; ignore stream write errors
                        pass
                    try:
                        self._log_path.parent.mkdir(parents=True, exist_ok=True)
                        with self._log_path.open("a", encoding="utf-8") as f:
                            f.write(data)
                    except Exception:
                        # Best-effort file logging; ignore write errors
                        pass

            def flush(self):
                with stream_lock:
                    try:
                        self._stream.flush()
                    except Exception:
                        # Best-effort flush; ignore stream flush errors
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
        container.setObjectName("OverlayRoot") # 最外层金边
        self.setCentralWidget(container)
        container.setMouseTracking(True)

        # 中间装饰色带层
        stripe_frame = QWidget(container)
        stripe_frame.setObjectName("StripeFrame") # 这里显示灰白带
        stripe_frame.setMouseTracking(True)

        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(7, 7, 7, 7) # 加大：让外框到色带之间的背景层显出来
        outer_layout.setSpacing(0)
        outer_layout.addWidget(stripe_frame)

        # 内部核心容器
        inner_frame = QWidget(stripe_frame)
        inner_frame.setObjectName("InnerFrame") # 这里显示核心背景和大圆角
        inner_frame.setMouseTracking(True)

        stripe_layout = QVBoxLayout(stripe_frame)
        stripe_layout.setContentsMargins(3, 3, 3, 3) # 保持：色带本身依然纤细
        stripe_layout.setSpacing(0)
        stripe_layout.addWidget(inner_frame)

        # 实际的内容布局都在 inner_frame 里
        layout = QVBoxLayout(inner_frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.title_label = QLabel("Ludiglot")
        self.title_label.setObjectName("Title")
        self.title_label.setFont(QFont("Segoe UI", 12))

        self.source_label = QTextEdit("等待捕获…")
        self.source_label.setObjectName("SourceText")
        self.source_label.setReadOnly(True)
        self.source_label.setAcceptRichText(True)  # 支持富文本
        self.source_label.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.source_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.source_label.setFrameStyle(QFrame.Shape.NoFrame)
        self.source_label.setMinimumHeight(60)
        self.source_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.cn_label = QTextEdit("")
        self.cn_label.setObjectName("AccentText")
        self.cn_label.setReadOnly(True)
        self.cn_label.setAcceptRichText(True)  # 显式启用富文本支持
        self.cn_label.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.cn_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cn_label.setFrameStyle(QFrame.Shape.NoFrame)
        self.cn_label.setMinimumHeight(80)
        self.cn_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("StatusText")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setObjectName("LogBox")
        self.log_box.setMinimumHeight(90)


        layout.addWidget(self.title_label)

        # 直接添加文本组件，移除卡片容器化
        layout.addWidget(self.source_label)
        
        self.star_divider = StarDivider(self)
        layout.addWidget(self.star_divider)
        
        layout.addWidget(self.cn_label)
        
        # 音频控制栏（进度条 + 播放/暂停按钮 + 时间显示）
        audio_control_layout = QHBoxLayout()
        self.play_pause_btn = PlayPauseButton(self)
        self.play_pause_btn.setObjectName("AudioControl")
        self.play_pause_btn.setFixedSize(28, 28)
        self.play_pause_btn.setEnabled(False)
        self.play_pause_btn.clicked.connect(self._toggle_audio_playback)
        self._icon_play = "▶"
        self._icon_pause = "Ⅱ"
        
        self.audio_slider = AudioWaveformProgressBar(self)
        self.audio_slider.setObjectName("AudioWaveformSlider")
        self.audio_slider.setEnabled(False)
        self.audio_slider.sigSeekStarted.connect(self._on_audio_seek_started)
        self.audio_slider.sigSeekFinished.connect(self._on_audio_seek_finished)
        
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("TimeLabel")
        self.time_label.setMinimumWidth(100)
        
        audio_control_layout.addWidget(self.play_pause_btn)
        audio_control_layout.addWidget(self.audio_slider, 1)
        audio_control_layout.addWidget(self.time_label)
        layout.addLayout(audio_control_layout)
        
        layout.addWidget(self.status_label)

        
        # 创建窗口右上角菜单按钮
        self._setup_window_menu()
    
    def _setup_window_menu(self) -> None:
        """创建窗口右上角下拉菜单 and 关闭按钮"""
        # 创建顶部控制栏小部件
        self.control_bar = QWidget(self)
        self.control_bar.setFixedHeight(45)
        
        # 使用水平布局来管理按钮
        layout = QHBoxLayout(self.control_bar)
        layout.setContentsMargins(0, 10, 12, 0)  # 边距
        layout.setSpacing(0)  # 按钮间距
        
        # 添加弹簧，将按钮推向右侧
        layout.addStretch()
        
        # 创建菜单按钮
        self.top_menu_btn = MenuIconButton(self.control_bar)
        self.top_menu_btn.setObjectName("TopMenuButton")
        layout.addWidget(self.top_menu_btn)
        
        # 创建关闭按钮
        self.top_close_btn = CloseIconButton(self.control_bar)
        self.top_close_btn.setObjectName("TopCloseButton")
        self.top_close_btn.clicked.connect(self.hide)
        layout.addWidget(self.top_close_btn)

        
        # 初始定位
        self._update_button_positions()
        
        # 创建下拉菜单
        self.window_menu = PersistentMenu(self)
        # self.top_menu_btn.setMenu(self.window_menu) # 禁用默认菜单，由 _show_window_menu 手动精确对齐
        
        # Update Database 操作
        update_action = QAction("Update Database", self)
        update_action.setToolTip("从游戏 Pak 重新解包并构建数据库")
        update_action.triggered.connect(self._update_database)
        self.window_menu.addAction(update_action)
        
        self.window_menu.addSeparator()

        # OCR 设置子菜单
        ocr_settings_menu = PersistentMenu("OCR Settings", self.window_menu)
        ocr_settings_menu.setStyleSheet(self.window_menu.styleSheet())
        self.window_menu.addMenu(ocr_settings_menu)

        # OCR 后端选择
        ocr_backend_menu = PersistentMenu("Backend", ocr_settings_menu)
        ocr_backend_menu.setStyleSheet(self.window_menu.styleSheet())
        ocr_settings_menu.addMenu(ocr_backend_menu)

        self.ocr_backend_group = QActionGroup(self)
        self.ocr_backend_group.setExclusive(True)
        for backend in ["auto", "glm_ollama", "paddle", "tesseract"]:
            display_name = {
                "auto": "Auto (Prefer WinOCR)",
                "glm_ollama": "GLM-OCR (Ollama)",
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
        font_settings_menu.setStyleSheet(self.window_menu.styleSheet())
        self.window_menu.addMenu(font_settings_menu)
        
        # 字号调节器
        font_size_menu = PersistentMenu("Size", font_settings_menu)
        font_size_menu.setStyleSheet(self.window_menu.styleSheet())
        font_settings_menu.addMenu(font_size_menu)
        
        # 共享调节器样式
        spinner_qss = """
            QAbstractSpinBox { 
                background: rgba(15, 18, 22, 255); 
                color: #f0f4f8; 
                border: 1px solid rgba(170, 155, 106, 90); 
                border-radius: 4px; 
                padding: 4px 22px 4px 6px; /* 22px 右边距：为右侧的增减按钮留出空间 */
                font-family: "Segoe UI", "Source Han Serif SC", sans-serif;
                font-size: 11px;
                selection-background-color: rgba(170, 155, 106, 80);
            }
            QAbstractSpinBox:hover {
                border: 1px solid rgba(170, 155, 106, 200);
            }
            QAbstractSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right; /* 按钮靠右边 */
                width: 18px;
                height: 11px;
                border-left: 1px solid rgba(170, 155, 106, 90); /* 左侧分割线 */
                background: rgba(170, 155, 106, 20);
            }
            QAbstractSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right; /* 按钮靠右边 */
                width: 18px;
                height: 11px;
                border-left: 1px solid rgba(170, 155, 106, 90); /* 左侧分割线 */
                border-top: 1px solid rgba(170, 155, 106, 90);
                background: rgba(170, 155, 106, 20);
            }
            QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { 
                background: rgba(170, 155, 106, 60); 
            }
            QAbstractSpinBox::up-arrow {
                image: none; /* 彻底禁用图像，交由底层 Gold 派生类 paintEvent 强行矢量精准绘制 */
                width: 0px;
                height: 0px;
            }
            QAbstractSpinBox::down-arrow {
                image: none; /* 彻底禁用图像，交由底层 Gold 派生类 paintEvent 强行矢量精准绘制 */
                width: 0px;
                height: 0px;
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
        self.size_spin = GoldSpinBox()
        self.size_spin.setRange(8, 72)
        self.size_spin.setFixedWidth(65)
        self.size_spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        self.size_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
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
        letter_spacing_menu.setStyleSheet(self.window_menu.styleSheet())
        font_settings_menu.addMenu(letter_spacing_menu)
        
        spacing_action = QWidgetAction(self)
        spacing_widget = QWidget()
        spacing_layout = QHBoxLayout(spacing_widget)
        spacing_layout.setContentsMargins(10, 2, 10, 2)
        spacing_layout.setSpacing(10)
        spacing_label = QLabel("Spacing")
        spacing_label.setStyleSheet("color: white; font-weight: normal;")
        self.spacing_spin = GoldDoubleSpinBox()
        self.spacing_spin.setRange(-10, 50)
        self.spacing_spin.setSingleStep(0.5)
        self.spacing_spin.setFixedWidth(65)
        self.spacing_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        line_spacing_menu.setStyleSheet(self.window_menu.styleSheet())
        font_settings_menu.addMenu(line_spacing_menu)
        
        lh_action = QWidgetAction(self)
        lh_widget = QWidget()
        lh_layout = QHBoxLayout(lh_widget)
        lh_layout.setContentsMargins(10, 2, 10, 2)
        lh_layout.setSpacing(10)
        lh_label = QLabel("Line Spacing")
        lh_label.setStyleSheet("color: white; font-weight: normal;")
        self.lh_spin = GoldDoubleSpinBox()
        self.lh_spin.setRange(0.5, 5.0)
        self.lh_spin.setSingleStep(0.1)
        self.lh_spin.setFixedWidth(65)
        self.lh_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        font_family_menu.setStyleSheet(self.window_menu.styleSheet())
        if font_settings_menu:
            font_settings_menu.addMenu(font_family_menu)
            
            # 英文字体
            en_font_menu = PersistentMenu("English", font_family_menu)
            en_font_menu.setStyleSheet(self.window_menu.styleSheet())
            font_family_menu.addMenu(en_font_menu)
            self._setup_font_selection_menu(en_font_menu, "en")
            
            # 中文字体
            cn_font_menu = PersistentMenu("Chinese", font_family_menu)
            cn_font_menu.setStyleSheet(self.window_menu.styleSheet())
            font_family_menu.addMenu(cn_font_menu)
            self._setup_font_selection_menu(cn_font_menu, "cn")

        self.window_menu.addSeparator()
        
        # 菜单展开方向 - 使用 PersistentMenu 保证无缝去边框和精确的 2px 鸣潮圆角
        direction_menu = PersistentMenu("Menu Direction", self.window_menu)
        direction_menu.setStyleSheet(self.window_menu.styleSheet())
        self.window_menu.addMenu(direction_menu)
        if direction_menu:
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
        
        direction = getattr(self, "_menu_direction", "right")
        
        if direction == "left":
            # 强制右边缘对齐：菜单左 X = 按钮右 X - 菜单宽度 - 2 (视觉缝隙补偿)
            target_x = btn_right_x - menu_w - 2
            self.window_menu.exec(QPoint(target_x, btn_bottom_y))
        else:
            # 向右展开：左边缘对齐 + 2 (默认行为)
            self.window_menu.exec(QPoint(btn_topleft.x() + 2, btn_bottom_y))
    
    def _initialize_menu_style(self):
        """初始化菜单样式，确保所有用户都能看到正确的样式"""
        direction = getattr(self, "_menu_direction", "right")
        layout_dir = Qt.LayoutDirection.RightToLeft if direction == "left" else Qt.LayoutDirection.LeftToRight
        item_align = "right" if direction == "left" else "left"
        arrow_svg = (
            "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path fill='transparent' d='M0 0 H10 V10 H0 Z'/></svg>"
            if direction == "left" else
            "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 10 10'><path fill='%23aa9b6a' d='M3 1 L7 5 L3 9 Z'/></svg>"
        )
        
        menu_style = f"""
            QMenu {{
                background-color: rgba(15, 18, 22, 245);
                color: #dcdcdc;
                font-family: "Segoe UI", "Source Han Serif SC", sans-serif;
                font-size: 12px;
                border: 1px solid rgba(170, 155, 106, 90);
                border-radius: 2px;
                padding: 0px; /* 彻底移除上下左右 padding，使首尾条目高亮完美触达菜单边界 */
                margin: 0px; /* 强制外边距为0，彻底消除一切空洞的黑底缝隙 */
            }}
            QMenu::item {{
                padding: 5px 10px; /* 缩减左右边距以紧凑界面，解决左右白边过宽问题 */
                margin: 0px; 
                border-radius: 0px; 
                text-align: {item_align};
                border: none; /* 彻底移除所有边框导致的额外空白断层 */
            }}
            QMenu::item:checked {{
                background-color: rgba(170, 155, 106, 35);
                color: #ffffff;
            }}
            QMenu::item:selected {{
                background-color: rgba(170, 155, 106, 25);
                color: #ffffff;
            }}
            QMenu::item:disabled {{
                color: rgba(255, 255, 255, 40);
                background-color: transparent;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: rgba(170, 155, 106, 40);
                margin: 0px 8px; /* 彻底移除上下 margin，使选项高亮与分隔线之间零缝隙完美贴合 */
            }}
            QMenu::right-arrow {{
                width: 8px;
                height: 8px;
                image: url("{arrow_svg}");
            }}
            QMenu::left-arrow {{
                width: 8px;
                height: 8px;
                image: url("{arrow_svg}");
            }}
            QMenu::indicator {{
                width: 0px;
                height: 0px;
                image: none;
            }}
            QLabel {{
                color: #dcdcdc;
                font-family: "Segoe UI", "Source Han Serif SC", sans-serif;
                font-size: 11px;
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
        
        direction = getattr(self, "_menu_direction", "right")
        
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
        arrow_svg = (
            "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path fill='transparent' d='M0 0 H10 V10 H0 Z'/></svg>"
            if direction == "left" else
            "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 10 10'><path fill='%23aa9b6a' d='M3 1 L7 5 L3 9 Z'/></svg>"
        )
        
        menu_style = f"""
            QMenu {{
                background-color: rgba(15, 18, 22, 245);
                color: #dcdcdc;
                font-family: "Segoe UI", "Source Han Serif SC", sans-serif;
                font-size: 12px;
                border: 1px solid rgba(170, 155, 106, 90);
                border-radius: 2px;
                padding: 0px; /* 彻底移除上下左右 padding，使首尾条目高亮完美触达菜单边界 */
                margin: 0px; /* 强制外边距为0，彻底消除一切空洞的黑底缝隙 */
            }}
            QMenu::item {{
                padding: 5px 10px; /* 缩减左右边距以紧凑界面，解决左右白边过宽问题 */
                margin: 0px; /* 强制项与项之间的外边距为0 */
                border-radius: 0px; /* 移除高亮圆角，防止圆角收缩导致左右留空丑陋 */
                text-align: {item_align};
                border-left: 3px solid transparent; 
            }}
            QMenu::item:checked {{
                background-color: rgba(170, 155, 106, 35);
                color: #ffffff;
                border-left: 3px solid #aa9b6a; /* 保证高亮左侧绝对直角 */
            }}
            QMenu::item:selected {{
                background-color: rgba(170, 155, 106, 25);
                color: #ffffff;
                border-left: 3px solid #aa9b6a; /* 保证高亮左侧绝对直角 */
            }}
            QMenu::item:disabled {{
                color: rgba(255, 255, 255, 40);
                background-color: transparent;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: rgba(170, 155, 106, 40);
                margin: 0px 8px; /* 彻底移除上下 margin，使选项高亮与分隔线之间零缝隙完美贴合 */
            }}
            QMenu::right-arrow {{
                width: 8px;
                height: 8px;
                image: url("{arrow_svg}");
            }}
            QMenu::left-arrow {{
                width: 8px;
                height: 8px;
                image: url("{arrow_svg}");
            }}
            QMenu::indicator {{
                width: 0px;
                height: 0px;
                image: none;
            }}
            QLabel {{
                color: #dcdcdc;
                font-family: "Segoe UI", "Source Han Serif SC", sans-serif;
                font-size: 11px;
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
            # 基于内框（inner_frame）计算位置：
            # 外部边距是 7 (outer_layout) + 3 (stripe_layout) = 10 px
            # 顶部与内框顶部对齐，即 y = 10 px
            # 宽度为整个内框宽度，即 self.width() - 20
            margin = 10
            self.control_bar.setGeometry(margin, margin, self.width() - 2 * margin, 45)

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
    
    def _build_content_fonts(self) -> tuple[QFont, QFont]:
        """构造英文/中文内容字体对象。"""
        # 确保字号合法（避免Qt警告）- 处理所有边界情况
        try:
            size_val = int(self.current_font_size) if self.current_font_size else 13
        except (ValueError, TypeError):
            size_val = 13
        valid_size = max(8, min(72, size_val))

        weight_map = {
            "Light": QFont.Weight.Light,
            "Normal": QFont.Weight.Normal,
            "SemiBold": QFont.Weight.DemiBold,
            "Bold": QFont.Weight.Bold,
            "Heavy": QFont.Weight.Black,
        }
        weight_val = weight_map.get(self.current_font_weight, QFont.Weight.DemiBold)

        en_font = QFont()
        en_font.setFamily(self.current_font_en)
        en_font.setPointSize(valid_size)
        en_font.setWeight(weight_val)
        en_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.current_letter_spacing)

        cn_font = QFont()
        cn_font.setFamily(self.current_font_cn)
        cn_font.setPointSize(valid_size)
        cn_font.setWeight(weight_val)
        cn_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.current_letter_spacing)
        return en_font, cn_font

    def _apply_text_document_style(self, editor: QTextEdit, font: QFont, force_char_style: bool) -> None:
        """对 QTextEdit 文档应用实时字体/行距设置。"""
        from PyQt6.QtGui import QTextCursor, QTextBlockFormat, QTextCharFormat

        doc = editor.document()
        doc.setDefaultFont(font)

        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)

        # 纯文本模式下强制覆盖字符格式，避免被 QSS 固定字号/字重锁死
        if force_char_style:
            char_fmt = QTextCharFormat()
            char_fmt.setFont(font)
            cursor.mergeCharFormat(char_fmt)

        # Qt 对 QTextEdit 的 QSS line-height 支持有限，改用文档块格式保证实时生效
        try:
            line_height_ratio = float(self.current_line_spacing)
        except (TypeError, ValueError):
            line_height_ratio = 1.2
        line_height_percent = int(max(50, min(400, line_height_ratio * 100)))
        block_fmt = QTextBlockFormat()
        try:
            # PyQt6 expects int for heightType; enum object may raise TypeError.
            height_type = int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        except Exception:
            height_type = int(getattr(QTextBlockFormat, "ProportionalHeight", 1))
        block_fmt.setLineHeight(float(line_height_percent), height_type)
        cursor.mergeBlockFormat(block_fmt)

    def _apply_font_settings(self):
        """应用字体设置到所有UI元素"""
        en_font, cn_font = self._build_content_fonts()

        # 应用到控件默认字体
        self.source_label.setFont(en_font)
        self.cn_label.setFont(cn_font)

        # 重新渲染文本，并对文档层强制应用字体/行距
        self._refresh_text_display()
        self._apply_text_document_style(self.source_label, en_font, force_char_style=not self._last_en_is_html)
        self._apply_text_document_style(self.cn_label, cn_font, force_char_style=not self._last_cn_is_html)

        self.signals.log.emit(
            f"[UI] 字体设置：{self.current_font_size}pt, {self.current_font_weight}, "
            f"字距{self.current_letter_spacing}px, 行距{self.current_line_spacing:.1f}x"
        )

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
        self.current_font_size = max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, self.current_font_size + delta))
        
        # 应用字体设置
        self._apply_font_settings()
        
        # 更新菜单显示
        if hasattr(self, 'font_size_label_action'):
            self.font_size_label_action.setText(f"{self.current_font_size}pt")
        
        self.signals.log.emit(f"[UI] 字体大小调整为 {self.current_font_size}pt")
    
    def _update_database(self) -> None:
        """更新数据库：从游戏 Pak 重新解包并构建"""
        from ludiglot.ui.dialogs import StyledDialog, StyledProgressDialog
        from ludiglot.ui.db_updater import DatabaseUpdateThread
        
        # 检查 Pak 配置
        if not (self.config.game_pak_root or self.config.game_install_root):
            StyledDialog.warning(
                self,
                "配置错误",
                "未设置游戏路径。\n请在 config/settings.json 中配置 game_pak_root 或 game_install_root。"
            )
            return
        
        # 确认对话框
        reply = StyledDialog.question(
            self,
            "更新数据库",
            f"即将从游戏 Pak 解包并重建数据库。\n\n"
            f"游戏路径: {self.config.game_pak_root or self.config.game_install_root}\n"
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
        try:
            style_path = Path(__file__).resolve().parent / "style.qss"
            if style_path.exists():
                qss = style_path.read_text(encoding="utf-8")
                self.setStyleSheet(qss)
                self.signals.log.emit(f"[UI] QSS 样式加载成功: {style_path}")
            else:
                self.signals.log.emit(f"[UI] QSS 样式文件不存在: {style_path}")
        except Exception as e:
            self.signals.log.emit(f"[UI] QSS 样式加载异常: {e}")

    def _connect_signals(self) -> None:
        self.signals.status.connect(self.status_label.setText)
        self.signals.error.connect(self._show_error)
        self.signals.result.connect(self._show_result)
        self.signals.log.connect(self._append_log)

    def _initialize_resources(self) -> None:
        callbacks = OverlayRuntimeCallbacks(
            status=self.signals.status.emit,
            log=self.signals.log.emit,
            error=self.signals.error.emit,
        )
        result = initialize_overlay_runtime(self.config, self.engine, callbacks)
        if not result.success or result.resources is None:
            return

        self.resources_initialized.emit(result.resources)

    def _on_runtime_resources_initialized(self, resources) -> None:
        self._apply_runtime_resources(resources)
        self.signals.status.emit("就绪")
        self.resources_loaded.emit()

    def _apply_runtime_resources(self, resources) -> None:
        self.db = resources.db
        self.matcher = resources.matcher
        self.audio_resolver = resources.audio_resolver
        self.skill_param_resolver = resources.skill_param_resolver
        self.voice_map = resources.voice_map
        self.voice_event_index = resources.voice_event_index
        self.audio_index = resources.audio_index
        self._external_wem_root = resources.external_wem_root
        self.audio_runtime = OverlayAudioRuntime(
            self.config,
            self.audio_resolver,
            self.audio_index,
            self.signals.log.emit,
        )

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
            self.play_pause_btn.set_playing(False)
            self.audio_timer.stop()
            self.signals.status.emit("已暂停")
        else:
            # 如果播放已经结束（进度在最末尾），重新播放时回到起点
            if self.player.get_position() >= 0.99:
                self.player.seek(0.0)
            self.player.resume()
            self.play_pause_btn.set_playing(True)
            self.audio_timer.start()
            
            # 更新状态为当前播放的文件名
            src_name = ""
            if hasattr(self.player, "_player") and self.player._player is not None:
                src_path = self.player._player.source().toLocalFile()
                if src_path:
                    src_name = Path(src_path).name
            if src_name:
                self.signals.status.emit(f"正在播放: {src_name}")
            else:
                self.signals.status.emit("正在播放")
    
    def _on_audio_seek_started(self) -> None:
        """波形拖动开始。"""
        pass
    
    def _on_audio_seek_finished(self, position: float) -> None:
        """波形释放时跳转到新位置。"""
        import time
        self._last_seek_time = time.time()
        
        self.player.seek(position)
        
        # 立即在 UI 上更新进度和时间，消除异步延迟感
        duration = self.player.get_duration()
        if duration > 0:
            self.audio_slider.set_progress(position, duration)
            current_ms = int(position * duration)
            current_sec = current_ms // 1000
            duration_sec = duration // 1000
            self.time_label.setText(f"{current_sec//60:02d}:{current_sec%60:02d} / {duration_sec//60:02d}:{duration_sec%60:02d}")
    
    def _update_audio_progress(self) -> None:
        """定时更新音频进度条和时间标签。"""
        # 如果刚进行过 seek，在 200ms 内不从播放器同步位置，避免异步延迟导致进度条跳回原处
        import time
        if hasattr(self, '_last_seek_time') and time.time() - self._last_seek_time < 0.2:
            return

        # 检测是否自然播放完毕（即使 is_playing 还是 True，如果底层 QMediaPlayer 状态已经是 EndOfMedia）
        is_natural_end = False
        if hasattr(self.player, "_player") and self.player._player is not None:
            from PyQt6.QtMultimedia import QMediaPlayer
            if self.player._player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                is_natural_end = True
                self.player.stop()  # 这会设置播放器的 _is_playing 为 False 并停止播放
        
        if not self.player.is_playing() or is_natural_end:
            self.audio_timer.stop()
            self.play_pause_btn.set_playing(False)
            duration = self.player.get_duration()
            if duration > 0:
                self.audio_slider.set_progress(1.0, duration)
                current_sec = duration // 1000
                self.time_label.setText(f"{current_sec//60:02d}:{current_sec%60:02d} / {current_sec//60:02d}:{current_sec%60:02d}")
            if is_natural_end:
                self.signals.status.emit("播放已结束")
            return
        
        position = self.player.get_position()
        duration = self.player.get_duration()
        
        # 更新进度条（但不在拖动时更新）
        if not self.audio_slider.is_dragging():
            self.audio_slider.set_progress(position, duration)
        
        # 更新时间标签
        if duration > 0:
            current_ms = int(position * duration)
            current_sec = current_ms // 1000
            duration_sec = duration // 1000
            self.time_label.setText(f"{current_sec//60:02d}:{current_sec%60:02d} / {duration_sec//60:02d}:{duration_sec%60:02d}")

    def _translate_title(self, title: str) -> str:
        """标题翻译委托给核心匹配器，UI 层只负责调用。"""
        if not self.matcher:
            return ""
        try:
            return self.matcher.resolve_title_cn(title)
        except Exception:
            return ""

    def _on_mode_changed(self, mode: str) -> None:
        self.engine.set_mode(mode)
        self.config.ocr_mode = mode
        self.signals.status.emit(f"OCR 模式: {mode}")
        self._persist_window_position()

    def _on_backend_changed(self, backend: str) -> None:
        self.config.ocr_backend = backend
        try:
            self.engine.allow_paddle = backend == "paddle"
        except Exception:
            # OCR backend configuration is optional; on any error we fall back to the engine's default
            pass
        self.signals.status.emit(f"OCR 后端: {backend}")
        self._persist_window_position()

    def trigger_capture(self) -> None:
        self.stop_audio()
        self.capture_requested.emit(True)

    def _capture_and_process_async(self, force_select: bool = False) -> None:
        if self._capture_in_progress:
            self.signals.log.emit("[HOTKEY] 正在处理中，忽略重复触发")
            return
        self._capture_in_progress = True
        import time
        t_start = time.time()
        selected_region: CaptureRegion | None = None
        snapshot: DesktopSnapshot | None = None
        thread_started = False
        try:
            # 新一轮 OCR 前先停止当前播放，避免旧音频与新结果串音
            self.stop_audio(emit_status=False)
            self.last_text_key = None
            self.last_hash = None
            self.last_event_name = None
            self.signals.log.emit("[HOTKEY] 触发捕获")
            if force_select or self.config.capture_mode == "select":
                self.signals.status.emit("冻结屏幕…")
                t_snap_start = time.time()
                try:
                    snapshot = self._capture_desktop_snapshot()
                except Exception as exc:
                    snapshot = None
                    self.signals.log.emit(f"[CAPTURE] 预截图失败，回退实时框选: {exc}")
                t_snap_end = time.time()
                if snapshot is not None:
                    self.signals.log.emit(f"[PERF] 屏幕快照耗时: {(t_snap_end - t_snap_start):.3f}s")
                self.signals.status.emit("请选择 OCR 区域…")
                t_select_start = time.time()
                selected_region = self._select_region(snapshot)
                t_select_end = time.time()
                self.signals.log.emit(f"[PERF] 区域选择耗时: {(t_select_end - t_select_start):.3f}s")
                if selected_region is None:
                    self.signals.status.emit("已取消")
                    return
            threading.Thread(
                target=self._capture_and_process,
                args=(selected_region, snapshot),
                daemon=True,
            ).start()
            thread_started = True
            self.signals.log.emit(f"[PERF] 异步调用总耗时: {(time.time() - t_start):.3f}s")
        except Exception as exc:
            self.signals.log.emit(f"[CAPTURE] 触发捕获异常: {exc}")
            self.signals.status.emit("捕获失败")
        finally:
            # 仅在未成功启动后台线程时（后台线程会自己清除标志）清除
            if not thread_started:
                self._capture_in_progress = False

    def _capture_and_process(self, selected_region: CaptureRegion | None, snapshot: DesktopSnapshot | None) -> None:
        import time
        t_total_start = time.time()
        try:
            self._do_capture_and_process(selected_region, snapshot, t_total_start)
        finally:
            self._capture_in_progress = False

    def _do_capture_and_process(self, selected_region: CaptureRegion | None, snapshot: DesktopSnapshot | None, t_total_start: float) -> None:
        run_capture_match_workflow(
            CaptureProcessRequest(
                capture_image=lambda: self._capture_image_to_memory(selected_region, snapshot),
                ocr_engine=self.engine,
                matcher=self.matcher,
                ocr_backend=self.config.ocr_backend,
                debug_dump_input=getattr(self.config, "ocr_debug_dump_input", False),
                debug_dump_dir=self.config.image_path.parent if getattr(self.config, "image_path", None) else Path.cwd(),
            ),
            CaptureProcessCallbacks(
                status=self.signals.status.emit,
                log=self.signals.log.emit,
                error=self.signals.error.emit,
                result=self.signals.result.emit,
            ),
        )

    def _expand_region(self, region: CaptureRegion) -> CaptureRegion:
        try:
            import mss
            with mss.mss() as sct:
                monitor = self._monitor_geometry_from_mapping(sct.monitors[1])
        except Exception:
            return region
        return expand_region_within_monitor(region, monitor)

    def _preprocess_image(self, image_path: Path) -> Path:
        try:
            from PIL import Image, ImageOps
            img = Image.open(image_path)
            
            # 1. 尺寸优化：移除强制放大
            # 这里的放大逻辑已被移动到 OCREngine 内部，采用更智能的 "Text-Grab" 自适应算法
            # 此处只需保留基本的格式转换
            processed = False

            # 2. 模式转换：转为灰度
            if img.mode != 'L':
                img = img.convert('L')
                processed = True
                
            # 3. 对比度增强
            img = ImageOps.autocontrast(img)
            processed = True
            
            # Save Debug Image
            try:
                debug_p = image_path.parent / "last_ocr_input.png"
                img.save(debug_p)
            except Exception: pass
            
            if processed:
                processed_path = image_path.parent / f"{image_path.stem}_proc{image_path.suffix}"
                img.save(processed_path)
                return processed_path
                
            return image_path
        except Exception as e:
            self.signals.log.emit(f"[PRE] 预处理失败: {e}")
            return image_path

    def _capture_image_to_memory(self, selected_region: CaptureRegion | None, snapshot: DesktopSnapshot | None = None) -> Any:
        return capture_input_to_memory(
            capture_options_from_config(self.config),
            selected_region=selected_region,
            snapshot=snapshot,
            adapters=CaptureInputAdapters(
                select_region=self._select_region,
                crop_snapshot=self._crop_snapshot,
                on_fallback=self.signals.log.emit,
            ),
        )

    def _needs_tesseract(self, lines: list[tuple[str, float]]) -> bool:
        return needs_tesseract(lines)

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

    def _display_preferences(self) -> DisplayPreferences:
        return DisplayPreferences(
            gender_preference=getattr(self.config, "gender_preference", "female"),
            font_en=self.current_font_en,
            font_cn=self.current_font_cn,
            font_size=int(self.current_font_size) if self.current_font_size else 13,
            font_weight_css=self._font_weight_css(),
            line_spacing=float(self.current_line_spacing) if self.current_line_spacing else 1.2,
            letter_spacing=float(self.current_letter_spacing) if self.current_letter_spacing else 0.0,
        )

    def _apply_display_pane(self, widget: QTextEdit, pane, *, lang: str) -> bool:
        if pane.is_html and pane.rendered_html is not None:
            widget.setHtml(pane.rendered_html)
            return True
        widget.setPlainText(pane.display_text)
        return False

    def _show_result(self, result: Dict[str, Any]) -> None:
        import time
        t_show_start = time.time()
        self.signals.log.emit("[DEBUG] _show_result called")
        self.signals.log.emit("[PERF] _show_result 开始")

        try:
            self.stop_audio(emit_status=False)
            self.last_match = result
            self.last_text_key = None
            self.last_hash = None
            self.last_event_name = None

            model = shape_translation_display(
                result,
                preferences=self._display_preferences(),
                param_resolver=self.skill_param_resolver,
                title_resolver=self._translate_title,
                voice_map=self.voice_map,
                voice_event_index=self.voice_event_index,
            )

            self.signals.log.emit("[WINDOW] 设置文本内容")
            self._last_en_is_html = self._apply_display_pane(self.source_label, model.source, lang="en")
            self._last_cn_is_html = self._apply_display_pane(self.cn_label, model.target, lang="cn")
            self._last_en_raw = model.source.display_text
            self._last_cn_raw = model.target.display_text

            for line in model.log_lines:
                self.signals.log.emit(line)

            audio_candidate = model.audio_candidate
            if audio_candidate and audio_candidate.origin == "multi":
                self.signals.log.emit("[WINDOW] 多条目模式：检测到高置信度音频，启用音频控件")
                self.play_pause_btn.setEnabled(True)
                self.audio_slider.setEnabled(True)
                self._play_audio_for_key(audio_candidate.text_key)
            elif audio_candidate:
                t_audio = time.time()
                identity = None
                if self.audio_runtime:
                    identity = self.audio_runtime.resolve_intent(
                        AudioIntent(
                            text_key=audio_candidate.text_key,
                            db_event=audio_candidate.db_event,
                            db_hash=audio_candidate.db_hash,
                            origin=audio_candidate.origin,
                        )
                    )
                if identity:
                    self.last_text_key = identity.text_key
                    self.last_hash = identity.hash_value
                    self.last_event_name = identity.event_name
                    if identity.source_type == "db_fallback":
                        self.signals.log.emit(f"[MATCH] text_key={audio_candidate.text_key} 使用数据库哈希={self.last_hash}")
                    else:
                        self.signals.log.emit(f"[MATCH] text_key={audio_candidate.text_key} hash={self.last_hash} ({identity.source_type})")
                else:
                    self.last_text_key = audio_candidate.text_key
                    self.signals.log.emit(f"[MATCH] text_key={audio_candidate.text_key} 未找到对应音频")
                self.signals.log.emit(f"[PERF] 音频解析: {(time.time()-t_audio)*1000:.1f}ms")
            elif model.is_multi:
                self.signals.log.emit("[WINDOW] 禁用音频控件（多条目模式）")

            en_font, cn_font = self._build_content_fonts()
            self._apply_text_document_style(self.source_label, en_font, force_char_style=not self._last_en_is_html)
            self._apply_text_document_style(self.cn_label, cn_font, force_char_style=not self._last_cn_is_html)

            has_audio = self.last_hash is not None or (audio_candidate is not None and audio_candidate.origin == "multi")
            self.play_pause_btn.setEnabled(has_audio)
            self.audio_slider.setEnabled(has_audio)

            if model.is_multi:
                self.show()
                self.signals.log.emit("[WINDOW] 已调用show()")
                self.raise_()
                self.signals.log.emit("[WINDOW] 已调用raise_()")
                self.activateWindow()
                self.signals.log.emit("[WINDOW] 窗口激活完成")
            else:
                self.signals.log.emit("[DEBUG] Calling show_and_activate...")
                self.show_and_activate()
                self.signals.log.emit("[DEBUG] show_and_activate returned.")

            if self.config.play_audio and self.last_hash is not None:
                self.signals.log.emit("[DEBUG] Calling play_audio...")
                self.play_audio()
                self.signals.log.emit("[DEBUG] play_audio returned.")

            self.signals.log.emit(f"[PERF] _show_result 总耗时: {(time.time()-t_show_start)*1000:.1f}ms")
        except Exception as exc:
            self.signals.error.emit(f"显示结果失败: {exc}")
            import traceback
            self.signals.log.emit(f"[ERROR] {traceback.format_exc()}")

    def _convert_game_html(self, text: str, lang: str = "cn") -> str:
        return convert_game_html(text, lang=lang, preferences=self._display_preferences())

    def _extract_numeric_values_from_context(self, ocr_context: str) -> list[str]:
        return extract_numeric_values_from_context(ocr_context)

    def _resolve_display_placeholders(
        self,
        text: str,
        lang: str = "en",
        ocr_context: str | None = None,
        text_key: str | None = None,
    ) -> str:
        return resolve_display_placeholders(
            text,
            lang=lang,
            ocr_context=ocr_context,
            text_key=text_key,
            gender_preference=getattr(self.config, "gender_preference", "female"),
            param_resolver=self.skill_param_resolver,
        )


    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        self._append_log(f"[ERROR] {message}")

    def _append_log(self, message: str) -> None:
        # 确保单次 sys.stdout.write 减少多线程交错导致的信息粘连
        msg_with_newline = message if message.endswith("\n") else message + "\n"
        try:
            sys.stdout.write(msg_with_newline)
            sys.stdout.flush()
        except Exception:
            # Best-effort console output; ignore stdout write/flush errors
            pass

        self.log_box.append(message)
        
        # 若 stdout 已被 Tee，_TeeStream 已经处理过写入文件了
        if hasattr(sys.stdout, "_ludiglot_tee"):
            return
            
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(msg_with_newline)
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

    def stop_audio(self, emit_status: bool = True) -> None:
        if hasattr(self, "player"):
            self.player.stop()
            if emit_status:
                self.signals.status.emit("已停止播放")
            
            # 重置音频控制UI
            if hasattr(self, 'audio_timer'):
                self.audio_timer.stop()
            if hasattr(self, 'play_pause_btn'):
                self.play_pause_btn.set_playing(False)
                self.play_pause_btn.setEnabled(False)
            if hasattr(self, 'audio_slider'):
                self.audio_slider.set_progress(0)
                self.audio_slider.setEnabled(False)
            if hasattr(self, 'time_label'):
                self.time_label.setText("00:00 / 00:00")

    def _play_audio_for_key(self, text_key: str) -> None:
        if not text_key:
            return
        identity = self.audio_runtime.resolve_intent(AudioIntent(text_key=text_key, origin="multi")) if self.audio_runtime else None
        if not identity:
            self.signals.log.emit(f"[AUDIO] text_key={text_key} 未找到对应音频，跳过播放")
            return
        self.last_text_key = identity.text_key
        self.last_hash = identity.hash_value
        self.last_event_name = identity.event_name
        self.signals.log.emit(f"[AUDIO] text_key={text_key} hash={self.last_hash} ({identity.source_type})")
        if self.config.play_audio:
            self.play_audio()

    def play_audio(self) -> None:
        if self.last_hash is None or not self.config.audio_cache_path or not self.audio_runtime:
            return

        try:
            print("[DEBUG] play_audio started", flush=True)
            identity = AudioPlaybackIdentity(
                text_key=self.last_text_key,
                hash_value=int(self.last_hash),
                event_name=self.last_event_name,
                source_type="unknown",
            )
            decision = self.audio_runtime.prepare_playback(identity)
            self.audio_index = self.audio_runtime.audio_index

            if decision.identity:
                self.last_text_key = decision.identity.text_key
                self.last_hash = decision.identity.hash_value
                self.last_event_name = decision.identity.event_name
                print(f"[DEBUG] play_audio resolved: {decision.identity.source_type}", flush=True)

            if decision.path is None:
                self.stop_audio(emit_status=False)
                self.signals.status.emit(decision.status_message or "未找到对应音频文件")
                print("[DEBUG] play_audio: path not found", flush=True)
                return

            self.signals.status.emit(f"正在播放: {decision.path.name}")
            print(f"[DEBUG] Invoking self.player.play: {decision.path}", flush=True)
            self.player.play(str(decision.path), block=False)

            self.play_pause_btn.setEnabled(True)
            self.play_pause_btn.set_playing(True)
            self.audio_slider.setEnabled(True)
            self.audio_slider.set_progress(0)
            self.audio_timer.start()
        except Exception as e:
            print(f"[ERROR] play_audio crashed: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.signals.error.emit(f"播放失败: {e}")



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
        if getattr(self, "disable_auto_hide", False):
            return super().eventFilter(obj, event)
            
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
                self._persist_window_position()
            self._persist_window_position()
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        """窗口大小改变事件：更新按钮位置"""
        super().resizeEvent(event)
        self._update_button_positions()

    def _restore_window_position(self) -> None:
        try:
            defaults = OverlayPreferences(
                window_pos=WindowPoint(*self.config.window_pos) if self.config.window_pos else None,
                font_size=self.current_font_size,
                font_weight=self.current_font_weight,
                letter_spacing=self.current_letter_spacing,
                line_spacing=self.current_line_spacing,
                menu_direction=getattr(self, "_menu_direction", "right"),
                font_en=self.current_font_en,
                font_cn=self.current_font_cn,
                ocr_backend=getattr(self.config, "ocr_backend", "auto"),
                ocr_mode=getattr(self.config, "ocr_mode", "auto"),
            )
            prefs = ConfigJsonStore(self._config_path).load_overlay_preferences(defaults)

            if prefs.window_size:
                self.resize(prefs.window_size.width, prefs.window_size.height)
                self.signals.log.emit(f"[RECOVERY] 恢复窗口尺寸: {prefs.window_size.width}x{prefs.window_size.height}")

            self.current_font_size = prefs.font_size
            self.current_font_weight = prefs.font_weight
            self.current_letter_spacing = prefs.letter_spacing
            self.current_line_spacing = prefs.line_spacing
            self.current_font_en = prefs.font_en or self.current_font_en
            self.current_font_cn = prefs.font_cn or self.current_font_cn
            self._menu_direction = prefs.menu_direction

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

            QTimer.singleShot(150, lambda d=self._menu_direction: self._set_menu_direction(d))
            self.signals.log.emit(
                f"[RECOVERY] 恢复 UI 设置: {self.current_font_size}pt, 字距{self.current_letter_spacing}px, 行距{self.current_line_spacing}x"
            )
        except Exception as e:
            self.signals.log.emit(f"[RECOVERY] 恢复配置失败: {e}")
            return

        if prefs.window_pos:
            restored = clamp_window_position(
                prefs.window_pos,
                WindowSize(self.width(), self.height()),
                self._available_window_bounds(),
            )
            self.move(restored.x, restored.y)
            self.signals.log.emit(f"[RECOVERY] 恢复窗口位置: {restored.x}, {restored.y}")

        self._apply_font_settings()

    def _available_window_bounds(self) -> list[WindowBounds]:
        bounds: list[WindowBounds] = []
        for screen in QGuiApplication.screens():
            geo = screen.availableGeometry()
            bounds.append(
                WindowBounds(
                    left=int(geo.left()),
                    top=int(geo.top()),
                    width=int(geo.width()),
                    height=int(geo.height()),
                )
            )
        return bounds

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
            if not self.isVisible():
                return

            pos = self.pos()
            size = self.size()
            ConfigJsonStore(self._config_path).save_overlay_preferences(
                OverlayPreferences(
                    window_pos=WindowPoint(int(pos.x()), int(pos.y())),
                    window_size=WindowSize(int(size.width()), int(size.height())),
                    font_size=self.current_font_size,
                    font_weight=self.current_font_weight,
                    letter_spacing=self.current_letter_spacing,
                    line_spacing=self.current_line_spacing,
                    menu_direction=getattr(self, "_menu_direction", "right"),
                    font_en=self.current_font_en,
                    font_cn=self.current_font_cn,
                    ocr_backend=getattr(self.config, "ocr_backend", "auto"),
                    ocr_mode=getattr(self.config, "ocr_mode", "auto"),
                )
            )
        except Exception:
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

    def _pil_to_pixmap(self, img, target_size: QSize | None = None) -> QPixmap:
        try:
            from PIL import Image
        except Exception as exc:
            raise RuntimeError("缺少 Pillow，无法生成截图背景") from exc
        if not isinstance(img, Image.Image):
            raise RuntimeError("无效截图对象，无法生成截图背景")
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        qimage = qimage.copy()
        pixmap = QPixmap.fromImage(qimage)
        if target_size and (pixmap.width() != target_size.width() or pixmap.height() != target_size.height()):
            pixmap = pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return pixmap

    def _monitor_geometry_from_mapping(self, monitor: dict) -> MonitorGeometry:
        return MonitorGeometry(
            left=int(monitor["left"]),
            top=int(monitor["top"]),
            width=int(monitor["width"]),
            height=int(monitor["height"]),
        )

    def _rect_from_qrect(self, rect: QRect) -> Rect:
        return Rect(x=int(rect.x()), y=int(rect.y()), width=int(rect.width()), height=int(rect.height()))

    def _screen_geometry_from_qscreen(self, screen, index: int) -> ScreenGeometry:
        geo = screen.geometry()
        return ScreenGeometry(
            index=index,
            x=int(geo.x()),
            y=int(geo.y()),
            width=int(geo.width()),
            height=int(geo.height()),
            dpr=float(screen.devicePixelRatio()),
            name=str(screen.name()),
        )

    def _screen_geometries(self) -> list[ScreenGeometry]:
        return [self._screen_geometry_from_qscreen(screen, idx) for idx, screen in enumerate(QGuiApplication.screens())]

    def _current_mss_monitors(self) -> list[MonitorGeometry]:
        try:
            import mss
            with mss.mss() as sct:
                return [self._monitor_geometry_from_mapping(mon) for mon in sct.monitors]
        except Exception:
            return []

    def _build_screen_pixmaps(self, desktop_img, monitors: list[MonitorGeometry]) -> list[QPixmap]:
        screens = QGuiApplication.screens()
        if not monitors:
            return []
        all_mon = monitors[0]
        pixmaps: list[QPixmap] = []
        for idx, screen in enumerate(screens):
            if idx + 1 < len(monitors):
                mon = monitors[idx + 1]
                crop_left = mon.left - all_mon.left
                crop_top = mon.top - all_mon.top
                crop_right = crop_left + mon.width
                crop_bottom = crop_top + mon.height
                crop = desktop_img.crop((crop_left, crop_top, crop_right, crop_bottom))
            else:
                crop = desktop_img
            pixmaps.append(self._pil_to_pixmap(crop, screen.geometry().size()))
        return pixmaps

    def _capture_desktop_snapshot(self) -> DesktopSnapshot:
        backend = str(getattr(self.config, "capture_backend", "mss")).lower()
        try:
            import mss
        except Exception as exc:
            raise RuntimeError("缺少 mss，无法截图") from exc
        try:
            from PIL import Image, ImageGrab
        except Exception as exc:
            raise RuntimeError("缺少 Pillow，无法截图") from exc

        with mss.mss() as sct:
            raw_monitors = sct.monitors
            if not raw_monitors:
                raise RuntimeError("未检测到屏幕")
            all_mon = raw_monitors[0]
            if backend == "winrt":
                bbox = (
                    all_mon["left"],
                    all_mon["top"],
                    all_mon["left"] + all_mon["width"],
                    all_mon["top"] + all_mon["height"],
                )
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
            else:
                sct_img = sct.grab(all_mon)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        monitors = normalize_monitors_to_image_size(
            [self._monitor_geometry_from_mapping(mon) for mon in raw_monitors],
            image_width=img.width,
            image_height=img.height,
        )
        all_monitor = monitors[0]
        screen_pixmaps = self._build_screen_pixmaps(img, monitors)
        return DesktopSnapshot(
            image=img,
            left=int(all_monitor.left),
            top=int(all_monitor.top),
            monitors=monitors,
            screen_pixmaps=screen_pixmaps,
        )

    def _crop_snapshot(self, snapshot: DesktopSnapshot, region: CaptureRegion):
        box = crop_box_for_snapshot_region(
            snapshot_left=snapshot.left,
            snapshot_top=snapshot.top,
            snapshot_width=snapshot.image.width,
            snapshot_height=snapshot.image.height,
            region=region,
        )
        return snapshot.image.crop(box)

    def _select_region(self, snapshot: DesktopSnapshot | None = None) -> CaptureRegion | None:
        """选择屏幕区域并转换为物理像素坐标（适配多屏不同DPI）。"""
        selector = ScreenSelector(snapshot.screen_pixmaps if snapshot else None)
        rect = selector.get_region()

        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return None

        print(f"[框选] 逻辑坐标: {rect}")
        rect_model = self._rect_from_qrect(rect)
        screens = self._screen_geometries()

        if snapshot is not None:
            try:
                mapping = map_selection_to_capture_region(rect_model, screens, monitors=snapshot.monitors)
                if mapping.source == "snapshot-monitor":
                    print(f"[框选] 快照映射: MSS Monitor={mapping.monitor}")
                    print(f"[框选] 快照缩放: sx={mapping.scale_x:.3f}, sy={mapping.scale_y:.3f}")
                    print(
                        f"[框选] 最终物理坐标: ({mapping.region.left}, {mapping.region.top}, "
                        f"{mapping.region.width}, {mapping.region.height})"
                    )
                    return mapping.region
            except Exception as e:
                print(f"[框选] 快照映射失败: {e}，回退到实时坐标映射")

        dpr_override = None
        override_raw = getattr(self.config, "capture_force_dpr", None)
        if override_raw is not None:
            try:
                dpr_override = float(override_raw)
            except Exception:
                pass

        monitors = self._current_mss_monitors()
        mapping = map_selection_to_capture_region(
            rect_model,
            screens,
            monitors=monitors,
            dpr_override=dpr_override,
            use_monitor_scale=False,
        )
        screen = next((item for item in screens if item.index == mapping.screen_index), screens[0] if screens else None)
        screen_name = screen.name if screen else ""
        suffix = " (override)" if dpr_override is not None else ""
        print(f"[框选] 命中屏幕: {screen_name} (Index {mapping.screen_index}), DPR: {mapping.scale_x}{suffix}")

        if mapping.source == "dpr-monitor":
            print(f"[框选] MSS Monitor: {mapping.monitor}")
        elif monitors:
            print("[框选] 警告：MSS 屏幕数量不匹配，回退到主屏估算")

        print(
            f"[框选] 最终物理坐标: ({mapping.region.left}, {mapping.region.top}, "
            f"{mapping.region.width}, {mapping.region.height})"
        )
        return mapping.region


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


class ScreenOverlay(QWidget):
    """单屏幕覆盖窗口"""
    region_selected = pyqtSignal(QRect)

    def __init__(self, screen, background: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self._screen = screen
        self._background = background
        self.setGeometry(screen.geometry()) # 逻辑坐标
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # 每个窗口只负责自己所在的屏幕，避免跨屏DPI问题
        self.setScreen(screen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        
        self.rubber_band: QRubberBand | None = None
        self.origin: QPoint | None = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if not painter.isActive(): return
        if self._background is not None:
            painter.drawPixmap(self.rect(), self._background)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80)) # 半透明遮罩
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
        if self.rubber_band and self.origin:
            rect = self.rubber_band.geometry().normalized()
            # 转换为全局逻辑坐标
            global_top_left = self.mapToGlobal(rect.topLeft())
            global_rect = QRect(global_top_left, rect.size())
            self.region_selected.emit(global_rect)
        else:
            self.region_selected.emit(QRect())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.region_selected.emit(QRect())
        else:
            super().keyPressEvent(event)


class ScreenSelector(QObject):
    """全屏选区控制器，管理多屏覆盖窗口。"""
    region_selected_signal = pyqtSignal(QRect)

    def __init__(self, backgrounds: list[QPixmap] | None = None) -> None:
        super().__init__()
        self._overlays: list[ScreenOverlay] = []
        self._selected_rect: QRect | None = None
        self._loop: QEventLoop | None = None

        # 为每个屏幕创建一个覆盖窗口
        screens = QGuiApplication.screens()
        for idx, screen in enumerate(screens):
            bg = backgrounds[idx] if backgrounds and idx < len(backgrounds) else None
            overlay = ScreenOverlay(screen, bg)
            overlay.region_selected.connect(self._on_region_selected)
            self._overlays.append(overlay)
            
        print(f"[ScreenSelector] 已初始化 {len(self._overlays)} 个屏幕覆盖层")

    def get_region(self) -> QRect | None:
        try:
            self._loop = QEventLoop()
            
            for overlay in self._overlays:
                overlay.showFullScreen() 
                overlay.raise_()
                overlay.activateWindow()
            
            self._loop.exec()
            
            # 清理
            for overlay in self._overlays:
                overlay.close()
                
            return self._selected_rect
        except Exception as e:
            print(f"[ScreenSelector ERROR] {e}")
            import traceback
            traceback.print_exc()
            for overlay in self._overlays:
                overlay.close()
            return None

    def _on_region_selected(self, rect: QRect) -> None:
        # 当任意一个屏幕完成了选区，保存结果并退出循环
        if not rect.isNull():
            self._selected_rect = rect
        if self._loop and self._loop.isRunning():
            self._loop.quit()
