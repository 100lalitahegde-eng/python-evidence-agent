"""Optional real retrieval of English Wikipedia lead extracts (secondary sources).

No caller-supplied URLs, redirects, credentials, or persistent response cache.
Each network call owns a killable subprocess, including DNS and socket reads.
"""
import asyncio
import json
import sys
from urllib.parse import urlencode
from .domain import Source, integer, text
from .ports import ProviderError, TransientProviderError


class WikipediaRetrieval:
    def __init__(self, user_agent="python-evidence-agent/0.3 "
                 "(+https://github.com/100lalitahegde-eng/python-evidence-agent)"):
        text(user_agent, "user agent", 512)
        if "\n" in user_agent or "\r" in user_agent:
            raise ValueError("invalid user agent")
        self.user_agent = user_agent

    async def _request(self, **params):
        url = "https://en.wikipedia.org/w/api.php?" + urlencode(
            {"action": "query", "format": "json", "formatversion": 2, **params})
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "evidence_agent.http_worker", url, self.user_agent,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            stdout, _ = await process.communicate()
            if process.returncode:
                raise ProviderError("transport failed")
            result = json.loads(stdout)
            if result.get("error") == "transient":
                raise TransientProviderError("temporary HTTP failure")
            if "data" not in result:
                raise ProviderError("HTTP failure")
            data = result["data"]
            if "error" in data:
                if data["error"].get("code") in {"maxlag", "ratelimited"}:
                    raise TransientProviderError("API busy")
                raise ProviderError("API failure")
            return data
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()

    async def search(self, question, limit):
        text(question, "question", 4000)
        integer(limit, "limit", 1, 20)
        data = await self._request(list="search", srsearch=question, srlimit=limit, srnamespace=0)
        try:
            rows = data["query"]["search"]
            if not isinstance(rows, list) or len(rows) > limit:
                raise ValueError
            ids = [self._id(row["pageid"]) for row in rows]
            if len(set(ids)) != len(ids):
                raise ValueError
            return ids
        except (KeyError, TypeError, ValueError):
            raise ProviderError("invalid search response") from None

    @staticmethod
    def _id(value):
        if type(value) is not int or value <= 0:
            raise ValueError("invalid page id")
        return str(value)

    async def read(self, source_id):
        if not isinstance(source_id, str) or not source_id.isascii() or not source_id.isdigit() or len(source_id) > 20 or int(source_id) <= 0:
            raise ProviderError("invalid page id")
        data = await self._request(pageids=source_id, prop="extracts", exintro=1, explaintext=1)
        try:
            pages = data["query"]["pages"]
            if not isinstance(pages, list) or len(pages) != 1:
                raise ValueError
            page = pages[0]
            if "missing" in page or self._id(page["pageid"]) != source_id:
                raise ValueError
            return Source(source_id, page["title"], "https://en.wikipedia.org/?curid=" + source_id, page["extract"])
        except (KeyError, TypeError, ValueError):
            raise ProviderError("invalid extract response") from None
