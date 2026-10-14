"""Offline, non-executable mascot assets and validated project storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import io
import json
import math
import os
import re
from pathlib import Path
import shutil
import stat
import tempfile
import uuid
import warnings
import zipfile
import zlib
from numbers import Real

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

STATE_ROWS = (
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
)
STATE_LABELS = {
    "idle": "Parado",
    "running-right": "Correndo à direita",
    "running-left": "Correndo à esquerda",
    "waving": "Acenando",
    "jumping": "Pulando",
    "failed": "Falha",
    "waiting": "Aguardando",
    "running": "Trabalhando",
    "review": "Revisando",
}


@dataclass
class AnimationSettings:
    fps: float = 6.0
    bob: float = 2.0
    sway: float = 1.0
    rotation: float = 1.0
    zoom: float = 1.0

    def __post_init__(self) -> None:
        for key, low, high in (
            ("fps", 1, 30),
            ("bob", 0, 24),
            ("sway", 0, 20),
            ("rotation", 0, 20),
            ("zoom", 0.25, 2),
        ):
            value = getattr(self, key)
            try:
                valid = not isinstance(value, bool) and isinstance(value, Real) and math.isfinite(value)
                valid = valid and low <= value <= high
            except (OverflowError, TypeError):
                valid = False
            if not valid:
                raise ValueError(f"{key}: número finito entre {low} e {high} necessário")


_WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)
}


def _safe_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value)
        or len(value) > 200
        or value.endswith(".")
        or value.split(".")[0].upper() in _WINDOWS_DEVICES
    ):
        raise ValueError("Identificador de projeto inseguro")
    return value


@dataclass
class MascotProject:
    id: str
    name: str
    agent_id: str = ""
    author: str = ""
    asset_license: str = ""
    source_kind: str = "image"
    animations: dict[str, AnimationSettings] = field(
        default_factory=lambda: {state: AnimationSettings() for state in STATE_ROWS}
    )
    schema_version: int = 1

    def __post_init__(self) -> None:
        _safe_id(self.id)
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 100:
            raise ValueError("Nome obrigatório, até 100 caracteres")
        if not isinstance(self.agent_id, str) or len(self.agent_id) > 100:
            raise ValueError("Identificador de agente: até 100 caracteres")
        if not isinstance(self.author, str) or not isinstance(self.asset_license, str):
            raise ValueError("Autor e licença devem ser texto")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Versão de schema não suportada")
        if self.source_kind not in ("image", "atlas"):
            raise ValueError("Tipo de fonte inválido")
        if not isinstance(self.animations, dict) or set(self.animations) != set(STATE_ROWS):
            raise ValueError("Animações devem conter todos os estados conhecidos")
        for settings in self.animations.values():
            if not isinstance(settings, AnimationSettings):
                raise ValueError("Parâmetros de animação inválidos")
            settings.__post_init__()

    def to_dict(self) -> dict:
        self.__post_init__()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MascotProject:
        if not isinstance(data, dict):
            raise ValueError("Metadados devem ser objeto JSON")
        fields = {
            "id",
            "name",
            "agent_id",
            "author",
            "asset_license",
            "source_kind",
            "animations",
            "schema_version",
        }
        if set(data) - fields or not {"id", "name"} <= set(data):
            raise ValueError("Campos do projeto inválidos")
        values = dict(data)
        if "animations" in values:
            if not isinstance(values["animations"], dict):
                raise ValueError("Animações inválidas")
            try:
                values["animations"] = {
                    key: AnimationSettings(**settings) for key, settings in values["animations"].items()
                }
            except (TypeError, AttributeError) as exc:
                raise ValueError("Parâmetros de animação inválidos") from exc
        try:
            return cls(**values)
        except TypeError as exc:
            raise ValueError("Metadados inválidos") from exc


_MAX_INPUT = 20 * 1024 * 1024
_MAX_PIXELS = 16_000_000
_MAX_JSON = 256 * 1024
_ATLAS_SIZES = {(1536, 1872), (1728, 1664)}


def _read_bytes(path: Path, limit: int) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Arquivo ausente, não regular ou link simbólico")
    if path.stat().st_size > limit:
        raise ValueError("Arquivo excede o limite permitido")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Arquivo excede o limite permitido")
    return data


def _decode_image(data: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ("PNG", "WEBP") or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Use PNG ou WebP de um único quadro")
                if image.width * image.height > _MAX_PIXELS:
                    raise ValueError("Imagem excede 16 megapixels")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                rgba = image.convert("RGBA")
                rgba.info.clear()
                return rgba
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Imagem inválida ou maior que 16 megapixels") from exc


def _remove_magenta(image: Image.Image) -> Image.Image:
    # Narrow chroma tolerance removes bright matte pixels without erasing dark outlines.
    differences = ImageChops.difference(image.convert("RGB"), Image.new("RGB", image.size, (255, 0, 255)))
    r, g, b = differences.split()
    matte = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 0 if v <= 16 else 255)
    image.putalpha(ImageChops.multiply(image.getchannel("A"), matte))
    return image


def _json_bytes(project: MascotProject) -> bytes:
    data = json.dumps(project.to_dict(), ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    if len(data) > _MAX_JSON:
        raise ValueError("Metadados excedem 256 KiB")
    return data


def _json_project(data: bytes) -> MascotProject:
    try:
        return MascotProject.from_dict(json.loads(data, object_pairs_hook=_unique_object))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Metadados JSON inválidos") from exc


def _atomic_bytes(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Library:
    """Project library owned by the current user; no execution or ZIP extraction.

    Corrupt metadata is skipped by listing, but explicit loads fail. Exports go
    outside the library to protect both projects and desktop configuration.
    """

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()

    def _directory(self, project_id: str) -> Path:
        directory = self.root / _safe_id(project_id)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Projeto ausente ou caminho inseguro")
        return directory

    def _install(self, project: MascotProject, image: Image.Image) -> MascotProject:
        _json_bytes(project)  # Validate before creating any directory.
        while True:
            project.id = uuid.uuid4().hex
            directory = self.root / project.id
            try:
                directory.mkdir()
                break
            except FileExistsError:
                continue
        try:
            metadata = _json_bytes(project)
            image.save(directory / "source.png", format="PNG")
            _atomic_bytes(directory / "project.json", metadata)
        except BaseException:
            shutil.rmtree(directory)
            raise
        return project

    def create(
        self,
        name: str,
        source: Path,
        agent_id: str = "",
        source_kind: str = "auto",
        remove_magenta: bool = True,
    ) -> MascotProject:
        if source_kind not in ("auto", "image", "atlas"):
            raise ValueError("Tipo de fonte inválido")
        image = _decode_image(_read_bytes(source, _MAX_INPUT))
        kind = "atlas" if source_kind == "auto" and image.size in _ATLAS_SIZES else source_kind
        if kind == "auto":
            kind = "image"
        if kind == "atlas" and image.size not in _ATLAS_SIZES:
            raise ValueError("Atlas deve ser 1536x1872 ou 1728x1664")
        project = MascotProject("new", name, agent_id=agent_id, source_kind=kind)
        if kind == "image" and remove_magenta:
            image = _remove_magenta(image)
        return self._install(project, image)

    def list_projects(self) -> list[MascotProject]:
        projects = []
        for directory in sorted(self.root.iterdir()):
            if directory.is_dir() and not directory.is_symlink() and not directory.name.startswith("."):
                try:
                    projects.append(self.load(directory.name))
                except ValueError:
                    continue
        return projects

    def load(self, project_id: str) -> MascotProject:
        project = _json_project(_read_bytes(self._directory(project_id) / "project.json", _MAX_JSON))
        if project.id != project_id:
            raise ValueError("Identificador não corresponde à pasta do projeto")
        return project

    def asset_path(self, project_id: str) -> Path:
        path = self._directory(project_id) / "source.png"
        if path.is_symlink() or not path.is_file():
            raise ValueError("Imagem do projeto ausente ou insegura")
        return path

    def save(self, project: MascotProject) -> None:
        if not isinstance(project, MascotProject):
            raise ValueError("Projeto inválido")
        data = _json_bytes(project)
        path = self._directory(project.id) / "project.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("Metadados ausentes ou inseguros")
        _atomic_bytes(path, data)

    def duplicate(self, project_id: str, name: str | None = None) -> MascotProject:
        original = self.load(project_id)
        project = MascotProject.from_dict(original.to_dict())
        project.name = name if name is not None else original.name[:92] + " (cópia)"
        image = _decode_image(_read_bytes(self.asset_path(project_id), 64 * 1024 * 1024))
        return self._install(project, image)

    def delete(self, project_id: str) -> None:
        self.load(project_id)
        shutil.rmtree(self._directory(project_id))

    def _export_target(self, destination: Path) -> Path:
        destination = Path(destination)
        if destination.is_symlink() or destination.resolve().is_relative_to(self.root):
            raise ValueError("Exporte fora da biblioteca, sem links simbólicos")
        return destination

    def render_frame(self, project_id: str, state: str, index: int = 0) -> Image.Image:
        project = self.load(project_id)
        image = _decode_image(_read_bytes(self.asset_path(project_id), 64 * 1024 * 1024))
        return _render(project, image, state, index)

    def export_project(self, project_id: str, destination: Path) -> Path:
        destination = self._export_target(destination)
        project = self.load(project_id)
        pixels = _read_bytes(self.asset_path(project_id), 64 * 1024 * 1024)
        _decode_image(pixels)
        package = _zip_bytes({"project.json": _json_bytes(project), "source.png": pixels})
        if len(package) > _MAX_INPUT:
            raise ValueError("Projeto exportado excederia 20 MiB; reduza a imagem de origem")
        _atomic_bytes(destination, package)
        return destination

    def import_zip(self, archive: Path) -> MascotProject:
        data = _read_bytes(archive, _MAX_INPUT)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zipped:
                entries = zipped.infolist()
                if len(entries) > 16 or sum(info.file_size for info in entries) > 64 * 1024 * 1024:
                    raise ValueError("ZIP excede 16 arquivos ou 64 MiB descompactados")
                names = set()
                for info in entries:
                    mode = stat.S_IFMT(info.external_attr >> 16)
                    if (
                        info.filename not in {"project.json", "source.png"}
                        or info.orig_filename != info.filename
                        or info.filename.casefold() in names
                        or mode not in (0, stat.S_IFREG)
                        or info.is_dir()
                        or info.flag_bits & 1
                        or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    ):
                        raise ValueError("Entrada ZIP insegura, duplicada ou inesperada")
                    names.add(info.filename.casefold())
                if names != {"project.json", "source.png"}:
                    raise ValueError("ZIP deve conter project.json e source.png na raiz")
                project = _json_project(_zip_read(zipped, "project.json", _MAX_JSON))
                image = _decode_image(_zip_read(zipped, "source.png", 64 * 1024 * 1024))
                if project.source_kind == "atlas" and image.size not in _ATLAS_SIZES:
                    raise ValueError("Dimensões de atlas inválidas")
        except (zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
            raise ValueError("Pacote de projeto inválido") from exc
        return self._install(project, image)

    def export_hermes(self, project_id: str, destination: Path) -> Path:
        destination = self._export_target(destination)
        project = self.load(project_id)
        image = _decode_image(_read_bytes(self.asset_path(project_id), 64 * 1024 * 1024))
        atlas = Image.new("RGBA", (1536, 1872))
        for row, state in enumerate(STATE_ROWS):
            frames = [_render(project, image, state, index) for index in range(6)]
            for column in range(8):
                atlas.paste(frames[column % 6], (column * 192, row * 208))
        buffer = io.BytesIO()
        atlas.save(buffer, format="PNG")
        manifest = {
            "id": project.id,
            "displayName": project.name,
            "description": f"Mascote criado no Mascot Studio: {project.name}",
            "spritesheetPath": "spritesheet.png",
        }
        files = {
            f"{project.id}/pet.json": json.dumps(manifest, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            ),
            f"{project.id}/spritesheet.png": buffer.getvalue(),
        }
        _atomic_bytes(destination, _zip_bytes(files))
        return destination


# Eight-row legacy atlases have no generic running row; reuse running-right.
_LEGACY_ROWS = {state: row for row, state in enumerate(STATE_ROWS[:7] + ("review",))}
_LEGACY_ROWS["running"] = 1
_IMAGE_PROFILES = {
    "idle": (0.5, 1, 0.3, 0, 1),
    "running-right": (2, 0.7, -2, -3, 1),
    "running-left": (-2, 0.7, 2, 3, 1),
    "waving": (0.5, 0.5, 4, -3, 1.03),
    "jumping": (0, 5, 0, 0, 1),
    "failed": (0, 0.5, 1, 18, 0.88),
    "waiting": (0.3, 0.5, 0.4, -6, 0.96),
    "running": (1.4, 1.8, 2, 0, 1.02),
    "review": (0.3, 0.4, 0.8, 6, 1),
}


def _render(project: MascotProject, image: Image.Image, state: str, index: int) -> Image.Image:
    if state not in STATE_ROWS or type(index) is not int:
        raise ValueError("Estado ou índice de quadro inválido")
    settings = project.animations[state]
    wave = math.sin(2 * math.pi * (index % 6) / 6)
    dx, dy = settings.sway * wave, -settings.bob * abs(wave)
    angle = settings.rotation * wave
    zoom = settings.zoom
    if project.source_kind == "atlas":
        if image.size not in _ATLAS_SIZES:
            raise ValueError("Dimensões de atlas inválidas")
        row = STATE_ROWS.index(state) if image.height == 1872 else _LEGACY_ROWS[state]
        column = index % 6
        sprite = image.crop((column * 192, row * 208, (column + 1) * 192, (row + 1) * 208))
    else:
        bbox = image.getbbox()
        sprite = ImageOps.contain(
            image.crop(bbox) if bbox else Image.new("RGBA", (1, 1)), (160, 176), Image.Resampling.LANCZOS
        )
        if state == "running-left":
            sprite = ImageOps.mirror(sprite)
        horizontal, vertical, rotation, tilt, scale = _IMAGE_PROFILES[state]
        dx *= horizontal
        dy *= vertical
        angle = angle * rotation + tilt
        zoom *= scale
    if zoom != 1:
        sprite = sprite.resize(
            (max(1, round(sprite.width * zoom)), max(1, round(sprite.height * zoom))),
            Image.Resampling.LANCZOS,
        )
    if angle:
        sprite = sprite.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    result = Image.new("RGBA", (192, 208))
    result.alpha_composite(
        sprite, (round((192 - sprite.width) / 2 + dx), round((208 - sprite.height) / 2 + dy))
    )
    return result


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _zip_read(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    if archive.getinfo(name).file_size > limit:
        raise ValueError("Entrada ZIP excede o limite permitido")
    with archive.open(name) as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Entrada ZIP excede o limite permitido")
    return data


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Chave JSON duplicada")
        result[key] = value
    return result
