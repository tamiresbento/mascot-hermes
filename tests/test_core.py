"""Real engine contract and adversarial inputs (synthetic assets only)."""

import importlib
import io
import json
import math
import random
import stat
import struct
import sys
import zipfile

from PIL import Image, ImageDraw, PngImagePlugin

import pytest


def engine():
    assert importlib.util.find_spec("mascot_studio.core") is not None, "engine not implemented"
    return importlib.import_module("mascot_studio.core")


def make_symlink_or_skip(link, target, *, target_is_directory=False):
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as exc:
        if sys.platform == "win32" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows sem privilégio para criar symlinks; segurança lexical continua coberta")
        raise


def test_state_rows_and_defaults():
    core = engine()
    assert core.STATE_ROWS == (
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
    assert set(core.STATE_LABELS) == set(core.STATE_ROWS)
    assert all(isinstance(label, str) and label for label in core.STATE_LABELS.values())
    settings = core.AnimationSettings()
    assert (settings.fps, settings.bob, settings.sway, settings.rotation, settings.zoom) == (6, 2, 1, 1, 1)


@pytest.mark.parametrize(
    "field, value",
    [
        ("fps", 0),
        ("fps", 31),
        ("bob", -1),
        ("bob", 25),
        ("sway", -1),
        ("sway", 21),
        ("rotation", -1),
        ("rotation", 21),
        ("zoom", 0.24),
        ("zoom", 2.01),
        ("fps", math.nan),
        ("bob", math.inf),
        ("sway", -math.inf),
        ("zoom", "1"),
        ("fps", True),
    ],
)
def test_settings_reject_invalid_numbers(field, value):
    core = engine()
    with pytest.raises(ValueError):
        core.AnimationSettings(**{field: value})


@pytest.mark.parametrize(
    "values",
    [
        dict(fps=1, bob=0, sway=0, rotation=0, zoom=0.25),
        dict(fps=30, bob=24, sway=20, rotation=20, zoom=2),
    ],
)
def test_settings_accept_bounds(values):
    assert engine().AnimationSettings(**values).fps == values["fps"]


def test_project_metadata_roundtrip_and_independent_defaults():
    core = engine()
    project = core.MascotProject(
        "sample-id", "Mascote", agent_id="agent-1", author="Pessoa", asset_license="CC0"
    )
    assert set(project.animations) == set(core.STATE_ROWS)
    project.animations["idle"].bob = 13
    assert project.animations["review"].bob == 2
    assert core.MascotProject.from_dict(project.to_dict()) == project
    assert core.MascotProject("other", "Outro").animations["idle"].bob == 2
    project.animations["idle"].fps = math.inf
    with pytest.raises(ValueError):
        project.to_dict()


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "../escape"},
        {"id": "C:\\temp"},
        {"id": ".."},
        {"id": "CON"},
        {"id": "x/y"},
        {"id": "x\\y"},
        {"id": ""},
        {"name": " "},
        {"name": "n" * 101},
        {"agent_id": "a" * 101},
        {"name": 9},
        {"source_kind": "python"},
        {"schema_version": 2},
        {"schema_version": True},
        {"animations": {}},
    ],
)
def test_project_rejects_invalid_metadata(changes):
    core = engine()
    fields = dict(id="valid-id", name="Mascote")
    fields.update(changes)
    with pytest.raises(ValueError):
        core.MascotProject(**fields)


@pytest.mark.parametrize("payload", [None, [], {}, {"id": "ok", "name": "Ok", "unknown": 1}])
def test_project_from_dict_rejects_bad_schema(payload):
    with pytest.raises(ValueError):
        engine().MascotProject.from_dict(payload)


@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "mascot.png"
    image = Image.new("RGBA", (80, 120), (255, 0, 255, 255))
    for x in range(20, 60):
        for y in range(20, 100):
            image.putpixel((x, y), (0, 0, 0, 255) if x < 25 else (25, 120, 230, 180))
    image.save(path)
    return path


def test_create_and_reopen_twelve_distinct_projects(tmp_path, image_file):
    core = engine()
    library = core.Library(tmp_path / "library")
    assert library.root == tmp_path / "library"
    projects = [library.create(f"Mascote {index}", image_file, f"agent-{index}") for index in range(12)]
    assert len({project.id for project in projects}) == 12
    reopened = core.Library(library.root)
    assert {p.id for p in reopened.list_projects()} == {p.id for p in projects}
    for project in projects:
        assert reopened.load(project.id) == project
        assert reopened.asset_path(project.id) == library.root / project.id / "source.png"
        assert (library.root / project.id / "project.json").is_file()
        with Image.open(reopened.asset_path(project.id)) as source:
            assert source.mode == "RGBA"
            assert source.getpixel((0, 0))[3] == 0
            assert source.getpixel((20, 30)) == (0, 0, 0, 255)
            assert source.getpixel((30, 30))[3] == 180


def test_create_can_preserve_magenta(tmp_path, image_file):
    library = engine().Library(tmp_path / "library")
    project = library.create("Cor", image_file, source_kind="image", remove_magenta=False)
    with Image.open(library.asset_path(project.id)) as image:
        assert image.getpixel((0, 0)) == (255, 0, 255, 255)


@pytest.mark.parametrize("case", ["absent", "invalid", "large-file", "large-image", "bad-kind", "bad-name"])
def test_create_validates_before_writing(tmp_path, image_file, case):
    library = engine().Library(tmp_path / "library")
    source = tmp_path / "input.png"
    kwargs = {}
    name = "Teste"
    if case == "invalid":
        source.write_bytes(b"not an image")
    elif case == "large-file":
        with source.open("wb") as handle:
            handle.truncate(20 * 1024 * 1024 + 1)
    elif case == "large-image":
        Image.new("1", (4001, 4000)).save(source)
    elif case == "bad-kind":
        source = image_file
        kwargs["source_kind"] = "exec"
    elif case == "bad-name":
        source = image_file
        name = " "
    with pytest.raises(ValueError):
        library.create(name, source, **kwargs)
    assert list(library.root.iterdir()) == []


def test_create_accepts_sixteen_megapixel_boundary(tmp_path):
    source = tmp_path / "boundary.png"
    Image.new("1", (4000, 4000)).save(source)
    library = engine().Library(tmp_path / "library")
    assert library.create("Limite", source).id


def test_save_is_validated_atomic_and_uncached(tmp_path, image_file):
    core = engine()
    library = core.Library(tmp_path / "library")
    project = library.create("Original", image_file)
    project.name = "Editado"
    project.animations["review"].fps = 17
    library.save(project)
    second = core.Library(library.root)
    assert second.load(project.id) == project
    metadata_path = library.root / project.id / "project.json"
    saved_bytes = metadata_path.read_bytes()
    project.animations["review"].zoom = 9
    with pytest.raises(ValueError):
        library.save(project)
    assert metadata_path.read_bytes() == saved_bytes
    assert {p.name for p in metadata_path.parent.iterdir()} == {"source.png", "project.json"}
    payload = json.loads(saved_bytes)
    payload["name"] = "Alterado externamente"
    metadata_path.write_text(json.dumps(payload))
    assert library.load(project.id).name == "Alterado externamente"


def test_duplicate_never_overwrites_and_delete_is_scoped(tmp_path, image_file):
    library = engine().Library(tmp_path / "library")
    original = library.create("Original", image_file)
    original.author = "Autor"
    original.animations["running"].bob = 15
    library.save(original)
    source_bytes = library.asset_path(original.id).read_bytes()
    other = library.duplicate(original.id, "Cópia")
    auto_named = library.duplicate(original.id)
    assert len({original.id, other.id, auto_named.id}) == 3
    assert other.name == "Cópia"
    assert other.author == "Autor"
    assert other.animations == original.animations
    assert library.load(original.id) == original
    assert library.asset_path(other.id).read_bytes() == source_bytes
    assert auto_named.name != original.name
    library.delete(other.id)
    assert {p.id for p in library.list_projects()} == {original.id, auto_named.id}
    with pytest.raises(ValueError):
        library.load(other.id)


@pytest.mark.parametrize("project_id", ["../escape", "x/y", "x\\y", "C:escape", "CON", ".", "..", "missing"])
def test_library_methods_reject_unsafe_or_absent_ids(tmp_path, project_id):
    library = engine().Library(tmp_path / "library")
    for operation in (library.load, library.asset_path, library.duplicate, library.delete):
        with pytest.raises(ValueError):
            operation(project_id)


def test_library_rejects_project_and_asset_symlinks(tmp_path, image_file):
    library = engine().Library(tmp_path / "library")
    project = library.create("Original", image_file)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("preserve")
    make_symlink_or_skip(library.root / "link", outside, target_is_directory=True)
    with pytest.raises(ValueError):
        library.delete("link")
    assert marker.read_text() == "preserve"
    asset = library.asset_path(project.id)
    asset.unlink()
    make_symlink_or_skip(asset, image_file)
    with pytest.raises(ValueError):
        library.asset_path(project.id)
    metadata = library.root / project.id / "project.json"
    metadata.unlink()
    make_symlink_or_skip(metadata, marker)
    with pytest.raises(ValueError):
        library.save(project)


def test_image_frames_states_modulo_and_editable_parameters(tmp_path, image_file):
    core = engine()
    library = core.Library(tmp_path / "library")
    project = library.create("Animado", image_file)
    initial = library.render_frame(project.id, "idle", 0)
    assert initial.size == (192, 208) and initial.mode == "RGBA"
    box = initial.getbbox()
    assert box and box[0] >= 8 and box[1] >= 8 and box[2] <= 184 and box[3] <= 200
    frames = [library.render_frame(project.id, state, 1).tobytes() for state in core.STATE_ROWS]
    assert len(set(frames)) == len(core.STATE_ROWS)
    assert (
        library.render_frame(project.id, "jumping", 7).tobytes()
        == library.render_frame(project.id, "jumping", 1).tobytes()
    )
    assert (
        library.render_frame(project.id, "jumping", -1).tobytes()
        == library.render_frame(project.id, "jumping", 5).tobytes()
    )
    assert library.render_frame(project.id, "idle", 1).tobytes() != initial.tobytes()
    project.animations["idle"] = core.AnimationSettings(fps=20, bob=20, sway=15, rotation=18, zoom=1.6)
    library.save(project)
    assert library.render_frame(project.id, "idle", 1).tobytes() != frames[0]
    for state in core.STATE_ROWS:
        for index in range(6):
            assert library.render_frame(project.id, state, index).size == (192, 208)
    with pytest.raises(ValueError):
        library.render_frame(project.id, "unknown")
    with pytest.raises(ValueError):
        library.render_frame(project.id, "idle", 1.5)


def colored_atlas(path, columns, rows):
    image = Image.new("RGBA", (columns * 192, rows * 208))
    draw = ImageDraw.Draw(image)
    for row in range(rows):
        for column in range(columns):
            draw.rectangle(
                (column * 192, row * 208, (column + 1) * 192 - 1, (row + 1) * 208 - 1),
                fill=(20 * row, 20 * column, 120, 255),
            )
    image.putpixel((0, 0), (255, 0, 255, 255))
    image.save(path)


@pytest.mark.parametrize("columns, rows", [(8, 9), (9, 8)])
def test_atlas_detection_real_rows_and_no_chroma_key(tmp_path, columns, rows):
    core = engine()
    source = tmp_path / "atlas.png"
    colored_atlas(source, columns, rows)
    library = core.Library(tmp_path / "library")
    project = library.create("Atlas", source)
    assert project.source_kind == "atlas"
    assert library.render_frame(project.id, "idle").getpixel((0, 0)) == (255, 0, 255, 255)
    legacy = {state: row for row, state in enumerate(core.STATE_ROWS[:7] + ("review",))}
    legacy["running"] = 1
    for state in core.STATE_ROWS:
        row = core.STATE_ROWS.index(state) if rows == 9 else legacy[state]
        frame = library.render_frame(project.id, state, 0)
        assert frame.getpixel((80, 80)) == (20 * row, 0, 120, 255)
        project.animations[state] = core.AnimationSettings(bob=0, sway=0, rotation=0, zoom=1)
    library.save(project)
    assert library.render_frame(project.id, "review", 7).getpixel((80, 80)) == (20 * (rows - 1), 20, 120, 255)
    project.animations["review"].zoom = 0.5
    project.animations["review"].rotation = 20
    library.save(project)
    frame = library.render_frame(project.id, "review", 1)
    assert frame.mode == "RGBA" and frame.getpixel((0, 0))[3] == 0


def test_explicit_atlas_rejects_wrong_dimensions(tmp_path, image_file):
    library = engine().Library(tmp_path / "library")
    with pytest.raises(ValueError):
        library.create("Not atlas", image_file, source_kind="atlas")
    assert not library.list_projects()


def test_project_zip_roundtrip_new_id_and_preserved_settings(tmp_path, image_file):
    library = engine().Library(tmp_path / "library")
    original = library.create("Editável", image_file, "agent-7")
    original.author = "Autor independente"
    original.asset_license = "CC0"
    original.animations["waving"].fps = 21
    original.animations["review"].zoom = 0.8
    library.save(original)
    original_data = original.to_dict()
    original_asset = library.asset_path(original.id).read_bytes()
    destination = tmp_path / "project.zip"
    assert library.export_project(original.id, destination) == destination
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {"project.json", "source.png"}
        assert json.loads(archive.read("project.json")) == original_data
        assert archive.read("source.png") == original_asset
    imported = library.import_zip(destination)
    assert imported.id != original.id
    imported_data = imported.to_dict()
    imported_data["id"] = original.id
    assert imported_data == original_data
    assert library.asset_path(imported.id).read_bytes() == original_asset
    assert library.load(original.id) == original
    assert len(library.list_projects()) == 2


def test_invalid_zip_schema_or_image_leaves_no_project(tmp_path):
    library = engine().Library(tmp_path / "library")
    image = io.BytesIO()
    Image.new("RGBA", (10, 10)).save(image, format="PNG")
    good = engine().MascotProject("example", "Exemplo").to_dict()
    for metadata, pixels in [(dict(good, schema_version=2), image.getvalue()), (good, b"bad-image")]:
        archive = tmp_path / "invalid.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("project.json", json.dumps(metadata))
            zipped.writestr("source.png", pixels)
        with pytest.raises(ValueError):
            library.import_zip(archive)
        assert list(library.root.iterdir()) == []
    invalid = tmp_path / "plain.zip"
    invalid.write_bytes(b"not a ZIP")
    with pytest.raises(ValueError):
        library.import_zip(invalid)
    with pytest.raises(ValueError):
        library.import_zip(tmp_path / "missing.zip")


def editable_zip(path, extra=None, *, metadata=None, source=None):
    buffer = io.BytesIO()
    Image.new("RGBA", (10, 10), (20, 130, 230, 180)).save(buffer, format="PNG")
    if metadata is None:
        metadata = engine().MascotProject("fixture", "Fixture").to_dict()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", json.dumps(metadata))
        archive.writestr("source.png", buffer.getvalue() if source is None else source)
        for info, data in extra or []:
            archive.writestr(info, data)
    return path


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "C:/escape",
        "C:escape",
        "\\server\\share",
        "..\\escape",
        "folder/../escape",
        "folder\\file",
        "./source.png",
        "folder//file",
        "folder/./file",
        "SOURCE.PNG",
        "source.png.",
        "source.png ",
        "folder/CON",
        "folder/NUL.txt",
        "a:b",
        "project.json",
        "source.png",
        "script.py",
        "folder/readme.txt",
    ],
)
def test_zip_rejects_unsafe_ambiguous_duplicate_or_unexpected_names(tmp_path, name):
    library = engine().Library(tmp_path / "library")
    path = tmp_path / "evil.zip"
    # duplicate ZIP names are intentionally produced, not a test warning leak.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        editable_zip(path, [(name, b"unsafe")])
    with pytest.raises(ValueError):
        library.import_zip(path)
    assert list(library.root.iterdir()) == []
    assert not (tmp_path / "escape").exists()


def test_zip_rejects_unix_symlink(tmp_path):
    library = engine().Library(tmp_path / "library")
    info = zipfile.ZipInfo("readme.txt")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    editable_zip(tmp_path / "link.zip", [(info, b"/etc/passwd")])
    with pytest.raises(ValueError):
        library.import_zip(tmp_path / "link.zip")
    assert list(library.root.iterdir()) == []


@pytest.mark.parametrize("case", ["count", "expanded", "archive", "image", "metadata", "atlas-size"])
def test_zip_resource_limits_and_prevalidation(tmp_path, case):
    library = engine().Library(tmp_path / "library")
    path = tmp_path / "limited.zip"
    if case == "count":
        editable_zip(path, [(f"note-{n}.txt", b"note") for n in range(15)])
    elif case == "expanded":
        editable_zip(path, [("readme.txt", b"0" * (64 * 1024 * 1024 + 1))])
        assert path.stat().st_size < 20 * 1024 * 1024
    elif case == "archive":
        editable_zip(path)
        with path.open("ab") as handle:
            handle.truncate(20 * 1024 * 1024 + 1)
    elif case == "image":
        image = io.BytesIO()
        Image.new("1", (4001, 4000)).save(image, format="PNG")
        editable_zip(path, source=image.getvalue())
    elif case == "metadata":
        metadata = engine().MascotProject("ok", "Nome").to_dict()
        metadata["author"] = "a" * (256 * 1024 + 1)
        editable_zip(path, metadata=metadata)
    else:
        metadata = engine().MascotProject("ok", "Nome", source_kind="atlas").to_dict()
        editable_zip(path, metadata=metadata)
    with pytest.raises(ValueError):
        library.import_zip(path)
    assert list(library.root.iterdir()) == []


@pytest.mark.parametrize("source_kind", ["image", "atlas"])
def test_hermes_export_nine_rows_eight_columns_six_effective_frames(tmp_path, image_file, source_kind):
    core = engine()
    library = core.Library(tmp_path / "library")
    source = image_file
    if source_kind == "atlas":
        source = tmp_path / "atlas.png"
        colored_atlas(source, 8, 9)
    project = library.create("Hermes compatível", source, source_kind=source_kind)
    project.author = "Independent creator"
    project.animations["idle"].fps = 19
    library.save(project)
    destination = tmp_path / "hermes.zip"
    assert library.export_hermes(project.id, destination) == destination
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) == {f"{project.id}/pet.json", f"{project.id}/spritesheet.png"}
        manifest = json.loads(archive.read(f"{project.id}/pet.json"))
        assert set(manifest) == {"id", "displayName", "description", "spritesheetPath"}
        assert manifest["id"] == project.id
        assert manifest["displayName"] == project.name
        assert manifest["spritesheetPath"] == "spritesheet.png"
        assert "fps" not in manifest
        with Image.open(io.BytesIO(archive.read(f"{project.id}/spritesheet.png"))) as atlas:
            assert atlas.size == (1536, 1872) and atlas.mode == "RGBA"
            for row, state in enumerate(core.STATE_ROWS):
                for column in range(8):
                    actual = atlas.crop((column * 192, row * 208, (column + 1) * 192, (row + 1) * 208))
                    expected = library.render_frame(project.id, state, column % 6)
                    assert actual.tobytes() == expected.tobytes()
    assert library.load(project.id) == project


@pytest.mark.parametrize("method", ["export_project", "export_hermes"])
def test_exports_cannot_overwrite_project_files_or_follow_links(tmp_path, image_file, method):
    library = engine().Library(tmp_path / "library")
    project = library.create("Preservar", image_file)
    asset = library.asset_path(project.id)
    metadata = library.root / project.id / "project.json"
    external = tmp_path / "keep.txt"
    external.write_text("preserve")
    link = tmp_path / "linked.zip"
    make_symlink_or_skip(link, external)
    for destination in (asset, metadata, link):
        old = destination.read_bytes()
        with pytest.raises(ValueError):
            getattr(library, method)(project.id, destination)
        assert destination.read_bytes() == old
    assert library.load(project.id) == project


def test_delete_does_not_remove_non_project_directories(tmp_path):
    library = engine().Library(tmp_path / "library")
    other = library.root / "unrelated"
    other.mkdir()
    marker = other / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(ValueError):
        library.delete("unrelated")
    assert marker.read_text() == "keep"


@pytest.mark.parametrize("method", ["export_project", "export_hermes"])
def test_export_physical_io_failure_removes_temporary_files(tmp_path, image_file, method):
    library = engine().Library(tmp_path / "library")
    project = library.create("IO", image_file)
    destination = tmp_path / "directory.zip"
    destination.mkdir()
    (destination / "keep").write_text("keep")
    before = {item.name for item in tmp_path.iterdir()}
    with pytest.raises(OSError):
        getattr(library, method)(project.id, destination)
    assert {item.name for item in tmp_path.iterdir()} == before
    assert (destination / "keep").read_text() == "keep"


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFDIR, stat.S_IFIFO, stat.S_IFCHR])
def test_zip_rejects_special_types_on_required_asset(tmp_path, mode):
    path = tmp_path / "special.zip"
    buffer = io.BytesIO()
    Image.new("RGBA", (5, 5)).save(buffer, format="PNG")
    info = zipfile.ZipInfo("source.png")
    info.create_system = 3
    info.external_attr = (mode | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("project.json", json.dumps(engine().MascotProject("ok", "Ok").to_dict()))
        archive.writestr(info, buffer.getvalue())
    library = engine().Library(tmp_path / "library")
    with pytest.raises(ValueError):
        library.import_zip(path)
    assert not list(library.root.iterdir())


def test_zip_crc_corruption_is_rejected_without_staging(tmp_path):
    path = editable_zip(tmp_path / "corrupt.zip")
    with zipfile.ZipFile(path) as archive:
        offset = archive.getinfo("source.png").header_offset
    data = bytearray(path.read_bytes())
    filename_size, extra_size = struct.unpack_from("<HH", data, offset + 26)
    data[offset + 30 + filename_size + extra_size + 5] ^= 0xFF
    path.write_bytes(data)
    library = engine().Library(tmp_path / "library")
    with pytest.raises(ValueError):
        library.import_zip(path)
    assert list(library.root.iterdir()) == []


def test_zip_null_byte_name_is_rejected(tmp_path):
    path = tmp_path / "null.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("project.json", json.dumps(engine().MascotProject("ok", "Ok").to_dict()))
        buffer = io.BytesIO()
        Image.new("RGBA", (5, 5)).save(buffer, format="PNG")
        archive.writestr("source.pngX", buffer.getvalue())
    path.write_bytes(path.read_bytes().replace(b"source.pngX", b"source.png\x00"))
    library = engine().Library(tmp_path / "library")
    with pytest.raises(ValueError):
        library.import_zip(path)
    assert not list(library.root.iterdir())


@pytest.mark.parametrize(
    "data",
    [
        b'{"id":"ok","name":"First","name":"Second"}',
        b'{"id":"ok","name":"Ok","schema_version":2,"schema_version":1}',
    ],
)
def test_duplicate_json_keys_are_rejected(tmp_path, data):
    path = tmp_path / "json.zip"
    buffer = io.BytesIO()
    Image.new("RGBA", (5, 5)).save(buffer, format="PNG")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("project.json", data)
        archive.writestr("source.png", buffer.getvalue())
    library = engine().Library(tmp_path / "library")
    with pytest.raises(ValueError):
        library.import_zip(path)
    assert not list(library.root.iterdir())


def test_library_skips_corrupt_metadata_without_hiding_good_projects(tmp_path, image_file):
    library = engine().Library(tmp_path / "library")
    good = library.create("Good", image_file)
    bad = library.create("Bad", image_file)
    (library.root / bad.id / "project.json").write_text("corrupt")
    assert library.list_projects() == [good]
    with pytest.raises(ValueError):
        library.load(bad.id)


def test_webp_input_is_normalized_to_rgba_png(tmp_path):
    path = tmp_path / "source.webp"
    Image.new("RGBA", (80, 80), (20, 120, 250, 123)).save(path, format="WEBP", lossless=True)
    library = engine().Library(tmp_path / "library")
    project = library.create("WebP", path)
    with Image.open(library.asset_path(project.id)) as image:
        assert image.format == "PNG" and image.mode == "RGBA"
        assert image.getpixel((20, 20)) == (20, 120, 250, 123)


def test_zip_accepts_windows_regular_file_attributes(tmp_path):
    path = tmp_path / "windows.zip"
    buffer = io.BytesIO()
    Image.new("RGBA", (5, 5)).save(buffer, format="PNG")
    metadata = json.dumps(engine().MascotProject("fixture", "Fixture").to_dict()).encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in (("project.json", metadata), ("source.png", buffer.getvalue())):
            info = zipfile.ZipInfo(name)
            info.create_system = 0
            info.external_attr = 0x20
            archive.writestr(info, payload)
    library = engine().Library(tmp_path / "library")
    assert library.import_zip(path).name == "Fixture"


def test_normalization_strips_source_embedded_metadata(tmp_path):
    path = tmp_path / "metadata.png"
    image = Image.new("RGBA", (12, 12), (20, 120, 240, 200))
    exif = Image.Exif()
    exif[270] = "private synthetic description"
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "private synthetic comment")
    image.save(path, pnginfo=metadata, exif=exif, icc_profile=b"synthetic-icc")
    library = engine().Library(tmp_path / "library")
    project = library.create("Pixels only", path)
    with Image.open(library.asset_path(project.id)) as stored:
        assert "exif" not in stored.info
        assert "icc_profile" not in stored.info
        assert "Comment" not in stored.info
        assert stored.getpixel((1, 1)) == (20, 120, 240, 200)


@pytest.mark.parametrize("format", ["GIF", "JPEG", "BMP"])
def test_create_denies_non_contract_image_formats(tmp_path, format):
    path = tmp_path / "disguised.png"
    Image.new("RGB", (12, 12)).save(path, format=format)
    library = engine().Library(tmp_path / "library")
    with pytest.raises(ValueError):
        library.create("Denied", path)
    assert not list(library.root.iterdir())


def test_create_denies_animated_webp(tmp_path):
    path = tmp_path / "animated.webp"
    Image.new("RGBA", (12, 12), "red").save(
        path,
        save_all=True,
        append_images=[Image.new("RGBA", (12, 12), "blue")],
        duration=100,
        loop=0,
    )
    library = engine().Library(tmp_path / "library")
    with pytest.raises(ValueError):
        library.create("Animated", path)
    assert not list(library.root.iterdir())


def test_truncated_image_is_rejected_before_writing(tmp_path, image_file):
    path = tmp_path / "truncated.png"
    path.write_bytes(image_file.read_bytes()[:40])
    library = engine().Library(tmp_path / "library")
    with pytest.raises(ValueError):
        library.create("Truncated", path)
    assert not list(library.root.iterdir())


def test_create_accepts_exact_twenty_mebibyte_boundary(tmp_path, image_file):
    path = tmp_path / "twenty.png"
    path.write_bytes(image_file.read_bytes())
    with path.open("ab") as handle:
        handle.truncate(20 * 1024 * 1024)
    library = engine().Library(tmp_path / "library")
    assert library.create("Twenty", path).id


@pytest.mark.parametrize("over", [False, True])
def test_zip_aggregate_sixty_four_mebibyte_boundary(tmp_path, over):
    path = tmp_path / "boundary.zip"
    metadata = json.dumps(engine().MascotProject("fixture", "Boundary").to_dict()).encode()
    image = io.BytesIO()
    Image.new("RGBA", (4, 4)).save(image, format="PNG")
    source = image.getvalue()
    padding = 64 * 1024 * 1024 - len(metadata) - len(source) + int(over)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", metadata)
        archive.writestr("source.png", source + b"0" * padding)
    assert path.stat().st_size < 20 * 1024 * 1024
    library = engine().Library(tmp_path / "library")
    if over:
        with pytest.raises(ValueError):
            library.import_zip(path)
        assert not list(library.root.iterdir())
    else:
        assert library.import_zip(path).name == "Boundary"


def test_chroma_key_preserves_dark_edges_and_removes_near_magenta(tmp_path):
    path = tmp_path / "chroma.png"
    pixels = [(255, 0, 255, 255), (249, 8, 251, 170), (0, 0, 0, 255), (60, 0, 60, 255), (200, 50, 100, 255)]
    image = Image.new("RGBA", (5, 1))
    image.putdata(pixels)
    image.save(path)
    library = engine().Library(tmp_path / "library")
    project = library.create("Chroma", path)
    with Image.open(library.asset_path(project.id)) as result:
        assert result.getpixel((0, 0))[3] == 0
        assert result.getpixel((1, 0))[3] == 0
        assert [result.getpixel((x, 0)) for x in (2, 3, 4)] == pixels[2:]


def test_export_refuses_unimportable_oversize_editable_package(tmp_path):
    # Valid compact WebP can expand beyond the editable ZIP input budget as PNG.
    source = tmp_path / "compact.webp"
    image = Image.frombytes("RGBA", (3000, 3000), random.Random(2026).randbytes(3000 * 3000 * 4))
    image.save(source, format="WEBP", quality=10, method=0)
    assert source.stat().st_size < 20 * 1024 * 1024
    library = engine().Library(tmp_path / "library")
    project = library.create("Expanded source", source, remove_magenta=False)
    assert library.asset_path(project.id).stat().st_size > 20 * 1024 * 1024
    destination = tmp_path / "preserved.zip"
    destination.write_bytes(b"preserve")
    with pytest.raises(ValueError):
        library.export_project(project.id, destination)
    assert destination.read_bytes() == b"preserve"
    assert library.load(project.id) == project
