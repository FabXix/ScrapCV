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
        members = self._members(listing.stdout)
        for member in members:
            safe_member_path(destination, member.path)  # valida rutas antes de extraer
            if member.is_link:
                raise UnsafeArchive(f"enlace simbólico dentro del archivo: {member.path}")
        files = [m for m in members if not m.is_dir]
        # Mismos límites que .zip y .tar, con los tamaños que declara el archivo…
        self._check_totals(len(files), sum(m.size for m in files), max(1, path.stat().st_size))
        run = subprocess.run([self._exe, "x", "-y", f"-o{destination}", str(path)], capture_output=True, timeout=600)
        if run.returncode != 0:
            raise ExtractionError("no se pudo descomprimir con 7z")
        # …y con lo que realmente quedó en disco, por si las cabeceras mentían.
        written = [p for p in destination.rglob("*") if p.is_file()]
        try:
            self._check_totals(len(written), sum(p.stat().st_size for p in written), max(1, path.stat().st_size))
        except UnsafeArchive:
            shutil.rmtree(destination, ignore_errors=True)
            raise

    @staticmethod
    def _members(listing: str) -> list["_SevenZipMember"]:
        """Lee la salida de `7z l -slt`: un bloque «Clave = valor» por miembro, después de «----------»."""
        _, _, body = listing.partition("\n----------")
        members = []
        for block in body.strip().split("\n\n"):
            fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
            if "Path" not in fields:
                continue
            attributes = fields.get("Attributes", "")
            unix_mode = attributes.split()[-1] if attributes.split() else ""  # «A_ lrwxrwxrwx» = enlace
            try:
                size = int(fields.get("Size") or 0)
            except ValueError:
                size = 0
            members.append(_SevenZipMember(
                path=fields["Path"],
                size=size,
                is_dir=fields.get("Folder") == "+" or attributes.startswith("D"),
                is_link=len(unix_mode) == 10 and unix_mode.startswith("l"),
            ))
        return members


@dataclass(frozen=True)
class _SevenZipMember:
    path: str
    size: int
    is_dir: bool
    is_link: bool
