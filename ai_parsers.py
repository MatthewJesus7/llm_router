# parsers.py
# ─────────────────────────────────────────────────────────────
# Não precisa mexer aqui a menos que adicione um provider novo
# com formato de resposta diferente de Google AI ou OpenAI-style
# ─────────────────────────────────────────────────────────────

import requests, logging
logger = logging.getLogger("ai-router")


# Fallback genérico — percorre o JSON em busca de qualquer texto útil
# Usado quando o formato da resposta não bate com os padrões conhecidos
def _find_text_in_json(obj, max_depth=6):
    if max_depth <= 0:
        return None
    if isinstance(obj, str) and obj.strip():
        return obj.strip()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ["text", "output", "generated_text", "result"] and isinstance(value, str):
                return value.strip()
            res = _find_text_in_json(value, max_depth-1)
            if res:
                return res
    if isinstance(obj, list):
        for item in obj:
            res = _find_text_in_json(item, max_depth-1)
            if res:
                return res
    return None


# Parser para respostas da Google AI (Gemini)
# Se adicionar outro modelo Google com estrutura diferente, ajuste aqui
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
            reason = data['promptFeedback'].get('blockReason','unknown')
            logger.warning(f"Resposta bloqueada pelo provider: {reason}")
            return f"[Blocked: {reason}]"

        # Último recurso: tenta achar qualquer string no JSON
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


# Parser genérico para APIs estilo OpenAI (e compatíveis como Groq, Together, etc.)
# Se o seu provider retorna um campo diferente, adicione o caminho em `patterns`
def parse_json_text_response(resp: requests.Response) -> str:
    try:
        j = resp.json()

        # ── adicione aqui novos padrões de resposta se necessário ──
        patterns = [
            ("choices", 0, "message", "content"),
            ("choices", 0, "text"),
            ("generated_text",),
            ("output",),
            ("text",),
            ("content",)
        ]
        # ────────────────────────────────────────────────────────────

        for p in patterns:
            result = _get_nested_value(j, p)
            if result and result.strip():
                return result.strip()

        logger.debug("Nenhum padrão conhecido encontrado no parser JSON")
        return str(j).strip()

    except Exception as e:
        logger.warning(f"Erro parse JSON genérico: {e}")
        return resp.text.strip()