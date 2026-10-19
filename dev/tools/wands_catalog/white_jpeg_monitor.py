#!/usr/bin/env python3
"""Studio monitor: check the Mini, mirror candidate JPGs, update HTML, notify."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import fcntl
from html import escape
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import time

from white_jpeg_worker import atomic_json, pretty_status, sha256

SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=yes",
               "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2"]
TERMINAL = {"complete", "complete_with_errors"}


def issues(snapshot, now):
    problems = []
    state = snapshot["state"]
    if state not in TERMINAL:
        if now - snapshot["updated_at"] > 600:
            problems.append("Worker status has not updated for 10 minutes")
        if snapshot.get("worker_alive") is False:
            problems.append("Worker process is not running")
        if state == "running" and now - (snapshot.get("last_finished_at") or snapshot["started_at"]) > 600:
            problems.append("No image has finished for 10 minutes")
        if state not in {"running", "loading_model", "verifying"}:
            problems.append("Worker state: " + state)
    if snapshot["free_disk_bytes"] < snapshot["reserve_bytes"]:
        problems.append("Mini free disk is below the 5 GiB reserve")
    if snapshot["failed"]:
        problems.append(f"{snapshot['failed']:,} images failed")
    if snapshot.get("error"):
        problems.append(snapshot["error"])
    return problems


def notify(message):
    # JSON string quoting is also valid for these plain AppleScript strings.
    script = "display notification " + json.dumps(message) + " with title " + json.dumps("Catalog image processing")
    result = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True, timeout=15)
    return {"accepted_by_macos": result.returncode == 0, "error": result.stderr.strip()[:300]}


def verify_completed_copy(job, config, snapshot):
    completed = 0
    originals = 0
    with (job / "mapping.csv").open() as stream:
        for row in csv.DictReader(stream):
            original = Path(config["originals"]) / row["original_file"]
            if sha256(original) != row["original_sha256"]:
                raise ValueError("An original no longer matches its initial hash: " + row["original_file"])
            originals += 1
            if row["state"] == "done":
                output = job / "media" / "wands-expanded" / row["output_file"]
                if output.is_symlink() or sha256(output) != row["output_sha256"]:
                    raise ValueError("Local candidate hash mismatch: " + row["output_file"])
                completed += 1
    if originals != snapshot["total"] or completed != snapshot["done"]:
        raise ValueError("The completed mapping count differs from job status")
    verification = {"verified_at": time.time(), "originals_intact": originals,
                    "candidate_mappings_verified": completed, "failed": snapshot["failed"],
                    "manifest_sha256": snapshot["manifest_sha256"], "visual_review": "pending"}
    atomic_json(job / "verification.json", verification)
    return verification


def dashboard(job, monitor_config, snapshot, monitor):
    def date(value):
        return datetime.fromtimestamp(value).astimezone().strftime("%a %b %d, %I:%M %p %Z") if value else "Unavailable"
    h = lambda value: escape(str(value), quote=True)
    if snapshot:
        heading = f"{snapshot['done']:,} / {snapshot['total']:,} finished"
        progress = snapshot["percent"]
        eta = date(snapshot["eta_at"])
        details = pretty_status(snapshot)
        cards = []
        samples = {r["file"]: r for r in snapshot.get("samples", []) + snapshot.get("latest", [])}
        for row in samples.values():
            original = Path(monitor_config["originals"]) / row["file"]
            output = job / "media" / "wands-expanded" / row["output_file"]
            if output.is_file():
                cards.append('<article><div><figure><img loading="lazy" src="' + h(original.as_uri()) + '" alt="Original image"><figcaption>Original</figcaption></figure><figure><img loading="lazy" src="' + h(output.as_uri()) + '" alt="White background JPEG"><figcaption>White JPG, quality 90</figcaption></figure></div><p>' + h(row["file"][:16]) + ("; " + h(row["warning"]) if row["warning"] else "") + '</p></article>')
    else:
        heading, progress, eta, details, cards = "Waiting for the Mini", 0, "Unavailable", "No worker status received yet.", []
    alerts = monitor.get("issues", [])
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60"><title>Catalog processing status</title><style>
    body{font:16px system-ui;background:#f4f6f7;color:#18202b;max-width:1200px;margin:32px auto;padding:0 24px}h1{font-size:28px}section,article{background:white;padding:20px;border-radius:12px;margin:20px 0}progress{width:100%;height:28px}pre{white-space:pre-wrap;line-height:1.8}article>div{display:grid;grid-template-columns:1fr 1fr;gap:16px}figure{margin:0}img{width:100%;max-height:420px;object-fit:contain;background:white}figcaption{margin-top:8px}.alert{color:#963300}@media(max-width:650px){article>div{grid-template-columns:1fr}}a{color:#165baf}</style></head><body><h1>Catalog image processing</h1>'''
    html += '<section><h2>' + h(heading) + '</h2><progress max="100" value="' + str(progress) + '"></progress><p>Estimated finish: <strong>' + h(eta) + '</strong></p><pre>' + h(details) + '</pre></section>'
    html += '<section><h2>Monitoring</h2><p>Last check: ' + h(date(monitor["checked_at"])) + '. Checks and local image copies update every five minutes while this Mac is awake and logged in. This page reloads every minute.</p><p>Local copy: ' + h(monitor.get("mirror_state", "waiting")) + '; last successful copy: ' + h(date(monitor.get("last_mirrored_at"))) + '.</p>'
    html += '<p class="alert">' + h("; ".join(alerts) if alerts else "No processing problems detected.") + '</p><p>Original files are preserved. Candidate JPGs are separate; visual review and catalog import remain pending.</p></section>'
    html += '<h2>Sample images</h2><p>First eight and latest eight finished images.</p>' + ''.join(cards) + '</body></html>'
    temporary = job / "status.html.tmp"
    temporary.write_text(html)
    os.replace(temporary, job / "status.html")


def check_audit(job, active, do_notify=True):
    audit=Path(active['audit_path']).resolve()
    if not audit.is_relative_to(job):raise ValueError('Audit is outside its job folder')
    state=json.loads((audit/'status.json').read_text())
    mini={}
    if (audit/'mini-config.json').exists():
        config=json.loads((audit/'mini-config.json').read_text())
        if (audit/'mini-imported.json').exists() and (audit/'mini-status.json').exists():
            imported=json.loads((audit/'mini-imported.json').read_text())
            cached=json.loads((audit/'mini-status.json').read_text())
            if (imported.get('state')=='complete' and cached.get('state') in TERMINAL and
                imported.get('manifest_sha256')==cached.get('manifest_sha256')==config['manifest_sha256']):mini=cached
        command=shlex.join([config['remote_python'],'-B',config['remote_worker'],'status','--job',config['remote_job'],'--json'])
        if not mini:
            try:
                result=subprocess.run(['/usr/bin/ssh',*SSH_OPTIONS,config['target'],command],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=45)
                if result.returncode==0:
                    mini=json.loads(result.stdout)
            except (OSError,ValueError,subprocess.TimeoutExpired):pass
    if not mini and (audit/'mini-status.json').exists():mini=json.loads((audit/'mini-status.json').read_text())
    report=json.loads((audit/'verification.json').read_text()) if (audit/'verification.json').exists() else None
    h=lambda value:escape(str(value),quote=True)
    phase=state['phase'];date=lambda x:datetime.fromtimestamp(x).astimezone().strftime('%a %b %d, %I:%M %p %Z') if x else 'Not available yet'
    audit_issues=[state['error']] if state.get('error') else []
    if state.get('mini_connection_warning'):audit_issues.append('Mini connection: '+state['mini_connection_warning'])
    if not report and time.time()-state['updated_at']>600:
        audit_issues.append('Audit progress has not updated for 10 minutes')
    if not report and state.get('pid'):
        try:os.kill(state['pid'],0)
        except ProcessLookupError:audit_issues.append('Audit process is not running')
        except PermissionError:pass
    heading='Verified selection complete' if report else phase.replace('_',' ').capitalize()
    html='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60"><title>Catalog scene-preserving audit</title><style>body{font:17px/1.6 system-ui;background:#f4f6f7;color:#18202b;max-width:1100px;margin:32px auto;padding:0 24px}section{background:white;border-radius:12px;padding:24px;margin:20px 0}img{width:42%;max-height:420px;object-fit:contain;background:white}pre{white-space:pre-wrap}a{color:#165baf}</style><h1>Catalog scene-preserving audit</h1>'
    html+='<section><h2>'+h(heading)+'</h2><p>Preserve originals for scenes, non-solid backgrounds, and bad or uncertain cutouts. Reuse verified white JPGs. The two flagged mirrors receive new generated images on white.</p>'
    if state.get('audit_kind')=='calibrated':
        html+='<p><strong>Calibrated re-audit:</strong> the previous selection is preserved. Labelled reference images: '+h(str(state.get('reference_labelled',0))+' / '+str(state.get('reference_total',210)))+'. Pilot: '+h(state.get('pilot_state','not started'))+'.</p>'
        reference_progress=audit/'reference-progress-sources.json'
        if reference_progress.is_file():
            parts=[];scored=0;expected=0
            for item in json.loads(reference_progress.read_text()):
                path=(audit/item['results']).resolve()
                if not path.is_relative_to(audit):raise ValueError('Reference progress outside audit folder')
                count=len(json.loads(path.read_text())) if path.is_file() else 0
                scored+=count;expected+=item['total'];parts.append(item['label']+': '+str(count)+' / '+str(item['total']))
            html+='<p>Pilot decisions scored: <strong>'+h(str(scored)+' / '+str(expected))+'</strong> ('+h('; '.join(parts))+').</p>'
        if state.get('pilot_summary'):html+='<pre>'+h(json.dumps(state['pilot_summary'],indent=2))+'</pre>'
        links=[]
        for name,label in [('validation-review.html','Earlier failed validation comparisons'),('pilot-review.html','Pilot comparisons'),('pilot-validation.json','Pilot validation'),('reference-validation.json','Reference checks'),('source-only-pilot/qualified-validation.json','Source eligibility pilot'),('pilot-spot-check/native-spot-check.json','Full-resolution spot check'),('selection-policy.json','Selection policy'),('source-integrity.json','Original integrity verification'),('RUNBOOK.md','Monitoring and recovery instructions')]:
            if (audit/name).is_file():links.append('<a href="'+h((audit/name).as_uri())+'">'+h(label)+'</a>')
        if links:html+='<p>'+' | '.join(links)+'</p>'
        if (audit/'source-integrity.json').is_file():
            integrity=json.loads((audit/'source-integrity.json').read_text())
            if integrity.get('state')=='verified':html+='<p>Original integrity: <strong>'+h(f"{integrity['originals_hash_verified']:,} image hashes verified")+'</strong>; original media CSV unchanged.</p>'
    html+='<p>Pixel and hash checks: <strong>'+h(f"{state['metrics_complete']:,} / {state['total']:,}")+'</strong>. Background classifications: '+h(f"{state['classified']:,}")+'.</p>'
    if 'product_reviews' in state:html+='<p>Individual product checks: <strong>'+h(f"{state['product_reviews']:,}")+'</strong>. '+('Every approved processed image requires an individual original/candidate review. Full processing starts only after pilot validation.' if state.get('audit_kind')=='calibrated' else 'Uncertain cutouts keep their originals. The background rules remain strict, so many otherwise valid studio shots may keep their originals.')+'</p>'
    if state.get('phase_total'):html+='<p>Current review pass: '+h(f"{state['phase_done']:,} / {state['phase_total']:,}")+'; estimate: '+h(date(state.get('eta_at')))+'.</p>'
    if state.get('estimated_complete_at') and not report:html+='<p>Estimated full selection ready: <strong>'+h(date(state['estimated_complete_at']))+'</strong>. '+h(state.get('estimate_basis',''))+'</p>'
    if mini:html+='<p>Eligible shots on the Mini: '+h(str(mini.get('done',0))+' / '+str(mini.get('total',0)))+'; '+h(mini.get('state'))+('' if mini.get('state') in TERMINAL else '; estimate: '+h(date(mini.get('eta_at'))))+'.</p>'
    html+='<p>Audit progress recorded: '+h(date(state['updated_at']))+'. Monitor checked: '+h(date(time.time()))+'.</p>'
    if audit_issues:html+='<p>Needs attention: '+h('; '.join(audit_issues))+'</p>'
    html+='</section><section><h2>'+('Verified selection' if report else 'Provisional selection')+'</h2><pre>'+h(json.dumps(report['counts'] if report else state['decisions'],indent=2))+'</pre><p>Original source images remain intact. Catalog import and publication have not been performed.</p>'
    if report:html+='<p><a href="'+h(Path(report['selected_media']).parent.as_uri())+'">Selected media folder</a> | <a href="'+h((audit/'selection.csv').as_uri())+'">Image selection CSV</a> | <a href="'+h((audit/'verification.json').as_uri())+'">Verification report</a></p>'
    html+='</section>'
    if state.get('audit_kind')=='calibrated' and (audit/'audit.sqlite3').is_file():
        try:
            with sqlite3.connect((audit/'audit.sqlite3').as_uri()+'?mode=ro',uri=True,timeout=5) as db:
                samples=[]
                for decision in ('white','original'):
                    samples.extend(db.execute("SELECT i.row_json,i.decision,i.reason,r.review,r.details FROM images i JOIN calibrated_reviews r ON i.file=r.file WHERE r.kind='pair' AND i.decision=? ORDER BY r.reviewed_at DESC LIMIT 4",(decision,)).fetchall())
            if samples:
                html+='<section><h2>Latest reviewed comparisons</h2><p>Original on the left; processed candidate on the right. Rejected candidates remain visible here for comparison. Their originals are retained in the selection.</p>'
                originals=Path(json.loads((job/'manifest.json').read_text())['originals'])
                for row_json,decision,reason,review,details in samples:
                    row=json.loads(row_json);candidate=Path(row.get('output_path') or job/'media/wands-expanded'/row['output_file'])
                    explanation=json.loads(review)['reason']
                    if decision=='original' and reason=='uncertain_individual_review':
                        confidence=json.loads(review)['confidence']
                        explanation=f'Review confidence {confidence:.0%}, below the required 95%: '+explanation
                    focused=json.loads(details or '{}').get('focus',{}).get('reviews',[])
                    if decision=='original':
                        for item in focused:
                            if item['review']['verdict']!='safe_background' or item['review']['confidence']<.95:
                                explanation=item['review']['reason'];break
                    html+='<article><p><strong>'+h('Use white JPG' if decision=='white' else 'Keep original')+'</strong>: '+h(explanation)+'</p><a href="'+h((originals/row['file']).as_uri())+'"><img src="'+h((originals/row['file']).as_uri())+'" alt="Original"></a> <a href="'+h(candidate.as_uri())+'"><img src="'+h(candidate.as_uri())+'" alt="Processed candidate"></a><p><small>'+h(row['file'])+'</small></p></article>'
                html+='</section>'
        except sqlite3.OperationalError:pass
    html+='<section><h2>New mirror replacements</h2>'
    for n in (1,2):html+='<img src="'+h((job/f'audit-20261017/replacements/mirror-{n:02d}.jpg').as_uri())+'" alt="New mirror on white background">'
    html+='</section></html>'
    temporary=job/'status.html.tmp';temporary.write_text(html);os.replace(temporary,job/'status.html')
    marker=audit/'notification-state.json'
    previous=json.loads(marker.read_text()) if marker.exists() else {}
    alert='complete' if report else 'needs_attention' if audit_issues or phase=='needs_attention' else None
    if not alert and previous.get('alert'):atomic_json(marker,{'alert':None,'cleared_at':time.time()})
    if alert and previous.get('alert')!=alert:
        message='Audited catalog selection is complete and verified. Originals are preserved.' if report else 'Catalog audit needs attention: '+'; '.join(audit_issues)[:160]
        event={'time':time.time(),'message':message,'notification':notify(message) if do_notify else {'disabled':True}}
        with (job/'alerts.jsonl').open('a') as stream:stream.write(json.dumps(event)+'\n')
        atomic_json(marker,{'alert':alert,'event':event})
    print('Audit: '+heading,flush=True)
    print(f"Images checked: {state['metrics_complete']:,} / {state['total']:,}; scene checks: {state['classified']:,}",flush=True)
    if state.get('phase_total'):print(f"Current review: {state['phase_done']:,} / {state['phase_total']:,}; ETA {date(state.get('eta_at'))}",flush=True)
    print('Selection: '+json.dumps(report['counts'] if report else state['decisions']),flush=True)
    if mini:print(f"Mini eligible shots: {mini.get('done',0):,} / {mini.get('total',0):,}; {mini.get('state')}"+('' if mini.get('state') in TERMINAL else '; ETA '+date(mini.get('eta_at'))),flush=True)
    return {'worker_state':'complete' if report else phase,'completion_verified':report,'issues':audit_issues}


def check(job, do_notify=True, mirror=True):
    job = job.resolve()
    if (job/'audit-active.json').exists():
        with (job/'monitor.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                print('A monitor refresh is already running.');return {'worker_state':'monitor_busy','issues':[]}
            return check_audit(job,json.loads((job/'audit-active.json').read_text()),do_notify)
    config = json.loads((job / "monitor-config.json").read_text())
    previous_path = job / "monitor-state.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    snapshot = None
    if (job / "status.json").exists():
        snapshot = json.loads((job / "status.json").read_text())
    monitor = {**previous, "checked_at": time.time(), "issues": [], "remote_ok": False}
    with (job / "monitor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            command = shlex.join([config["remote_python"], config["remote_worker"], "status", "--job", config["remote_job"], "--json"])
            result = subprocess.run(["/usr/bin/ssh", *SSH_OPTIONS, config["target"], command],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=45)
            if result.returncode:
                raise RuntimeError("Cannot read Mini status: " + result.stderr.strip()[:400])
            snapshot = json.loads(result.stdout)
            if snapshot["manifest_sha256"] != config["manifest_sha256"] or snapshot["encoding"]["quality"] != 90:
                raise ValueError("Remote job identity does not match this monitor")
            atomic_json(job / "status.json", snapshot)
            monitor["remote_ok"] = True
            monitor["issues"] = issues(snapshot, time.time())
            if mirror:
                (job / "media").mkdir(exist_ok=True)
                rsync = ["/usr/bin/rsync", "-rt", "--partial", "--delay-updates", "--exclude=.*", "-e",
                         shlex.join(["/usr/bin/ssh", *SSH_OPTIONS]),
                         config["target"] + ":" + config["remote_job"] + "/media/", str(job / "media") + "/"]
                copied = subprocess.run(rsync, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
                if copied.returncode:
                    raise RuntimeError("Local JPG copy failed: " + copied.stderr.strip()[:400])
                monitor["mirror_state"] = "up to date at last check"
                monitor["last_mirrored_at"] = time.time()
                if snapshot["state"] in TERMINAL:
                    mapping = subprocess.run(["/usr/bin/ssh", *SSH_OPTIONS, config["target"],
                                              shlex.join(["cat", config["remote_job"] + "/mapping.csv"])],
                                             stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
                    if mapping.returncode:
                        raise RuntimeError("Cannot retrieve the completed image mapping")
                    temporary = job / "mapping.csv.tmp"
                    temporary.write_bytes(mapping.stdout)
                    os.replace(temporary, job / "mapping.csv")
                    if not monitor.get("completion_verified"):
                        monitor["completion_verified"] = verify_completed_copy(job, config, snapshot)
                    monitor["mirror_state"] = "completed copy verified against content hashes"
            monitor["last_remote_ok_at"] = time.time()
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            monitor["issues"].append(str(error))
            if not monitor["remote_ok"]:
                monitor["mirror_state"] = "waiting for connection to the Mini"
        state = snapshot["state"] if snapshot else "unreachable"
        monitor["worker_state"] = state
        fingerprint = json.dumps({"issues": monitor["issues"], "terminal": state if state in TERMINAL else None}, sort_keys=True)
        previous_fingerprint = previous.get("alert_fingerprint")
        if fingerprint != previous_fingerprint:
            message = None
            if monitor["issues"]:
                message = "; ".join(monitor["issues"])[:240]
            elif state in TERMINAL:
                message = f"Finished: {snapshot['done']:,}/{snapshot['total']:,} JPGs. {snapshot['failed']:,} errors. Local candidates are ready for review."
            elif previous.get("issues"):
                message = "The Mini is processing normally again."
            if message:
                event = {"time": time.time(), "message": message, "notification": notify(message) if do_notify else {"disabled": True}}
                with (job / "alerts.jsonl").open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
                monitor["last_alert"] = event
            monitor["alert_fingerprint"] = fingerprint
        if snapshot and snapshot["restarts"] > previous.get("worker_restarts", snapshot["restarts"]):
            message = f"The Mini worker restarted and resumed from its checkpoint ({snapshot['done']:,} finished)."
            event = {"time": time.time(), "message": message, "notification": notify(message) if do_notify else {"disabled": True}}
            with (job / "alerts.jsonl").open("a") as stream:
                stream.write(json.dumps(event) + "\n")
            monitor["last_alert"] = event
        if snapshot:
            monitor["worker_restarts"] = snapshot["restarts"]
        atomic_json(previous_path, monitor)
        dashboard(job, config, snapshot, monitor)
        print(pretty_status(snapshot) if snapshot else "No remote status available")
        print("Monitor: " + ("; ".join(monitor["issues"]) if monitor["issues"] else "healthy"))
        return monitor


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True, type=Path)
    p.add_argument("--no-notify", action="store_true")
    p.add_argument("--no-mirror", action="store_true")
    a = p.parse_args()
    result = check(a.job, not a.no_notify, not a.no_mirror)
    config = json.loads((a.job / "monitor-config.json").read_text())
    label = config.get("monitor_label")
    # Retain all results and the saved plist in the job folder, then retire only
    # our own scheduled agent after the completed local copy has been verified.
    if result.get("completion_verified") and result.get("worker_state") in TERMINAL and label and os.environ.get("XPC_SERVICE_NAME") == label:
        print("Completed copy verified; retiring the scheduled monitor.", flush=True)
        plist = Path.home() / "Library" / "LaunchAgents" / (label + ".plist")
        plist.unlink(missing_ok=True)
        subprocess.run(["/bin/launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True)


if __name__ == "__main__":
    main()
