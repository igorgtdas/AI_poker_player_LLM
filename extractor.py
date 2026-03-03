# -*- coding: utf-8 -*-
"""
Extração de dados da mesa de poker a partir de uma imagem usando um LLM com visão (OCR).
Retorna um JSON estruturado para alimentar o consultor (segundo LLM).
"""
from __future__ import annotations
import json
import os
import re
from typing import Any, Optional

# Schema esperado do JSON extraído (para validação e defaults)
SCHEMA_EXTRACAO = {
    "total_number_of_players": 2,       # int: número de jogadores na mão
    "position": "BTN",                  # str: UTG, UTG+1, HJ, CO, BTN, SB, BB
    "player_cards": [],                  # list[str]: 0 ou 2 cartas (vazio se sem cartas na mão)
    "community_cards": [],                 # list[str]: 0 (preflop), 3 (flop), 4 (turn), 5 (river)
    "money_beted": 0.0,              # float: total de dollars apostadas (pote/contexto)
    "risk_based_on_position_player": "",    # str: descrição opcional do risco pela posição
}

PROMPT_EXTRACAO = """You are analyzing a Texas Hold'em poker table image (screenshot or photo).

Extract ONLY the following information and respond with a single valid JSON object, no other text or markdown.

Required keys (use exact names):
- "total_number_of_players": The total number of actived players is defined by the number of usernames at the table. Each player is identified by a unique username and has an associated hand value in US$ dollars.
- "position": string, your position. One of: UTG, UTG+1, HJ, CO, BTN, SB, BB. Check the position based on Dealer Button of the POKER stars
- "player_cards": array of 0 or 2 strings, your hole cards. Format per card: value (2-9, T, J, Q, K, A) + suit (s=spades, h=hearts, d=diamonds, c=clubs). Examples: "As", "Kh", "Td", "7c". Use empty [] if you have no cards in hand, folded, or cards are not visible. I am the player below of the table, my username is {usernamePlayer}
- "community_cards": array of 0, 3, 4, or 5 community cards in the same format. Empty [] if preflop. This cards are together on the middle of the table
- "money_beted": money has beted on the middle of the table are already in the pot (or current bet to call in BB). Use 0 if unknown.
- "risk_based_on_position_player": string, brief assessment of position risk (e.g. "early position, first to act" or "button, last to act"). Empty string if not relevant.

If something is not visible or unclear, use sensible defaults: position "BTN", player_cards [], community_cards [], total_number_of_players 2, money_beted 0, risk_based_on_position_player "".

Output ONLY the JSON object, no code block, no explanation."""


def _montar_prompt_extracao(username_player: Optional[str] = None) -> str:
    """Substitui a variável {usernamePlayer} no prompt de extração."""
    nome = (username_player or "").strip() or "the player at the bottom of the table"
    return PROMPT_EXTRACAO.format(usernamePlayer=nome)


def _chamar_vision_llm(prompt: str, caminho_imagem: str, **kwargs: Any) -> str:
    """Chama o LLM de visão. Se GROQ_API_KEY estiver definida, usa Groq (Llama 4 Scout com vision)."""
    from advisor import consultar_llama_vision
    return consultar_llama_vision(
        prompt,
        caminho_imagem=caminho_imagem,
        **kwargs,
    )


def _extrair_json_da_resposta(texto: str) -> dict:
    """Tenta extrair um objeto JSON do texto (pode vir dentro de ```json ... ```)."""
    texto = texto.strip()
    # Remove bloco markdown
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", texto)
    if match:
        texto = match.group(1).strip()
    # Primeiro objeto JSON encontrado
    start = texto.find("{")
    if start == -1:
        raise ValueError("Nenhum JSON encontrado na resposta do LLM")
    depth = 0
    end = -1
    for i in range(start, len(texto)):
        if texto[i] == "{":
            depth += 1
        elif texto[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("JSON malformado na resposta")
    return json.loads(texto[start:end])


def _normalizar_dados(bruto: dict) -> dict:
    """Normaliza e preenche defaults do dict extraído."""
    out = dict(SCHEMA_EXTRACAO)
    if "total_number_of_players" in bruto:
        try:
            out["total_number_of_players"] = int(bruto["total_number_of_players"])
        except (TypeError, ValueError):
            pass
    if "position" in bruto and str(bruto["position"]).strip():
        out["position"] = str(bruto["position"]).strip().upper()
    if "player_cards" in bruto and isinstance(bruto["player_cards"], list):
        out["player_cards"] = [str(c).strip() for c in bruto["player_cards"] if str(c).strip()][:2]
    if "community_cards" in bruto and isinstance(bruto["community_cards"], list):
        out["community_cards"] = [str(c).strip() for c in bruto["community_cards"] if str(c).strip()][:5]
    if "money_beted" in bruto:
        try:
            out["money_beted"] = float(bruto["money_beted"])
        except (TypeError, ValueError):
            pass
    if "risk_based_on_position_player" in bruto:
        out["risk_based_on_position_player"] = str(bruto["risk_based_on_position_player"]).strip()
    return out


def extrair_json_da_imagem(
    caminho_imagem: str,
    *,
    username_player: Optional[str] = None,
    use_api: Optional[bool] = None,
    api_base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_model: Optional[str] = None,
    modelo_ollama: str = "llama3.2-vision",
) -> dict:
    """
    Analisa uma imagem da mesa de poker com um LLM de visão e retorna um dict
    com: total_number_of_players, position, player_cards, community_cards, money_beted, risk_based_on_position_player.
    username_player: nome do jogador (username) na mesa; usado no prompt para identificar "player_cards".
    """
    if not os.path.isfile(caminho_imagem):
        raise FileNotFoundError(f"Imagem não encontrada: {caminho_imagem}")

    prompt = _montar_prompt_extracao(username_player)
    raw = _chamar_vision_llm(
        prompt,
        caminho_imagem,
        use_api=use_api,
        api_base_url=api_base_url,
        api_key=api_key,
        api_model=api_model,
        modelo=modelo_ollama,
    )
    bruto = _extrair_json_da_resposta(raw)
    return _normalizar_dados(bruto)
