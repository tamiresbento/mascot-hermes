"""Comandos locais do Mascot Studio; nenhum serviço ou conta é necessário."""

from __future__ import annotations

import argparse
from importlib.resources import as_file, files
import json
import os
from pathlib import Path
import sys
import zipfile


def default_library() -> Path:
    override = os.environ.get("MASCOT_STUDIO_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "DevPyTech" / "MascotStudio" / "library"
    return (
        Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        / "devpytech-mascot-studio"
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="mascot-studio", description="Crie, edite e exiba seus próprios mascotes de desktop."
    )
    result.add_argument("--library", type=Path, default=None, help="Diretório da biblioteca local")
    result.add_argument("--version", action="version", version="Mascot Studio 0.1.0")
    commands = result.add_subparsers(dest="command")
    gui = commands.add_parser("gui", help="Abrir editor e companheiros de tela")
    gui.add_argument("--show", nargs="*", default=[], metavar="ID", help="IDs ou 'all' para exibir todos")
    gui.add_argument("--no-editor", action="store_true", help="Apenas mascotes e bandeja, sem abrir o editor")
    create = commands.add_parser("create", help="Criar projeto a partir de imagem ou atlas")
    create.add_argument("name")
    create.add_argument("--image", type=Path, required=True)
    create.add_argument("--agent", default="")
    create.add_argument("--kind", choices=["auto", "image", "atlas"], default="auto")
    create.add_argument("--keep-background", action="store_true")
    sample = commands.add_parser("sample", help="Criar exemplo original Orbi")
    sample.add_argument("--name", default="Orbi")
    sample.add_argument("--agent", default="")
    listing = commands.add_parser("list", help="Listar projetos")
    listing.add_argument("--json", action="store_true", dest="as_json")
    duplicate = commands.add_parser("duplicate", help="Duplicar sem sobrescrever o original")
    duplicate.add_argument("id")
    duplicate.add_argument("--name", default=None)
    exporter = commands.add_parser("export", help="Exportar ZIP editável ou Hermes")
    exporter.add_argument("id")
    exporter.add_argument("output", type=Path)
    exporter.add_argument("--format", choices=["project", "hermes"], default="project")
    importer = commands.add_parser("import", help="Importar ZIP editável")
    importer.add_argument("archive", type=Path)
    status = commands.add_parser("status", help="Registrar estado explícito de um agente local")
    status.add_argument("agent")
    status.add_argument("state")
    validate = commands.add_parser("validate", help="Validar metadados e quadros de um projeto")
    validate.add_argument("id")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = (args.library if args.library is not None else default_library()).expanduser()
    try:
        if args.command == "status":
            from .events import update_agent_state

            states = update_agent_state(root, args.agent, args.state)
            print(json.dumps({"agent": args.agent, "state": states[args.agent]}, ensure_ascii=False))
            return 0
        from .core import STATE_ROWS, Library

        library = Library(root)
        if args.command in (None, "gui"):
            from .desktop import run_desktop

            show = getattr(args, "show", [])
            ids = [project.id for project in library.list_projects()] if "all" in show else show
            return run_desktop(library, ids, editor=not getattr(args, "no_editor", False))
        if args.command == "create":
            project = library.create(
                args.name,
                args.image,
                agent_id=args.agent,
                source_kind=args.kind,
                remove_magenta=not args.keep_background,
            )
            print(json.dumps(project.to_dict(), ensure_ascii=False, indent=2))
        elif args.command == "sample":
            with as_file(files("mascot_studio").joinpath("assets/orbi.png")) as source:
                project = library.create(
                    args.name, source, agent_id=args.agent, source_kind="image", remove_magenta=True
                )
            project.author = "DevPyTech — exemplo gerado por IA"
            project.asset_license = "CC0-1.0, na medida dos direitos detidos; consulte assets/ART_LICENSE.md"
            library.save(project)
            print(json.dumps(project.to_dict(), ensure_ascii=False, indent=2))
        elif args.command == "list":
            projects = library.list_projects()
            if args.as_json:
                print(json.dumps([project.to_dict() for project in projects], ensure_ascii=False, indent=2))
            elif not projects:
                print("Nenhum mascote. Use 'sample' ou importe sua imagem no editor.")
            else:
                for project in projects:
                    print(f"{project.id}\t{project.name}\t{project.agent_id or 'sem agente'}")
        elif args.command == "duplicate":
            print(json.dumps(library.duplicate(args.id, args.name).to_dict(), ensure_ascii=False, indent=2))
        elif args.command == "export":
            method = library.export_hermes if args.format == "hermes" else library.export_project
            print(method(args.id, args.output))
        elif args.command == "import":
            print(json.dumps(library.import_zip(args.archive).to_dict(), ensure_ascii=False, indent=2))
        elif args.command == "validate":
            project = library.load(args.id)
            for state in STATE_ROWS:
                for index in range(6):
                    frame = library.render_frame(project.id, state, index)
                    if (
                        frame.mode != "RGBA"
                        or frame.size != (192, 208)
                        or frame.getchannel("A").getbbox() is None
                    ):
                        raise ValueError(f"Quadro inválido: {state}/{index}")
            print(
                json.dumps(
                    {"id": project.id, "states": len(STATE_ROWS), "frames_per_state": 6, "valid": True}
                )
            )
        return 0
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
