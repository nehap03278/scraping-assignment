"""Exercise the real HttpClient (retries, errors, throttling) against a local server."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from scrapers.http_client import FetchError, HttpClient


class ScriptedHandler(BaseHTTPRequestHandler):
    """Replies with the next status from ``server.script[path]`` (last one repeats)."""

    def do_GET(self):  # noqa: N802 - name required by BaseHTTPRequestHandler
        self.server.hits[self.path] = self.server.hits.get(self.path, 0) + 1
        statuses = self.server.script.get(self.path, [404])
        status = statuses[min(self.server.hits[self.path] - 1, len(statuses) - 1)]
        body = f"status {status}".encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedHandler)
    httpd.script, httpd.hits = {}, {}
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def make_client(**overrides):
    options = dict(user_agent="test-agent", timeout=5, delay=0, max_retries=2, backoff_factor=0)
    options.update(overrides)
    return HttpClient(**options)


def url(server, path):
    return f"http://127.0.0.1:{server.server_address[1]}{path}"


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retries_temporary_errors_then_succeeds(server, status):
    server.script["/flaky"] = [status, status, 200]
    response = make_client().get(url(server, "/flaky"))
    assert response.status_code == 200
    assert server.hits["/flaky"] == 3


def test_gives_up_after_max_retries(server, caplog):
    server.script["/down"] = [503]
    client = make_client()
    with pytest.raises(FetchError) as excinfo:
        client.get(url(server, "/down"))
    assert excinfo.value.reason == "HTTP 503"
    assert server.hits["/down"] == 3  # 1 attempt + 2 retries
    assert client.failed_requests == 1
    assert "Request failed" in caplog.text


def test_client_errors_are_not_retried(server):
    with pytest.raises(FetchError, match="HTTP 404"):
        make_client().get(url(server, "/missing"))
    assert server.hits["/missing"] == 1


@pytest.mark.parametrize(
    ("exception", "reason"),
    [
        (requests.exceptions.ConnectionError("refused"), "connection error"),
        (requests.exceptions.ReadTimeout("slow"), "timeout"),
        (requests.exceptions.InvalidURL("bad"), "request failed"),
    ],
)
def test_network_errors_become_fetch_error(monkeypatch, exception, reason):
    client = make_client()

    def boom(*args, **kwargs):
        raise exception

    monkeypatch.setattr(client.session, "get", boom)
    with pytest.raises(FetchError, match=reason):
        client.get("https://quotes.toscrape.com/")
    assert client.failed_requests == 1


def test_sends_user_agent(server):
    assert make_client().session.headers["User-Agent"] == "test-agent"


def test_requests_are_spaced_by_delay(server):
    server.script["/ok"] = [200]
    client = make_client(delay=0.2)
    start = time.perf_counter()
    for _ in range(3):
        client.get(url(server, "/ok"))
    assert time.perf_counter() - start >= 0.4  # two waits between three requests
