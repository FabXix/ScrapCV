"""Archivos comprimidos (CAR-09, CAR-10) con descompresión segura.

Protecciones:
- Rutas fuera de la carpeta destino ("zip slip") o absolutas: se rechazan.
- Enlaces simbólicos y dispositivos dentro del archivo: se ignoran.
- Archivos desproporcionados ("zip bomb"): límite de tamaño total, de número
  de archivos y de tasa de compresión.
- Anidamiento: límite de profundidad.
"""
from __future__ import annotations

import shutil
import subprocess
from abc import abstractmethod
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from scrapcv.domain.facts import Flag
from scrapcv.extraction.base import (
    ExtractionContext,
    ExtractionError,
    ExtractionResult,
    FormatExtractor,
    UnpackedArchive,
)


@dataclass(frozen=True)
class ArchiveLimits:
    max_total_bytes: int = 500 * 1024 * 1024
    max_members: int = 10_000
    max_ratio: float = 200.0
    max_depth: int = 3


class UnsafeArchive(ExtractionError):
    pass


def safe_member_path(destination: Path, member_name: str) -> Path:
    """Devuelve la ruta destino o lanza UnsafeArchive si escapa de `destination`."""
    pure = PurePosixPath(member_name.replace("\\", "/"))
    if pure.is_absolute() or (pure.parts and ":" in pure.parts[0]):
        raise UnsafeArchive(f"ruta absoluta en el archivo: {member_name}")
    target = (destination / Path(*pure.parts)).resolve() if pure.parts else destination.resolve()
    root = destination.resolve()
    if target != root and root not in target.parents:
        raise UnsafeArchive(f"ruta fuera de la carpeta destino: {member_name}")
    return target


class _ArchiveExtractor(FormatExtractor):
    def __init__(self, limits: ArchiveLimits = ArchiveLimits()) -> None:
        self._limits = limits

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        label = ctx.label(path)
        if ctx.depth >= self._limits.max_depth:
            return ExtractionResult(flags=[Flag(label, "anidamiento excesivo de archivos comprimidos")])
        destination = ctx.work_dir / "unpacked" / label.replace("!/", "__").replace("/", "__")
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        self._unpack(path, destination)
        return ExtractionResult(unpacked=[UnpackedArchive(destination, f"{label}!/")])

    def _check_totals(self, members: int, total: int, compressed: int) -> None:
        if members > self._limits.max_members:
            raise UnsafeArchive("demasiados archivos dentro del comprimido")
        if total > self._limits.max_total_bytes:
            raise UnsafeArchive("contenido descomprimido desproporcionado")
        if compressed and total / compressed > self._limits.max_ratio:
            raise UnsafeArchive("tasa de compresión sospechosa (posible zip bomb)")

    @abstractmethod
    def _unpack(self, path: Path, destination: Path) -> None:
        """Template Method: cada formato sabe descomprimirse; las reglas comunes viven aquí."""


class ZipExtractor(_ArchiveExtractor):
    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() == ".zip"

    def _unpack(self, path: Path, destination: Path) -> None:
        try:
            with zipfile.ZipFile(path) as archive:
                infos = [i for i in archive.infolist() if not i.is_dir()]
                total = sum(i.file_size for i in infos)
                self._check_totals(len(infos), total, max(1, path.stat().st_size))
                for info in infos:
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        continue  # enlace simbólico
                    target = safe_member_path(destination, info.filename)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("wb") as sink:
                        shutil.copyfileobj(source, sink)
        except zipfile.BadZipFile as exc:
            raise ExtractionError("zip dañado") from exc


class TarExtractor(_ArchiveExtractor):
    def can_handle(self, path: Path) -> bool:
        name = path.name.lower()
        return name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"))

    def _unpack(self, path: Path, destination: Path) -> None:
        try:
            with tarfile.open(path) as archive:
                members = [m for m in archive.getmembers() if m.isfile()]  # sin links ni dispositivos
                total = sum(m.size for m in members)
                self._check_totals(len(members), total, max(1, path.stat().st_size))
                for member in members:
                    target = safe_member_path(destination, member.name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        continue
                    with source, target.open("wb") as sink:
                        shutil.copyfileobj(source, sink)
        except tarfile.TarError as exc:
            raise ExtractionError("tar dañado") from exc


class SevenZipExtractor(_ArchiveExtractor):
    """.rar y .7z solo si 7z está instalado; si no, se marca (CAR-10)."""

    def __init__(self, limits: ArchiveLimits = ArchiveLimits(), executable: str | None = None) -> None:
        super().__init__(limits)
        self._exe = executable or shutil.which("7z") or shutil.which("7za")

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in (".rar", ".7z")

    def extract(self, path: Path, ctx: ExtractionContext) -> ExtractionResult:
        if not self._exe:
            return ExtractionResult(flags=[Flag(ctx.label(path), "requiere 7z instalado para abrir .rar/.7z")])
        return super().extract(path, ctx)

    def _unpack(self, path: Path, destination: Path) -> None:
        listing = subprocess.run([self._exe, "l", "-slt", str(path)], capture_output=True, text=True, timeout=120)
        if listing.returncode != 0:
            raise ExtractionError("archivo .rar/.7z dañado")
        names = [line[7:] for line in listing.stdout.splitlines() if line.startswith("Path = ")][1:]
        for name in names:
            safe_member_path(destination, name)  # valida antes de extraer
        run = subprocess.run([self._exe, "x", "-y", f"-o{destination}", str(path)], capture_output=True, timeout=600)
        if run.returncode != 0:
            raise ExtractionError("no se pudo descomprimir con 7z")
