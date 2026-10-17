import asyncio
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch, AsyncMock
from urllib.error import HTTPError, URLError
from evidence_agent.http_worker import fetch, MAX_BYTES
from evidence_agent.wikipedia import WikipediaRetrieval
from evidence_agent.ports import ProviderError


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_read_contract(self):
        adapter = WikipediaRetrieval()
        adapter._request = AsyncMock(return_value={"query": {"search": [{"pageid": 42}]}})
        self.assertEqual(await adapter.search("Earth", 2), ["42"])
        adapter._request.assert_awaited_once_with(list="search", srsearch="Earth", srlimit=2, srnamespace=0)
        adapter._request.return_value = {"query": {"pages": [{"pageid": 42, "title": "Earth", "extract": "Earth is a planet."}]}}
        source = await adapter.read("42")
        self.assertEqual(source.text, "Earth is a planet.")
        self.assertEqual(source.url, "https://en.wikipedia.org/?curid=42")
        for payload in ({}, {"query": {"pages": []}}, {"query": {"pages": [{"pageid": 43}]}}):
            adapter._request.return_value = payload
            with self.assertRaises(ProviderError):
                await adapter.read("42")
        for value in ("https://localhost", "-1", "0", "1&other=1"):
            with self.assertRaises(ProviderError):
                await adapter.read(value)

    async def test_timeout_reaps_real_transport_process(self):
        create = asyncio.create_subprocess_exec
        children = []
        async def blocked_transport(*args, **kwargs):
            proc = await create(sys.executable, "-c", "import time; time.sleep(30)", **kwargs)
            children.append(proc)
            return proc
        with patch("asyncio.create_subprocess_exec", blocked_transport):
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(WikipediaRetrieval().search("Earth", 1), .1)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)

    async def test_transport_cancel_kills_and_waits(self):
        class Process:
            returncode = None
            killed = False
            async def communicate(self):
                await asyncio.Event().wait()
            def kill(self):
                self.killed = True
                self.returncode = -9
            async def wait(self):
                return self.returncode
        proc = Process()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            task = asyncio.create_task(WikipediaRetrieval().search("Earth", 1))
            await asyncio.sleep(.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(proc.killed)


class HTTPTests(unittest.TestCase):
    def test_real_http_transport_loopback(self):
        # Exercise urllib over a real socket; production adapter fixes HTTPS origin.
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"query":{"search":[{"pageid":42}]}}')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            result = fetch(f"http://127.0.0.1:{server.server_port}/", "test")
            self.assertEqual(result["data"]["query"]["search"][0]["pageid"], 42)
            child = subprocess.run([sys.executable, "-m", "evidence_agent.http_worker", f"http://127.0.0.1:{server.server_port}/", "test"], capture_output=True, text=True, timeout=5, check=True)
            self.assertEqual(json.loads(child.stdout), result)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_status_body_and_size_failures(self):
        for status in (400, 403, 404, 429, 500, 503):
            with patch("urllib.request.OpenerDirector.open", side_effect=HTTPError("url", status, "secret", {}, None)):
                self.assertEqual(fetch("https://example.org", "test"), {"error": "transient" if status == 429 or status >= 500 else "permanent"})
        for body in (b"broken", b"[]", b"x" * (MAX_BYTES + 1)):
            with patch("urllib.request.OpenerDirector.open", return_value=io.BytesIO(body)):
                self.assertEqual(fetch("https://example.org", "test"), {"error": "permanent"})
        with patch("urllib.request.OpenerDirector.open", side_effect=URLError("secret")):
            self.assertEqual(fetch("https://example.org", "test"), {"error": "transient"})
