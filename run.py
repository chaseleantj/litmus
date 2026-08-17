"""Litmus — build the frontend if stale, serve it, open the browser.

    litmus                # one process on http://127.0.0.1:8000, opens the browser
    litmus --no-browser   # same, but headless — for agents and scripts
    litmus --dev          # vite dev server (HMR) on :5173 + backend on :8000
"""

import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
FRONTEND = APP_DIR / "frontend"
DIST = FRONTEND / "dist"
PORT = 8000
DEV_PORT = 5173

NPM = "npm.cmd" if sys.platform == "win32" else "npm"


def newest_mtime(path: Path) -> float:
    return max((f.stat().st_mtime for f in path.rglob("*") if f.is_file()), default=0.0)


def frontend_is_stale() -> bool:
    if not (DIST / "index.html").exists():
        return True
    sources = [FRONTEND / "src", FRONTEND / "index.html", FRONTEND / "package.json"]
    newest_src = max(
        newest_mtime(p) if p.is_dir() else p.stat().st_mtime
        for p in sources
        if p.exists()
    )
    return newest_src > newest_mtime(DIST)


def ensure_node_modules() -> None:
    if not (FRONTEND / "node_modules").is_dir():
        print("Installing frontend dependencies...")
        subprocess.run([NPM, "ci"], cwd=FRONTEND, check=True)


def build_frontend() -> None:
    print("Building frontend...")
    subprocess.run([NPM, "run", "build"], cwd=FRONTEND, check=True)


def open_when_ready(url: str, health: str) -> None:
    """Poll until the server answers, then open the browser once."""
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            urllib.request.urlopen(health, timeout=1)
            webbrowser.open(url)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    print(f"Server did not come up in time; open {url} manually.")


def run_prod(open_browser: bool) -> None:
    ensure_node_modules()
    if frontend_is_stale():
        build_frontend()
    url = f"http://127.0.0.1:{PORT}"
    if open_browser:
        threading.Thread(
            target=open_when_ready, args=(url, f"{url}/api/health"), daemon=True
        ).start()
    print(f"Serving on {url}  (Ctrl+C to stop)")
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=APP_DIR / "backend",
    )


def run_dev(open_browser: bool) -> None:
    ensure_node_modules()
    url = f"http://127.0.0.1:{DEV_PORT}"
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--reload"],
        cwd=APP_DIR / "backend",
    )
    if open_browser:
        threading.Thread(
            target=open_when_ready, args=(url, f"http://127.0.0.1:{PORT}/api/health"), daemon=True
        ).start()
    print(f"Dev server on {url}  (Ctrl+C to stop)")
    try:
        # Pass the port through rather than trusting vite.config.ts to agree
        # with DEV_PORT — otherwise the browser opens on the wrong one.
        subprocess.run([NPM, "run", "dev", "--", "--port", str(DEV_PORT)], cwd=FRONTEND)
    finally:
        backend.terminate()


if __name__ == "__main__":
    open_browser = "--no-browser" not in sys.argv
    try:
        run_dev(open_browser) if "--dev" in sys.argv else run_prod(open_browser)
    except KeyboardInterrupt:
        pass
