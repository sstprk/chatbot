from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class MnemoClient:

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 120.0):
        self._url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=self._timeout)

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["X-Api-Key"] = self._api_key
        return h

    async def query(
        self,
        text: str,
        system_prompt: str | None = None,
        include_provenance: bool = False,
    ) -> dict:
        body: dict = {
            "query": text,
            "include_provenance": include_provenance,
        }
        if system_prompt:
            body["system_prompt"] = system_prompt
        try:
            r = await self._client.post(
                f"{self._url}/query",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.error("query_timeout url=%s", self._url)
            return {"error": "timeout", "answer": None}
        except httpx.HTTPStatusError as e:
            logger.error(
                "query_http_error status=%d url=%s",
                e.response.status_code,
                self._url,
            )
            return {"error": f"http_{e.response.status_code}", "answer": None}
        except Exception as e:
            logger.error("query_error error=%s", e)
            return {"error": str(e), "answer": None}

    async def health(self) -> bool:
        try:
            r = await self._client.get(
                f"{self._url}/query/health",
                timeout=5.0,
            )
            return r.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()


def format_response(data: dict, settings) -> str:
    if "error" in data and data["error"]:
        return settings.error_message

    answer = data.get("answer") or settings.error_message
    parts = [answer]

    if settings.show_sources:
        sources = data.get("sources") or []
        if sources:
            seen: set[str] = set()
            lines: list[str] = []
            for src in sources:
                src_type = src.get("source_type", "unknown")
                if src_type == "slack":
                    key = f"slack:{src.get('channel', '')}"
                    label = f"Slack > #{src.get('channel', 'unknown')}"
                elif src_type == "notion":
                    key = f"notion:{src.get('doc_title', '')}"
                    label = f"Notion > {src.get('doc_title', 'untitled')}"
                else:
                    key = f"{src_type}:{src.get('title', src.get('id', ''))}"
                    label = f"{src_type} > {src.get('title', 'unknown')}"
                if key not in seen:
                    seen.add(key)
                    lines.append(f"• {label}")
                if len(lines) >= 5:
                    break
            if lines:
                parts.append("\n\n:books: *Sources:*\n" + "\n".join(lines))

    if settings.show_provenance:
        prov = data.get("provenance")
        if prov:
            cache_hits = prov.get("cache_hits", 0)
            total = prov.get("total_retrieved", prov.get("global_hits", 0))
            parts.append(f"\n\n:bar_chart: Cache: {cache_hits} hits / {total} retrieved")

    return "".join(parts)
