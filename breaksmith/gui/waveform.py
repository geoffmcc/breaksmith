from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from breaksmith.app import WaveformPeaks
from breaksmith.models import AudioAnalysis


class WaveformWidget(QWidget):
    seekRequested = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(170)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Waveform timeline")
        self._peaks: WaveformPeaks | None = None
        self._analysis: AudioAnalysis | None = None
        self._position = 0.0

    def set_waveform(self, peaks: WaveformPeaks | None) -> None:
        self._peaks = peaks
        self._position = 0.0
        self.update()

    def set_analysis(self, analysis: AudioAnalysis | None) -> None:
        self._analysis = analysis
        self.update()

    def set_position(self, seconds: float) -> None:
        self._position = max(0.0, seconds)
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self._peaks is None or self.width() <= 0:
            return
        ratio = max(0.0, min(1.0, event.position().x() / self.width()))
        self.seekRequested.emit(ratio * self._peaks.duration_seconds)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect().adjusted(12, 12, -12, -22)
        painter.fillRect(self.rect(), QColor("#111318"))
        painter.setPen(QPen(QColor("#2b303a"), 1))
        painter.drawRect(rect)
        if self._peaks is None or not self._peaks.peaks:
            painter.setPen(QColor("#8b94a7"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Load audio to show the real waveform")
            return
        mid = rect.center().y()
        half = rect.height() / 2.0
        count = len(self._peaks.peaks)
        painter.setPen(QPen(QColor("#71d1ff"), 1))
        for x in range(rect.width()):
            idx = min(count - 1, int(x / max(1, rect.width()) * count))
            low, high = self._peaks.peaks[idx]
            y1 = mid - high * half
            y2 = mid - low * half
            painter.drawLine(rect.left() + x, int(y1), rect.left() + x, int(y2))
        if self._analysis is not None:
            duration = max(0.001, self._peaks.duration_seconds)
            painter.setPen(QPen(QColor("#ffc857"), 1))
            for beat in self._analysis.beat_times:
                x = rect.left() + int((beat / duration) * rect.width())
                if rect.left() <= x <= rect.right():
                    painter.drawLine(x, rect.top(), x, rect.bottom())
        x = rect.left() + int((self._position / max(0.001, self._peaks.duration_seconds)) * rect.width())
        painter.setPen(QPen(QColor("#ff5c7a"), 2))
        painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.setPen(QColor("#8b94a7"))
        painter.drawText(QRectF(rect.left(), rect.bottom() + 4, rect.width(), 18), f"0:00      {self._peaks.duration_seconds:.2f}s")
