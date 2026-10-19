#!/usr/bin/env python3
"""Checkpointed, local BiRefNet conversion into a separate white JPEG candidate.

Input files are only read. Output names are their new content hashes; the final
mapping.csv records the corresponding original names. No catalog CSV is edited.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import sys
import time

MODEL_SHA256 = "58f621f00f5d756097615970a88a791584600dcf7c45b18a0a6267535a1ebd3c"
PACKAGES = {"Pillow": "12.3.0", "rembg": "2.0.84", "onnxruntime": "1.30.0"}
ENCODING = {"quality": 90, "subsampling": 2, "optimize": True, "progressive": True}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def prepare(source, job, inputs, weights, expected_count):
    source, job = source.resolve(), job.resolve()
    if job.exists() or job.is_symlink():
        raise FileExistsError("Use a fresh job directory: " + str(job))
    if job.is_relative_to(source) or source.is_relative_to(job):
        raise ValueError("Output overlaps the originals")
    paths = sorted(source.iterdir())
    if len(paths) != expected_count:
        raise ValueError(f"Expected {expected_count} source images, found {len(paths)}")
    images = []
    for n, path in enumerate(paths, 1):
        if path.is_symlink() or not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}\.jpg", path.name):
            raise ValueError("Unexpected source: " + str(path))
        if sha256(path) != path.stem:
            raise ValueError("Original content hash mismatch: " + path.name)
        images.append({"n": n, "file": path.name, "sha256": path.stem, "bytes": path.stat().st_size})
        if n % 10000 == 0:
            print(f"Verified {n:,}/{expected_count:,} originals", flush=True)
    manifest = {"schema": 1, "originals": str(source), "images": images}
    job.mkdir(parents=True)
    atomic_json(job / "manifest.json", manifest)
    config = {"schema": 1, "inputs": str(inputs), "weights": str(weights),
              "manifest_sha256": sha256(job / "manifest.json"), "model_sha256": MODEL_SHA256,
              "packages": PACKAGES, "encoding": ENCODING, "reserve_bytes": 5 * 1024**3,
              "benchmark_seconds_per_image": 162.7179 / 32, "prepared_at": time.time()}
    atomic_json(job / "config.json", config)
    print(json.dumps({"job": str(job), "originals_verified": len(images),
                      "source_bytes": sum(r["bytes"] for r in images),
                      "manifest_sha256": config["manifest_sha256"]}), flush=True)


def connect(job):
    db = sqlite3.connect(job / "checkpoint.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS images (
          n INTEGER PRIMARY KEY, file TEXT UNIQUE NOT NULL, source_sha256 TEXT NOT NULL,
          source_bytes INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0, output_file TEXT, output_sha256 TEXT,
          output_bytes INTEGER, seconds REAL, finished_at REAL, warning TEXT, error TEXT);
        CREATE INDEX IF NOT EXISTS image_state ON images(state,n);
        CREATE INDEX IF NOT EXISTS image_finished ON images(state,finished_at DESC);
    """)
    return db


def meta(db, key, value=None):
    if value is not None:
        db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def initialize(job, config, manifest):
    db = connect(job)
    identity = {"manifest": config["manifest_sha256"], "model": config["model_sha256"],
                "encoding": config["encoding"], "packages": config["packages"]}
    existing = meta(db, "identity")
    if existing is not None and existing != identity:
        db.close()
        raise ValueError("Job identity changed; refusing to reuse checkpoint")
    if existing is None:
        with db:
            meta(db, "identity", identity)
            db.executemany("INSERT INTO images(n,file,source_sha256,source_bytes) VALUES (?,?,?,?)",
                           [(r["n"], r["file"], r["sha256"], r["bytes"]) for r in manifest["images"]])
            meta(db, "started_at", time.time())
            meta(db, "restarts", -1)
    if db.execute("SELECT count(*) FROM images").fetchone()[0] != len(manifest["images"]):
        raise ValueError("Checkpoint image count differs from manifest")
    return db


def export_mapping(job, db):
    temporary = job / "mapping.csv.tmp"
    with temporary.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["original_file", "original_sha256", "state", "output_file", "output_sha256",
                         "original_bytes", "output_bytes", "seconds", "warning", "error"])
        for row in db.execute("SELECT * FROM images ORDER BY n"):
            writer.writerow([row["file"], row["source_sha256"], row["state"], row["output_file"],
                             row["output_sha256"], row["source_bytes"], row["output_bytes"],
                             row["seconds"], row["warning"], row["error"]])
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, job / "mapping.csv")


def status_snapshot(job, db, config, state, current=None, error=None):
    counts = dict(db.execute("SELECT state,count(*) FROM images GROUP BY state").fetchall())
    done, failed = counts.get("done", 0), counts.get("error", 0)
    total = sum(counts.values())
    recent = db.execute("SELECT avg(seconds) FROM (SELECT seconds FROM images WHERE state='done' ORDER BY finished_at DESC LIMIT 256)").fetchone()[0]
    per_image = recent or config["benchmark_seconds_per_image"]
    remaining = max(0, total - done - failed)
    now = time.time()
    eta = now + remaining * per_image if state in {"running", "loading_model", "verifying"} else None
    failures = [dict(r) for r in db.execute("SELECT file,error FROM images WHERE state='error' ORDER BY n LIMIT 12")]
    samples = [dict(r) for r in db.execute("SELECT file,output_file,warning FROM images WHERE state='done' ORDER BY n LIMIT 8")]
    latest = [dict(r) for r in db.execute("SELECT file,output_file,warning FROM images WHERE state='done' ORDER BY finished_at DESC LIMIT 8")]
    snapshot = {"schema": 1, "state": state, "updated_at": now, "pid": os.getpid(),
                "started_at": meta(db, "started_at"), "restarts": meta(db, "restarts"),
                "total": total, "done": done, "failed": failed, "remaining": remaining,
                "percent": round(100 * (done + failed) / total, 4) if total else 0,
                "seconds_per_image": round(per_image, 4), "eta_at": eta,
                "eta_basis": "last 256 completed images" if recent else "32-image Mac mini benchmark",
                "current_file": current, "last_finished_at": db.execute("SELECT max(finished_at) FROM images").fetchone()[0],
                "source_bytes": db.execute("SELECT sum(source_bytes) FROM images").fetchone()[0],
                "output_bytes": db.execute("SELECT coalesce(sum(output_bytes),0) FROM images WHERE state='done'").fetchone()[0],
                "review_flags": db.execute("SELECT count(*) FROM images WHERE warning IS NOT NULL").fetchone()[0],
                "free_disk_bytes": shutil.disk_usage(job).free, "reserve_bytes": config["reserve_bytes"],
                "encoding": config["encoding"], "model_sha256": config["model_sha256"],
                "manifest_sha256": config["manifest_sha256"], "worker_sha256": sha256(Path(__file__)),
                "error": error, "failures": failures, "samples": samples, "latest": latest,
                "visual_review": "pending", "catalog_imported": False}
    atomic_json(job / "status.json", snapshot)
    return snapshot


def load_session(config):
    import onnxruntime as ort
    from rembg import new_session
    from rembg.sessions.birefnet_general import BiRefNetSessionGeneral
    for package, expected in config["packages"].items():
        if version(package) != expected:
            raise ValueError(f"Runtime changed: {package}")
    weights = Path(config["weights"])
    if weights.is_symlink() or sha256(weights) != config["model_sha256"]:
        raise ValueError("Model content hash mismatch")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    original = BiRefNetSessionGeneral.download_models
    BiRefNetSessionGeneral.download_models = classmethod(lambda cls, *args, **kwargs: str(weights.resolve()))
    try:
        session = new_session("birefnet-general", providers=["CPUExecutionProvider"], sess_opts=options)
    finally:
        BiRefNetSessionGeneral.download_models = original
    if session.inner_session.get_providers() != ["CPUExecutionProvider"]:
        raise ValueError("Unexpected inference provider")
    return session


def convert_one(job, row, config, session):
    from PIL import Image
    source = Path(config["inputs"]) / row["file"]
    if source.is_symlink() or not source.is_file() or source.stat().st_size != row["source_bytes"]:
        raise ValueError("Input file missing, replaced, or wrong size")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != row["source_sha256"]:
        raise ValueError("Input content hash mismatch")
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "JPEG":
            raise ValueError("Expected a JPEG original")
        rgb = image.convert("RGB")
    masks = session.predict(rgb)
    if len(masks) != 1 or masks[0].size != rgb.size or masks[0].mode != "L":
        raise ValueError("Unexpected segmentation mask")
    mask = masks[0]
    histogram = mask.histogram()
    fraction = sum(histogram[128:]) / (rgb.width * rgb.height)
    if mask.getextrema()[1] == 0:
        raise ValueError("Empty foreground mask; image retained as an error")
    warning = "foreground_fraction=" + str(round(fraction, 5)) if fraction < 0.005 or fraction > 0.995 else None
    cutout = rgb.copy()
    cutout.putalpha(mask)
    white = Image.alpha_composite(Image.new("RGBA", rgb.size, (255, 255, 255, 255)), cutout).convert("RGB")
    encoded = io.BytesIO()
    white.save(encoded, "JPEG", **config["encoding"])
    output = encoded.getvalue()
    output_hash = hashlib.sha256(output).hexdigest()
    output_file = output_hash + ".jpg"
    media = job / "media" / "wands-expanded"
    media.mkdir(parents=True, exist_ok=True)
    target = media / output_file
    # Hash filenames and exclusive publication also handle duplicate outputs and
    # a crash between writing the image and committing its SQLite checkpoint.
    temporary = media / ("." + output_file + ".part")
    with temporary.open("wb") as stream:
        stream.write(output)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.is_symlink() or sha256(target) != output_hash:
                raise ValueError("Existing output does not match its content hash")
    finally:
        temporary.unlink(missing_ok=True)
    if sha256(source) != row["source_sha256"]:
        raise ValueError("Input changed during conversion")
    return {"output_file": output_file, "output_sha256": output_hash,
            "output_bytes": len(output), "warning": warning}


def run(job, max_images=0, session_factory=load_session):
    job = job.resolve()
    config = json.loads((job / "config.json").read_text())
    if sha256(job / "manifest.json") != config["manifest_sha256"]:
        raise ValueError("Manifest content hash mismatch")
    if config["encoding"] != ENCODING or config["model_sha256"] != MODEL_SHA256:
        raise ValueError("Unexpected model or JPEG settings")
    inputs = Path(config["inputs"]).resolve()
    if job == inputs or job.is_relative_to(inputs):
        raise ValueError("Job overlaps its inputs")
    stop = False
    def stopping(signum, frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    with (job / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = initialize(job, config, json.loads((job / "manifest.json").read_text()))
        try:
            with db:
                db.execute("UPDATE images SET state='pending' WHERE state='processing'")
                meta(db, "restarts", meta(db, "restarts") + 1)
            # Checkpointed outputs are checked on every restart, without touching
            # them or recalculating any successfully finished image.
            status_snapshot(job, db, config, "verifying")
            media = job / "media" / "wands-expanded"
            completed = db.execute("SELECT n,output_file,output_sha256 FROM images WHERE state='done'").fetchall()
            for checked, row in enumerate(completed, 1):
                path = media / row["output_file"]
                if not path.exists() and not path.is_symlink():
                    with db:
                        db.execute("""UPDATE images SET state='pending',output_file=NULL,output_sha256=NULL,
                            output_bytes=NULL,seconds=NULL,finished_at=NULL,warning=NULL WHERE n=?""", (row["n"],))
                elif path.is_symlink() or not path.is_file() or sha256(path) != row["output_sha256"]:
                    raise ValueError("Checkpointed output is missing or changed: " + row["output_file"])
                if checked % 1000 == 0:
                    status_snapshot(job, db, config, "verifying")
            status_snapshot(job, db, config, "loading_model")
            session = session_factory(config)
            processed = 0
            consecutive_errors = 0
            while not stop:
                row = db.execute("SELECT * FROM images WHERE state='pending' ORDER BY n LIMIT 1").fetchone()
                if row is None:
                    break
                while shutil.disk_usage(job).free < config["reserve_bytes"] and not stop:
                    status_snapshot(job, db, config, "paused_low_disk", row["file"])
                    time.sleep(30)
                if stop:
                    break
                status_snapshot(job, db, config, "running", row["file"])
                with db:
                    db.execute("UPDATE images SET state='processing',attempts=attempts+1 WHERE n=?", (row["n"],))
                started = time.monotonic()
                try:
                    result = convert_one(job, row, config, session)
                    with db:
                        db.execute("""UPDATE images SET state='done',output_file=?,output_sha256=?,output_bytes=?,
                            warning=?,seconds=?,finished_at=?,error=NULL WHERE n=?""",
                            (result["output_file"], result["output_sha256"], result["output_bytes"], result["warning"],
                             time.monotonic() - started, time.time(), row["n"]))
                    consecutive_errors = 0
                except (OSError, ValueError, RuntimeError) as error:
                    with db:
                        db.execute("UPDATE images SET state='error',error=?,finished_at=? WHERE n=?",
                                   (str(error)[:1000], time.time(), row["n"]))
                    consecutive_errors += 1
                    print(json.dumps({"error": str(error), "file": row["file"]}), flush=True)
                    if consecutive_errors >= 3:
                        raise RuntimeError("Three consecutive image failures; worker needs attention") from error
                processed += 1
                if processed % 100 == 0:
                    print(json.dumps({"state": "running", "done_this_session": processed, "file": row["file"]}), flush=True)
                if max_images and processed >= max_images:
                    break
            remaining = db.execute("SELECT count(*) FROM images WHERE state='pending'").fetchone()[0]
            state = "stopped" if stop else "checkpointed" if remaining else "complete_with_errors" if db.execute("SELECT 1 FROM images WHERE state='error' LIMIT 1").fetchone() else "complete"
            if not remaining and not stop:
                if sha256(Path(config["weights"])) != config["model_sha256"]:
                    raise ValueError("Model changed during conversion")
                export_mapping(job, db)
            result = status_snapshot(job, db, config, state)
            print(json.dumps({k: result[k] for k in ("state", "done", "failed", "remaining", "restarts")}), flush=True)
            return result
        except BaseException as error:
            status_snapshot(job, db, config, "needs_attention", error=str(error)[:1000])
            raise
        finally:
            db.close()


def pretty_status(snapshot):
    def date(value):
        return datetime.fromtimestamp(value, timezone.utc).astimezone().strftime("%a %b %d %I:%M %p %Z") if value else "unavailable"
    lines = [f"State: {snapshot['state']}",
             f"Finished: {snapshot['done']:,} / {snapshot['total']:,} ({snapshot['percent']:.2f}%)",
             f"Errors: {snapshot['failed']:,}; review flags: {snapshot['review_flags']:,}; restarts: {snapshot['restarts']}",
             f"Speed: {snapshot['seconds_per_image']:.2f} sec/image; estimated finish: {date(snapshot['eta_at'])}",
             f"Last progress: {date(snapshot['last_finished_at'])}",
             f"Status updated: {date(snapshot['updated_at'])} ({int(time.time()-snapshot['updated_at'])} seconds ago)",
             f"Mini free disk: {snapshot['free_disk_bytes']/1024**3:.1f} GiB; output: {snapshot['output_bytes']/1024**3:.2f} GiB"]
    if snapshot.get("error"):
        lines.append("Attention: " + snapshot["error"])
    if snapshot.get("worker_alive") is False and snapshot["state"] not in {"complete", "complete_with_errors"}:
        lines.append("Attention: the worker process is not running")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    for option in ("source", "job", "inputs", "weights"):
        prep.add_argument("--" + option, type=Path, required=True)
    prep.add_argument("--expected-count", type=int, default=95401)
    runner = commands.add_parser("run")
    runner.add_argument("--job", type=Path, required=True)
    runner.add_argument("--max-images", type=int, default=0)
    status = commands.add_parser("status")
    status.add_argument("--job", type=Path, required=True)
    status.add_argument("--json", action="store_true")
    a = p.parse_args()
    if a.command == "prepare":
        prepare(a.source, a.job, a.inputs, a.weights, a.expected_count)
    elif a.command == "run":
        run(a.job, a.max_images)
    else:
        snapshot = json.loads((a.job / "status.json").read_text())
        try:
            os.kill(snapshot["pid"], 0)
            snapshot["worker_alive"] = True
        except ProcessLookupError:
            snapshot["worker_alive"] = False
        print(json.dumps(snapshot) if a.json else pretty_status(snapshot))


if __name__ == "__main__":
    main()
