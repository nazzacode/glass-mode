"""shared test fixtures: a local HTTP server for tools/glasslab/fixtures (pages link ../../../styles/…, so it serves the
repo root) and a marker for tests that drive a real browser (`-m "not e2e"` skips them)."""
import functools, http.server, threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: drives headless Zen/Firefox (slow; needs a browser)")


@pytest.fixture(scope="session")
def fixture_url():
    """url(name) → http://127.0.0.1:<port>/tools/glasslab/fixtures/<name>"""
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=str(ROOT))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield lambda name: f"http://127.0.0.1:{srv.server_port}/tools/glasslab/fixtures/{name}"
    srv.shutdown()
