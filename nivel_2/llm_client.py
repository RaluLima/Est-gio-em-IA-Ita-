"""Cliente LLM provedor-agnóstico com cache-first.

Usa endpoints compatíveis com o SDK OpenAI (Groq, Gemini, OpenRouter, Ollama).
Respostas anteriores ficam em llm_cache/ para poupar cota das camadas gratuitas;
sem cache e sem chave configurada, falha com instrução clara.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

PASTA_REPO = Path(__file__).resolve().parent.parent
PASTA_CACHE = PASTA_REPO / "llm_cache"

ENDPOINTS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GOOGLE_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), None),
}


def extrair_json(texto: str) -> str:
    """Recupera o primeiro objeto JSON balanceado dentro da resposta do modelo."""
    ini = texto.find("{")
    if ini == -1:
        raise ValueError("nenhum objeto JSON na resposta")
    profundidade = 0
    for i, ch in enumerate(texto[ini:], start=ini):
        profundidade += (ch == "{") - (ch == "}")
        if profundidade == 0:
            return texto[ini : i + 1]
    raise ValueError("JSON nao balanceado na resposta")


def chamar_llm(case_key: str, system: str, user: str, temperatura: float = 0.2) -> tuple[str, dict]:
    """Retorna (texto_resposta, metricas). Cache-first; API real como fallback."""
    t0 = time.perf_counter()
    PASTA_CACHE.mkdir(exist_ok=True)
    arquivo = PASTA_CACHE / f"{case_key}.json"
    if arquivo.exists():
        registro = json.loads(arquivo.read_text(encoding="utf-8"))
        origem = f"cache[{registro.get('origem', 'desconhecida')}]"
    else:
        registro = chamada_api_real(system, user, temperatura)
        arquivo.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        origem = "api"
    metricas = {
        "origem": origem,
        "tokens_prompt": registro.get("usage", {}).get("prompt_tokens"),
        "tokens_resposta": registro.get("usage", {}).get("completion_tokens"),
        "latencia_ms": round((time.perf_counter() - t0) * 1000),
    }
    return registro["response_text"], metricas


def chave_disponivel() -> bool:
    """Indica se há provedor + chave configurados no ambiente/.env."""
    from dotenv import load_dotenv

    load_dotenv(PASTA_REPO / ".env")
    provedor = os.getenv("LLM_PROVIDER", "").lower()
    if provedor not in ENDPOINTS:
        return False
    var_chave = ENDPOINTS[provedor][1]
    return var_chave is None or bool(os.getenv(var_chave))


def chamada_api_real(system: str, user: str, temperatura: float) -> dict:
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(PASTA_REPO / ".env")
    provedor = os.getenv("LLM_PROVIDER", "").lower()
    if provedor not in ENDPOINTS:
        raise RuntimeError(
            f"Provedor '{provedor}' invalido. Configure LLM_PROVIDER no .env "
            f"(opcoes: {', '.join(ENDPOINTS)}). Veja .env.example."
        )
    base_url, var_chave = ENDPOINTS[provedor]
    chave = os.getenv(var_chave) if var_chave else "local"
    if var_chave and not chave:
        raise RuntimeError(f"Variavel {var_chave} ausente no .env.")
    modelo = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

    cliente = OpenAI(base_url=base_url, api_key=chave)
    resp = cliente.chat.completions.create(
        model=modelo,
        temperature=temperatura,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return {
        "case_key": None,
        "model": modelo,
        "system": system,
        "user": user,
        "response_text": resp.choices[0].message.content,
        "usage": {
            "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
            "completion_tokens": getattr(resp.usage, "completion_tokens", None),
        },
        "latency_ms": None,
        "origem": "api",
    }
