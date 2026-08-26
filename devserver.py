"""로컬 개발 서버 — Vercel 없이 프론트와 api/ 를 함께 띄운다.

    python3 devserver.py        # http://127.0.0.1:8787

배포에는 쓰이지 않는다. Vercel은 api/*.py 를 서버리스 함수로,
나머지를 정적 파일로 알아서 처리한다.
"""
import importlib.util
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "api" / "_lib"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "api" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ENDPOINTS = {"/api/chat": load("chat"), "/api/travel": load("travel")}


class Dev(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def do_POST(self):
        mod = ENDPOINTS.get(self.path)
        if mod is None:
            return self.send_error(404)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            result = mod.handle(body)
            code = 400 if result.get("error") else 200
        except Exception as e:                                   # noqa: BLE001
            result, code = {"error": type(e).__name__, "message": str(e)}, 500
        raw = json.dumps(result, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"  {self.command} {self.path}\n")


if __name__ == "__main__":
    print("http://127.0.0.1:8787 — Ctrl+C로 종료")
    HTTPServer(("127.0.0.1", 8787), Dev).serve_forever()
