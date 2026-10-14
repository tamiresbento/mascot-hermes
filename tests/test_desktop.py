"""Testes reais de Qt; executar com QT_QPA_PLATFORM=offscreen."""

import importlib
import importlib.util
import json
import zipfile

import pytest
from PIL import Image
from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QContextMenuEvent, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox


@pytest.fixture
def window_library(library, image_source):
    project = library.create("Companheiro", image_source)
    library.test_project_id = project.id
    return library


def test_mascot_is_independent_translucent_topmost_and_survives_editor_minimize(qtbot, window_library):
    desktop = importlib.import_module("mascot_studio.desktop")
    assert hasattr(desktop, "MascotWindow"), "Janela independente ainda não implementada"
    editor = QMainWindow()
    qtbot.addWidget(editor)
    editor.show()
    pet = desktop.MascotWindow(window_library, window_library.test_project_id)
    qtbot.addWidget(pet)
    pet.show()
    qtbot.waitUntil(pet.isVisible)
    assert pet.parent() is None
    assert pet.isWindow()
    assert pet.windowFlags() & Qt.WindowType.Tool
    assert pet.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert pet.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert pet.windowTitle() == "Mascote — Companheiro"
    assert pet.project_id == window_library.test_project_id
    editor.showMinimized()
    qtbot.wait(30)
    assert pet.isVisible()
    assert not pet.isMinimized()
    editor.close()
    assert pet.isVisible()


def test_animation_caches_six_pixmaps_per_state_and_reloads_settings(qtbot, window_library):
    desktop = importlib.import_module("mascot_studio.desktop")
    calls = []
    render = window_library.render_frame

    def counted_render(project_id, state, index=0):
        calls.append((state, index))
        return render(project_id, state, index)

    window_library.render_frame = counted_render
    pet = desktop.MascotWindow(window_library, window_library.test_project_id)
    qtbot.addWidget(pet)
    assert hasattr(pet, "frame_cache"), "Cache de QPixmap ausente"
    from PySide6.QtGui import QPixmap

    assert len(pet.frame_cache["idle"]) == 6
    assert all(isinstance(frame, QPixmap) and not frame.isNull() for frame in pet.frame_cache["idle"])
    assert len(calls) == 6
    pet.show()
    qtbot.wait(350)
    assert len(calls) == 6, "Tick não deve executar render/Pillow/IO"
    assert pet.frame_index != 0
    pet.set_state("review")
    assert pet.current_state == "review"
    assert len(calls) == 12
    pet.set_state("idle")
    assert len(calls) == 12
    changed = window_library.load(window_library.test_project_id)
    changed.animations["idle"].fps = 12.0
    window_library.save(changed)
    pet.reload_project()
    assert pet.current_state == "idle"
    assert 80 <= pet.timer.interval() <= 84
    assert len(calls) == 18
    pet.set_scale(1.5)
    assert pet.width() == 288
    assert pet.height() == 312
    with pytest.raises(ValueError):
        pet.set_state("invalid-state")
    with pytest.raises(ValueError):
        pet.set_scale(float("nan"))


def test_drag_uses_global_coordinates_and_context_menu_does_not_block(qtbot, qapp, window_library):
    desktop = importlib.import_module("mascot_studio.desktop")
    pet = desktop.MascotWindow(window_library, window_library.test_project_id)
    qtbot.addWidget(pet)
    pet.move(80, 90)
    pet.show()
    for event_type, global_pos, button, buttons in (
        (
            QMouseEvent.Type.MouseButtonPress,
            QPointF(90, 100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
        ),
        (QMouseEvent.Type.MouseMove, QPointF(-510, -100), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton),
        (
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(-510, -100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
        ),
    ):
        event = QMouseEvent(
            event_type, QPointF(10, 10), global_pos, button, buttons, Qt.KeyboardModifier.NoModifier
        )
        qapp.sendEvent(pet, event)
    assert pet.x() == -520, "Arrastar entre monitores não deve prender na tela primária"
    assert pet.y() == -110
    opened = []
    assert hasattr(pet, "editor_requested"), "Callback de reabrir editor ausente"
    pet.editor_requested.connect(lambda: opened.append(True))
    menu = pet.build_context_menu()
    actions = {action.text(): action for action in menu.actions()}
    assert "Mostrar editor" in actions
    assert "Ocultar mascote" in actions
    states = actions["Estado"].menu()
    review_action = next(action for action in states.actions() if action.text() == "Revisando")
    review_action.trigger()
    assert pet.current_state == "review"
    actions["Mostrar editor"].trigger()
    assert opened == [True]
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, pet.rect().center(), pet.mapToGlobal(pet.rect().center())
    )
    qapp.sendEvent(pet, event)
    assert pet.context_menu.isVisible(), "Menu deve usar popup, nunca exec bloqueante"
    pet.context_menu.hide()
    actions["Ocultar mascote"].trigger()
    assert not pet.isVisible()
    assert not pet.timer.isActive()
    menu.deleteLater()


@pytest.fixture
def library(tmp_path):
    from mascot_studio.core import Library

    return Library(tmp_path / "library")


@pytest.fixture
def image_source(tmp_path):
    path = tmp_path / "test-companion.png"
    image = Image.new("RGBA", (60, 80), (0, 0, 0, 0))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    draw.ellipse((5, 5, 55, 70), fill=(24, 170, 130, 255), outline=(0, 0, 0, 255), width=3)
    image.save(path)
    return path


def test_editor_empty_library_exposes_portuguese_editor_and_import_guidance(qtbot, library):
    desktop = importlib.import_module("mascot_studio.desktop")
    assert hasattr(desktop, "StudioWindow"), "Editor nativo ausente"
    studio = desktop.StudioWindow(library)
    qtbot.addWidget(studio)
    studio.show()
    assert studio.project_list.count() == 0
    assert "Importe" in studio.empty_label.text()
    assert "exemplo" in studio.empty_label.text()
    assert studio.import_image_button.isEnabled()
    assert studio.example_button.isEnabled()
    assert not studio.save_button.isEnabled()
    assert studio.state_combo.count() == 9
    assert studio.mode_combo.itemText(0) == "Manual"
    assert set(studio.parameter_inputs) == {"fps", "bob", "sway", "rotation", "zoom"}
    assert studio.parameter_inputs["fps"].minimum() == 1
    assert studio.parameter_inputs["fps"].maximum() == 30
    assert studio.parameter_inputs["zoom"].minimum() == 0.25
    assert studio.name_edit.maxLength() == 100
    assert studio.agent_id_edit.maxLength() == 100
    assert studio.export_hermes_button.text() == "Exportar Hermes…"
    assert studio.preview_label is not None
    assert studio.mascot_windows == {}
    studio.close()
    assert not studio.isVisible()


def test_editor_shows_twelve_unique_pets_and_minimize_close_do_not_hide_them(qtbot, library, image_source):
    from mascot_studio.desktop import StudioWindow

    projects = [library.create(f"Mascote {index:02}", image_source) for index in range(12)]
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    studio.show()
    assert hasattr(studio, "show_all_mascots"), "Mostrar todos não implementado"
    studio.show_all_mascots()
    assert len(studio.mascot_windows) == 12
    for project in projects:
        pet = studio.mascot_windows[project.id]
        qtbot.addWidget(pet)
        assert studio.show_mascot(project.id) is pet
        assert pet.parent() is None
        assert pet.isVisible()
        assert not pet.isMinimized()
        assert pet.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    studio.showMinimized()
    qtbot.wait(30)
    assert all(pet.isVisible() and not pet.isMinimized() for pet in studio.mascot_windows.values())
    studio.close()
    assert all(pet.isVisible() and not pet.isMinimized() for pet in studio.mascot_windows.values())
    pet = studio.mascot_windows[projects[0].id]
    pet.editor_requested.emit()
    assert studio.isVisible()
    assert not studio.isMinimized()


def test_editor_edits_multiple_states_saves_and_reopens_without_resetting_manual_state(
    qtbot, library, image_source
):
    from mascot_studio.desktop import StudioWindow

    project = library.create("Inicial", image_source, agent_id="agent-initial")
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    studio.show()
    assert studio.name_edit.text() == "Inicial", "Campos ainda não carregam o projeto selecionado"
    assert studio.agent_id_edit.text() == "agent-initial"
    pet = studio.show_mascot(project.id)
    qtbot.addWidget(pet)
    studio.name_edit.setText("Companheiro revisado")
    studio.agent_id_edit.setText("task-runner")
    studio.author_edit.setText("Autoria de teste")
    studio.license_edit.setText("CC0")
    studio.state_combo.setCurrentIndex(studio.state_combo.findData("review"))
    assert pet.current_state == "review"
    values = {"fps": 12.0, "bob": 5.0, "sway": 3.0, "rotation": 4.0, "zoom": 1.25}
    for key, value in values.items():
        studio.parameter_inputs[key].setValue(value)
    studio.state_combo.setCurrentIndex(studio.state_combo.findData("waving"))
    studio.parameter_inputs["fps"].setValue(9.5)
    studio.state_combo.setCurrentIndex(studio.state_combo.findData("review"))
    assert studio.parameter_inputs["fps"].value() == 12.0
    qtbot.mouseClick(studio.save_button, Qt.MouseButton.LeftButton)
    saved = library.load(project.id)
    assert saved.name == "Companheiro revisado"
    assert saved.agent_id == "task-runner"
    assert saved.author == "Autoria de teste"
    assert saved.asset_license == "CC0"
    assert saved.animations["waving"].fps == 9.5
    for key, value in values.items():
        assert getattr(saved.animations["review"], key) == value
    assert pet.current_state == "review"
    assert pet.timer.interval() == 83
    studio.reload_projects()
    assert studio.state_combo.currentData() == "review"
    assert pet.current_state == "review"
    assert not studio.preview_label.pixmap().isNull()
    reopened = StudioWindow(library)
    qtbot.addWidget(reopened)
    assert reopened.name_edit.text() == saved.name
    reopened.state_combo.setCurrentIndex(reopened.state_combo.findData("review"))
    assert reopened.parameter_inputs["fps"].value() == 12.0


def test_ui_import_duplicate_editable_and_hermes_exports_roundtrip(
    qtbot, library, image_source, tmp_path, monkeypatch
):
    from mascot_studio.desktop import StudioWindow
    from PySide6.QtWidgets import QFileDialog, QInputDialog

    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    studio.show()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(image_source), "PNG"))
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Projeto importado", True))
    qtbot.mouseClick(studio.import_image_button, Qt.MouseButton.LeftButton)
    assert studio.project_list.count() == 1, "Botão importar imagem não criou o projeto"
    original_id = studio.selected_project_id
    assert library.load(original_id).name == "Projeto importado"
    studio.agent_id_edit.setText("worker-a")
    assert studio.save_selected()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Cópia editável", True))
    qtbot.mouseClick(studio.duplicate_button, Qt.MouseButton.LeftButton)
    duplicate_id = studio.selected_project_id
    assert duplicate_id != original_id
    assert library.load(duplicate_id).agent_id == "worker-a"
    assert library.load(original_id).name == "Projeto importado"
    editable = tmp_path / "editable.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(editable), "ZIP"))
    qtbot.mouseClick(studio.export_project_button, Qt.MouseButton.LeftButton)
    with zipfile.ZipFile(editable) as archive:
        assert set(archive.namelist()) == {"project.json", "source.png"}
        assert json.loads(archive.read("project.json"))["name"] == "Cópia editável"
    hermes = tmp_path / "hermes.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(hermes), "ZIP"))
    qtbot.mouseClick(studio.export_hermes_button, Qt.MouseButton.LeftButton)
    with zipfile.ZipFile(hermes) as archive:
        assert f"{duplicate_id}/pet.json" in archive.namelist()
        assert f"{duplicate_id}/spritesheet.png" in archive.namelist()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(editable), "ZIP"))
    qtbot.mouseClick(studio.import_zip_button, Qt.MouseButton.LeftButton)
    assert studio.project_list.count() == 3
    assert studio.selected_project_id not in {original_id, duplicate_id}
    assert library.load(studio.selected_project_id).agent_id == "worker-a"


def test_empty_library_can_open_packaged_example_without_cli(qtbot, library):
    from mascot_studio.desktop import StudioWindow

    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    studio.show()
    qtbot.mouseClick(studio.example_button, Qt.MouseButton.LeftButton)
    assert studio.project_list.count() == 1, "Abrir exemplo não está conectado"
    project = library.load(studio.selected_project_id)
    assert project.source_kind == "image"
    assert library.asset_path(project.id).is_file()
    assert not studio.preview_label.pixmap().isNull()
    assert not studio.empty_label.isVisible()


def test_local_events_only_change_matching_automatic_pets_and_never_reset_manual(
    qtbot, library, image_source, monkeypatch
):
    from mascot_studio.desktop import StudioWindow
    import socket

    projects = [
        library.create("Automático", image_source, agent_id="worker-a"),
        library.create("Manual", image_source, agent_id="worker-a"),
        library.create("Outro agente", image_source, agent_id="worker-b"),
    ]
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    pets = [studio.show_mascot(project.id) for project in projects]
    for pet in pets:
        qtbot.addWidget(pet)
        pet.set_state("waving")
    assert hasattr(studio, "poll_agent_states"), "Polling de eventos locais ausente"
    assert studio.event_timer.interval() >= 1000
    studio.select_project(projects[0].id)
    studio.mode_combo.setCurrentIndex(studio.mode_combo.findData("automatic"))
    studio.select_project(projects[2].id)
    studio.mode_combo.setCurrentIndex(studio.mode_combo.findData("automatic"))
    event_path = library.root / "agent-states.json"
    event_path.write_text(json.dumps({"schema_version": 1, "agents": {"worker-a": "review"}}))

    def forbidden_network(*args, **kwargs):
        raise AssertionError("Interface deve ser estritamente local")

    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    studio.poll_agent_states()
    assert [pet.current_state for pet in pets] == ["review", "waving", "waving"]
    studio.reload_projects()
    assert [pet.current_state for pet in pets] == ["review", "waving", "waving"]
    studio.select_project(projects[0].id)
    assert studio.mode_combo.currentData() == "automatic"
    studio.mode_combo.setCurrentIndex(studio.mode_combo.findData("manual"))
    event_path.write_text(
        json.dumps({"schema_version": 1, "agents": {"worker-a": "failed", "worker-b": "running"}})
    )
    studio.poll_agent_states()
    assert pets[0].current_state == "review"
    assert pets[2].current_state == "running"
    assert studio.event_timer.isActive()


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b" " * (64 * 1024 + 1),
        json.dumps({"schema_version": True, "agents": {"worker-a": "review"}}).encode(),
        json.dumps({"schema_version": 1, "agents": {"worker-a": []}}).encode(),
        json.dumps({"schema_version": 1, "agents": {"worker-a": "unknown"}}).encode(),
        json.dumps({"schema_version": 2, "agents": {"worker-a": "review"}}).encode(),
    ],
    ids=["corrupt", "oversize", "boolean-schema", "unhashable-state", "unknown-state", "new-schema"],
)
def test_invalid_local_events_are_nonmodal_and_keep_last_state(qtbot, library, image_source, payload):
    from mascot_studio.desktop import StudioWindow

    project = library.create("Evento inválido", image_source, agent_id="worker-a")
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    pet = studio.show_mascot(project.id)
    qtbot.addWidget(pet)
    pet.set_state("waving")
    studio.mode_combo.setCurrentIndex(studio.mode_combo.findData("automatic"))
    (library.root / "agent-states.json").write_bytes(payload)
    studio.poll_agent_states()
    assert pet.current_state == "waving"
    assert "ignorados" in studio.statusBar().currentMessage()
    assert studio.event_timer.isActive()
    assert studio.findChildren(QMessageBox) == []


def test_desktop_restores_visibility_geometry_scale_state_and_clamps_offscreen(qtbot, library, image_source):
    from mascot_studio.desktop import StudioWindow

    projects = [library.create(name, image_source) for name in ("Visível", "Oculto")]
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    pets = [studio.show_mascot(project.id) for project in projects]
    for pet in pets:
        qtbot.addWidget(pet)
    pets[0].set_scale(1.5)
    pets[0].set_state("review")
    pets[0].move(99999, -99999)
    pets[1].hide()
    assert hasattr(studio, "save_desktop"), "Persistência desktop ausente"
    assert studio.save_desktop()
    data = json.loads((library.root / "desktop.json").read_text())
    assert data["schema_version"] == 1
    assert data["mascots"][projects[0].id]["visible"] is True
    assert data["mascots"][projects[1].id]["visible"] is False
    assert data["mascots"][projects[0].id]["scale"] == 1.5
    restored = StudioWindow(library)
    qtbot.addWidget(restored)
    restored.restore_desktop()
    assert set(restored.mascot_windows) == {projects[0].id}
    pet = restored.mascot_windows[projects[0].id]
    qtbot.addWidget(pet)
    assert pet.current_state == "review"
    assert pet.scale == 1.5
    assert pet.isVisible()
    assert any(screen.availableGeometry().contains(pet.geometry()) for screen in QGuiApplication.screens())
    restored.select_project(projects[0].id)
    assert restored.state_combo.currentData() == "review"
    pet.move(120, 130)
    restored.close()
    saved = json.loads((library.root / "desktop.json").read_text())
    assert saved["mascots"][projects[0].id]["x"] == 120
    assert saved["mascots"][projects[0].id]["y"] == 130
    assert pet.isVisible()


def test_pet_context_state_and_visibility_sync_editor_and_persist_immediately(qtbot, library, image_source):
    from mascot_studio.desktop import StudioWindow

    project = library.create("Contexto", image_source, agent_id="worker-a")
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    studio.show()
    pet = studio.show_mascot(project.id)
    qtbot.addWidget(pet)
    studio.name_edit.setText("Rascunho preservado")
    pet.set_state("jumping")
    assert studio.state_combo.currentData() == "jumping", "Menu do mascote precisa sincronizar o editor"
    assert studio.name_edit.text() == "Rascunho preservado"
    record = json.loads((library.root / "desktop.json").read_text())["mascots"][project.id]
    assert record["state"] == "jumping"
    assert record["visible"] is True
    pet.hide()
    record = json.loads((library.root / "desktop.json").read_text())["mascots"][project.id]
    assert record["visible"] is False
    assert studio.show_mascot(project.id) is pet
    record = json.loads((library.root / "desktop.json").read_text())["mascots"][project.id]
    assert record["visible"] is True
    studio.mode_combo.setCurrentIndex(studio.mode_combo.findData("automatic"))
    pet.set_state("waving")
    assert studio.mode_combo.currentData() == "manual", "Estado escolhido no mascote é um comando manual"


def test_tray_reopens_editor_and_explicit_shutdown_stops_independent_pets(qtbot, library, image_source):
    from mascot_studio.desktop import StudioWindow
    from PySide6.QtWidgets import QSystemTrayIcon

    project = library.create("Bandeja", image_source)
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    pet = studio.show_mascot(project.id)
    qtbot.addWidget(pet)
    assert hasattr(studio, "create_tray"), "Bandeja e saída explícita ausentes"
    tray = studio.create_tray()
    assert isinstance(tray, QSystemTrayIcon)
    assert not tray.icon().isNull()
    assert {action.text() for action in tray.contextMenu().actions()} >= {
        "Mostrar editor",
        "Sair do aplicativo",
    }
    studio.close()
    assert pet.isVisible()
    assert not studio.isVisible()
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    assert studio.isVisible()
    assert not studio.isMinimized()
    studio.shutdown(quit_app=False)
    assert not pet.isVisible()
    assert not pet.timer.isActive()
    assert not studio.event_timer.isActive()
    assert not studio.preview_timer.isActive()
    assert not tray.isVisible()
    data = json.loads((library.root / "desktop.json").read_text())
    assert data["mascots"][project.id]["visible"] is True, "Salvar deve ocorrer antes de ocultar ao sair"
    studio.shutdown(quit_app=False)


def test_run_desktop_executes_real_qt_loop_pet_only_and_exits_via_tray(qtbot, qapp, library, image_source):
    import mascot_studio.desktop as desktop

    assert hasattr(desktop, "run_desktop"), "Entrypoint desktop ausente"
    project = library.create("Runtime", image_source)
    observed = {}
    timer = QTimer()
    timer.setSingleShot(True)
    watchdog = QTimer()
    watchdog.setSingleShot(True)

    def finish():
        try:
            studio = next(
                widget for widget in qapp.topLevelWidgets() if isinstance(widget, desktop.StudioWindow)
            )
            observed["editor_hidden"] = not studio.isVisible()
            pet = studio.mascot_windows[project.id]
            observed["pet_visible"] = pet.isVisible() and pet.parent() is None
            studio.tray_icon.contextMenu().actions()[0].trigger()
            observed["editor_reopened"] = studio.isVisible()
            studio.close()
            observed["pet_survived_close"] = pet.isVisible() and not pet.isMinimized()
            next(
                action
                for action in studio.tray_icon.contextMenu().actions()
                if action.text() == "Sair do aplicativo"
            ).trigger()
        finally:
            qapp.quit()

    def safety_exit():
        observed["watchdog"] = True
        qapp.quit()

    timer.timeout.connect(finish)
    watchdog.timeout.connect(safety_exit)
    timer.start(60)
    watchdog.start(2500)
    try:
        assert desktop.run_desktop(library, [project.id], editor=False) == 0
    finally:
        timer.stop()
        watchdog.stop()
    assert observed == {
        "editor_hidden": True,
        "pet_visible": True,
        "editor_reopened": True,
        "pet_survived_close": True,
    }
    assert (library.root / "desktop.json").is_file()


def test_run_desktop_rejects_second_runtime_for_same_library(qapp, qtbot, library, capsys):
    from mascot_studio.desktop import run_desktop, StudioWindow
    from PySide6.QtCore import QLockFile

    lock = QLockFile(str(library.root / ".desktop.lock"))
    lock.setStaleLockTime(0)
    assert lock.tryLock(0)
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(qapp.quit)
    watchdog.start(200)
    try:
        result = run_desktop(library)
    finally:
        watchdog.stop()
        lock.unlock()
    assert result == 2, "Segunda instância da mesma biblioteca precisa falhar sem duplicar mascotes"
    assert "já está aberto" in capsys.readouterr().err
    assert not any(isinstance(widget, StudioWindow) for widget in qapp.topLevelWidgets())


def test_public_windows_bootstrap_qapplication_in_fresh_process(tmp_path, image_source):
    import os
    import subprocess
    import sys

    code = """
from pathlib import Path
import sys
from mascot_studio.core import Library
from mascot_studio.desktop import MascotWindow, StudioWindow, ensure_app
library = Library(Path(sys.argv[1]))
project = library.create('Companheiro', Path(sys.argv[2]))
pet = MascotWindow(library, project.id)
studio = StudioWindow(library)
assert ensure_app().quitOnLastWindowClosed() is False
assert pet.parent() is None
studio.shutdown(quit_app=False)
pet.close()
print('BOOTSTRAP_OK')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "fresh"), str(image_source)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "BOOTSTRAP_OK" in result.stdout


def test_failed_asset_reload_keeps_last_in_memory_frames_and_timer_safe(qtbot, window_library):
    from mascot_studio.desktop import MascotWindow

    pet = MascotWindow(window_library, window_library.test_project_id)
    qtbot.addWidget(pet)
    pet.show()
    previous_frames = pet.frame_cache["idle"]
    window_library.asset_path(window_library.test_project_id).unlink()
    with pytest.raises((ValueError, OSError)):
        pet.reload_project()
    assert pet.frame_cache.get("idle") is previous_frames, (
        "Erro de IO não pode destruir a animação válida em memória"
    )
    qtbot.wait(200)
    assert pet.timer.isActive()


@pytest.mark.parametrize(
    "kind", ["corrupt-json", "boolean-schema", "invalid-scale", "invalid-coordinate", "invalid-editor"]
)
def test_corrupt_desktop_configuration_is_ignored_without_modal(qtbot, library, image_source, kind):
    from mascot_studio.desktop import StudioWindow

    project = library.create("Configuração", image_source)
    record = {"x": 10, "y": 20, "scale": 1.0, "visible": True, "state": "idle", "automatic": False}
    data = {"schema_version": 1, "mascots": {project.id: record}}
    if kind == "boolean-schema":
        data["schema_version"] = True
    elif kind == "invalid-scale":
        record["scale"] = float("nan")
    elif kind == "invalid-coordinate":
        record["x"] = "not-a-number"
    elif kind == "invalid-editor":
        data["editor"] = {"x": 0, "y": 0, "width": True, "height": 600}
    path = library.root / "desktop.json"
    path.write_text("{" if kind == "corrupt-json" else json.dumps(data))
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    assert "Configuração desktop ignorada" in studio.statusBar().currentMessage()
    studio.restore_desktop()
    assert studio.mascot_windows == {}
    assert studio.findChildren(QMessageBox) == []
    assert studio.project_list.count() == 1


def test_clamp_preserves_negative_monitor_and_recovers_disconnected_monitor():
    from mascot_studio.desktop import _clamp_rect
    from PySide6.QtCore import QRect

    areas = [QRect(-1920, 0, 1920, 1080), QRect(0, 0, 1920, 1040)]
    left_monitor = QRect(-1800, 200, 192, 208)
    assert _clamp_rect(left_monitor, areas) == left_monitor
    recovered = _clamp_rect(QRect(99999, -99999, 192, 208), areas)
    assert any(area.contains(recovered) for area in areas)
    huge = _clamp_rect(QRect(100, 100, 3000, 2000), areas)
    assert any(area.contains(huge) for area in areas)


def test_event_timer_really_polls_and_resize_does_not_disable_automatic_mode(qtbot, library, image_source):
    from mascot_studio.desktop import StudioWindow

    project = library.create("Timer real", image_source, agent_id="worker-a")
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    pet = studio.show_mascot(project.id)
    qtbot.addWidget(pet)
    studio.mode_combo.setCurrentIndex(studio.mode_combo.findData("automatic"))
    (library.root / "agent-states.json").write_text(
        json.dumps({"schema_version": 1, "agents": {"worker-a": "jumping"}})
    )
    assert studio.event_timer.timerType() == Qt.TimerType.PreciseTimer, (
        "Evite polling antecipado do CoarseTimer"
    )
    qtbot.waitUntil(lambda: pet.current_state == "jumping", timeout=1800)
    assert studio.mode_combo.currentData() == "automatic"
    pet.set_scale(1.5)
    assert studio.mode_combo.currentData() == "automatic"


def test_show_actions_handle_missing_assets_and_continue_showing_other_projects(qtbot, library, image_source):
    from mascot_studio.desktop import StudioWindow

    broken = library.create("Imagem ausente", image_source)
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    library.asset_path(broken.id).unlink()
    studio._show_selected()
    assert "Erro:" in studio.statusBar().currentMessage()
    assert studio.mascot_windows == {}
    valid = library.create("Imagem válida", image_source)
    studio.reload_projects()
    qtbot.mouseClick(studio.show_all_button, Qt.MouseButton.LeftButton)
    assert set(studio.mascot_windows) == {valid.id}
    qtbot.addWidget(studio.mascot_windows[valid.id])
    assert studio.mascot_windows[valid.id].isVisible()


def test_without_system_tray_editor_remains_recoverable_when_last_pet_is_hidden(qtbot, library, image_source):
    from mascot_studio.desktop import StudioWindow

    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    studio.create_tray()
    studio.tray_available = False
    studio.show()
    studio.close()
    assert studio.isVisible(), "Sem bandeja nem pets, ocultar editor deixaria runtime inacessível"
    assert "Sair" in studio.statusBar().currentMessage()
    project = library.create("Último mascote", image_source)
    studio.reload_projects()
    pet = studio.show_mascot(project.id)
    qtbot.addWidget(pet)
    studio.close()
    assert not studio.isVisible()
    pet.hide()
    assert studio.isVisible(), "Ocultar último mascote sem bandeja deve reabrir o editor"


def test_context_menu_reports_io_error_without_breaking_cached_animation(qtbot, window_library):
    from mascot_studio.desktop import StudioWindow

    studio = StudioWindow(window_library)
    qtbot.addWidget(studio)
    pet = studio.show_mascot(window_library.test_project_id)
    qtbot.addWidget(pet)
    window_library.asset_path(window_library.test_project_id).unlink()
    menu = pet.build_context_menu()
    state_menu = next(action for action in menu.actions() if action.text() == "Estado").menu()
    next(action for action in state_menu.actions() if action.text() == "Revisando").trigger()
    assert pet.current_state == "idle"
    assert "Erro:" in studio.statusBar().currentMessage()
    qtbot.wait(180)
    assert pet.timer.isActive()
    menu.deleteLater()


def test_editor_preserves_long_author_and_license_metadata(qtbot, library, image_source):
    from mascot_studio.desktop import StudioWindow

    project = library.create("Metadados completos", image_source)
    project.author = "Autoría " * 600
    project.asset_license = "Termo de licença. " * 1500
    library.save(project)
    studio = StudioWindow(library)
    qtbot.addWidget(studio)
    assert studio.author_edit.text() == project.author, "Não truncar metadados aceitos pelo core"
    assert studio.license_edit.text() == project.asset_license
    assert studio.save_selected()
    saved = library.load(project.id)
    assert saved.author == project.author
    assert saved.asset_license == project.asset_license


def test_ensure_app_reuses_qapplication_and_keeps_runtime_alive(qapp):
    assert importlib.util.find_spec("mascot_studio.desktop") is not None, "Interface desktop ausente"
    desktop = importlib.import_module("mascot_studio.desktop")
    assert desktop.ensure_app() is qapp
    assert desktop.ensure_app() is qapp
    assert not qapp.quitOnLastWindowClosed()
