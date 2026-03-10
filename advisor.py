# -*- coding: utf-8 -*-
"""
Assistente de decisão no poker usando Llama (Groq, Ollama ou API OpenAI-compatible).
Combina: posição, cartas da mesa, probabilidade de vitória e contexto do pote.
"""
from __future__ import annotations
import base64
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

from poker_engine import probabilidade_vitoria_monte_carlo
from posicao import Posicao, posicao_from_string


MODELO_VISAO = "llama3.2-vision"
SIMULACOES_PADRAO = 800

# Groq (Llama 4 Scout)
ENV_GROQ_API_KEY = "GROQ_API_KEY"
ENV_GROQ_MODEL = "GROQ_MODEL"
DEFAULT_GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# OpenAI (gpt-4o, gpt-4o-mini, gpt-4.1, etc.)
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_OPENAI_MODEL = "OPENAI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"  # ou gpt-4.1, gpt-4o conforme OPENAI_MODEL no .env

# API OpenAI-compatible (ex.: Llama Vision, outros provedores)
ENV_API_BASE_URL = "LLAMA_VISION_API_BASE_URL"
ENV_API_KEY = "LLAMA_VISION_API_KEY"
ENV_MODEL = "LLAMA_VISION_MODEL"
DEFAULT_API_MODEL = "meta-llama/Llama-3.2-11B-Vision-Instruct"


def construir_prompt(
    posicao: Posicao,
    suas_cartas: List[str],
    cartas_mesa: List[str],
    prob_vitoria: float,
    num_oponentes: int = 1,
    tamanho_pote: float = 0,
    sua_stack: float = 0,
    blind: float = 0,
    acoes_anteriores: Optional[str] = None,
    imagem_fornecida: bool = False,
) -> str:
    """Monta o prompt em inglês para o modelo (Vision funciona melhor em inglês)."""
    fase = "preflop" if len(cartas_mesa) == 0 else "flop" if len(cartas_mesa) == 3 else "turn" if len(cartas_mesa) == 4 else "river"
    board_str = ", ".join(cartas_mesa) if cartas_mesa else "none"
    pos_desc = f"{posicao.value} ({posicao.forca_relativa} position). {posicao.descricao}"
    hole_cards_str = ", ".join(suas_cartas) if suas_cartas else "none (no cards in hand or not visible)"

    prompt = f"""You are an expert Texas Hold'em poker assistant. Based ONLY on the following data, recommend the best action: FOLD, CHECK, CALL, or RAISE (and suggest size if raise).

CONTEXT:
- Your position: {pos_desc}
- Your hole cards: {hole_cards_str}
- Board: {board_str}
- Street: {fase}
- Number of opponents: {num_oponentes}
- Estimated equity (win probability): {prob_vitoria:.1%}
- Pot size: {tamanho_pote}
- Your stack: {sua_stack}
- Big blind: {blind}
"""
    if acoes_anteriores:
        prompt += f"- Recent actions: {acoes_anteriores}\n"
    if imagem_fornecida:
        prompt += "- An image of the table is attached; use it to confirm or refine your recommendation.\n"

    prompt += """
Respond in 2-4 short sentences. First give your recommendation (e.g. "Recommendation: RAISE to 2.5bb" or "Recommendation: FOLD"). Then briefly explain why considering position and equity. Keep the answer concise and in English."""
    return prompt


def _preflop_confidence_label(score: float) -> str:
    """Rótulo padronizado para confiança do motor pré-flop (evita 'High' para 0.6)."""
    if score >= 0.8:
        return "High"
    if score >= 0.6:
        return "Medium"
    if score >= 0.4:
        return "Low-Medium"
    return "Low"


def construir_prompt_veredito(
    dados_completos: Dict[str, Any],
    prob_vitoria: float,
    preflop_engine_result: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Monta o prompt do analista técnico: usa SOMENTE os dados estruturados;
    resposta em Recommendation, Confidence, Main reasons, Data limitations, Strategic note.
    Se preflop_engine_result for passado (round preflop), inclui a saída do motor pré-flop no prompt.
    """
    json_str = json.dumps(dados_completos, indent=2, ensure_ascii=False)
    dealer_incerto = dados_completos.get("dealer_button_nao_identificado") is True
    nota_dealer = "\n- The field dealer_button_nao_identificado is true: dealer button was not identified (position may be uncertain). Mention this under Data limitations." if dealer_incerto else ""
    position = (dados_completos.get("position") or "").strip().upper()
    nota_co = "\n- If position is CO: do not state that 'opening ranges are generally stronger'; CO is a late position with a wide open range." if position == "CO" else ""
    facing_bet = dados_completos.get("facing_bet_to_call") is True
    nota_facing_bet = (
        "\n- facing_bet_to_call is true: a 'Call' (or 'Call X') button is visible, so someone has bet and hero can Fold or Call (or Check if hero has already matched). Recommend one of: Fold, Call [amount], or Check if applicable. Do not recommend Raise unless the UI clearly offers it."
        if facing_bet else ""
    )

    preflop_block = ""
    if preflop_engine_result:
        preflop_block = f"""
PREFLOP DECISION ENGINE OUTPUT (use as reference; align your recommendation with it when data supports):
- recommended_action: {preflop_engine_result.get("recommended_action", "unknown")}
- hand: {preflop_engine_result.get("hand", "")} | hand_class: {preflop_engine_result.get("hand_class", "")}
- scenario: {preflop_engine_result.get("scenario", "")}
- confidence: {preflop_engine_result.get("confidence", 0)} ({_preflop_confidence_label(preflop_engine_result.get("confidence", 0))})
- reasoning: {preflop_engine_result.get("reasoning", [])}
"""

    prompt = f"""You are a technical poker analyst.
Your role is to explain the best action using ONLY the structured data provided.

STRUCTURED DATA (JSON from the table):
{json_str}

ADDITIONAL:
- Estimated equity (win probability from simulation): {prob_vitoria:.1%}
{nota_dealer}
{nota_co}
{nota_facing_bet}
{preflop_block}

RULES:
1. Never invent previous actions. Use only what is in the data.
2. Never confuse stack (chips in hand) with current bet. The schema does not include per-player bet amounts to avoid this.
3. Never describe Hero's position differently from the "position" field in the JSON. Use that value exactly.
4. If data is insufficient, reduce confidence and say so explicitly.
5. The recommendation must consider position, effective stack (if present), confirmed prior action, pot odds, and hand playability.
6. Equity alone is not enough to justify the decision.
7. In preflop, give strong weight to the PREFLOP DECISION ENGINE OUTPUT above when present.
8. Respond in this exact format (in English):

- Recommendation: (one sentence: best action and optional size, e.g. "Fold" / "Check" / "Call" / "Raise to 2.5 BB")
- Confidence: (Low | Low-Medium | Medium | High)
- Main reasons: (2-4 bullet points)
- Data limitations: (what is missing or uncertain)
- Strategic note: (one short line)"""
    return prompt


def construir_prompt_veredito_enum(recomendacao: str) -> str:
    """Prompt para o agente que extrai apenas o veredito enum a partir da recomendação do analista."""
    return f"""Based on the following poker recommendation, output a single line with the verdict.

RECOMMENDATION:
{recomendacao}

Output exactly one line in this format:
- VERDICT: FOLD
- VERDICT: CHECK
- VERDICT: CALL
- VERDICT: RAISE X.X BB   (replace X.X with the suggested raise size in big blinds, e.g. 2.5 or 3)

Output only that line, nothing else."""


def extrair_veredito_da_resposta(texto: str) -> str:
    """
    Extrai o veredito (FOLD, CHECK, RAISE X BB) da resposta do agente.
    Retorna string no formato "FOLD", "CHECK" ou "RAISE 2.5" (número em BB).
    """
    if not texto or not isinstance(texto, str):
        return ""
    texto = texto.strip().upper()
    # VERDICT: FOLD / CHECK / CALL / RAISE 2.5 BB
    m = re.search(r"VERDICT\s*:\s*(FOLD|CHECK|CALL|RAISE\s+[\d.]+(?:\s*BB)?)", texto, re.IGNORECASE)
    if m:
        val = m.group(1).strip().upper()
        val = re.sub(r"\s*BB\s*$", "", val, flags=re.IGNORECASE).strip()
        if val in ("FOLD", "CHECK", "CALL"):
            return val
        return "RAISE " + re.sub(r"^RAISE\s*", "", val, flags=re.IGNORECASE).strip()
    return ""


def obter_veredito_enum(
    recomendacao: str,
    *,
    use_groq: Optional[bool] = None,
    groq_api_key: Optional[str] = None,
    groq_model: Optional[str] = None,
    groq_stream: bool = False,
    use_openai: Optional[bool] = None,
    openai_api_key: Optional[str] = None,
    openai_model: Optional[str] = None,
    use_api: Optional[bool] = None,
    api_base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_model: Optional[str] = None,
) -> str:
    """
    Segundo agente: a partir do texto da recomendação, chama o LLM para obter
    apenas o veredito enum (FOLD | CHECK | RAISE X BB). Retorna string, ex.: "FOLD", "CHECK", "RAISE 2.5".
    """
    if not (recomendacao or "").strip():
        return ""
    prompt = construir_prompt_veredito_enum(recomendacao.strip())
    raw = consultar_llama_vision(
        prompt,
        caminho_imagem=None,
        use_groq=use_groq,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_stream=groq_stream,
        use_openai=use_openai,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        use_api=use_api,
        api_base_url=api_base_url,
        api_key=api_key,
        api_model=api_model,
    )
    return extrair_veredito_da_resposta(raw or "")


def _usar_groq() -> bool:
    """True se GROQ_API_KEY estiver definida."""
    return bool(os.environ.get(ENV_GROQ_API_KEY))


def _usar_openai() -> bool:
    """True se OPENAI_API_KEY estiver definida."""
    return bool(os.environ.get(ENV_OPENAI_API_KEY))

def _usar_api() -> bool:
    """True se LLAMA_VISION_API_BASE_URL estiver definida."""
    return bool(os.environ.get(ENV_API_BASE_URL))


def _groq_resposta_texto(completion, stream: bool = False) -> str:
    """Extrai o texto da resposta Groq. Evita AttributeError se a API retornar formato inesperado."""
    if completion is None:
        raise ValueError("Resposta vazia da API Groq")
    if isinstance(completion, str):
        raise ValueError(f"Resposta inesperada da API Groq (string em vez de objeto): {completion[:200]}")
    if not hasattr(completion, "choices") or not completion.choices:
        msg = getattr(completion, "message", None) or str(completion)[:300]
        raise ValueError(f"Resposta da Groq sem 'choices'. Detalhes: {msg}")
    if stream:
        parts = []
        for chunk in completion:
            if hasattr(chunk, "choices") and chunk.choices and getattr(chunk.choices[0], "delta", None):
                part = chunk.choices[0].delta.content or ""
                parts.append(part)
        return "".join(parts).strip()
    return (completion.choices[0].message.content or "").strip()


def consultar_groq(
    prompt: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
    stream: bool = False,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """Chama Llama 4 Scout (ou outro modelo) via API Groq. Apenas texto (sem imagem)."""
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("Para usar a Groq, instale: pip install groq")

    api_key = api_key or os.environ.get(ENV_GROQ_API_KEY)
    if not api_key:
        raise ValueError("Defina GROQ_API_KEY ou passe api_key")
    model = modelo or os.environ.get(ENV_GROQ_MODEL) or DEFAULT_GROQ_MODEL

    client = Groq(api_key=api_key)
    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "stream": stream,
    }
    completion = client.chat.completions.create(**kwargs)
    return _groq_resposta_texto(completion, stream=stream)


def consultar_groq_vision(
    prompt: str,
    caminho_imagem: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """Chama Llama 4 Scout na Groq com imagem (vision). Mesmo modelo para OCR e recomendação."""
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("Para usar a Groq, instale: pip install groq")

    api_key = api_key or os.environ.get(ENV_GROQ_API_KEY)
    if not api_key:
        raise ValueError("Defina GROQ_API_KEY ou passe api_key")
    model = modelo or os.environ.get(ENV_GROQ_MODEL) or DEFAULT_GROQ_MODEL
    if not os.path.isfile(caminho_imagem):
        raise FileNotFoundError(f"Imagem não encontrada: {caminho_imagem}")

    data_url = _imagem_para_base64_data_url(caminho_imagem)
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=temperature,
        max_completion_tokens=max_tokens,
        stream=False,
    )
    return _groq_resposta_texto(completion, stream=False)


def _retry_on_rate_limit(fn: Callable[[], Any], max_retries: int = 3, base_wait: int = 25) -> Any:
    """Executa fn(); em 429 (rate limit), espera e tenta de novo até max_retries."""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            is_429 = (
                getattr(e, "status_code", None) == 429
                or "429" in err_str
                or "rate limit" in err_str
            )
            if is_429 and attempt < max_retries:
                wait = base_wait
                if "try again in" in err_str or "in 20s" in err_str:
                    import re as re_mod
                    m = re_mod.search(r"try again in (\d+)s", err_str)
                    if m:
                        wait = int(m.group(1)) + 5
                time.sleep(wait)
                continue
            raise
    raise last_err


def consultar_openai(
    prompt: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Chama a API OpenAI (GPT-4o, gpt-4o-mini, etc.) — apenas texto. Retry automático em 429."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Para usar a OpenAI, instale: pip install openai")
    api_key = api_key or os.environ.get(ENV_OPENAI_API_KEY)
    if not api_key:
        raise ValueError("Defina OPENAI_API_KEY ou passe api_key")
    model = modelo or os.environ.get(ENV_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL
    client = OpenAI(api_key=api_key)

    def _call() -> Any:
        return client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )

    response = _retry_on_rate_limit(_call)
    return (response.choices[0].message.content or "").strip()


def consultar_openai_vision(
    prompt: str,
    caminho_imagem: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Chama a API OpenAI com imagem (ex.: gpt-4o, gpt-4o-mini). Retry automático em 429."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Para usar a OpenAI, instale: pip install openai")
    api_key = api_key or os.environ.get(ENV_OPENAI_API_KEY)
    if not api_key:
        raise ValueError("Defina OPENAI_API_KEY ou passe api_key")
    model = modelo or os.environ.get(ENV_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL
    if not os.path.isfile(caminho_imagem):
        raise FileNotFoundError(f"Imagem não encontrada: {caminho_imagem}")
    data_url = _imagem_para_base64_data_url(caminho_imagem)
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    client = OpenAI(api_key=api_key)

    def _call() -> Any:
        return client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=max_tokens,
        )

    response = _retry_on_rate_limit(_call)
    return (response.choices[0].message.content or "").strip()


def _imagem_para_base64_data_url(caminho: str) -> str:
    """Lê arquivo de imagem e retorna data URL em base64 (ex: data:image/png;base64,...)."""
    with open(caminho, "rb") as f:
        raw = f.read()
    ext = os.path.splitext(caminho)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def consultar_llama_vision_api(
    prompt: str,
    caminho_imagem: Optional[str] = None,
    modelo: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Chama Llama 3.2 Vision via API (endpoint OpenAI-compatible). Retorna o texto da resposta."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Para usar a API, instale: pip install openai")

    base_url = base_url or os.environ.get(ENV_API_BASE_URL)
    if not base_url:
        raise ValueError("Defina LLAMA_VISION_API_BASE_URL ou passe base_url")
    api_key = api_key or os.environ.get(ENV_API_KEY)
    if not api_key:
        api_key = "sk-placeholder"  # vários endpoints locais aceitam qualquer valor
    model = modelo or os.environ.get(ENV_MODEL) or DEFAULT_API_MODEL

    content: list = [{"type": "text", "text": prompt}]
    if caminho_imagem and os.path.isfile(caminho_imagem):
        data_url = _imagem_para_base64_data_url(caminho_imagem)
        content.append({"type": "image_url", "image_url": {"url": data_url}})

    client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=500,
    )
    return (response.choices[0].message.content or "").strip()


def consultar_llama_vision_ollama(
    prompt: str,
    caminho_imagem: Optional[str] = None,
    modelo: str = MODELO_VISAO,
) -> str:
    """Chama o modelo Llama 3.2 Vision via Ollama (local). Retorna o texto da resposta."""
    try:
        import ollama
    except ImportError:
        raise ImportError("Instale o pacote ollama: pip install ollama")

    messages = [{"role": "user", "content": prompt}]
    kwargs = {"model": modelo, "messages": messages}
    if caminho_imagem and os.path.isfile(caminho_imagem):
        kwargs["messages"][0]["images"] = [caminho_imagem]

    response = ollama.chat(**kwargs)
    return response.message.content or ""


def consultar_llama_vision(
    prompt: str,
    caminho_imagem: Optional[str] = None,
    modelo: str = MODELO_VISAO,
    *,
    use_groq: Optional[bool] = None,
    groq_api_key: Optional[str] = None,
    groq_model: Optional[str] = None,
    groq_stream: bool = False,
    use_openai: Optional[bool] = None,
    openai_api_key: Optional[str] = None,
    openai_model: Optional[str] = None,
    use_api: Optional[bool] = None,
    api_base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_model: Optional[str] = None,
) -> str:
    """
    Chama o modelo de linguagem (e visão, se houver imagem).
    Ordem: Groq > OpenAI > API OpenAI-compatible > Ollama local.
    """
    if use_groq is None:
        use_groq = _usar_groq() or groq_api_key is not None
    if use_groq:
        model_groq = groq_model or os.environ.get(ENV_GROQ_MODEL) or DEFAULT_GROQ_MODEL
        if caminho_imagem and os.path.isfile(caminho_imagem):
            return consultar_groq_vision(
                prompt,
                caminho_imagem,
                modelo=model_groq,
                api_key=groq_api_key,
            )
        return consultar_groq(
            prompt,
            modelo=model_groq,
            api_key=groq_api_key,
            stream=groq_stream,
        )
    if use_openai is None:
        use_openai = _usar_openai() or openai_api_key is not None
    if use_openai:
        model_openai = openai_model or os.environ.get(ENV_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL
        if caminho_imagem and os.path.isfile(caminho_imagem):
            return consultar_openai_vision(
                prompt,
                caminho_imagem,
                modelo=model_openai,
                api_key=openai_api_key,
            )
        return consultar_openai(
            prompt,
            modelo=model_openai,
            api_key=openai_api_key,
        )
    if use_api is None:
        use_api = _usar_api() or api_base_url is not None
    if use_api:
        return consultar_llama_vision_api(
            prompt,
            caminho_imagem=caminho_imagem,
            modelo=api_model or modelo,
            base_url=api_base_url,
            api_key=api_key,
        )
    return consultar_llama_vision_ollama(prompt, caminho_imagem=caminho_imagem, modelo=modelo)


def melhor_jogada(
    posicao: str,
    suas_cartas: List[str],
    cartas_mesa: Optional[List[str]] = None,
    num_oponentes: int = 1,
    simulacoes: int = SIMULACOES_PADRAO,
    tamanho_pote: float = 0,
    sua_stack: float = 0,
    blind: float = 1.0,
    acoes_anteriores: Optional[str] = None,
    caminho_imagem: Optional[str] = None,
    modelo: str = MODELO_VISAO,
    *,
    dados_completos: Optional[Dict[str, Any]] = None,
    use_groq: Optional[bool] = None,
    groq_api_key: Optional[str] = None,
    groq_model: Optional[str] = None,
    groq_stream: bool = False,
    use_openai: Optional[bool] = None,
    openai_api_key: Optional[str] = None,
    openai_model: Optional[str] = None,
    use_api: Optional[bool] = None,
    api_base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_model: Optional[str] = None,
) -> dict:
    """
    Calcula a probabilidade de vitória e pergunta ao modelo a melhor jogada.

    Se dados_completos for passado (JSON extraído da mesa), o agente final recebe
    esse JSON inteiro como contexto e deve devolver um veredito explícito: FOLD, CHECK, CALL ou RAISE.

    Retorna dict com: probabilidade_vitoria, recomendacao (texto do modelo), prompt_usado.

    Provedores (prioridade):
    - Groq (Llama 4 Scout): defina GROQ_API_KEY ou use_groq=True.
    - OpenAI (GPT-4o, gpt-4o-mini): defina OPENAI_API_KEY ou use_openai=True.
    - API OpenAI-compatible: defina LLAMA_VISION_API_BASE_URL ou use_api=True.
    - Ollama local: padrão se nenhum dos anteriores.
    """
    cartas_mesa = cartas_mesa or []
    suas_cartas = suas_cartas or []

    # player_cards = [] significa que o hero já não está ativo (já deu fold) — não há decisão a tomar
    if len(suas_cartas) == 0 and dados_completos is not None:
        msg = (
            "No action — you are not in the hand. "
            "Empty player_cards means you have already folded or are not active. No decision required."
        )
        return {
            "probabilidade_vitoria": 0.0,
            "recomendacao": msg,
            "prompt_usado": "(hero folded: player_cards empty)",
            "veredito": "FOLDED",
            "hero_folded": True,
        }

    pos = posicao_from_string(posicao)

    prob = probabilidade_vitoria_monte_carlo(
        suas_cartas=suas_cartas,
        cartas_mesa=cartas_mesa,
        num_oponentes=num_oponentes,
        simulacoes=simulacoes,
    )

    preflop_engine_result = None
    if dados_completos is not None:
        round_ = (dados_completos.get("round") or "").strip().lower()
        if round_ == "preflop":
            try:
                from preflop_engine import preflop_state_from_schema, preflop_decision_engine
                state = preflop_state_from_schema(dados_completos)
                if state is not None:
                    preflop_engine_result = preflop_decision_engine(state)
            except Exception:
                pass
        prompt = construir_prompt_veredito(dados_completos, prob, preflop_engine_result=preflop_engine_result)
    else:
        prompt = construir_prompt(
            posicao=pos,
            suas_cartas=suas_cartas,
            cartas_mesa=cartas_mesa,
            prob_vitoria=prob,
            num_oponentes=num_oponentes,
            tamanho_pote=tamanho_pote,
            sua_stack=sua_stack,
            blind=blind,
            acoes_anteriores=acoes_anteriores,
            imagem_fornecida=bool(caminho_imagem and os.path.isfile(caminho_imagem)),
        )

    recomendacao = consultar_llama_vision(
        prompt,
        caminho_imagem=caminho_imagem,
        modelo=modelo,
        use_groq=use_groq,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_stream=groq_stream,
        use_openai=use_openai,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        use_api=use_api,
        api_base_url=api_base_url,
        api_key=api_key,
        api_model=api_model,
    )

    # Segundo agente: veredito enum (FOLD | CHECK | RAISE X BB) a partir da recomendação
    veredito = ""
    if dados_completos is not None and (recomendacao or "").strip():
        try:
            veredito = obter_veredito_enum(
                recomendacao,
                use_groq=use_groq,
                groq_api_key=groq_api_key,
                groq_model=groq_model,
                groq_stream=groq_stream,
                use_openai=use_openai,
                openai_api_key=openai_api_key,
                openai_model=openai_model,
                use_api=use_api,
                api_base_url=api_base_url,
                api_key=api_key,
                api_model=api_model,
            )
        except Exception:
            pass

    out = {
        "probabilidade_vitoria": prob,
        "recomendacao": recomendacao,
        "prompt_usado": prompt,
        "veredito": veredito,
    }
    if preflop_engine_result is not None:
        out["preflop_engine"] = preflop_engine_result
    return out
