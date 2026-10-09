#!/usr/bin/env python3
"""Sedna Ops host runner — runs whitelisted aws-util scripts on this Mac on
behalf of the Sedna Ops backend.

Why a separate process: the backend runs in Docker, but everything these
scripts need lives on the host — the AWS CLI and its SSO session cache
(~/.aws), git + GitLab credentials, and the ~/environments repos. Proven in
the sedna-dev hypothesis test (H1–H4). Credentials never leave this Mac;
the backend only ever sees job status and log lines.

Safety rules:
  - Binds to 127.0.0.1 only (Docker Desktop's host.docker.internal still
    reaches it; nothing else on the network can).
  - Every request needs the shared X-Runner-Token from runner.env.
  - Only the job types in JOBS can run, with validated arguments — there is
    no "run this command" endpoint.
  - One non-dry-run upgrade per environment at a time.

Stdlib only (macOS ships Python 3.9). Start with:
    python3 runner/sedna_runner.py
Config: runner/runner.env (git-ignored) — see runner.env.example.
"""
import hmac
import json
import os
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "logs"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SSO_PROBE_PROFILE = "ecr-profile"  # always present; shares the SSO session with every env profile
MAX_LOG_LINES = 20000


def _load_env_file(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


CONFIG = _load_env_file(HERE / "runner.env")
TOKEN = CONFIG.get("RUNNER_TOKEN", "")
PORT = int(CONFIG.get("RUNNER_PORT", "8765"))
AWS_UTIL_DIR = Path(os.path.expanduser(CONFIG.get("AWS_UTIL_DIR", "~/aws-util")))
ENVIRONMENTS_DIR = AWS_UTIL_DIR.parent / "environments"  # same derivation as upgrade_environment.sh


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _subprocess_env() -> dict:
    env = dict(os.environ)
    extra = ["/usr/local/bin", "/opt/homebrew/bin", os.path.expanduser("~/.fzf/bin")]
    env["PATH"] = ":".join(extra + [env.get("PATH", "/usr/bin:/bin")])
    env["AWS_SCRIPTS_DIR"] = str(AWS_UTIL_DIR)
    if CONFIG.get("GITLAB_TOKEN"):
        env["GITLAB_TOKEN"] = CONFIG["GITLAB_TOKEN"]
    return env


def _redact(line: str) -> str:
    secret = CONFIG.get("GITLAB_TOKEN")
    return line.replace(secret, "<GITLAB_TOKEN>") if secret else line


# ── GitLab token check ───────────────────────────────────────────────────
# upgrade_environment.sh pushes with your SSH key but only uses the token
# *after* the push (find/watch the pipeline, cancel Terraform) — so a bad
# token would fail mid-upgrade with the version change already pushed.
# Checked up front instead: GitLab's "who am I" for tokens, read-only.
GITLAB_API = "https://gitlab.com/api/v4"
GITLAB_CHECK_TTL = 3600  # seconds — one GitLab call per hour at most
_gitlab_cache: dict = {"at": 0.0, "result": None}


def gitlab_token_cached() -> dict:
    """Last check result for the status card — never calls GitLab."""
    if not CONFIG.get("GITLAB_TOKEN"):
        return {"set": False, "ok": False, "reason": "GITLAB_TOKEN not set in runner.env"}
    if _gitlab_cache["result"] and time.time() - _gitlab_cache["at"] < GITLAB_CHECK_TTL:
        return _gitlab_cache["result"]
    return {"set": True, "ok": None, "reason": "not checked yet — checked when a real upgrade starts"}


def gitlab_token_status(force: bool = False) -> dict:
    """Live check — only called when a real upgrade is invoked (reuses a
    result from the last hour)."""
    token = CONFIG.get("GITLAB_TOKEN")
    if not token:
        return {"set": False, "ok": False, "reason": "GITLAB_TOKEN not set in runner.env"}
    if not force and _gitlab_cache["result"] and time.time() - _gitlab_cache["at"] < GITLAB_CHECK_TTL:
        return _gitlab_cache["result"]
    req = urllib.request.Request(f"{GITLAB_API}/personal_access_tokens/self", headers={"PRIVATE-TOKEN": token})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            info = json.loads(resp.read().decode())
        scopes = info.get("scopes") or []
        ok = bool(info.get("active")) and not info.get("revoked") and "api" in scopes
        reason = None if ok else ("token lacks the 'api' scope" if "api" not in scopes else "token is inactive or revoked")
        result = {"set": True, "ok": ok, "name": info.get("name"), "scopes": scopes,
                  "expires_at": info.get("expires_at"), "reason": reason}
    except urllib.error.HTTPError as exc:
        result = {"set": True, "ok": False, "reason": "GitLab rejected the token (invalid or expired)" if exc.code == 401 else f"GitLab returned HTTP {exc.code}"}
    except Exception as exc:  # offline etc. — unknown, not proven bad
        return {"set": True, "ok": None, "reason": f"couldn't reach GitLab: {str(exc)[:120]}"}
    _gitlab_cache.update(at=time.time(), result=result)
    return result


# ── Environments ─────────────────────────────────────────────────────────

def read_environments() -> list:
    """environments.txt: <name> <account> <region> <version>. The account
    id is deliberately not returned — the backend has no use for it."""
    path = AWS_UTIL_DIR / "environments.txt"
    envs = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 3 or line.startswith("#"):
            continue
        name, region = parts[0], parts[2]
        listed = parts[3] if len(parts) > 3 else None
        ci = ENVIRONMENTS_DIR / name / "docker" / ".gitlab-ci.yml"
        repo_version = None
        if ci.exists():
            m = re.search(r'VERSION:\s*"([^"]*)"', ci.read_text())
            repo_version = m.group(1) if m else None
        envs.append({
            "name": name, "region": region, "listed_version": listed,
            "repo_version": repo_version, "repo_present": ci.exists(),
        })
    return envs


def env_names() -> set:
    return {e["name"] for e in read_environments()}


# ── SSO ──────────────────────────────────────────────────────────────────

def sso_status() -> dict:
    try:
        r = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", SSO_PROBE_PROFILE, "--output", "json"],
            capture_output=True, text=True, timeout=25, env=_subprocess_env(), stdin=subprocess.DEVNULL,
        )
        valid = r.returncode == 0
        arn = json.loads(r.stdout).get("Arn") if valid else None
        error = None if valid else (r.stderr.strip().splitlines() or ["SSO check failed"])[-1][:300]
    except Exception as exc:  # aws missing, timeout, …
        valid, arn, error = False, None, str(exc)[:300]
    expires_at = None
    cache = Path.home() / ".aws" / "sso" / "cache"
    if cache.exists():
        for f in sorted(cache.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            if "accessToken" in data and data.get("expiresAt"):
                expires_at = data["expiresAt"]  # never return the token itself
                break
    who = arn.split("/")[-1] if arn else None
    return {"valid": valid, "identity": who, "expires_at": expires_at, "error": error}


# ── GitLab pipeline status (read-only) ───────────────────────────────────
# The same chain upgrade_environment.sh's watch_gitlab_pipelines() follows
# (parent pipeline → "docker" bridge → downstream pipeline →
# build_customer_image job; "terraform" bridge noted) — but read-only: it
# never cancels or triggers anything. Needed because that watch crashes on
# macOS bash 3.2, leaving nothing to say when the image is actually built
# (force-deploying before then restarts the OLD image — confirmed 2026-10-09).
GITLAB_GROUP = "dataloy-developers"
_typical_build: dict = {}


def _gl(path: str):
    req = urllib.request.Request(f"{GITLAB_API}{path}", headers={"PRIVATE-TOKEN": CONFIG.get("GITLAB_TOKEN", "")})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def pipeline_status(env: str, pipeline_id: str) -> dict:
    if env not in env_names():
        raise ValueError(f"Unknown environment: {env}")
    if not pipeline_id.isdigit():
        raise ValueError("pipeline id must be numeric")
    if not CONFIG.get("GITLAB_TOKEN"):
        return {"ok": False, "error": "GITLAB_TOKEN not set in runner.env"}
    try:
        project = _gl(f"/projects/{urllib.request.quote(f'{GITLAB_GROUP}/{env}', safe='')}")
        pid = project["id"]
        parent = _gl(f"/projects/{pid}/pipelines/{pipeline_id}")
        bridges = _gl(f"/projects/{pid}/pipelines/{pipeline_id}/bridges?per_page=100")
        if not bridges:  # same fallback as list_pipeline_bridges()
            bridges = [j for j in _gl(f"/projects/{pid}/pipelines/{pipeline_id}/jobs?per_page=100") if j.get("name") in ("docker", "terraform")]
        docker = next((b for b in bridges if b.get("name") == "docker"), None)
        terraform = next((b for b in bridges if b.get("name") == "terraform"), None)
        build = None
        child_id = (docker or {}).get("downstream_pipeline", {}) or {}
        child_id = child_id.get("id") if isinstance(child_id, dict) else None
        if child_id:
            jobs = _gl(f"/projects/{pid}/pipelines/{child_id}/jobs?per_page=100")
            j = next((x for x in jobs if x.get("name") == "build_customer_image"), None)
            if j:
                build = {k: j.get(k) for k in ("status", "started_at", "finished_at", "duration", "web_url")}
        # Typical successful build time for this project, for a progress estimate.
        if pid not in _typical_build:
            recent = _gl(f"/projects/{pid}/jobs?scope[]=success&per_page=100")
            durs = sorted(x["duration"] for x in recent if x.get("name") == "build_customer_image" and x.get("duration"))
            _typical_build[pid] = durs[len(durs) // 2] if durs else None
        return {
            "ok": True, "pipeline_id": int(pipeline_id), "web_url": parent.get("web_url"), "parent_status": parent.get("status"),
            "docker_status": (docker or {}).get("status"), "terraform_status": (terraform or {}).get("status"),
            "child_pipeline_id": child_id, "build": build, "typical_build_seconds": _typical_build.get(pid),
            "checked_at": now_iso(),
        }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"GitLab returned HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


# ── Deployment monitor ───────────────────────────────────────────────────

def deployment_snapshot(env: str) -> dict:
    """One refresh of aws-util's own monitor, in its own JSON mode:
    `ecs_deployment_monitor.sh --env NAME --json` — same AWS calls, same
    `stable` rule as the terminal view. The app polls this every 5s (the
    script's default interval) instead of the --watch loop that only ends
    on 'q'."""
    if env not in env_names():
        raise ValueError(f"Unknown environment: {env}")
    r = subprocess.run(
        ["bash", str(AWS_UTIL_DIR / "ecs_deployment_monitor.sh"), "--env", env, "--json"],
        capture_output=True, text=True, timeout=60, cwd=str(AWS_UTIL_DIR),
        env=_subprocess_env(), stdin=subprocess.DEVNULL,
    )
    out = r.stdout.strip()
    try:
        data = json.loads(out[out.index("{"):]) if "{" in out else {}
    except ValueError:
        data = {}
    if r.returncode != 0 or not data or "error" in data:
        err = data.get("error") or (r.stderr.strip().splitlines() or ["monitor failed"])[-1]
        return {"ok": False, "error": err[:300], "checked_at": now_iso()}
    return {"ok": True, "checked_at": now_iso(), **data}


# ── Jobs ─────────────────────────────────────────────────────────────────

class Job:
    def __init__(self, kind: str, args: dict, argv: list):
        self.id = uuid.uuid4().hex[:12]
        self.kind, self.args, self.argv = kind, args, argv
        self.status = "running"
        self.exit_code = None
        self.started_at, self.finished_at = now_iso(), None
        self.lines: list = []
        self.proc = None
        self.lock = threading.Lock()
        LOG_DIR.mkdir(exist_ok=True)
        self.log_path = LOG_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}-{self.id}.log"

    def add(self, text: str) -> None:
        text = _redact(text.rstrip("\n"))
        with self.lock:
            if len(self.lines) < MAX_LOG_LINES:
                self.lines.append({"ts": now_iso(), "text": text})
        with open(self.log_path, "a") as fh:
            fh.write(text + "\n")

    def view(self, since: int = 0) -> dict:
        with self.lock:
            return {
                "id": self.id, "kind": self.kind, "args": self.args, "status": self.status,
                "exit_code": self.exit_code, "started_at": self.started_at, "finished_at": self.finished_at,
                "line_count": len(self.lines), "lines": self.lines[since:],
            }


JOBS: dict = {}
JOBS_LOCK = threading.Lock()


def _build_argv(kind: str, args: dict) -> list:
    if kind == "upgrade_environment":
        env, version, dry = args.get("environment"), args.get("version"), bool(args.get("dry_run", True))
        if env not in env_names():
            raise ValueError(f"Unknown environment: {env}")
        if not isinstance(version, str) or not VERSION_RE.match(version):
            raise ValueError("version must look like X.Y.Z")
        if not dry:
            gl = gitlab_token_status()
            if not gl["set"]:
                raise ValueError("GITLAB_TOKEN is not set in runner.env — required for a real upgrade")
            if gl["ok"] is False:
                raise ValueError(f"GitLab token check failed: {gl['reason']} — fix it before a real upgrade")
        argv = ["bash", str(AWS_UTIL_DIR / "upgrade_environment.sh"), "--cmd", "--yes", "--no-monitor"]
        if dry:
            argv.append("--dry-run")
        return argv + [version, env]
    if kind == "ecr_tag_check":
        version = args.get("version")
        if not isinstance(version, str) or not VERSION_RE.match(version):
            raise ValueError("version must look like X.Y.Z")
        return ["bash", str(AWS_UTIL_DIR / "ecr_tag_check.sh"), version]
    if kind == "ecs_force_deploy":
        # aws-util's `awsforcedeploy` alias, using the script's own
        # non-interactive flags: --yes auto-selects the cluster/service
        # (select_cluster_auto/select_service_auto), --no-monitor skips the
        # tail that only ends on 'q'.
        env = args.get("environment")
        if env not in env_names():
            raise ValueError(f"Unknown environment: {env}")
        return ["bash", str(AWS_UTIL_DIR / "ecs_force_deploy.sh"), "--cmd", "--yes", "--no-monitor", env]
    if kind == "sso_login":
        # Opens the browser on this Mac for the user to approve.
        return ["aws", "sso", "login", "--profile", SSO_PROBE_PROFILE]
    raise ValueError(f"Unknown job type: {kind}")


def _run(job: Job) -> None:
    job.add(f"$ {' '.join(job.argv)}")
    try:
        job.proc = subprocess.Popen(
            job.argv, cwd=str(AWS_UTIL_DIR), env=_subprocess_env(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True,
        )
        for line in job.proc.stdout:
            job.add(line)
        job.exit_code = job.proc.wait()
        if job.status != "cancelled":
            job.status = "succeeded" if job.exit_code == 0 else "failed"
            if job.status == "failed" and job.kind == "upgrade_environment" and _known_watch_crash(job):
                job.status = "warning"
                job.add("[runner] ⚠ The version change was pushed and the GitLab pipeline started, then the script's "
                        "pipeline watch hit the known bash 3.2 arithmetic error in lib/gitlab-pipeline.sh "
                        "(it does the same in a terminal). Not a failed upgrade: once build_customer_image "
                        "has finished, run Force deploy (awsforcedeploy), and again if it doesn't take.")
    except Exception as exc:
        job.add(f"[runner] failed to start: {exc}")
        job.status, job.exit_code = "failed", -1
    job.finished_at = now_iso()
    job.add(f"[runner] finished: {job.status} (exit {job.exit_code})")


def _known_watch_crash(job: "Job") -> bool:
    """The one failure treated as a warning: push succeeded, pipeline found,
    then watch_gitlab_pipelines() died on bash 3.2's quoted-operand error."""
    text = "\n".join(line["text"] for line in job.lines)
    return ("main -> main" in text and "Found pipeline #" in text
            and "syntax error: operand expected" in text)


def start_job(kind: str, args: dict) -> Job:
    argv = _build_argv(kind, args)
    with JOBS_LOCK:
        if kind in ("upgrade_environment", "ecs_force_deploy") and not args.get("dry_run", False if kind == "ecs_force_deploy" else True):
            for j in JOBS.values():
                if (j.kind in ("upgrade_environment", "ecs_force_deploy") and j.status == "running"
                        and j.args.get("environment") == args.get("environment") and not j.args.get("dry_run", False)):
                    raise ValueError(f"{j.kind} for {args['environment']} is already running ({j.id})")
        job = Job(kind, args, argv)
        JOBS[job.id] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job


def cancel_job(job: Job) -> None:
    if job.proc and job.status == "running":
        job.status = "cancelled"
        job.add("[runner] cancel requested — sending SIGTERM to the script's process group")
        try:
            os.killpg(job.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


# ── HTTP ─────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "SednaRunner/1"

    def log_message(self, fmt, *args):  # keep the terminal readable
        print(f"[{datetime.now():%H:%M:%S}] {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}")

    def _send(self, code: int, body) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        given = self.headers.get("X-Runner-Token", "")
        if not TOKEN or not hmac.compare_digest(given, TOKEN):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def do_GET(self):
        if not self._authorized():
            return
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        try:
            if parts == ["health"]:
                return self._send(200, {
                    "ok": True, "aws_util_dir": str(AWS_UTIL_DIR), "aws_util_present": AWS_UTIL_DIR.exists(),
                    "gitlab_token_set": bool(CONFIG.get("GITLAB_TOKEN")), "time": now_iso(),
                    "gitlab": gitlab_token_cached(),
                })
            if parts == ["environments"]:
                return self._send(200, read_environments())
            if parts == ["sso"]:
                return self._send(200, sso_status())
            if len(parts) == 3 and parts[0] == "pipeline":
                return self._send(200, pipeline_status(parts[1], parts[2]))
            if len(parts) == 2 and parts[0] == "monitor":
                return self._send(200, deployment_snapshot(parts[1]))
            if len(parts) == 2 and parts[0] == "jobs":
                job = JOBS.get(parts[1])
                if not job:
                    return self._send(404, {"error": "job not found (runner may have restarted)"})
                since = int(parse_qs(url.query).get("since", ["0"])[0])
                return self._send(200, job.view(since))
            return self._send(404, {"error": "not found"})
        except Exception as exc:
            return self._send(500, {"error": str(exc)[:500]})

    def do_POST(self):
        if not self._authorized():
            return
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        try:
            if parts == ["jobs"]:
                body = self._body()
                job = start_job(body.get("kind", ""), body.get("args") or {})
                return self._send(201, job.view())
            if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel":
                job = JOBS.get(parts[1])
                if not job:
                    return self._send(404, {"error": "job not found"})
                cancel_job(job)
                return self._send(200, job.view(len(job.lines)))
            return self._send(404, {"error": "not found"})
        except ValueError as exc:
            return self._send(400, {"error": str(exc)})
        except Exception as exc:
            return self._send(500, {"error": str(exc)[:500]})


def main() -> None:
    if not TOKEN:
        raise SystemExit(f"RUNNER_TOKEN missing — create {HERE / 'runner.env'} (see runner.env.example)")
    if not (AWS_UTIL_DIR / "upgrade_environment.sh").exists():
        raise SystemExit(f"upgrade_environment.sh not found under {AWS_UTIL_DIR}")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Sedna runner listening on 127.0.0.1:{PORT} — aws-util: {AWS_UTIL_DIR} — "
          f"GITLAB_TOKEN {'set' if CONFIG.get('GITLAB_TOKEN') else 'NOT set (dry-runs only)'}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
