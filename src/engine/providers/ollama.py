"""Ollama adapter — local models via Ollama's native API. Zero cost, no key.

Ideal for offline development: unlimited, private, free. Implemented with the
Python standard library only (no SDK), against Ollama's ``/api/chat`` endpoint
with ``format="json"`` — proof that the ``complete_json`` interface is the real
contract, not any vendor SDK.

The provider only "exists" when the local server is reachable AND at least one
model is pulled, so it appears in the dropdown only when it can actually serve.
The reachability probe is memoized briefly so page reruns don't each pay for it,
and it auto-selects an installed model if the configured default isn't present.
"""

from __future__ import annotations

import json
import time
import urllib.request

from src import consts
from src.engine.providers.base import TransportError, extract_json
from src.engine.schema import phase_json_schema

_DEFAULT_BASE_URL = "http://localhost:11434"
_PROBE_TTL = 10.0          
_GEN_TIMEOUT = 120.0       
_probe_cache: dict[str, tuple[float, list[str] | None]] = {}


def _installed_models(base_url: str, timeout: float = 0.8) -> list[str]:
    """Model names pulled into Ollama; raises TransportError if unreachable.

    Both success and failure are memoized for a few seconds so repeated page
    reruns don't re-probe (connection-refused is instant, but this also bounds
    the slow-server case).
    """
    now = time.time()
    cached = _probe_cache.get(base_url)
    if cached and now - cached[0] < _PROBE_TTL:
        if cached[1] is None:
            raise TransportError(f"Ollama not reachable at {base_url} (cached)")
        return cached[1]
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [m["name"] for m in data.get("models", [])]
    except Exception as e:
        _probe_cache[base_url] = (now, None)
        raise TransportError(f"Ollama not reachable at {base_url} ({e})") from e
    _probe_cache[base_url] = (now, names)
    return names


class OllamaProvider:
    name = consts.PROVIDER_OLLAMA

    def __init__(self, model: str | None = None,
                 base_url: str = _DEFAULT_BASE_URL) -> None:
        installed = _installed_models(base_url)  
        if not installed:
            raise TransportError("Ollama is running but has no models — "
                                 "run e.g. `ollama pull llama3.2`")
        want = model or consts.PROVIDER_MODELS.get(self.name, "")
        want_base = want.split(":")[0]
        self.model = next(
            (m for m in installed if m == want or m.split(":")[0] == want_base),
            installed[0],
        )
        self._base_url = base_url

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "format": schema or phase_json_schema(),  
            "options": {"temperature": 0.3},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/api/chat", data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=_GEN_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise TransportError(f"Ollama call failed ({e})") from e
        return extract_json(data.get("message", {}).get("content", ""))
