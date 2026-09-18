"""Local JSON HTTP API; bounded requests, no request logging or exposed keys."""
from __future__ import annotations

from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
import socket
import sqlite3
from pathlib import Path
import threading
from uuid import uuid4

from . import __version__
from .contracts import Brief
from .corpus import CorpusStore
from .feedback import FeedbackStore
from .lexicon import RhymeLexicon
from .meter import MeterSpec, analyze_meter
from .pipeline import LyricPipeline
from .prosody import analyze_text
from .settings import load_settings, make_provider


def make_handler(*, output_root, corpus_path=None, lexicon_path=None, feedback_path=None, config=None,
                 token=None, provider_factory=None):
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    settings = load_settings(config)
    busy = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version, sys_version = "TurkishLyricEngine", ""

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, fmt, *args):
            pass  # HTTP logs could contain secrets or private lyric data.

        def reply(self, code, value):
            data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if token and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.reply(401, {"error": "API authorization required"})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            if self.path != "/health":
                self.reply(404, {"error": "unknown endpoint"})
                return
            self.reply(200, {"status": "ok", "version": __version__, "corpus_supplied": corpus_path is not None,
                             "generation_model_configured": bool(settings["provider"].get("model") or os.environ.get("TLE_MODEL"))})

        def do_POST(self):
            if not self.authorized():
                return
            if self.path not in {"/analyze", "/generate", "/feedback", "/search"}:
                self.reply(404, {"error": "unknown endpoint"})
                return
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("chunked requests are not supported")
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 100_000:
                    self.reply(413, {"error": "body must be 1..100000 bytes"})
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("JSON body must be an object")
                if self.path == "/analyze":
                    if set(body) - {"text", "meter", "durak"}:
                        raise ValueError("unknown analyze field")
                    text = body["text"]
                    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
                        raise ValueError("text must be 1..20000 characters")
                    result = {"prosody": analyze_text(text), "meter": analyze_meter(text, MeterSpec(body.get("meter"), tuple(body["durak"]) if body.get("durak") else None))}
                elif self.path == "/search":
                    if set(body) - {"query", "limit"}:
                        raise ValueError("unknown search field")
                    if not corpus_path:
                        result = {"status": "no_corpus", "matches": []}
                    else:
                        with CorpusStore(corpus_path, create=False) as store:
                            result = store.search(body["query"], limit=body.get("limit", 10))
                elif self.path == "/feedback":
                    if not feedback_path:
                        raise ValueError("feedback database is not configured")
                    with FeedbackStore(feedback_path) as store:
                        result = {"feedback_id": store.add(**body), "preferences": store.preferences(body["genre"])}
                else:
                    if set(body) - (set(Brief.__dataclass_fields__) | {"seed"}):
                        raise ValueError("unknown generation field")
                    seed = body.pop("seed", 0)
                    values = {**settings["generation"], **body}
                    if values.get("durak"):
                        values["durak"] = tuple(values["durak"])
                    brief = Brief(**values)
                    if not busy.acquire(blocking=False):
                        self.reply(409, {"error": "another generation is running"})
                        return
                    try:
                        with ExitStack() as stack:
                            provider = provider_factory() if provider_factory else make_provider(settings["provider"])
                            judge = make_provider(settings["judge"]) if settings["judge"] else None
                            corpus = stack.enter_context(CorpusStore(corpus_path, create=False)) if corpus_path else None
                            feedback = stack.enter_context(FeedbackStore(feedback_path)) if feedback_path else None
                            lexicon = RhymeLexicon.from_file(lexicon_path) if lexicon_path else None
                            engine = LyricPipeline(provider, judge=judge, corpus=corpus, lexicon=lexicon, feedback=feedback)
                            result = engine.generate(brief, directory=root / uuid4().hex, seed=seed)
                    finally:
                        busy.release()
                self.reply(200, result)
            except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
                self.reply(400, {"error": str(exc)[:800]})

    return Handler


def serve(*, host="127.0.0.1", port=8765, **options):
    token = os.environ.get("TLE_SERVER_TOKEN")
    if host not in {"localhost", "127.0.0.1", "::1"} and not token:
        raise ValueError("non-loopback API binding requires TLE_SERVER_TOKEN")
    if not 1 <= port <= 65535:
        raise ValueError("invalid API port")
    handler = make_handler(token=token, **options)
    class Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with Server((host, port), handler) as server:
        server.serve_forever(poll_interval=.2)
