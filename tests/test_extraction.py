import io
import tarfile
import zipfile

import pytest

from scrapcv.extraction.analyzer import StaticAnalyzer
from scrapcv.extraction.base import ExtractionContext, ExtractionResult, ExtractorRegistry, FormatExtractor
from scrapcv.extraction.extractors.archives import ArchiveLimits, TarExtractor, UnsafeArchive, ZipExtractor, safe_member_path
from scrapcv.extraction.factory import default_registry
from scrapcv.extraction.links import LinkClassifier
from scrapcv.extraction.policies import CredentialPolicy


def _zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _analyze(raw, tmp_path, registry=None):
    return StaticAnalyzer(registry or default_registry()).analyze("k", raw, tmp_path / "work")


def test_counts_languages_lines_and_dependencies(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "main.py").write_text("import os\n\nprint('hola')\n")
    (raw / "util.js").write_text("const a = 1;\n")
    (raw / "requirements.txt").write_text("flask==3.0\n# comentario\nrequests>=2\n")
    facts = _analyze(raw, tmp_path).facts
    assert facts.languages["Python"].lines == 2
    assert facts.languages["JavaScript"].files == 1
    assert facts.dependencies == ["flask", "requests"]


def test_never_reads_credentials(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / ".env").write_text("TOKEN=secreto")
    (raw / "id_rsa").write_text("PRIVATE")
    (raw / "app.py").write_text("x = 1\n")
    outcome = _analyze(raw, tmp_path)
    assert outcome.facts.credentials_skipped == 2
    assert all("secreto" not in s.text for s in outcome.snippets)


@pytest.mark.parametrize("name", [".env", "prod.env", "server.pem", "id_ed25519", "credentials.json", ".npmrc"])
def test_credential_policy(name, tmp_path):
    assert CredentialPolicy().is_sensitive(tmp_path / name)


def test_nested_zip_is_unpacked_and_node_modules_ignored(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    inner = _zip_bytes({"src/app.ts": "let x = 1;\nlet y = 2;\n", "node_modules/lib/index.js": "1\n2\n3\n"})
    (raw / "entrega.zip").write_bytes(_zip_bytes({"proyecto.zip": inner}))
    facts = _analyze(raw, tmp_path).facts
    assert facts.languages == {"TypeScript": facts.languages["TypeScript"]}
    assert facts.languages["TypeScript"].lines == 2
    assert facts.code_files == ["entrega.zip!/proyecto.zip!/src/app.ts"]


def test_zip_slip_is_rejected(tmp_path):
    with pytest.raises(UnsafeArchive):
        safe_member_path(tmp_path, "../../fuera.txt")
    with pytest.raises(UnsafeArchive):
        safe_member_path(tmp_path, "/etc/passwd")


def test_malicious_zip_is_flagged_not_extracted(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "malo.zip").write_bytes(_zip_bytes({"../escape.py": "print(1)\n"}))
    facts = _analyze(raw, tmp_path).facts
    assert not (tmp_path / "escape.py").exists()
    assert any("fuera de la carpeta" in f.reason for f in facts.flags)


def test_zip_bomb_ratio_is_rejected(tmp_path):
    bomb = tmp_path / "bomba.zip"
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ceros.txt", "0" * 5_000_000)
    ctx = ExtractionContext(tmp_path, "", tmp_path / "work")
    with pytest.raises(UnsafeArchive):
        ZipExtractor(ArchiveLimits(max_ratio=50)).extract(bomb, ctx)


def test_tar_with_symlink_member_is_skipped(tmp_path):
    archive_path = tmp_path / "x.tar"
    with tarfile.open(archive_path, "w") as archive:
        link = tarfile.TarInfo("enlace")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        archive.addfile(link)
        data = b"print(1)\n"
        info = tarfile.TarInfo("ok.py")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    ctx = ExtractionContext(tmp_path, "", tmp_path / "work")
    result = TarExtractor().extract(archive_path, ctx)
    files = [p.name for p in result.unpacked[0].folder.rglob("*")]
    assert files == ["ok.py"]


def test_unknown_or_broken_files_do_not_stop_the_analysis(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "roto.pdf").write_bytes(b"no soy un pdf")
    (raw / "datos.xyz").write_bytes(b"???")
    (raw / "ok.py").write_text("a = 1\n")
    facts = _analyze(raw, tmp_path).facts
    assert facts.languages["Python"].lines == 1
    reasons = {f.path: f.reason for f in facts.flags}
    assert "datos.xyz" in reasons and "roto.pdf" in reasons


def test_new_format_only_needs_a_new_class(tmp_path):
    """Mantenibilidad (7.1): un formato nuevo no modifica el analizador."""

    class FortranExtractor(FormatExtractor):
        def can_handle(self, path):
            return path.suffix == ".f90"

        def extract(self, path, ctx):
            from scrapcv.extraction.base import CodeFileStat

            return ExtractionResult(code=[CodeFileStat("Fortran", 3, ctx.label(path))])

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "calc.f90").write_text("x\ny\nz\n")
    registry = ExtractorRegistry().register(FortranExtractor())
    assert _analyze(raw, tmp_path, registry).facts.languages["Fortran"].lines == 3


def test_link_classifier():
    links = LinkClassifier().find("ver https://github.com/a/b y https://youtu.be/x, https://ejemplo.com.", "s")
    assert [(l.kind, l.url) for l in links] == [
        ("repositorio", "https://github.com/a/b"), ("youtube", "https://youtu.be/x"), ("otro", "https://ejemplo.com"),
    ]
