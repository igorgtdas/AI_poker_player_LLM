# -*- coding: utf-8 -*-
"""
Pipeline: imagem da mesa → LLM visão (extrai JSON) → LLM consultor (probabilidade + recomendação).
"""
from __future__ import annotations
from typing import Any, Optional

from advisor import melhor_jogada
from extractor import extrair_json_da_imagem
from poker_engine import normalizar_carta_str


def _contexto_extra(dados: dict) -> str:
    """Monta texto de contexto para o consultor a partir de bbs e risco."""
    partes = []
    bbs = dados.get("bbs_apostadas")
    if bbs is not None and bbs > 0:
        partes.append(f"Big blinds já no pote / aposta atual: {bbs} BB")
    risco = dados.get("risco_baseado_na_posicao") or ""
    if risco:
        partes.append(f"Risco pela posição: {risco}")
    return ". ".join(partes) if partes else ""


def imagem_para_recomendacao(
    caminho_imagem: str,
    *,
    # Extrator (LLM visão)
    username_player: Optional[str] = None,
    use_vision_api: Optional[bool] = None,
    vision_api_base_url: Optional[str] = None,
    vision_api_key: Optional[str] = None,
    vision_api_model: Optional[str] = None,
    vision_model_ollama: str = "llama3.2-vision",
    # Consultor (segundo LLM: Groq, API ou Ollama)
    use_groq: Optional[bool] = None,
    groq_api_key: Optional[str] = None,
    groq_model: Optional[str] = None,
    groq_stream: bool = False,
    use_api: Optional[bool] = None,
    api_base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_model: Optional[str] = None,
    simulacoes: int = 800,
    blind: float = 1.0,
) -> dict:
    """
    Fluxo completo: lê a imagem com um LLM de visão, extrai JSON da mesa,
    e passa os dados para o LLM consultor (melhor_jogada), que retorna
    probabilidade de vitória e recomendação.

    Retorna:
      - dados_extraidos: dict do JSON extraído da imagem
      - probabilidade_vitoria: float
      - recomendacao: str
      - prompt_usado: str (do consultor)
    """
    dados = extrair_json_da_imagem(
        caminho_imagem,
        username_player=username_player,
        use_api=use_vision_api,
        api_base_url=vision_api_base_url,
        api_key=vision_api_key,
        api_model=vision_api_model,
        modelo_ollama=vision_model_ollama,
    )

    posicao = dados.get("posicao") or "BTN"
    # Normaliza cartas: LLM às vezes retorna só valor ("9") em vez de "9s"
    suas_cartas = [normalizar_carta_str(c) for c in (dados.get("suas_cartas") or [])]
    cartas_mesa = [normalizar_carta_str(c) for c in (dados.get("cartas_mesa") or [])]
    quantos = max(1, int(dados.get("quantos_player_na_mesa") or 2))
    num_oponentes = max(0, quantos - 1)
    bbs = float(dados.get("bbs_apostadas") or 0)
    tamanho_pote = bbs * blind if blind else bbs
    acoes_anteriores = _contexto_extra(dados)

    if len(suas_cartas) != 2:
        raise ValueError(
            f"A extração retornou {len(suas_cartas)} cartas (esperado 2). "
            "Verifique a imagem ou o JSON extraído."
        )
    if len(cartas_mesa) not in (0, 3, 4, 5):
        raise ValueError(
            f"Cartas da mesa inválidas: {len(cartas_mesa)} (esperado 0, 3, 4 ou 5)."
        )

    resultado = melhor_jogada(
        posicao=posicao,
        suas_cartas=suas_cartas,
        cartas_mesa=cartas_mesa,
        num_oponentes=num_oponentes,
        simulacoes=simulacoes,
        tamanho_pote=tamanho_pote,
        sua_stack=0,
        blind=blind,
        acoes_anteriores=acoes_anteriores or None,
        caminho_imagem=None,
        use_groq=use_groq,
        groq_api_key=groq_api_key,
        groq_model=groq_model,
        groq_stream=groq_stream,
        use_api=use_api,
        api_base_url=api_base_url,
        api_key=api_key,
        api_model=api_model,
    )

    return {
        "dados_extraidos": dados,
        "probabilidade_vitoria": resultado["probabilidade_vitoria"],
        "recomendacao": resultado["recomendacao"],
        "prompt_usado": resultado["prompt_usado"],
    }
