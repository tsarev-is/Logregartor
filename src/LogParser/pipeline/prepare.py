"""Загрузка закреплённых данных; из TAR извлекаются только три известных файла."""

import shutil
import tarfile
import urllib.request
from pathlib import Path

from .artifacts import atomic_writer, sha256, write_json

SOURCES = {
    "OpenStack.tar.gz": ("https://zenodo.org/records/3227177/files/OpenStack.tar.gz?download=1",
        "87c98c5ed03262e05cdb7a6f3717033df76d88fda0f7d2db23bd9fa4200f1879"),
    "OpenStack_2k.log_structured.csv": ("https://raw.githubusercontent.com/logpai/loghub/master/OpenStack/OpenStack_2k.log_structured.csv",
        "ecc88e7909777181824260e9bdacd1469bd24d55131d6fc14e9c8c17edc49ff0"),
    "OpenStack_2k.log": ("https://raw.githubusercontent.com/logpai/loghub/master/OpenStack/OpenStack_2k.log",
        "025a1bc64ff5b2ef4a4bda6c4ad5c5c5f18478b71cd1ad2b0676e01625629f2f"),
}
LOG_FILES = ("openstack_normal1.log", "openstack_normal2.log", "openstack_abnormal.log")


def prepare(output_dir, cache_dir=None):
    output_dir = Path(output_dir)
    cache_dir = Path(cache_dir) if cache_dir else output_dir / "downloads"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in SOURCES.items():
        target = cache_dir / name
        if not target.exists():
            with atomic_writer(target, "wb") as out, urllib.request.urlopen(url, timeout=60) as incoming:
                shutil.copyfileobj(incoming, out)
        if sha256(target) != expected:
            raise ValueError(f"dataset checksum mismatch: {target}")
    with tarfile.open(cache_dir / "OpenStack.tar.gz", "r:gz") as archive:
        for name in LOG_FILES:
            member = archive.getmember(name)
            if not member.isfile():
                raise ValueError(f"unexpected archive entry: {name}")
            with archive.extractfile(member) as incoming, atomic_writer(output_dir / name, "wb") as out:
                shutil.copyfileobj(incoming, out)
        # Labels are deliberately not extracted into the ingestion directory.
    for name in ("OpenStack_2k.log", "OpenStack_2k.log_structured.csv"):
        target = output_dir / name
        if target.resolve() != (cache_dir / name).resolve():
            with (cache_dir / name).open("rb") as incoming, atomic_writer(target, "wb") as out:
                shutil.copyfileobj(incoming, out)
    report = {"sources": {name: {"url": url, "sha256": checksum} for name, (url, checksum) in SOURCES.items()},
              "files": {name: sha256(output_dir / name) for name in LOG_FILES}}
    write_json(output_dir / "dataset.json", report)
    return report
