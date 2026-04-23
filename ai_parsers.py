# parsers.py
# ─────────────────────────────────────────────────────────────
# Não precisa mexer aqui a menos que adicione um provider novo
# com formato de resposta diferente de Google AI ou OpenAI-style
# ─────────────────────────────────────────────────────────────

import requests, logging
logger = logging.getLogger("ai-router")


def _find_text_in_json(obj, max_depth=6):
    """Fallback genérico — percorre o JSON em busca de qualquer texto útil."""
    if max_depth <= 0:
        return None
    if isinstance(obj, str) and obj.strip():
        return obj.strip()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ["text", "output", "generated_text", "result"] and isinstance(value, str):
                return value.strip()
            res = _find_text_in_json(value, max_depth - 1)
            if res:
                return res
    if isinstance(obj, list):
        for item in obj:
            res = _find_text_in_json(item, max_depth - 1)
            if res:
                return res
    return None


def parse_google_ai_response(resp: requests.Response) -> str:
    try:
        data = resp.json()

        if "candidates" in data and data["candidates"]:
            cand = data["candidates"][0]
            if "content" in cand:
                parts = cand["content"].get("parts", [])
                for p in parts:
                    if isinstance(p, dict) and "text" in p:
                        return p["text"].strip()

        if "output" in data and isinstance(data["output"], str):
            return data["output"].strip()

        if "generatedText" in data and isinstance(data["generatedText"], str):
            return data["generatedText"].strip()

        if "promptFeedback" in data:
            reason = data["promptFeedback"].get("blockReason", "unknown")
            logger.warning(f"Resposta bloqueada pelo provider: {reason}")
            return f"[Blocked: {reason}]"

        text = _find_text_in_json(data)
        if text:
            logger.debug("Fallback parser acionado (_find_text_in_json)")
            return text.strip()

        raise RuntimeError("Estrutura inesperada (Google AI).")

    except Exception as e:
        logger.warning(f"Erro parse Google: {e}")
        return resp.text.strip()


def _get_nested_value(obj, keys):
    current = obj
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and isinstance(key, int) and key < len(current):
            current = current[key]
        else:
            return None
    return current if isinstance(current, str) else None


def parse_json_text_response(resp: requests.Response) -> str:
    """Parser genérico para APIs estilo OpenAI chat/completions."""
    try:
        j = resp.json()

        patterns = [
            ("choices", 0, "message", "content"),
            ("choices", 0, "text"),
            ("generated_text",),
            ("output",),
            ("text",),
            ("content",),
        ]

        for p in patterns:
            result = _get_nested_value(j, p)
            if result and result.strip():
                return result.strip()

        logger.debug("Nenhum padrão conhecido encontrado no parser JSON")
        return str(j).strip()

    except Exception as e:
        logger.warning(f"Erro parse JSON genérico: {e}")
        return resp.text.strip()


def parse_grok_response(resp: requests.Response) -> str:
    """
    Parser para Grok via Responses API (/v1/responses).

    A estrutura do Responses API é diferente do chat/completions:

    {
      "output": [
        {
          "type": "message",
          "content": [
            { "type": "output_text", "text": "resposta aqui" }
          ]
        },
        {
          "type": "web_search_call",   ← tool call (informativo, não é a resposta)
          ...
        }
      ]
    }

    Também lida com:
      - reasoning_content em modelos de reasoning (grok-4.20-*-reasoning)
      - Fallback para chat/completions caso o endpoint seja o antigo
    """
    try:
        j = resp.json()

        # ── 1. Responses API: output[] com type="message" ─────────────────
        output_items = j.get("output") or []
        if isinstance(output_items, list):
            for item in output_items:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "message":
                    continue
                content_blocks = item.get("content") or []
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    # output_text é o tipo principal de resposta
                    if block.get("type") == "output_text":
                        text = block.get("text", "")
                        if text and text.strip():
                            return text.strip()
                    # fallback: qualquer bloco com "text"
                    text = block.get("text", "")
                    if text and text.strip():
                        return text.strip()

        # ── 2. Fallback: formato chat/completions (endpoint antigo) ───────
        choices = j.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if content and content.strip():
                return content.strip()

            # reasoning_content para modelos de reasoning
            reasoning = message.get("reasoning_content")
            if reasoning and reasoning.strip():
                logger.debug("Grok: usando reasoning_content como fallback")
                return reasoning.strip()

        # ── 3. Último recurso: varre o JSON ───────────────────────────────
        text = _find_text_in_json(j)
        if text:
            logger.debug("Grok: fallback _find_text_in_json acionado")
            return text.strip()

        raise RuntimeError(
            f"Grok Responses API: nenhum texto extraível. "
            f"output_types={[i.get('type') for i in output_items]}. "
            f"JSON (300 chars): {str(j)[:300]}"
        )

    except RuntimeError:
        raise
    except Exception as e:
        logger.warning(f"Erro parse Grok: {e}")
        return resp.text.strip()