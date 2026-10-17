"""Bounded HTTPS transport subprocess, invoked by WikipediaRetrieval."""
import json
import sys
import urllib.error
import urllib.request

MAX_BYTES = 1_000_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, user_agent):
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                return {"error": "permanent"}
            payload = json.loads(data)
            if not isinstance(payload, dict):
                return {"error": "permanent"}
            return {"data": payload}
    except urllib.error.HTTPError as exc:
        return {"error": "transient" if exc.code == 429 or 500 <= exc.code < 600 else "permanent"}
    except (urllib.error.URLError, TimeoutError):
        return {"error": "transient"}
    except (ValueError, UnicodeError):
        return {"error": "permanent"}


if __name__ == "__main__":
    print(json.dumps(fetch(sys.argv[1], sys.argv[2])))
