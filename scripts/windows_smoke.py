"""Verificação nativa Windows: dez pets sobre janela normal e editor minimizado.

Executa apenas sobre janelas próprias. Não manipula aplicativos do usuário.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
from importlib.resources import as_file, files
import json
from pathlib import Path
import platform
import sys
import tempfile
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, default=Path.home() / ".cache" / "mascot-studio-tests")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Esta verificação exige desktop Windows real, sem offscreen.")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMainWindow, QLabel
    from mascot_studio.core import Library
    from mascot_studio.desktop import StudioWindow, ensure_app

    args.workdir.mkdir(parents=True, exist_ok=True)
    app = ensure_app()
    user32 = ctypes.windll.user32
    get_style = user32.GetWindowLongPtrW if hasattr(user32, "GetWindowLongPtrW") else user32.GetWindowLongW
    get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetWindow.restype = wintypes.HWND
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.EnumWindows.argtypes = [
        ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
        wintypes.LPARAM,
    ]
    started = time.perf_counter()
    facts = {
        "platform": platform.platform(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tests": [],
        "mascots": [],
    }
    editor = probe = None
    try:
        with tempfile.TemporaryDirectory(dir=args.workdir) as temporary:
            library = Library(Path(temporary))
            projects = []
            with as_file(files("mascot_studio").joinpath("assets/orbi.png")) as source:
                for i in range(10):
                    projects.append(
                        library.create(f"Teste agente {i + 1}", source, agent_id=f"agente-{i + 1}")
                    )
            assert len({project.id for project in projects}) == 10
            facts["tests"].append("dez projetos independentes criados com arte real de exemplo")
            editor = StudioWindow(library)
            editor.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            editor.show()
            area = app.primaryScreen().availableGeometry()
            windows = []
            for index, project in enumerate(projects):
                window = editor.show_mascot(project.id)
                window.set_scale(0.55)
                window.move(area.left() + 40 + (index % 5) * 120, area.top() + 80 + (index // 5) * 140)
                window.set_state("review")
                windows.append(window)
            QTest.qWait(400)
            probe = QMainWindow()
            probe.setWindowTitle("Mascot Studio — janela própria de diagnóstico")
            probe.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            probe.setCentralWidget(
                QLabel("Diagnóstico de sobreposição: mascotes devem continuar sobre esta janela normal.")
            )
            probe.setGeometry(
                area.left() + 20, area.top() + 50, min(800, area.width() - 40), min(420, area.height() - 90)
            )
            probe.show()
            probe_handle = int(probe.winId())
            user32.SetWindowPos(probe_handle, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
            editor.showMinimized()
            QTest.qWait(500)
            editor_handle = int(editor.winId())
            assert user32.IsIconic(editor_handle), "O editor não foi minimizado nativamente."
            order = []
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            @callback_type
            def collect(handle, _):
                order.append(int(handle))
                return True

            assert user32.EnumWindows(collect, 0), "Não foi possível enumerar janelas."
            for window in windows:
                handle = int(window.winId())
                style = int(get_style(handle, -20))
                native_visible = bool(user32.IsWindowVisible(handle))
                native_minimized = bool(user32.IsIconic(handle))
                owner = user32.GetWindow(handle, 4)
                topmost = bool(style & 0x8)
                above_probe = (
                    handle in order
                    and probe_handle in order
                    and order.index(handle) < order.index(probe_handle)
                )
                assert window.parent() is None
                assert native_visible and not native_minimized
                assert topmost and above_probe, (handle, style, above_probe)
                assert owner != editor_handle
                assert window.current_state == "review"
                facts["mascots"].append(
                    {
                        "project_id": window.project_id,
                        "visible": native_visible,
                        "minimized": native_minimized,
                        "topmost_win32": topmost,
                        "above_normal_probe": above_probe,
                        "independent_of_editor": owner != editor_handle,
                        "qt_translucent": bool(
                            window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                        ),
                    }
                )
            facts["tests"].extend(
                [
                    "editor minimizado pelo Windows",
                    "dez janelas Win32 visíveis e não minimizadas",
                    "dez janelas com WS_EX_TOPMOST e acima de janela normal",
                    "janelas sem vínculo de minimização com editor",
                ]
            )
            image_hashes = set()
            for _ in range(6):
                QTest.qWait(185)
                image = windows[0].grab().toImage()
                image_hashes.add(hashlib.sha256(bytes(image.constBits())).hexdigest())
            assert len(image_hashes) > 1, "Mascote não apresentou quadros diferentes no desktop real."
            facts["tests"].append("quadros animados diferentes capturados no Windows real")
            facts["animation_unique_captures"] = len(image_hashes)
            facts["monitor_count"] = len(app.screens())
            facts["second_monitor_verified"] = False
            if len(app.screens()) > 1:
                second = app.screens()[1]
                box = second.availableGeometry()
                windows[-1].move(box.left() + 35, box.top() + 45)
                QTest.qWait(350)
                handle = int(windows[-1].winId())
                assert windows[-1].screen() == second, "O mascote não foi movido ao segundo monitor."
                assert user32.IsWindowVisible(handle) and not user32.IsIconic(handle)
                assert int(get_style(handle, -20)) & 0x8
                facts["second_monitor_verified"] = True
                facts["tests"].append("mascote visível e topmost no segundo monitor com editor minimizado")
            facts["passed"] = True
    except Exception as exc:
        facts["passed"] = False
        facts["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if editor is not None:
            for window in list(editor.mascot_windows.values()):
                window.close()
            editor.hide()
        if probe is not None:
            probe.close()
        app.quit()
        facts["duration_seconds"] = round(time.perf_counter() - started, 3)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(facts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
