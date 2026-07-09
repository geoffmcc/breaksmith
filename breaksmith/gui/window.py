from __future__ import annotations

import json
import logging
import platform
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThreadPool, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from breaksmith import __version__
from breaksmith.app import (
    AnalysisRequest,
    AnalysisResult,
    GenerationRequest,
    GenerationResult,
    ProgressEvent,
    build_waveform_peaks,
    generate_patterns,
    list_run_manifests,
    read_source_metadata,
)
from breaksmith.models import ALL_STYLES, GENRES, GROOVE_PRESETS, METER_PRESETS
from breaksmith.presets import GenerationPreset, list_presets, load_preset, preset_dir, save_preset, user_data_dir
from .jobs import CancelToken, FunctionJob
from .waveform import WaveformWidget


def _logs_dir() -> Path:
    path = user_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _configure_logging() -> None:
    logging.basicConfig(
        filename=_logs_dir() / "breaksmith-gui.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("Breaksmith GUI %s on %s Python %s", __version__, platform.platform(), sys.version)


class PreferencesDialog(QDialog):
    def __init__(self, settings: QSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.output = QLineEdit(str(settings.value("output_parent", "output")))
        self.theme = QComboBox()
        self.theme.addItems(["dark"])
        form = QFormLayout(self)
        form.addRow("Default output parent", self.output)
        form.addRow("Theme", self.theme)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Breaksmith")
        self.resize(1280, 820)
        self.setAcceptDrops(True)
        self.settings = QSettings("Breaksmith", "Breaksmith")
        self.pool = QThreadPool.globalInstance()
        self.active_jobs: list[FunctionJob] = []
        self.cancel_token: CancelToken | None = None
        self.source_path: Path | None = None
        self.analysis: AnalysisResult | None = None
        self.generation: GenerationResult | None = None
        self.current_run_dir: Path | None = None
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8)
        self.player.positionChanged.connect(lambda ms: self.waveform.set_position(ms / 1000.0))
        self.player.errorOccurred.connect(lambda *_: self._show_error("Playback error", self.player.errorString()))
        self._build_ui()
        self._build_actions()
        self._apply_theme()
        self._refresh_history()
        self._refresh_presets()
        self._set_busy(False)

    def _build_ui(self) -> None:
        self.waveform = WaveformWidget()
        self.waveform.seekRequested.connect(self._seek)
        self.source_label = QLabel("No audio loaded")
        self.metadata_label = QLabel("Open or drag an audio file to begin.")
        self.metadata_label.setWordWrap(True)
        self.open_button = QPushButton("Open Audio")
        self.open_button.clicked.connect(self.open_audio)
        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.clicked.connect(self.analyze)
        self.generate_button = QPushButton("Generate")
        self.generate_button.clicked.connect(self.generate)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_current_job)
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.play_source)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.player.pause)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.player.stop)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.valueChanged.connect(lambda value: self.audio_output.setVolume(value / 100.0))

        top = QHBoxLayout()
        for widget in (self.open_button, self.analyze_button, self.generate_button, self.cancel_button, self.play_button, self.pause_button, self.stop_button):
            top.addWidget(widget)
        top.addWidget(QLabel("Volume"))
        top.addWidget(self.volume)

        source_box = QGroupBox("Source")
        source_layout = QVBoxLayout(source_box)
        source_layout.addWidget(self.source_label)
        source_layout.addWidget(self.metadata_label)
        source_layout.addLayout(top)
        source_layout.addWidget(self.waveform)

        self.bpm_override = QDoubleSpinBox()
        self.bpm_override.setRange(0.0, 300.0)
        self.bpm_override.setSpecialValueText("Auto")
        self.bpm_override.setDecimals(2)
        self.grid_start = QDoubleSpinBox()
        self.grid_start.setRange(0.0, 36000.0)
        self.grid_start.setDecimals(3)
        self.time_signature = QComboBox()
        self.time_signature.addItems(sorted(METER_PRESETS))
        self.render_click = QCheckBox("Render click")
        analysis_box = QGroupBox("Analysis")
        analysis_form = QFormLayout(analysis_box)
        analysis_form.addRow("BPM override", self.bpm_override)
        analysis_form.addRow("Grid start", self.grid_start)
        analysis_form.addRow("Time signature", self.time_signature)
        analysis_form.addRow("Diagnostics", self.render_click)
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        analysis_form.addRow(self.analysis_text)

        self.genre = QComboBox()
        self.genre.addItems(GENRES)
        self.style = QComboBox()
        self.style.addItems(["all", *ALL_STYLES])
        self.bars = QSpinBox()
        self.bars.setRange(0, 512)
        self.bars.setSpecialValueText("Source")
        self.variants = QSpinBox()
        self.variants.setRange(1, 64)
        self.seed = QSpinBox()
        self.seed.setRange(-2_000_000_000, 2_000_000_000)
        self.seed.setValue(42)
        self.density = self._unit_spin(0.5)
        self.swing = self._unit_spin(0.0, maximum=0.5)
        self.humanize = self._unit_spin(0.0)
        self.variation = self._unit_spin(0.25)
        self.groove = QComboBox()
        self.groove.addItems(sorted(GROOVE_PRESETS))
        self.preview = QCheckBox("Render preview WAV")
        self.preview.setChecked(True)
        generation_box = QGroupBox("Generation")
        gen_form = QFormLayout(generation_box)
        for label, widget in (
            ("Genre", self.genre), ("Style", self.style), ("Bars", self.bars),
            ("Variations", self.variants), ("Seed", self.seed), ("Density", self.density),
            ("Swing", self.swing), ("Humanize", self.humanize), ("Variation", self.variation),
            ("Groove", self.groove), ("Preview", self.preview),
        ):
            gen_form.addRow(label, widget)
        preset_buttons = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.save_preset_button = QPushButton("Save Preset")
        self.save_preset_button.clicked.connect(self.save_preset)
        self.load_preset_button = QPushButton("Load Preset")
        self.load_preset_button.clicked.connect(self.load_selected_preset)
        preset_buttons.addWidget(self.preset_combo)
        preset_buttons.addWidget(self.load_preset_button)
        preset_buttons.addWidget(self.save_preset_button)
        gen_form.addRow("Presets", preset_buttons)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self.play_selected_result)
        self.artifacts = QTextEdit()
        self.artifacts.setReadOnly(True)
        self.history = QListWidget()
        self.history.itemDoubleClicked.connect(self.reopen_selected_run)
        tabs = QTabWidget()
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        results_layout.addWidget(QLabel("Double-click a generated result to play its preview."))
        results_layout.addWidget(self.results)
        results_layout.addWidget(self.artifacts)
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.addWidget(QLabel("Double-click a run to inspect its manifest."))
        history_layout.addWidget(self.history)
        tabs.addTab(results_tab, "Results")
        tabs.addTab(history_tab, "Run History")

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(analysis_box)
        controls_layout.addWidget(generation_box)
        controls_layout.addStretch(1)

        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(source_box)
        left_layout.addWidget(tabs)
        splitter.addWidget(left)
        splitter.addWidget(controls)
        splitter.setSizes([820, 380])
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    def _unit_spin(self, value: float, *, maximum: float = 1.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, maximum)
        spin.setSingleStep(0.05)
        spin.setDecimals(2)
        spin.setValue(value)
        return spin

    def _build_actions(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        actions = [
            ("New Session", QKeySequence.StandardKey.New, self.new_session),
            ("Open Audio", QKeySequence.StandardKey.Open, self.open_audio),
            ("Open Run Directory", None, self.open_run_dir),
            ("Preferences", QKeySequence.StandardKey.Preferences, self.preferences),
            ("Quit", QKeySequence.StandardKey.Quit, self.close),
        ]
        for text, shortcut, slot in actions:
            action = QAction(text, self)
            if shortcut is not None:
                action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        tools = menu.addMenu("Tools")
        for text, slot in (("Analyze", self.analyze), ("Generate", self.generate), ("Cancel Task", self.cancel_current_job), ("View Logs", self.open_logs)):
            action = QAction(text, self)
            action.triggered.connect(slot)
            tools.addAction(action)
        help_menu = menu.addMenu("Help")
        about = QAction("About", self)
        about.triggered.connect(self.about)
        help_menu.addAction(about)
        toolbar = QToolBar("Primary")
        self.addToolBar(toolbar)
        for text, slot in (("Open", self.open_audio), ("Analyze", self.analyze), ("Generate", self.generate), ("Stop", self.cancel_current_job), ("Folder", self.open_run_dir)):
            action = QAction(text, self)
            action.triggered.connect(slot)
            toolbar.addAction(action)

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #151922; color: #e8edf7; font-size: 10.5pt; }
            QGroupBox { border: 1px solid #303746; border-radius: 8px; margin-top: 12px; padding: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #b9c4d8; }
            QPushButton { background: #273246; border: 1px solid #3b465a; border-radius: 6px; padding: 7px 12px; }
            QPushButton:hover { background: #32405a; } QPushButton:disabled { color: #687286; background: #202633; }
            QLineEdit, QTextEdit, QListWidget, QComboBox, QSpinBox, QDoubleSpinBox { background: #10141c; border: 1px solid #303746; border-radius: 5px; padding: 4px; color: #f4f7fb; }
            QTabWidget::pane { border: 1px solid #303746; } QTabBar::tab { background: #202633; padding: 8px 14px; }
            QTabBar::tab:selected { background: #2f3a50; } QStatusBar { background: #10141c; color: #b9c4d8; }
        """)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        urls = event.mimeData().urls()
        if urls:
            self.load_audio(Path(urls[0].toLocalFile()))

    def open_audio(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Open Audio", "", "Audio Files (*.wav *.aif *.aiff *.flac *.ogg *.mp3 *.m4a);;All Files (*)")
        if filename:
            self.load_audio(Path(filename))

    def load_audio(self, path: Path) -> None:
        self.source_path = path
        self.source_label.setText(str(path))
        self.analysis = None
        self.generation = None
        self.results.clear()
        self.artifacts.clear()
        self.waveform.set_analysis(None)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self._start_job(lambda progress, cancel: (read_source_metadata(path), build_waveform_peaks(path), progress), self._metadata_ready)

    def _metadata_ready(self, result: object) -> None:
        metadata, peaks, _progress = result  # type: ignore[misc]
        self.metadata_label.setText(
            f"{metadata.filename} | {metadata.duration_seconds:.2f}s | {metadata.sample_rate} Hz | "
            f"{metadata.channels} ch | {metadata.format}/{metadata.subtype} | {metadata.file_size} bytes"
        )
        self.waveform.set_waveform(peaks)
        self._set_busy(False)

    def _analysis_request(self) -> AnalysisRequest:
        if self.source_path is None:
            raise ValueError("Load an audio file before analyzing.")
        output = Path(str(self.settings.value("output_parent", "output")))
        return AnalysisRequest(
            audio=self.source_path,
            output=output,
            bpm=self.bpm_override.value() or None,
            grid_start=self.grid_start.value() or None,
            time_signature=self.time_signature.currentText(),
            render_click=self.render_click.isChecked(),
        )

    def _generation_request(self) -> GenerationRequest:
        if self.source_path is None:
            raise ValueError("Load an audio file before generating.")
        return GenerationRequest(
            audio=self.source_path,
            output=Path(str(self.settings.value("output_parent", "output"))),
            genre=self.genre.currentText(),
            style=self.style.currentText(),
            bars=self.bars.value() or None,
            variants=self.variants.value(),
            seed=self.seed.value(),
            bpm=self.bpm_override.value() or None,
            grid_start=self.grid_start.value() or None,
            density=self.density.value(),
            swing=self.swing.value(),
            humanize=self.humanize.value(),
            variation=self.variation.value(),
            groove=self.groove.currentText(),
            preview=self.preview.isChecked(),
            time_signature=self.time_signature.currentText(),
        )

    def analyze(self) -> None:
        try:
            request = self._analysis_request()
        except Exception as exc:
            self._show_error("Cannot analyze", str(exc))
            return
        self._start_job(lambda progress, cancel: __import__("breaksmith.app", fromlist=["analyze_source"]).analyze_source(request, progress=progress, cancel=cancel), self._analysis_ready)

    def _analysis_ready(self, result: object) -> None:
        self.analysis = result  # type: ignore[assignment]
        analysis = self.analysis.analysis
        self.current_run_dir = self.analysis.run_dir
        self.waveform.set_analysis(analysis)
        warnings = "\n".join([*analysis.loop_warnings, *analysis.warnings]) or "None"
        self.analysis_text.setPlainText(
            f"Selected BPM: {analysis.bpm:.2f} ({analysis.tempo_source})\n"
            f"Raw BPM: {analysis.raw_detected_bpm:.2f}\n"
            f"Confidence: tempo={analysis.tempo_confidence:.2f}, beat={analysis.beat_confidence:.2f}\n"
            f"Grid: {analysis.bar_count} bars, {analysis.steps_per_bar} steps/bar\n"
            f"Fit: {analysis.duration_fit}, complete bars={analysis.complete_bar_count}\n"
            f"Candidates: {', '.join(f'{value:.2f}' for value in analysis.candidate_bpm_values)}\n"
            f"Warnings: {warnings}\n"
            f"Run: {self.analysis.run_dir}"
        )
        self._refresh_history()
        self._set_busy(False)

    def generate(self) -> None:
        try:
            request = self._generation_request()
        except Exception as exc:
            self._show_error("Cannot generate", str(exc))
            return
        self._start_job(lambda progress, cancel: generate_patterns(request, progress=progress, cancel=cancel), self._generation_ready)

    def _generation_ready(self, result: object) -> None:
        self.generation = result  # type: ignore[assignment]
        self.current_run_dir = self.generation.run_dir
        self.waveform.set_analysis(self.generation.analysis)
        self.results.clear()
        for item_result in self.generation.results:
            item = QListWidgetItem(f"{item_result.label} | {item_result.pattern.bars} bars | seed {item_result.seed}")
            item.setData(Qt.ItemDataRole.UserRole, item_result)
            self.results.addItem(item)
        self.artifacts.setPlainText("\n".join(str(self.generation.run_dir / a["path"]) for a in self.generation.artifacts))
        self._refresh_history()
        self._set_busy(False)

    def _start_job(self, function, finished) -> None:
        self.cancel_token = CancelToken()
        job = FunctionJob(function, token=self.cancel_token)
        job.signals.progress.connect(self._progress)
        job.signals.finished.connect(finished)
        job.signals.failed.connect(self._job_failed)
        job.signals.canceled.connect(self._job_canceled)
        job.signals.finished.connect(lambda _result, current=job: self._forget_job(current))
        job.signals.failed.connect(lambda _message, _details, current=job: self._forget_job(current))
        job.signals.canceled.connect(lambda _message, current=job: self._forget_job(current))
        self.active_jobs.append(job)
        self._set_busy(True)
        self.pool.start(job)

    def _forget_job(self, job: FunctionJob) -> None:
        if job in self.active_jobs:
            self.active_jobs.remove(job)

    def _progress(self, event: object) -> None:
        if isinstance(event, ProgressEvent):
            suffix = f" ({event.current}/{event.total})" if event.current and event.total else ""
            self.statusBar().showMessage(f"{event.message}{suffix}")

    def _job_failed(self, message: str, details: str) -> None:
        logging.error("GUI job failed: %s\n%s", message, details)
        self._set_busy(False)
        self._show_error("Operation failed", message, details)

    def _job_canceled(self, message: str) -> None:
        self._set_busy(False)
        self.statusBar().showMessage(message)

    def cancel_current_job(self) -> None:
        if self.cancel_token is not None:
            self.cancel_token.cancel()
            self.statusBar().showMessage("Cancel requested")

    def _set_busy(self, busy: bool) -> None:
        self.analyze_button.setEnabled(not busy and self.source_path is not None)
        self.generate_button.setEnabled(not busy and self.source_path is not None)
        self.cancel_button.setEnabled(busy)

    def play_source(self) -> None:
        if self.source_path is None:
            return
        self.player.setSource(QUrl.fromLocalFile(str(self.source_path)))
        self.player.play()

    def play_selected_result(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        result = item.data(Qt.ItemDataRole.UserRole)
        preview = result.artifacts.get("preview") if result else None
        if preview and Path(preview).exists():
            self.player.setSource(QUrl.fromLocalFile(str(preview)))
            self.player.play()
        else:
            self._show_error("No preview", "This result has no rendered preview WAV.")

    def _seek(self, seconds: float) -> None:
        self.player.setPosition(round(seconds * 1000))

    def new_session(self) -> None:
        self.source_path = None
        self.analysis = None
        self.generation = None
        self.current_run_dir = None
        self.source_label.setText("No audio loaded")
        self.metadata_label.setText("Open or drag an audio file to begin.")
        self.analysis_text.clear()
        self.results.clear()
        self.artifacts.clear()
        self.waveform.set_waveform(None)
        self._set_busy(False)

    def open_run_dir(self) -> None:
        path = self.current_run_dir or Path(str(self.settings.value("output_parent", "output")))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _refresh_history(self) -> None:
        self.history.clear()
        for run in list_run_manifests(Path(str(self.settings.value("output_parent", "output"))), limit=50):
            options = run.get("options", {}) if isinstance(run.get("options"), dict) else {}
            label = f"{run.get('created_at', 'unknown')} | {run.get('source_filename', 'source')} | bpm={options.get('selected_bpm', 'n/a')}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, run)
            self.history.addItem(item)

    def reopen_selected_run(self) -> None:
        item = self.history.currentItem()
        if item is None:
            return
        run = item.data(Qt.ItemDataRole.UserRole)
        self.current_run_dir = Path(run.get("run_directory", ""))
        self.artifacts.setPlainText(json.dumps(run, indent=2, default=str))
        self.statusBar().showMessage(f"Reopened manifest: {self.current_run_dir}")

    def _refresh_presets(self) -> None:
        self.preset_combo.clear()
        for preset in list_presets():
            self.preset_combo.addItem(preset.name, preset)

    def save_preset(self) -> None:
        name, ok = QFileDialog.getSaveFileName(self, "Save Preset", str(preset_dir() / "preset.json"), "JSON (*.json)")
        if not ok or not name:
            return
        preset = GenerationPreset(Path(name).stem, self._generation_request())
        path = save_preset(preset, Path(name).parent)
        self.statusBar().showMessage(f"Saved preset: {path}")
        self._refresh_presets()

    def load_selected_preset(self) -> None:
        preset = self.preset_combo.currentData()
        if preset is None:
            filename, _ = QFileDialog.getOpenFileName(self, "Load Preset", str(preset_dir()), "JSON (*.json)")
            if not filename:
                return
            preset = load_preset(Path(filename))
        request = preset.request
        self.genre.setCurrentText(request.genre or "dnb")
        self.style.setCurrentText(request.style)
        self.bars.setValue(request.bars or 0)
        self.variants.setValue(request.variants)
        self.seed.setValue(request.seed)
        self.density.setValue(request.density if request.density is not None else 0.5)
        self.swing.setValue(request.swing if request.swing is not None else 0.0)
        self.humanize.setValue(request.humanize if request.humanize is not None else 0.0)
        self.variation.setValue(request.variation if request.variation is not None else 0.25)
        self.groove.setCurrentText(request.groove)

    def preferences(self) -> None:
        dialog = PreferencesDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.setValue("output_parent", dialog.output.text())
            self._refresh_history()

    def open_logs(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(_logs_dir())))

    def about(self) -> None:
        QMessageBox.about(self, "About Breaksmith", f"Breaksmith {__version__}\nShared core, CLI, and PySide6 desktop interface.")

    def _show_error(self, title: str, message: str, details: str | None = None) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(message)
        if details:
            box.setDetailedText(details)
        box.exec()


def run_gui(audio: str | None = None) -> int:
    _configure_logging()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Breaksmith")
    app.setOrganizationName("Breaksmith")
    window = MainWindow()
    if audio:
        window.load_audio(Path(audio))
    window.show()
    return app.exec()
