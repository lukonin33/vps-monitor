"""
RU-side external probe for VPS 5.129.207.254 stability monitoring.
Runs as Yandex Cloud Function on timer trigger every 5 min.
Probes 4 plyeyada domains + SSH22 + TCP443, commits CSV to logs/probes-ru.csv
in github.com/lukonin33/vps-monitor via Contents API.

chat-id: infra-vps-stability-monitoring-01
task-id: vps-stability-diagnostic-monitoring-2026-05-09

Env vars required:
  GITHUB_TOKEN — fine-grained PAT, scope: lukonin33/vps-monitor → Contents R/W
  GITHUB_REPO  — lukonin33/vps-monitor (default)
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

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "lukonin33/vps-monitor")
CSV_PATH = "logs/probes-ru.csv"


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


def run_all_probes() -> dict[str, str]:
    """Run all 6 probes in parallel. Worst-case wall = max(HTTP_TIMEOUT, TCP_TIMEOUT) ~ 5s."""
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        http_futures = {name: ex.submit(probe_http, url) for name, url in DOMAINS.items()}
        tcp_futures = {name: ex.submit(probe_tcp, VPS_IP, port) for name, port in TCP_PORTS.items()}
        for name, fut in http_futures.items():
            results[name] = fut.result()
        for name, fut in tcp_futures.items():
            results[name] = fut.result()
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


def handler(event, context):
    if not GITHUB_TOKEN:
        return {"statusCode": 500, "body": "GITHUB_TOKEN env var not set"}

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = run_all_probes()

    # Stable column order: same as DOMAINS + TCP_PORTS for human readability
    ordered_keys = list(DOMAINS.keys()) + list(TCP_PORTS.keys())
    line = f"{ts}," + ",".join(f"{k}={results[k]}" for k in ordered_keys)

    # Commit to GitHub. Retry with fresh sha if 409 (race with another invocation).
    for attempt in range(3):
        try:
            sha, current = github_get_file(GITHUB_TOKEN, GITHUB_REPO, CSV_PATH)
            new_content = current + line + "\n" if current else line + "\n"
            github_put_file(
                GITHUB_TOKEN, GITHUB_REPO, CSV_PATH, new_content, sha,
                message=f"ru-probe {line}",
            )
            return {"statusCode": 200, "body": line}
        except urllib.error.HTTPError as e:
            if e.code == 409 and attempt < 2:
                continue
            return {"statusCode": e.code, "body": f"github error: {e.code} {e.reason}"}
        except Exception as e:
            return {"statusCode": 500, "body": f"exception: {type(e).__name__}: {e}"}

    return {"statusCode": 500, "body": "unreachable"}
