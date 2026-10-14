"""Editor nativo e mascotes independentes; nenhuma integração de rede."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QEvent, QLockFile, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .core import Library, MascotProject

_application: QApplication | None = None


def _dispose_mascots(pets: dict[str, MascotWindow]) -> None:
    """Destruição real do editor encerra órfãos; closeEvent não chama esta função."""
    for pet in tuple(pets.values()):
        pet.on_changed = None
        try:
            pet.timer.stop()
            pet.hide()
            pet.deleteLater()
        except RuntimeError:
            # O Qt/pytest-qt pode já ter destruído essa janela top-level.
            continue
    pets.clear()


def _clamp_rect(rect: QRect, areas: list[QRect]) -> QRect:
    """Preserva monitor conectado (inclusive coordenadas negativas) ou usa o mais próximo."""
    if not areas:
        return QRect(rect)
    center = rect.center()
    area = min(
        areas,
        key=lambda screen: (
            (center.x() - min(max(center.x(), screen.left()), screen.right())) ** 2
            + (center.y() - min(max(center.y(), screen.top()), screen.bottom())) ** 2
        ),
    )
    width, height = min(rect.width(), area.width()), min(rect.height(), area.height())
    x = min(max(rect.x(), area.left()), area.right() - width + 1)
    y = min(max(rect.y(), area.top()), area.bottom() - height + 1)
    return QRect(x, y, width, height)


def _clamp_window(window: QWidget) -> None:
    areas = [screen.availableGeometry() for screen in QApplication.screens()]
    rect = _clamp_rect(QRect(window.pos(), window.size()), areas)
    window.resize(rect.size())
    window.move(rect.topLeft())


def _render_pixmaps(library: Library, project_id: str, state: str) -> tuple[QPixmap, ...]:
    frames = []
    for index in range(6):
        image = library.render_frame(project_id, state, index).convert("RGBA")
        raw = image.tobytes()
        # copy() desassocia o buffer Python; não há IO no timer/paintEvent.
        qt_image = QImage(
            raw, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888
        ).copy()
        frames.append(QPixmap.fromImage(qt_image))
    return tuple(frames)


class MascotWindow(QWidget):
    """Mascote top-level sem ownership do editor (inclusive em Windows)."""

    editor_requested = Signal()
    error_occurred = Signal(str)

    def __init__(self, library: Library, project_id: str, *, on_changed=None):
        ensure_app()
        super().__init__(
            None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.library = library
        self._project_id = project_id
        self.on_changed = on_changed
        self._drag_offset: QPoint | None = None
        self.context_menu: QMenu | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.project = library.load(project_id)
        self._current_state = "idle"
        self.scale = 1.0
        self.frame_index = 0
        self.frame_cache: dict[str, tuple[QPixmap, ...]] = {}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance_frame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(f"Mascote — {self.project.name}")
        self.setFixedSize(192, 208)
        self.reload_project()

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def current_state(self) -> str:
        return self._current_state

    def _cache_state(self, state: str) -> None:
        if state in self.frame_cache:
            return
        self.frame_cache[state] = _render_pixmaps(self.library, self.project_id, state)

    def set_state(self, state: str) -> None:
        if state not in self.project.animations:
            raise ValueError(f"Estado inválido: {state}")
        self._cache_state(state)
        self._current_state = state
        self.frame_index = 0
        self.timer.setInterval(round(1000 / self.project.animations[state].fps))
        self.update()
        self._notify_changed()

    def reload_project(self) -> None:
        project = self.library.load(self.project_id)
        state = self.current_state if self.current_state in project.animations else "idle"
        # Só substitua o cache válido depois de todos os quadros novos existirem.
        frames = _render_pixmaps(self.library, self.project_id, state)
        self.project = project
        self.frame_cache = {state: frames}
        self.setWindowTitle(f"Mascote — {project.name}")
        self.set_state(state)

    def set_scale(self, scale: float) -> None:
        if not isinstance(scale, (int, float)) or not math.isfinite(scale) or not 0.25 <= scale <= 2:
            raise ValueError("Tamanho deve estar entre 0,25 e 2.")
        self.scale = float(scale)
        self.setFixedSize(round(192 * scale), round(208 * scale))
        self._notify_changed()

    def _notify_changed(self) -> None:
        if self.on_changed is not None:
            self.on_changed()

    def _advance_frame(self) -> None:
        self.frame_index = (self.frame_index + 1) % 6
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self.frame_cache[self.current_state][self.frame_index])
        painter.end()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.timer.start()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            # Coordenadas globais podem ser negativas nos monitores à esquerda/acima.
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._notify_changed()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _request_state(self, state: str) -> None:
        try:
            self.set_state(state)
        except (ValueError, OSError) as exc:
            self.setToolTip(f"Erro: {exc}")
            self.error_occurred.emit(str(exc))

    def build_context_menu(self) -> QMenu:
        from .core import STATE_LABELS, STATE_ROWS

        menu = QMenu(self)
        states = menu.addMenu("Estado")
        for state in STATE_ROWS:
            action = states.addAction(STATE_LABELS[state])
            action.setCheckable(True)
            action.setChecked(state == self.current_state)
            action.triggered.connect(lambda checked=False, value=state: self._request_state(value))
        sizes = menu.addMenu("Tamanho")
        for scale in (0.5, 0.75, 1.0, 1.5, 2.0):
            action = sizes.addAction(f"{scale * 100:g}%")
            action.setCheckable(True)
            action.setChecked(scale == self.scale)
            action.triggered.connect(lambda checked=False, value=scale: self.set_scale(value))
        menu.addSeparator()
        menu.addAction("Mostrar editor", self.editor_requested.emit)
        menu.addAction("Ocultar mascote", self.hide)
        return menu

    def contextMenuEvent(self, event) -> None:
        if self.context_menu is not None:
            self.context_menu.close()
            self.context_menu.deleteLater()
        self.context_menu = self.build_context_menu()
        # Não abre loop aninhado; testes/headless podem fechar a janela com segurança.
        self.context_menu.popup(event.globalPos())
        event.accept()

    def hideEvent(self, event) -> None:
        self.timer.stop()
        if self.context_menu is not None:
            self.context_menu.hide()
        super().hideEvent(event)
        self._notify_changed()


class StudioWindow(QMainWindow):
    """Editor local; fechar apenas oculta o editor, não as janelas top-level."""

    def __init__(self, library: Library):
        ensure_app()
        super().__init__(None)
        self.library = library
        self._desktop_records: dict[str, dict] = {}
        self._shutting_down = False
        self._restoring = False
        self.tray_icon: QSystemTrayIcon | None = None
        self.tray_available = False
        self.mascot_windows: dict[str, MascotWindow] = {}
        pets = self.mascot_windows
        self.destroyed.connect(lambda: _dispose_mascots(pets))
        self._known_states: dict[str, str] = {}
        self._applying_events = False
        self._drafts: dict[str, MascotProject] = {}
        self._manual_states: dict[str, str] = {}
        self._automatic_ids: set[str] = set()
        self.event_timer = QTimer(self)
        self.event_timer.setInterval(1000)
        self.event_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.event_timer.timeout.connect(self.poll_agent_states)
        self._event_error: str | None = None
        self._editing_id: str | None = None
        self._editing_state = "idle"
        self._loading = False
        self._preview_cache: dict[tuple[str, str], tuple[QPixmap, ...]] = {}
        self._preview_frames: tuple[QPixmap, ...] = ()
        self._preview_index = 0
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._advance_preview)
        self.setWindowTitle("Mascot Studio")
        self.resize(1020, 740)
        self._build_ui()
        self.reload_projects()
        self._load_desktop()
        self.event_timer.start()

    def _build_ui(self) -> None:
        from .core import STATE_LABELS, STATE_ROWS

        central = QWidget(self)
        outer = QVBoxLayout(central)
        title = QLabel("Mascot Studio — editor e companheiros flutuantes")
        outer.addWidget(title)
        self.empty_label = QLabel(
            "Nenhum projeto. Importe PNG/WebP, atlas Hermes ou ZIP editável, ou abra o exemplo."
        )
        self.empty_label.setWordWrap(True)
        outer.addWidget(self.empty_label)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.project_list = QListWidget()
        self.project_list.setObjectName("project_list")
        left_layout.addWidget(self.project_list, 1)
        for name, text in (
            ("import_image_button", "Novo / importar imagem…"),
            ("import_zip_button", "Importar projeto ZIP…"),
            ("example_button", "Abrir exemplo"),
            ("duplicate_button", "Duplicar…"),
            ("reload_button", "Atualizar lista"),
        ):
            button = QPushButton(text)
            button.setObjectName(name)
            setattr(self, name, button)
            left_layout.addWidget(button)
        self.remove_magenta_check = QCheckBox("Remover fundo magenta de imagem simples")
        self.remove_magenta_check.setChecked(True)
        self.remove_magenta_check.setToolTip("Não altera o preto nem os contornos. Não se aplica a atlas.")
        left_layout.addWidget(self.remove_magenta_check)
        self.source_kind_combo = QComboBox()
        for text, value in (
            ("Detectar imagem / atlas", "auto"),
            ("Imagem simples", "image"),
            ("Atlas Hermes", "atlas"),
        ):
            self.source_kind_combo.addItem(text, value)
        left_layout.addWidget(self.source_kind_combo)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        metadata = QGroupBox("Projeto")
        metadata_form = QFormLayout(metadata)
        for name, label in (
            ("name_edit", "Nome"),
            ("agent_id_edit", "Identificador do agente"),
            ("author_edit", "Autor"),
            ("license_edit", "Licença da imagem"),
        ):
            field = QLineEdit()
            field.setObjectName(name)
            field.setMaxLength(100 if name in ("name_edit", "agent_id_edit") else 256 * 1024)
            setattr(self, name, field)
            metadata_form.addRow(label, field)
        self.agent_id_edit.setPlaceholderText("Opcional; coincide com a chave do arquivo de eventos local")
        right_layout.addWidget(metadata)
        animation = QGroupBox("Animação por estado")
        animation_form = QFormLayout(animation)
        self.state_combo = QComboBox()
        self.state_combo.setObjectName("state_combo")
        for state in STATE_ROWS:
            self.state_combo.addItem(STATE_LABELS[state], state)
        animation_form.addRow("Estado", self.state_combo)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("mode_combo")
        self.mode_combo.addItem("Manual", "manual")
        self.mode_combo.addItem("Eventos locais (automático)", "automatic")
        animation_form.addRow("Controle do estado", self.mode_combo)
        self.parameter_inputs: dict[str, QDoubleSpinBox] = {}
        for key, label, low, high, step, value in (
            ("fps", "Quadros por segundo", 1, 30, 0.5, 6),
            ("bob", "Salto vertical (px)", 0, 24, 1, 2),
            ("sway", "Balanço horizontal (px)", 0, 20, 1, 1),
            ("rotation", "Rotação (graus)", 0, 20, 1, 1),
            ("zoom", "Zoom da animação", 0.25, 2, 0.05, 1),
        ):
            field = QDoubleSpinBox()
            field.setObjectName(key)
            field.setRange(low, high)
            field.setDecimals(2)
            field.setSingleStep(step)
            field.setValue(value)
            self.parameter_inputs[key] = field
            animation_form.addRow(label, field)
        right_layout.addWidget(animation)
        self.preview_label = QLabel("Selecione um projeto")
        self.preview_label.setObjectName("preview_label")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(192, 208)
        self.preview_label.setStyleSheet("background: #252b35; color: #eeeeee; border-radius: 6px;")
        right_layout.addWidget(self.preview_label)
        hint = QLabel(
            "Salve para aplicar os parâmetros. Eventos: agent-states.json na biblioteca, no máximo 1 Hz. "
            "Adaptador local opcional; não conecta automaticamente ao Hermes ou a outros agentes."
        )
        hint.setWordWrap(True)
        right_layout.addWidget(hint)
        self._selected_buttons = [self.duplicate_button]
        for rows in (
            (
                ("save_button", "Salvar alterações"),
                ("show_button", "Mostrar mascote"),
                ("hide_button", "Ocultar mascote"),
            ),
            (("export_project_button", "Exportar projeto…"), ("export_hermes_button", "Exportar Hermes…")),
        ):
            row = QHBoxLayout()
            for name, text in rows:
                button = QPushButton(text)
                button.setObjectName(name)
                setattr(self, name, button)
                self._selected_buttons.append(button)
                row.addWidget(button)
            right_layout.addLayout(row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right)
        splitter.addWidget(scroll)
        splitter.setSizes([280, 680])
        footer = QHBoxLayout()
        self.show_all_button = QPushButton("Mostrar todos os mascotes")
        self.quit_button = QPushButton("Sair do aplicativo")
        footer.addWidget(self.show_all_button)
        footer.addStretch()
        footer.addWidget(self.quit_button)
        outer.addLayout(footer)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Offline. Seus projetos e imagens permanecem nesta biblioteca.")
        self.reload_button.clicked.connect(self.reload_projects)
        self.show_all_button.clicked.connect(self.show_all_mascots)
        self.show_button.clicked.connect(self._show_selected)
        self.hide_button.clicked.connect(self._hide_selected)
        self.project_list.currentItemChanged.connect(self._load_selected)
        self.state_combo.currentIndexChanged.connect(self._state_changed)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.save_button.clicked.connect(self.save_selected)
        self.import_image_button.clicked.connect(self._choose_image)
        self.import_zip_button.clicked.connect(self._choose_zip)
        self.example_button.clicked.connect(self.open_example)
        self.duplicate_button.clicked.connect(self._duplicate_selected)
        self.export_project_button.clicked.connect(lambda: self._export_selected(hermes=False))
        self.export_hermes_button.clicked.connect(lambda: self._export_selected(hermes=True))
        self.quit_button.clicked.connect(lambda: self.shutdown())

    def create_tray(self) -> QSystemTrayIcon:
        if self.tray_icon is not None:
            return self.tray_icon
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Mascot Studio — mascotes e editor")
        menu = QMenu(self)
        menu.addAction("Mostrar editor", self.show_editor)
        menu.addAction("Mostrar todos os mascotes", self.show_all_mascots)
        menu.addSeparator()
        menu.addAction("Sair do aplicativo", lambda: self.shutdown())
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if self.tray_available:
            self.tray_icon.show()
        else:
            self.statusBar().showMessage(
                "Bandeja indisponível nesta sessão. Reabra pelo menu do mascote; use Sair para encerrar."
            )
        return self.tray_icon

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_editor()

    def shutdown(self, *, quit_app: bool = True) -> None:
        if self._shutting_down:
            return
        self.save_desktop()
        self._shutting_down = True
        self.event_timer.stop()
        self.preview_timer.stop()
        for pet in self.mascot_windows.values():
            pet.on_changed = None
            pet.timer.stop()
            pet.hide()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.hide()
        if quit_app:
            ensure_app().quit()

    def _quit_cleanup(self) -> None:
        self.shutdown(quit_app=False)

    def open_example(self) -> None:
        from importlib.resources import as_file, files

        try:
            asset = files("mascot_studio").joinpath("assets/orbi.png")
            with as_file(asset) as source:
                project = self.library.create(
                    "Orbi — exemplo", source, source_kind="image", remove_magenta=False
                )
            self.reload_projects()
            self.select_project(project.id)
            self.statusBar().showMessage(
                "Exemplo aberto. Para usar sua arte, escolha Novo / importar imagem."
            )
        except (ValueError, OSError) as exc:
            self._report_error(exc)

    def select_project(self, project_id: str) -> bool:
        for index in range(self.project_list.count()):
            item = self.project_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == project_id:
                self.project_list.setCurrentItem(item)
                return True
        return False

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar imagem ou atlas", "", "Imagens PNG/WebP (*.png *.webp)"
        )
        if not path:
            return
        name, accepted = QInputDialog.getText(
            self, "Novo mascote", "Nome do projeto", text=Path(path).stem[:100]
        )
        if not accepted:
            return
        try:
            project = self.library.create(
                name,
                Path(path),
                source_kind=self.source_kind_combo.currentData(),
                remove_magenta=self.remove_magenta_check.isChecked(),
            )
            self.reload_projects()
            self.select_project(project.id)
            self.statusBar().showMessage("Imagem importada. Edite os estados e salve as alterações.")
        except (ValueError, OSError) as exc:
            self._report_error(exc)

    def _choose_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar projeto editável", "", "Projeto editável (*.zip)"
        )
        if not path:
            return
        try:
            project = self.library.import_zip(Path(path))
            self.reload_projects()
            self.select_project(project.id)
            self.statusBar().showMessage("Projeto editável importado com identificador próprio.")
        except (ValueError, OSError) as exc:
            self._report_error(exc)

    def _duplicate_selected(self) -> None:
        project_id = self.selected_project_id
        if project_id is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Duplicar mascote", "Nome da cópia", text=(self.name_edit.text() + " — cópia")[:100]
        )
        if not accepted:
            return
        if not self.save_selected():
            return
        try:
            project = self.library.duplicate(project_id, name=name)
            self.reload_projects()
            self.select_project(project.id)
            self.statusBar().showMessage("Cópia criada sem sobrescrever o projeto original.")
        except (ValueError, OSError) as exc:
            self._report_error(exc)

    def _export_selected(self, *, hermes: bool) -> None:
        project_id = self.selected_project_id
        if project_id is None:
            return
        suffix = "-hermes" if hermes else ""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar pacote Hermes" if hermes else "Exportar projeto editável",
            f"{project_id}{suffix}.zip",
            "Arquivo ZIP (*.zip)",
        )
        if not path or not self.save_selected():
            return
        try:
            destination = Path(path)
            if destination.suffix.lower() != ".zip":
                destination = destination.with_name(destination.name + ".zip")
            exporter = self.library.export_hermes if hermes else self.library.export_project
            exporter(project_id, destination)
            message = (
                "Pacote Hermes exportado. A cadência no Hermes é própria, não o FPS deste editor."
                if hermes
                else ("Projeto editável exportado: metadados e imagem original.")
            )
            self.statusBar().showMessage(message)
        except (ValueError, OSError) as exc:
            self._report_error(exc)

    def _capture_edits(self) -> None:
        if self._loading or self._editing_id not in self._drafts:
            return
        project = self._drafts[self._editing_id]
        project.name = self.name_edit.text()
        project.agent_id = self.agent_id_edit.text()
        project.author = self.author_edit.text()
        project.asset_license = self.license_edit.text()
        settings = project.animations[self._editing_state]
        for key, field in self.parameter_inputs.items():
            field.interpretText()
            setattr(settings, key, field.value())

    def _load_selected(self, *args) -> None:
        self._capture_edits()
        project_id = self.selected_project_id
        self._editing_id = project_id
        self._loading = True
        try:
            for button in self._selected_buttons:
                button.setEnabled(project_id is not None)
            fields = (
                self.name_edit,
                self.agent_id_edit,
                self.author_edit,
                self.license_edit,
                self.state_combo,
                self.mode_combo,
                *self.parameter_inputs.values(),
            )
            for field in fields:
                field.setEnabled(project_id is not None)
            if project_id is None:
                for field in (self.name_edit, self.agent_id_edit, self.author_edit, self.license_edit):
                    field.clear()
                self.preview_label.clear()
                self.preview_label.setText("Selecione um projeto")
                self._preview_frames = ()
                self.preview_timer.stop()
                return
            if project_id not in self._drafts:
                self._drafts[project_id] = self.library.load(project_id)
            project = self._drafts[project_id]
            self.name_edit.setText(project.name)
            self.agent_id_edit.setText(project.agent_id)
            self.author_edit.setText(project.author)
            self.license_edit.setText(project.asset_license)
            pet = self.mascot_windows.get(project_id)
            state = pet.current_state if pet is not None else self._manual_states.get(project_id, "idle")
            self._editing_state = state
            self.state_combo.setCurrentIndex(self.state_combo.findData(state))
            automatic = project_id in self._automatic_ids
            self.mode_combo.setCurrentIndex(self.mode_combo.findData("automatic" if automatic else "manual"))
            self.state_combo.setEnabled(not automatic)
            self._load_animation_fields()
        except (ValueError, OSError) as exc:
            self._report_error(exc)
        finally:
            self._loading = False

    def _load_animation_fields(self) -> None:
        if self._editing_id is None:
            return
        settings = self._drafts[self._editing_id].animations[self._editing_state]
        for key, field in self.parameter_inputs.items():
            field.setValue(getattr(settings, key))
        self._refresh_preview()

    def _mode_changed(self, index: int) -> None:
        if self._loading or self._editing_id is None:
            return
        automatic = self.mode_combo.currentData() == "automatic"
        if automatic:
            self._automatic_ids.add(self._editing_id)
        else:
            self._automatic_ids.discard(self._editing_id)
        self.state_combo.setEnabled(not automatic)
        self.save_desktop()

    def poll_agent_states(self) -> None:
        if not self._automatic_ids:
            return
        path = self.library.root / "agent-states.json"
        try:
            if not path.exists():
                return
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
                raise ValueError("Eventos locais devem ser arquivo regular de até 64 KiB.")
            with path.open("rb") as handle:
                raw = handle.read(64 * 1024 + 1)
            if len(raw) > 64 * 1024:
                raise ValueError("Eventos locais excedem 64 KiB.")
            data = json.loads(raw)
            from .core import STATE_ROWS

            if (
                not isinstance(data, dict)
                or type(data.get("schema_version")) is not int
                or data["schema_version"] != 1
                or set(data) != {"schema_version", "agents"}
                or not isinstance(data.get("agents"), dict)
            ):
                raise ValueError("Formato de eventos locais inválido.")
            if any(
                not isinstance(agent_id, str)
                or len(agent_id) > 100
                or not isinstance(state, str)
                or state not in STATE_ROWS
                for agent_id, state in data["agents"].items()
            ):
                raise ValueError("Identificador de agente ou estado local inválido.")
            for project_id, pet in self.mascot_windows.items():
                if project_id not in self._automatic_ids or not pet.project.agent_id:
                    continue
                state = data["agents"].get(pet.project.agent_id)
                if state not in pet.project.animations or state == pet.current_state:
                    continue
                self._applying_events = True
                try:
                    pet.set_state(state)
                finally:
                    self._applying_events = False
            self._event_error = None
        except (ValueError, OSError, UnicodeError, RecursionError) as exc:
            message = f"Eventos locais ignorados: {exc}"
            if message != self._event_error:
                self.statusBar().showMessage(message)
                self._event_error = message

    def _state_changed(self, index: int) -> None:
        if self._loading or self._editing_id is None:
            return
        self._capture_edits()
        state = self.state_combo.currentData()
        self._editing_state = state
        self._manual_states[self._editing_id] = state
        self._loading = True
        try:
            pet = self.mascot_windows.get(self._editing_id)
            if pet is not None:
                pet.set_state(state)
            self._load_animation_fields()
        except (ValueError, OSError) as exc:
            self._report_error(exc)
        finally:
            self._loading = False
        self.save_desktop()

    def _refresh_preview(self) -> None:
        if self._editing_id is None:
            return
        key = (self._editing_id, self._editing_state)
        if key not in self._preview_cache:
            self._preview_cache[key] = _render_pixmaps(self.library, *key)
        self._preview_frames = self._preview_cache[key]
        self._preview_index = 0
        self.preview_label.setPixmap(self._preview_frames[0])
        fps = self._drafts[self._editing_id].animations[self._editing_state].fps
        self.preview_timer.setInterval(round(1000 / fps))
        if self.isVisible():
            self.preview_timer.start()

    def _advance_preview(self) -> None:
        if self._preview_frames:
            self._preview_index = (self._preview_index + 1) % 6
            self.preview_label.setPixmap(self._preview_frames[self._preview_index])

    def save_selected(self) -> bool:
        if self.selected_project_id is None:
            return False
        self._capture_edits()
        project_id = self.selected_project_id
        try:
            self.library.save(self._drafts[project_id])
            self._drafts[project_id] = self.library.load(project_id)
            self._preview_cache = {
                key: value for key, value in self._preview_cache.items() if key[0] != project_id
            }
            pet = self.mascot_windows.get(project_id)
            if pet is not None:
                pet.reload_project()
            self.reload_projects()
            self.statusBar().showMessage("Projeto salvo. Parâmetros aplicados ao mascote e à prévia.")
            return True
        except (ValueError, OSError) as exc:
            self._report_error(exc)
            return False

    def _report_error(self, error: Exception | str) -> None:
        # Erros de arquivo/polling não abrem diálogos nem bloqueiam o loop Qt.
        self.statusBar().showMessage(f"Erro: {error}")

    def _load_desktop(self) -> None:
        from .core import STATE_ROWS

        path = self.library.root / "desktop.json"
        try:
            if not path.exists():
                return
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
                raise ValueError("Configuração deve ser arquivo regular de até 1 MiB.")
            with path.open("rb") as handle:
                raw = handle.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("Configuração excede 1 MiB.")
            data = json.loads(raw)
            if (
                not isinstance(data, dict)
                or type(data.get("schema_version")) is not int
                or data["schema_version"] != 1
                or not isinstance(data.get("mascots"), dict)
            ):
                raise ValueError("Schema desktop inválido.")
            records = {}
            known_ids = {project.id for project in self.library.list_projects()}
            for project_id, record in data["mascots"].items():
                if project_id not in known_ids:
                    continue
                if (
                    not isinstance(record, dict)
                    or not {"x", "y", "scale", "visible", "state", "automatic"} <= set(record)
                    or any(type(record[key]) is not int or abs(record[key]) > 1_000_000 for key in ("x", "y"))
                    or type(record["visible"]) is not bool
                    or type(record["automatic"]) is not bool
                    or not isinstance(record["state"], str)
                    or record["state"] not in STATE_ROWS
                    or isinstance(record["scale"], bool)
                    or not isinstance(record["scale"], (int, float))
                    or not math.isfinite(record["scale"])
                    or not 0.25 <= record["scale"] <= 2
                ):
                    raise ValueError("Geometria ou estado de mascote inválido.")
                records[project_id] = dict(record)
            editor = data.get("editor")
            if editor is not None:
                if (
                    not isinstance(editor, dict)
                    or not {"x", "y", "width", "height"} <= set(editor)
                    or any(
                        type(editor[key]) is not int or abs(editor[key]) > 1_000_000
                        for key in ("x", "y", "width", "height")
                    )
                    or editor["width"] < 1
                    or editor["height"] < 1
                ):
                    raise ValueError("Geometria do editor inválida.")
                self.resize(editor["width"], editor["height"])
                self.move(editor["x"], editor["y"])
                _clamp_window(self)
            self._desktop_records = records
            self._manual_states.update({key: record["state"] for key, record in records.items()})
            self._automatic_ids.update(key for key, record in records.items() if record["automatic"])
            self._load_selected()
        except (ValueError, OSError, UnicodeError, RecursionError, OverflowError) as exc:
            self.statusBar().showMessage(f"Configuração desktop ignorada: {exc}")

    def restore_desktop(self) -> None:
        self._restoring = True
        try:
            for project_id, record in tuple(self._desktop_records.items()):
                if record["visible"]:
                    try:
                        self.show_mascot(project_id)
                    except (ValueError, OSError) as exc:
                        self._report_error(exc)
        finally:
            self._restoring = False
        self._load_selected()

    def save_desktop(self) -> bool:
        if self._restoring or self._shutting_down:
            return False
        temporary = None
        try:
            records = {key: dict(value) for key, value in self._desktop_records.items()}
            known_ids = {project.id for project in self.library.list_projects()}
            for project_id in self._manual_states.keys() | self._automatic_ids:
                records.setdefault(
                    project_id,
                    {"x": 32, "y": 32, "scale": 1.0, "visible": False, "state": "idle", "automatic": False},
                )
            for project_id, pet in self.mascot_windows.items():
                records[project_id] = {
                    "x": pet.x(),
                    "y": pet.y(),
                    "scale": pet.scale,
                    "visible": pet.isVisible(),
                    "state": pet.current_state,
                    "automatic": False,
                }
            for project_id, record in records.items():
                if project_id not in self.mascot_windows:
                    record["state"] = self._manual_states.get(project_id, record["state"])
                record["automatic"] = project_id in self._automatic_ids
            records = {key: value for key, value in records.items() if key in known_ids}
            geometry = self.normalGeometry() if self.isMinimized() else QRect(self.pos(), self.size())
            if geometry.isEmpty():
                geometry = QRect(self.pos(), self.size())
            data = {
                "schema_version": 1,
                "mascots": records,
                "editor": {
                    "x": geometry.x(),
                    "y": geometry.y(),
                    "width": geometry.width(),
                    "height": geometry.height(),
                },
            }
            encoded = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
            descriptor, name = tempfile.mkstemp(prefix=".desktop-", suffix=".tmp", dir=self.library.root)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.library.root / "desktop.json")
            self._desktop_records = records
            return True
        except (ValueError, OSError) as exc:
            self._report_error(exc)
            return False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def show_editor(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _ensure_recoverable(self) -> bool:
        if (
            self.tray_icon is not None
            and not self.tray_available
            and not any(pet.isVisible() for pet in self.mascot_windows.values())
        ):
            self.show_editor()
            self.statusBar().showMessage(
                "Bandeja indisponível e nenhum mascote visível. Use Sair do aplicativo para encerrar."
            )
            return True
        return False

    def _mascot_changed(self, project_id: str) -> None:
        if self._shutting_down or self._restoring:
            return
        pet = self.mascot_windows.get(project_id)
        if pet is None:
            return
        changed_state = self._known_states.get(project_id) != pet.current_state
        self._known_states[project_id] = pet.current_state
        if changed_state:
            if not self._applying_events:
                self._manual_states[project_id] = pet.current_state
                self._automatic_ids.discard(project_id)
            if project_id == self._editing_id and not self._loading:
                self._capture_edits()
                self._loading = True
                try:
                    self._editing_state = pet.current_state
                    self.state_combo.setCurrentIndex(self.state_combo.findData(pet.current_state))
                    automatic = project_id in self._automatic_ids
                    self.mode_combo.setCurrentIndex(
                        self.mode_combo.findData("automatic" if automatic else "manual")
                    )
                    self.state_combo.setEnabled(not automatic)
                    self._load_animation_fields()
                except (ValueError, OSError) as exc:
                    self._report_error(exc)
                finally:
                    self._loading = False
        self.save_desktop()
        self._ensure_recoverable()

    def show_mascot(self, project_id: str) -> MascotWindow:
        if project_id not in self.mascot_windows:
            pet = MascotWindow(self.library, project_id)
            pet.editor_requested.connect(self.show_editor)
            pet.error_occurred.connect(self._report_error)
            screen = self.screen() or QApplication.primaryScreen()
            if screen is not None:
                offset = 32 + (len(self.mascot_windows) % 8) * 24
                pet.move(screen.availableGeometry().topLeft() + QPoint(offset, offset))
            self.mascot_windows[project_id] = pet
            record = self._desktop_records.get(project_id)
            pet.set_state(self._manual_states.get(project_id, "idle"))
            if record is not None:
                pet.set_scale(record["scale"])
                pet.move(record["x"], record["y"])
            _clamp_window(pet)
            self._known_states[project_id] = pet.current_state
            pet.on_changed = lambda: self._mascot_changed(project_id)
        pet = self.mascot_windows[project_id]
        pet.showNormal()
        self._mascot_changed(project_id)
        return pet

    def show_all_mascots(self) -> None:
        try:
            projects = self.library.list_projects()
        except (ValueError, OSError) as exc:
            self._report_error(exc)
            return
        for project in projects:
            try:
                self.show_mascot(project.id)
            except (ValueError, OSError) as exc:
                self._report_error(exc)

    def _show_selected(self) -> None:
        if self.selected_project_id is not None:
            try:
                self.show_mascot(self.selected_project_id)
            except (ValueError, OSError) as exc:
                self._report_error(exc)

    def _hide_selected(self) -> None:
        pet = self.mascot_windows.get(self.selected_project_id)
        if pet is not None:
            pet.hide()

    def reload_projects(self) -> None:
        selected = self.selected_project_id
        projects = self.library.list_projects()
        self.project_list.blockSignals(True)
        try:
            self.project_list.clear()
            for project in projects:
                item = QListWidgetItem(project.name)
                item.setData(Qt.ItemDataRole.UserRole, project.id)
                self.project_list.addItem(item)
                if project.id == selected:
                    self.project_list.setCurrentItem(item)
            if self.project_list.currentItem() is None and projects:
                self.project_list.setCurrentRow(0)
        finally:
            self.project_list.blockSignals(False)
        self.empty_label.setVisible(not projects)
        self._load_selected()

    @property
    def selected_project_id(self) -> str | None:
        item = self.project_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._preview_frames and not self._shutting_down:
            self.preview_timer.start()

    def hideEvent(self, event) -> None:
        self.preview_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        if self._shutting_down:
            event.accept()
            return
        self.save_desktop()
        event.ignore()
        if not self._ensure_recoverable():
            self.hide()


def ensure_app() -> QApplication:
    """Reutiliza a aplicação e mantém o runtime enquanto o editor está oculto."""
    global _application
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    if not isinstance(app, QApplication):
        raise RuntimeError("O editor requer QApplication; existe apenas uma QCoreApplication nesta execução.")
    _application = app  # mantém a aplicação viva mesmo em uso direto dos construtores.
    app.setQuitOnLastWindowClosed(False)
    return app


def run_desktop(library: Library, show_ids: list[str] | None = None, *, editor: bool = True) -> int:
    """Executa Qt; uma instância por biblioteca, ids explícitos substituem a visibilidade salva."""
    lock = QLockFile(str(library.root / ".desktop.lock"))
    # Um runtime pode durar dias. Não expire o lock apenas por idade.
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        print(
            "Mascot Studio já está aberto nesta biblioteca, ou o lock não pôde ser criado.", file=sys.stderr
        )
        return 2
    studio = None
    app = ensure_app()
    try:
        studio = StudioWindow(library)
        app.aboutToQuit.connect(studio._quit_cleanup)
        studio.create_tray()
        if show_ids is None:
            studio.restore_desktop()
        else:
            for record in studio._desktop_records.values():
                record["visible"] = False
            for project_id in dict.fromkeys(show_ids):
                studio.show_mascot(project_id)
        if editor or (
            not studio.tray_available and not any(pet.isVisible() for pet in studio.mascot_windows.values())
        ):
            studio.show_editor()
            _clamp_window(studio)
        return app.exec()
    finally:
        if studio is not None:
            app.aboutToQuit.disconnect(studio._quit_cleanup)
            studio.shutdown(quit_app=False)
            studio.deleteLater()
            # exec() terminou; processe apenas a destruição deste editor, não outro loop.
            QCoreApplication.sendPostedEvents(studio, QEvent.Type.DeferredDelete)
        lock.unlock()
