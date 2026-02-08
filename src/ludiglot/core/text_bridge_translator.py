from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable


class OllamaTextBridgeTranslator:
    """Translate OCR text (EN -> zh-Hans) for detached bilingual matching fallback."""

    def __init__(
        self,
        endpoint: str | None,
        model: str | None,
        timeout: float = 8.0,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        ep = str(endpoint or "").strip()
        if ep and not ep.startswith(("http://", "https://")):
            ep = f"http://{ep}"
        self.endpoint = ep.rstrip("/") if ep else ""
        self.model = str(model or "").strip()
        self.timeout = float(timeout) if timeout and timeout > 0 else 8.0
        self._logger = logger
        self._cache: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self.model)

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)

    def _build_prompt(self, text: str) -> str:
        return (
            "Translate the following in-game English text to Simplified Chinese.\n"
            "Output translated text only.\n"
            "Rules:\n"
            "1) Keep placeholders like {0}, {1}, %d, %s unchanged.\n"
            "2) Keep numbers, units and time expressions unchanged.\n"
            "3) Do not add explanations.\n"
            "TEXT:\n"
            f"{text}"
        )

    def _post_ollama(self, prompt: str) -> str:
        url = f"{self.endpoint}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read()
        obj = json.loads(raw.decode("utf-8", errors="ignore"))
        if not isinstance(obj, dict):
            return ""
        if obj.get("error"):
            return ""
        return str(obj.get("response") or "").strip()

    def _sanitize_output(self, text: str) -> str:
        out = str(text or "").strip()
        if not out:
            return ""
        if out.startswith("```") and out.endswith("```"):
            out = out.strip("`").strip()
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        if not lines:
            return ""
        out = " ".join(lines)
        if len(out) >= 2 and out[0] == out[-1] and out[0] in {"'", '"', "“", "”"}:
            out = out[1:-1].strip()
        return out

    def translate_en_to_zh(self, text: str) -> str:
        query = str(text or "").strip()
        if not query or not self.available:
            return ""
        if query in self._cache:
            return self._cache[query]

        # 防止缓存失控
        if len(self._cache) >= 512:
            keys = list(self._cache.keys())[:256]
            for k in keys:
                self._cache.pop(k, None)

        prompt = self._build_prompt(query[:1000])
        translated = ""
        try:
            translated = self._sanitize_output(self._post_ollama(prompt))
        except urllib.error.URLError as exc:
            self._log(f"[MATCH] 跨语言桥接调用失败: {exc}")
        except Exception as exc:
            self._log(f"[MATCH] 跨语言桥接调用异常: {exc}")

        self._cache[query] = translated
        return translated

