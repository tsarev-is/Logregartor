"""Детерминированное обучение и сопоставление с неизменяемым словарём Drain3."""

import copy
import importlib.metadata
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

from drain3 import TemplateMiner
from drain3.file_persistence import FilePersistence
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

from . import VERSION
from .artifacts import (ROOT, atomic_writer, canonical, digest, distinct_paths,
                        load_json, read_events, read_report, sha256, write_json)


def versions():
    return {name: importlib.metadata.version(name) for name in ("drain3", "jsonpickle", "cachetools")}


def miner_config(settings):
    cfg = TemplateMinerConfig()
    cfg.drain_depth = settings["depth"]
    cfg.drain_sim_th = settings["sim_th"]
    cfg.drain_max_children = settings["max_children"]
    cfg.drain_max_clusters = None  # Never evict evidence vocabulary.
    cfg.parametrize_numeric_tokens = True
    cfg.masking_instructions = [MaskingInstruction(m["regex"], m["name"]) for m in settings["masks"]]
    if cfg.drain_depth < 3 or not 0 <= cfg.drain_sim_th <= 1:
        raise ValueError("invalid Drain depth or similarity threshold")
    return cfg


def eligible(event):
    return event["parse_status"] == "ok" and bool(event["message"].strip())


def template_input(event, settings):
    message = event["message"]
    if settings["strip_instance_prefix"] and event["instance_id"]:
        prefix = "[instance: " + event["instance_id"] + "]"
        if message == prefix or message.startswith(prefix + " "):
            message = message[len(prefix):].lstrip(" ")
    return message


def template_id(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fit(events, report_path, state_dir, config_path=None):
    report = read_report(events, report_path)
    settings = load_json(config_path or ROOT / "config/drain.json")
    state_dir = Path(state_dir)
    if state_dir.exists():
        raise ValueError("state directory already exists; train a new immutable vocabulary in a new directory")
    miner = TemplateMiner(config=miner_config(settings))
    count = 0
    for event in read_events(events, report):
        if event["template_status"] != "pending":
            raise ValueError("fit requires parser output, not transformed events")
        message = template_input(event, settings)
        if eligible(event) and message.strip():
            miner.add_log_message(message)
            count += 1
    templates = sorted({c.get_template() for c in miner.drain.clusters})
    identity = {"schema_version": 1, "pipeline_version": VERSION, "dependencies": versions(),
                "settings": settings, "templates": templates,
                "parser_version": report["parser_version"],
                "timezone_assumption": report["timezone_assumption"],
                "reference_sources": sorted(f["source_sha256"] for f in report["files"])}
    version = digest(identity)
    catalog = [{"template_id": template_id(t), "template_version": version, "template_text": t} for t in templates]
    state_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".logparser-state-", dir=state_dir.parent))
    try:
        snapshot = temporary / "snapshot.bin"
        miner.persistence_handler = FilePersistence(str(snapshot))
        miner.save_state("frozen")
        write_json(temporary / "templates.json", catalog)
        manifest = {"identity": identity, "template_version": version, "training_messages": count,
                    "snapshot_sha256": sha256(snapshot), "catalog_sha256": sha256(temporary / "templates.json")}
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(state_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def load_state(state_dir):
    state_dir = Path(state_dir)
    manifest = load_json(state_dir / "manifest.json")
    identity = manifest["identity"]
    if digest(identity) != manifest["template_version"]:
        raise ValueError("template identity digest mismatch")
    if identity["pipeline_version"] != VERSION or identity["dependencies"] != versions():
        raise ValueError("template runtime versions differ; use the pinned environment or retrain")
    for name, key in (("snapshot.bin", "snapshot_sha256"), ("templates.json", "catalog_sha256")):
        if sha256(state_dir / name) != manifest[key]:
            raise ValueError(f"template artifact checksum mismatch: {name}")
    catalog = load_json(state_dir / "templates.json")
    expected = [{"template_id": template_id(t), "template_version": manifest["template_version"], "template_text": t}
                for t in identity["templates"]]
    if catalog != expected:
        raise ValueError("catalog differs from vocabulary identity")
    # Only locally generated, trusted snapshots may be loaded: Drain3 uses jsonpickle.
    miner = TemplateMiner(FilePersistence(str(state_dir / "snapshot.bin")), miner_config(identity["settings"]))
    if sorted({c.get_template() for c in miner.drain.clusters}) != identity["templates"]:
        raise ValueError("snapshot templates differ from catalog")
    miner.persistence_handler = None
    return miner, manifest, catalog


def transform(events, report_path, output, output_report, state_dir):
    distinct_paths(events, report_path, output, output_report)
    started = time.monotonic()
    report = read_report(events, report_path)
    miner, manifest, _ = load_state(state_dir)
    for key in ("parser_version", "timezone_assumption"):
        if report[key] != manifest["identity"][key]:
            raise ValueError(f"vocabulary and parser input differ: {key}")
    counts = Counter()
    version = manifest["template_version"]
    with atomic_writer(output) as out:
        for event in read_events(events, report):
            if event["template_status"] != "pending":
                raise ValueError("transform requires parser output")
            event["template_version"] = version
            message = template_input(event, manifest["identity"]["settings"])
            if eligible(event) and message.strip():
                cluster = miner.match(message, full_search_strategy="always")
                event["template_status"] = "matched" if cluster else "unknown"
                event["template_id"] = template_id(cluster.get_template()) if cluster else None
            else:
                event["template_status"] = "skipped"
            counts[event["template_status"]] += 1
            out.write(canonical(event) + "\n")
    result = copy.deepcopy(report)
    result.update(events_sha256=sha256(output), template_version=version, template_counts=dict(counts),
                  pipeline_version=VERSION, elapsed_seconds=time.monotonic() - started)
    result["processing_version"] = digest({k: result[k] for k in
        ("schema_version", "parser_version", "timezone_assumption", "template_version", "pipeline_version")})
    write_json(output_report, result)
    return result
