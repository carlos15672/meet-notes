"""Always-on-top meeting controls. The backend owns recording and analysis."""
import argparse
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import QLockFile, QPoint, QSettings, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget)

import floating_api as api

ROOT = Path(__file__).resolve().parents[1]


def clock(seconds):
    value = max(0, int(seconds or 0))
    return f"{value // 60:02d}:{value % 60:02d}"


class ApiWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    def run(self):
        try:
            self.succeeded.emit(self.operation())
        except Exception as exc:
            self.failed.emit(str(exc))


class MicBadge(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(48, 48)
        self.setAccessibleName("Captura de audio")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#3975A4"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 48, 48, 14, 14)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor("white"), 2.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawRoundedRect(20, 11, 8, 18, 4, 4)
        painter.drawArc(15, 17, 18, 18, 180 * 16, 180 * 16)
        painter.drawLine(24, 34, 24, 39)
        painter.drawLine(19, 39, 29, 39)


class FloatingWindow(QWidget):
    def __init__(self, preview=False):
        super().__init__()
        self.preview = preview
        self.session_id = None
        self.current = None
        self.pending = False
        self.polling = False
        self.close_after_finish = False
        self.last_action = None
        self.workers = set()
        self.drag_offset = None
        self.settings = QSettings("meet-notes", "floating-window")
        self.setWindowTitle("meet-notes · Captura en vivo")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName("Ventana flotante de meet-notes")
        self._build()
        self._show_setup()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.top() + 32)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        if preview:
            self._apply({"id": "vista-previa", "status": "capturando", "duration": 1421,
                "segmentos": [{"texto": "Estamos revisando el diseño de la pantalla de registro."}],
                "marcas": [], "meeting_id": None, "error": ""})
        else:
            self._run(api.devices, self._devices_ready, self._error)

    def _build(self):
        self.setStyleSheet("""
            QWidget { font-family: 'Segoe UI'; color: #173653; }
            QFrame#shell { background: #E9F1F8; border: 1px solid #B7CBDC; border-radius: 23px; }
            QFrame#header { background: #E9F1F8; border-top-left-radius: 22px; border-top-right-radius: 22px; }
            QFrame#body { background: #D9E8F5; border-bottom-left-radius: 22px; border-bottom-right-radius: 22px; }
            QLabel#brand { color: #2E6E9E; font-size: 18px; font-weight: 700; }
            QLabel#sub { color: #526D87; font-size: 11px; }
            QLabel#hint { color: #49677F; font-size: 12px; }
            QLabel#preview { color: #173653; font-size: 12px; font-weight: 600; }
            QLabel#notice { color: #A33F32; font-size: 11px; }
            QFrame#rec { background: #F8E4DC; border-radius: 20px; }
            QLabel#recText { color: #9F3E2D; font-size: 14px; font-weight: 700; }
            QPushButton { min-height: 43px; border-radius: 13px; padding: 3px 11px;
                font-size: 12px; font-weight: 600; background: white; border: 1px solid #BCD2E4; }
            QPushButton:hover { background: #F6FAFD; border-color: #77A9CE; }
            QPushButton:disabled { color: #8A9DAF; background: #EDF2F6; }
            QPushButton#primary { background: #3975A4; border: 1px solid #3975A4; color: white; }
            QPushButton#primary:hover { background: #2F668F; }
            QPushButton#close { min-height: 25px; max-width: 25px; border: none;
                background: transparent; font-size: 19px; color: #698399; padding: 0; }
            QPushButton#close:hover { background: #DCE8F1; }
            QLineEdit, QComboBox { background: white; border: 1px solid #B9CFDF;
                border-radius: 9px; padding: 7px 9px; min-height: 24px; font-size: 11px; }
            QLineEdit:focus, QComboBox:focus { border-color: #3975A4; }
            QLabel#field { color: #335775; font-size: 11px; font-weight: 600; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(13, 13, 13, 16)
        outer.setSpacing(0)
        self.shell = QFrame()
        self.shell.setObjectName("shell")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(20, 45, 68, 65))
        self.shell.setGraphicsEffect(shadow)
        outer.addWidget(self.shell)
        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(93)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 17, 19, 14)
        header_layout.setSpacing(12)
        header_layout.addWidget(MicBadge())
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.brand = QLabel("meet-notes")
        self.brand.setObjectName("brand")
        self.subtitle = QLabel("Captura local de reuniones")
        self.subtitle.setObjectName("sub")
        self.subtitle.setWordWrap(True)
        titles.addWidget(self.brand)
        titles.addWidget(self.subtitle)
        header_layout.addLayout(titles, 1)
        self.rec = QFrame()
        self.rec.setObjectName("rec")
        rec_layout = QHBoxLayout(self.rec)
        rec_layout.setContentsMargins(12, 6, 12, 6)
        rec_layout.setSpacing(7)
        dot = QLabel("●")
        dot.setStyleSheet("color:#BC4932; font-size:12px;")
        self.rec_text = QLabel("REC 00:00")
        self.rec_text.setObjectName("recText")
        rec_layout.addWidget(dot)
        rec_layout.addWidget(self.rec_text)
        header_layout.addWidget(self.rec)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("close")
        self.close_button.setToolTip("Cerrar ventana")
        self.close_button.setAccessibleName("Cerrar ventana flotante")
        self.close_button.clicked.connect(self.close)
        header_layout.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)
        shell_layout.addWidget(header)

        body = QFrame()
        body.setObjectName("body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(22, 16, 22, 19)
        body_layout.setSpacing(8)
        self.notice = QLabel("")
        self.notice.setObjectName("notice")
        self.notice.setWordWrap(True)
        self.notice.hide()
        body_layout.addWidget(self.notice)
        self.pages = QStackedWidget()
        body_layout.addWidget(self.pages)
        self._build_setup()
        self._build_recording()
        self._build_finished()
        shell_layout.addWidget(body)
        self.setFixedWidth(510)

    def _build_setup(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        prompt = QLabel("Prepara tu reunión")
        prompt.setObjectName("preview")
        layout.addWidget(prompt)
        label = QLabel("Tu nombre en la reunión")
        label.setObjectName("field")
        layout.addWidget(label)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej. Juan")
        self.name_input.setText(self.settings.value("userName", ""))
        self.name_input.setMaxLength(80)
        layout.addWidget(self.name_input)
        label = QLabel("Título · opcional")
        label.setObjectName("field")
        layout.addWidget(label)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Ej. Revisión UX/UI")
        self.title_input.setMaxLength(120)
        layout.addWidget(self.title_input)
        row = QHBoxLayout()
        row.setSpacing(10)
        for title, attr in (("Audio de la reunión", "system_combo"), ("Tu micrófono", "microphone_combo")):
            column = QVBoxLayout()
            label = QLabel(title)
            label.setObjectName("field")
            combo = QComboBox()
            combo.setAccessibleName(title)
            combo.addItem("Buscando dispositivos…", None)
            setattr(self, attr, combo)
            column.addWidget(label)
            column.addWidget(combo)
            row.addLayout(column, 1)
        layout.addLayout(row)
        self.start_button = QPushButton("Iniciar escucha")
        self.start_button.setObjectName("primary")
        self.start_button.setAccessibleName("Iniciar captura en vivo")
        self.start_button.clicked.connect(self._start)
        layout.addWidget(self.start_button)
        self.pages.addWidget(page)

    def _build_recording(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)
        self.state_line = QLabel("● Escuchando audio del sistema y micrófono")
        self.state_line.setObjectName("hint")
        layout.addWidget(self.state_line)
        self.preview_line = QLabel("Pulsa Marcar momento para guardar un instante importante.")
        self.preview_line.setObjectName("preview")
        self.preview_line.setWordWrap(True)
        self.preview_line.setMinimumHeight(30)
        layout.addWidget(self.preview_line)
        buttons = QHBoxLayout()
        buttons.setSpacing(9)
        self.pause_button = QPushButton("Pausar")
        self.pause_button.clicked.connect(self._pause_or_resume)
        self.mark_button = QPushButton("Marcar momento")
        self.mark_button.clicked.connect(lambda: self._action("marcar"))
        self.finish_button = QPushButton("Terminar y resumir")
        self.finish_button.setObjectName("primary")
        self.finish_button.clicked.connect(lambda: self._action("finalizar"))
        for button in (self.pause_button, self.mark_button, self.finish_button):
            buttons.addWidget(button, 1)
        layout.addLayout(buttons)
        self.pages.addWidget(page)

    def _build_finished(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.finish_heading = QLabel("Procesando la reunión…")
        self.finish_heading.setObjectName("preview")
        layout.addWidget(self.finish_heading)
        self.finish_detail = QLabel("Conservamos la transcripción mientras termina el análisis.")
        self.finish_detail.setObjectName("hint")
        self.finish_detail.setWordWrap(True)
        layout.addWidget(self.finish_detail)
        row = QHBoxLayout()
        self.results_button = QPushButton("Abrir resultados")
        self.results_button.setObjectName("primary")
        self.results_button.clicked.connect(self._results_or_retry)
        self.new_button = QPushButton("Nueva reunión")
        self.new_button.clicked.connect(self._show_setup)
        row.addWidget(self.results_button)
        row.addWidget(self.new_button)
        layout.addLayout(row)
        self.pages.addWidget(page)

    def _run(self, operation, success, failure=None):
        worker = ApiWorker(operation)
        self.workers.add(worker)
        worker.succeeded.connect(success)
        worker.failed.connect(failure or self._error)
        worker.finished.connect(lambda: self.workers.discard(worker))
        worker.start()

    def _error(self, message):
        self.pending = False
        self.polling = False
        self._buttons_enabled(True)
        self.notice.setStyleSheet("")
        self.notice.setText(message)
        self.notice.show()
        if self.close_after_finish:
            self.close_after_finish = False
        self.last_action = None

    def _clear_notice(self):
        self.notice.hide()
        self.notice.setText("")
        self.notice.setStyleSheet("")

    def _devices_ready(self, response):
        for combo, kind, selected in ((self.system_combo, "sistema", response["sistema_predeterminado"]),
                                       (self.microphone_combo, "microfono", response["microfono_predeterminado"])):
            combo.clear()
            for item in response["dispositivos"]:
                if item["tipo"] == kind:
                    combo.addItem(item["nombre"], item["id"])
            index = combo.findData(selected)
            if index >= 0:
                combo.setCurrentIndex(index)
        self._run(api.sessions, self._existing_session, self._error)

    def _existing_session(self, sessions):
        current = next((item for item in sessions if item["status"] in
            ("capturando", "pausada", "finalizando", "analizando", "interrumpida")), None)
        if current:
            self._apply(current)

    def _buttons_enabled(self, enabled):
        for button in (self.start_button, self.pause_button, self.mark_button, self.finish_button):
            button.setEnabled(enabled)

    def _start(self):
        name = self.name_input.text().strip()
        if not name:
            self.name_input.setFocus()
            self._error("Escribe el nombre con el que te mencionan en la reunión.")
            return
        if self.system_combo.currentData() is None or self.microphone_combo.currentData() is None:
            self._error("Selecciona el audio del sistema y un micrófono.")
            return
        self.settings.setValue("userName", name)
        self.pending = True
        self.last_action = None
        self._buttons_enabled(False)
        self._clear_notice()
        self._run(lambda: api.start(name, self.title_input.text().strip() or "Reunión en vivo",
            self.system_combo.currentData(), self.microphone_combo.currentData()), self._action_done)

    def _pause_or_resume(self):
        self._action("reanudar" if self.current and self.current["status"] == "pausada" else "pausar")

    def _action(self, verb):
        if not self.session_id or self.pending:
            return
        self.pending = True
        self.last_action = verb
        self._buttons_enabled(False)
        self._clear_notice()
        self._run(lambda: api.action(self.session_id, verb), self._action_done)

    def _action_done(self, state):
        action = self.last_action
        self.last_action = None
        self.pending = False
        self._clear_notice()
        self._apply(state)
        if action == "marcar":
            self.notice.setText("Momento guardado en la reunión.")
            self.notice.setStyleSheet("color:#26704C;")
            self.notice.show()
        if self.close_after_finish and state["status"] in ("finalizando", "analizando", "lista"):
            self.close_after_finish = False
            self.close()

    def _poll(self):
        if not self.session_id or self.polling or self.pending or self.preview:
            return
        self.polling = True
        def done(state):
            self.polling = False
            self._apply(state)
        self._run(lambda: api.session(self.session_id), done, self._error)

    def _apply(self, state):
        self.session_id = state["id"]
        self.current = state
        status = state["status"]
        self.rec_text.setText(("PAUSA " if status == "pausada" else "REC ") + clock(state["duration"]))
        self.rec.setVisible(status in ("capturando", "pausada"))
        if status in ("capturando", "pausada"):
            self.pages.setCurrentIndex(1)
            self.setFixedHeight(300)
            self.subtitle.setText("Pausada · audio guardado" if status == "pausada" else "Escuchando · procesado en tu equipo")
            self.state_line.setText("◌ Captura pausada" if status == "pausada" else "● Audio del sistema y micrófono activos")
            self.pause_button.setText("Reanudar" if status == "pausada" else "Pausar")
            self._buttons_enabled(True)
            self.mark_button.setEnabled(status == "capturando")
            segments = state.get("segmentos") or []
            self.preview_line.setText("Último: " + segments[-1]["texto"] if segments else
                "Pulsa Marcar momento para guardar un instante importante.")
        else:
            self.pages.setCurrentIndex(2)
            self.setFixedHeight(245)
            self.subtitle.setText("Transcripción y resumen local")
            labels = {"finalizando": "Transcribiendo la reunión…", "analizando": "Preparando resumen y tareas…",
                      "lista": "Resumen listo", "interrumpida": "Captura interrumpida", "error": "No se pudo finalizar"}
            self.finish_heading.setText(labels.get(status, "Procesando la reunión…"))
            self.finish_detail.setText(state.get("error") or
                ("Abre los resultados para revisar la transcripción y las tareas." if status == "lista"
                 else "La grabación se conserva mientras termina el procesamiento."))
            self.results_button.setText("Reintentar finalización" if status in ("interrumpida", "error") else "Abrir resultados")
            self.results_button.setEnabled(status in ("lista", "interrumpida", "error") and
                (status != "lista" or bool(state.get("meeting_id"))))
            self.new_button.setEnabled(status == "lista")

    def _show_setup(self):
        self.session_id = None
        self.current = None
        self.pages.setCurrentIndex(0)
        self.rec.hide()
        self.subtitle.setText("Captura local de reuniones")
        self.setFixedHeight(455)
        self._clear_notice()
        self._buttons_enabled(True)

    def _results_or_retry(self):
        if self.current and self.current["status"] in ("interrumpida", "error"):
            self._action("finalizar")
        else:
            self._open_results()

    def _open_results(self):
        meeting_id = self.current.get("meeting_id") if self.current else None
        if meeting_id:
            webbrowser.open(f"http://127.0.0.1:5173/#/resultados/{meeting_id}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 100:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        if self.preview:
            super().closeEvent(event)
            return
        if self.pending:
            event.ignore()
            return
        if self.current and self.current["status"] in ("capturando", "pausada"):
            answer = QMessageBox.question(self, "Captura en curso",
                "La reunión sigue capturándose. ¿Terminar y generar el resumen antes de cerrar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.close_after_finish = True
            self._action("finalizar")
            event.ignore()
            return
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", metavar="PNG", help="Guardar una vista de prueba sin conectarse a la API")
    parser.add_argument("--preview-setup", action="store_true", help="Mostrar la configuración en la vista de prueba")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setApplicationName("meet-notes")
    app.setFont(QFont("Segoe UI", 10))
    lock = None
    if not args.preview:
        location = ROOT / "backend/data"
        location.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(location / "ventana-flotante.lock"))
        if not lock.tryLock(100):
            return 0
    window = FloatingWindow(preview=bool(args.preview))
    if args.preview_setup:
        window._show_setup()
    window.show()
    if args.preview:
        def capture_preview():
            window.grab().save(args.preview)
            window.close()
            app.quit()
        QTimer.singleShot(250, capture_preview)
    try:
        return app.exec()
    finally:
        if lock:
            lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
