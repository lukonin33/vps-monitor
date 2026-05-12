"""
RU-side external probe for VPS 5.129.207.254 stability monitoring.
Runs as Yandex Cloud Function on timer trigger every 5 min.
Probes 4 plyeyada domains + SSH22 + TCP443, commits CSV to logs/probes-ru.csv
in github.com/lukonin33/vps-monitor via Contents API.

Optional: when VPS_CANDIDATE_IPS env var is set (comma-separated list of IPs),
also probes each candidate via TCP 22 + TCP 443 and commits to a separate
file logs/probes-candidates.csv. Used for Phase 6.5 — testing new IPs before
migrating DNS off the old one.

GitHub PAT is read from Yandex Lockbox at runtime (cached in-memory across
warm invocations). This prevents PAT loss on every CLI redeploy
(YC env block is immutable per version).

chat-id: infra-vps-stability-monitoring-01
task-id: vps-stability-diagnostic-monitoring-2026-05-09

Env vars:
  LOCKBOX_SECRET_ID  — ID of Lockbox secret containing key 'github_token' (required)
  GITHUB_REPO        — lukonin33/vps-monitor (default)
  VPS_CANDIDATE_IPS  — comma-separated extra IPs to probe (e.g. "5.129.X.Y,31.130.X.Y"). Empty = skip.

IAM permissions required for service account:
  lockbox.payloadViewer — on the specific Lockbox secret (granted via add-access-binding)
"""
import base64
import datetime
import json
import os
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

VPS_IP = "5.129.207.254"
DOMAINS = {
    "zavod": "https://zavod.smm-ministr.ru/",
    "survey": "https://survey.smm-ministr.ru/",
    "brand": "https://brand.smm-ministr.ru/",
    "smm": "https://krutly.com/",
}
TCP_PORTS = {"ssh22": 22, "tcp443": 443}
HTTP_TIMEOUT = 5
TCP_TIMEOUT = 3

LOCKBOX_SECRET_ID = os.environ.get("LOCKBOX_SECRET_ID")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "lukonin33/vps-monitor")
CSV_PATH_MAIN = "logs/probes-ru.csv"
CSV_PATH_CANDIDATES = "logs/probes-candidates.csv"

# Module-level cache — warm container retains across invocations (~5 min)
_cached_github_token: str | None = None


def get_iam_token() -> str:
    """Fetch IAM token for current service account from YC metadata service.
    YC injects this endpoint for any function/VM with SA attached."""
    url = "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token"
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())["access_token"]


def get_lockbox_secret(secret_id: str, key: str) -> str:
    """Fetch a specific key from Lockbox secret payload."""
    iam_token = get_iam_token()
    url = f"https://payload.lockbox.api.cloud.yandex.net/lockbox/v1/secrets/{secret_id}/payload"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {iam_token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read())
    for entry in payload.get("entries", []):
        if entry.get("key") == key:
            return entry.get("textValue", "")
    raise KeyError(f"Key '{key}' not found in Lockbox secret {secret_id}")


def get_github_token() -> str:
    """Return cached GitHub PAT or fetch from Lockbox on cold start."""
    global _cached_github_token
    if _cached_github_token is None:
        if not LOCKBOX_SECRET_ID:
            raise RuntimeError("LOCKBOX_SECRET_ID env var not set")
        _cached_github_token = get_lockbox_secret(LOCKBOX_SECRET_ID, "github_token")
    return _cached_github_token


def parse_candidate_ips() -> list[str]:
    """Read VPS_CANDIDATE_IPS env, return list of cleaned IPs (drops empty/whitespace)."""
    raw = os.environ.get("VPS_CANDIDATE_IPS", "")
    return [ip.strip() for ip in raw.split(",") if ip.strip()]


def probe_http(url: str) -> str:
    """HTTP HEAD probe. Returns code as str or 'TIMEOUT'/'ERR_*'."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except (urllib.error.URLError, socket.timeout, TimeoutError):
        return "TIMEOUT"
    except Exception as e:
        return f"ERR_{type(e).__name__}"


def probe_tcp(host: str, port: int) -> str:
    """TCP connect probe. Returns 'OK' or 'FAIL'."""
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT):
            return "OK"
    except (socket.timeout, socket.gaierror, ConnectionRefusedError, OSError):
        return "FAIL"


def run_main_probes() -> dict[str, str]:
    """Probe 4 HTTPS domains + 2 TCP ports on current VPS in parallel."""
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        http_futures = {name: ex.submit(probe_http, url) for name, url in DOMAINS.items()}
        tcp_futures = {name: ex.submit(probe_tcp, VPS_IP, port) for name, port in TCP_PORTS.items()}
        for name, fut in http_futures.items():
            results[name] = fut.result()
        for name, fut in tcp_futures.items():
            results[name] = fut.result()
    return results


def run_candidate_probes(ips: list[str]) -> dict[str, str]:
    """For each candidate IP, probe TCP 22 + TCP 443 in parallel. Returns dict keyed by '<ip>_<port>'."""
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(2 * len(ips), 2)) as ex:
        futures = {}
        for ip in ips:
            futures[f"{ip}_22"] = ex.submit(probe_tcp, ip, 22)
            futures[f"{ip}_443"] = ex.submit(probe_tcp, ip, 443)
        for key, fut in futures.items():
            results[key] = fut.result()
    return results


def github_get_file(token: str, repo: str, path: str):
    """GET file via Contents API. Returns (sha, content_str) or (None, '')."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            content = base64.b64decode(data["content"]).decode("utf-8")
            return data["sha"], content
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, ""
        raise


def github_put_file(token: str, repo: str, path: str, new_content: str, sha: str | None, message: str):
    """PUT file via Contents API. sha=None creates new file."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    body = {
        "message": message,
        "content": base64.b64encode(new_content.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status


def commit_csv_line(token: str, repo: str, path: str, line: str, commit_msg: str) -> None:
    """Append line to CSV file in repo, retry on 409 race. Raises on persistent failure."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            sha, current = github_get_file(token, repo, path)
            new_content = current + line + "\n" if current else line + "\n"
            github_put_file(token, repo, path, new_content, sha, message=commit_msg)
            return
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 409 and attempt < 2:
                continue
            raise
    if last_error:
        raise last_error


def handler(event, context):
    try:
        github_token = get_github_token()
    except Exception as e:
        return {"statusCode": 500, "body": f"token fetch failed: {type(e).__name__}: {e}"}

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate_ips = parse_candidate_ips()

    # --- Main probe (existing schema, dashboard compat) ---
    main_results = run_main_probes()
    main_keys = list(DOMAINS.keys()) + list(TCP_PORTS.keys())
    main_line = f"{ts}," + ",".join(f"{k}={main_results[k]}" for k in main_keys)

    # --- Candidate probe (only if VPS_CANDIDATE_IPS is set) ---
    candidate_line: str | None = None
    if candidate_ips:
        cand_results = run_candidate_probes(candidate_ips)
        # Stable column order: for each IP, port 22 then port 443
        parts = [f"ips={'|'.join(candidate_ips)}"]
        for ip in candidate_ips:
            parts.append(f"{ip}_22={cand_results[f'{ip}_22']}")
            parts.append(f"{ip}_443={cand_results[f'{ip}_443']}")
        candidate_line = f"{ts}," + ",".join(parts)

    # --- Commit both (separate files, separate commits) ---
    bodies = []
    try:
        commit_csv_line(github_token, GITHUB_REPO, CSV_PATH_MAIN, main_line, f"ru-probe {main_line}")
        bodies.append(f"main: {main_line}")
    except urllib.error.HTTPError as e:
        return {"statusCode": e.code, "body": f"github main error: {e.code} {e.reason}"}
    except Exception as e:
        return {"statusCode": 500, "body": f"main exception: {type(e).__name__}: {e}"}

    if candidate_line:
        try:
            commit_csv_line(github_token, GITHUB_REPO, CSV_PATH_CANDIDATES, candidate_line, f"cand-probe {candidate_line}")
            bodies.append(f"candidates: {candidate_line}")
        except urllib.error.HTTPError as e:
            # Don't fail the whole invocation if candidate write fails
            bodies.append(f"candidates failed: github {e.code} {e.reason}")
        except Exception as e:
            bodies.append(f"candidates failed: {type(e).__name__}: {e}")

    return {"statusCode": 200, "body": " | ".join(bodies)}
