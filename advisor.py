# -*- coding: utf-8 -*-
"""
Assistente de decisão no poker usando Llama (Groq, Ollama ou API OpenAI-compatible).
Combina: posição, cartas da mesa, probabilidade de vitória e contexto do pote.
"""
from __future__ import annotations
import base64
import os
from typing import List, Optional

from poker_engine import probabilidade_vitoria_monte_carlo
from posicao import Posicao, posicao_from_string


MODELO_VISAO = "llama3.2-vision"
SIMULACOES_PADRAO = 800

# Groq (Llama 4 Scout)
ENV_GROQ_API_KEY = "GROQ_API_KEY"
ENV_GROQ_MODEL = "GROQ_MODEL"
DEFAULT_GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# OpenAI (oficial: gpt-4o, gpt-4o-mini, etc.)
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_OPENAI_MODEL = "OPENAI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

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


def consultar_openai(
    prompt: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Chama a API OpenAI (GPT-4o, gpt-4o-mini, etc.) — apenas texto."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Para usar a OpenAI, instale: pip install openai")
    api_key = api_key or os.environ.get(ENV_OPENAI_API_KEY)
    if not api_key:
        raise ValueError("Defina OPENAI_API_KEY ou passe api_key")
    model = modelo or os.environ.get(ENV_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


def consultar_openai_vision(
    prompt: str,
    caminho_imagem: str,
    modelo: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Chama a API OpenAI com imagem (ex.: gpt-4o, gpt-4o-mini)."""
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
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
    )
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

    Retorna dict com: probabilidade_vitoria, recomendacao (texto do modelo), prompt_usado.

    Provedores (prioridade):
    - Groq (Llama 4 Scout): defina GROQ_API_KEY ou use_groq=True.
    - OpenAI (GPT-4o, gpt-4o-mini): defina OPENAI_API_KEY ou use_openai=True.
    - API OpenAI-compatible: defina LLAMA_VISION_API_BASE_URL ou use_api=True.
    - Ollama local: padrão se nenhum dos anteriores.
    """
    cartas_mesa = cartas_mesa or []
    pos = posicao_from_string(posicao)

    prob = probabilidade_vitoria_monte_carlo(
        suas_cartas=suas_cartas,
        cartas_mesa=cartas_mesa,
        num_oponentes=num_oponentes,
        simulacoes=simulacoes,
    )

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

    return {
        "probabilidade_vitoria": prob,
        "recomendacao": recomendacao,
        "prompt_usado": prompt,
    }
