# -*- coding: utf-8 -*-
"""
Extração de dados da mesa de poker a partir de uma imagem usando um LLM com visão (OCR).
Suporta modo em uma única imagem ou por regiões (quadrantes): contexto, community_cards, hole_cards.
Retorna um JSON estruturado para alimentar o consultor (segundo LLM).
"""
from __future__ import annotations
import json
import os
import re
import tempfile
from typing import Any, Optional

# Schema esperado do JSON extraído (para validação e defaults)
SCHEMA_EXTRACAO = {
    "total_number_of_players": 2,       # int: número de jogadores na mão
    "position": "BTN",                  # str: UTG, UTG+1, HJ, CO, BTN, SB, BB
    "round": "preflop",                  # str: preflop | flop | turn | river (rodada atual)
    "player_cards": [],                 # list[str]: 0 ou 2 cartas (vazio se sem cartas na mão)
    "community_cards": [],              # list[str]: vazio [] no preflop; 3 (flop), 4 (turn) ou 5 (river)
    "pot": 0.0,                         # float: pot (pote) — total no pote / aposta a pagar (em BB ou valor)
    "risk_based_on_position_player": "", # str: descrição opcional do risco pela posição
}

PROMPT_EXTRACAO = """You are analyzing a Texas Hold'em poker table image (screenshot or photo).

Extract ONLY the following information and respond with a single valid JSON object, no other text or markdown.

Required keys (use exact names):
- "total_number_of_players": integer, number of active players at the table (usernames visible).
- "position": string, my position. One of: UTG, UTG+1, HJ, CO, BTN, SB, BB. Use two-step reasoning. Step 1: Where is the dealer button (D)? The D is a circular chip with the letter "D" in the middle, in front of the Button (BTN) player. Describe which seat or area has it (e.g. top, right, bottom center). How many seats at the table? Step 2: I am always the player at the BOTTOM CENTER of the table. Given where the D is, positions go CLOCKWISE from BTN: BTN (has D), then SB, BB, UTG, UTG+1, HJ, CO. What is my position? If the D is not visible or unclear, still output one valid position (e.g. BTN).
- "player_cards": array of 0 or 2 strings, your hole cards. Format: value (2-9, T, J, Q, K, A) + suit (s, h, d, c). Examples: "As", "Kh". Use [] if no cards in hand, folded, or not visible. I am the player below the table, my username is {usernamePlayer}.
- "community_cards": array of community cards in the same format. Empty [] if no board cards yet. Otherwise 3 (flop), 4 (turn) or 5 (river) cards in the middle of the table.
- "pot": number, pot size — money already in the pot or current bet to call (in BB or absolute). Use 0 if unknown.
- "risk_based_on_position_player": string, brief position risk (e.g. "early position, first to act"). Empty string if not relevant.

If unclear, use defaults: position "BTN", player_cards [], community_cards [], total_number_of_players 2, pot 0, risk_based_on_position_player "".

Output ONLY the JSON object, no code block, no explanation."""

# Prompts por região (quando use_regions=True): cada imagem é analisada com schema específico.
PROMPT_REGIAO_CONTEXTO = """You are analyzing the FULL poker table screenshot (context only).

This crop shows the CENTER of the table: my seat (bottom center) and neighboring seats. Use two-step reasoning for position.

Step 1 — Locate the dealer button: The D is a circular chip with the letter "D" in the middle, in front of the BTN player. Where do you see it? (e.g. which seat or area: top, left, right, bottom center?) How many seats/players are visible?

Step 2 — My position: I am the player at the BOTTOM CENTER of this crop. Positions go CLOCKWISE from the player who has the D: BTN (has D), then SB, BB, UTG, UTG+1, HJ, CO. What is my position?

From this image extract ONLY (output a single valid JSON with exactly these keys):
- "total_number_of_players": integer, number of active players at the table (from Step 1 or count; exclude "Sitting Out" if possible).
- "position": string, my position from Step 2. One of: UTG, UTG+1, HJ, CO, BTN, SB, BB. If the D is not visible, still output one valid position (e.g. BTN).
- "pot": number, the pot value shown (e.g. "Pot: 945" or similar). Use 0 if not visible.
- "risk_based_on_position_player": string, brief note (e.g. "button, last to act"). Empty string if not relevant.

Do NOT extract player_cards, community_cards or round; those come from other crops or are set automatically.
Respond with ONLY the JSON object. No other text."""

PROMPT_REGIAO_COMMUNITY = """You are analyzing ONLY the CENTRAL part of the poker table where the board (community) cards are.

This crop shows only the community cards (flop/turn/river). Identify each card.
Format: value (2-9, T, J, Q, K, A) + suit (s=spades, h=hearts, d=diamonds, c=clubs). Example: "Kc", "3d", "7h", "9s", "9c".

Respond with a single valid JSON: { "community_cards": [ "card1", "card2", ... ] }
- If you see 0 cards, use [].
- Flop = 3 cards, turn = 4, river = 5. No other keys. No explanation."""

PROMPT_REGIAO_HOLE = """You are analyzing ONLY the crop showing MY hole cards (bottom center of the table).

This crop shows only my two private cards. Identify each card.
Format: value (2-9, T, J, Q, K, A) + suit (s=spades, h=hearts, d=diamonds, c=clubs). Examples: "Jc", "Td".

Respond with a single valid JSON: { "player_cards": [ "card1", "card2" ] }
- If no cards or folded/not visible, use [].
- Exactly 0 or 2 cards. No other keys. No explanation."""

# Prompt para a imagem composta dos 6 assentos: identificar BTN pelo D dentro do recorte do assento
PROMPT_SEATS = """You are viewing a composite image of a 6-max poker table. It has exactly 6 labeled crops, one per seat:

Row 1: seat_12h (top), seat_2h (top-right), seat_4h (right).
Row 2: seat_6h labeled "Hero" (bottom center — that is me), seat_8h (bottom-left), seat_10h (top-left).

The dealer button (D) is a white circle with the letter "D" and appears INSIDE or right next to one of these 6 seat crops — that seat is the Button (BTN). Look at each crop: in which one do you see the D? The D is usually near the player's name or stack in that crop.

Important: Do NOT guess from position. The D is visible inside exactly one of these 6 crops. If you see the D in the crop labeled "Hero" (seat_6h), then button_seat is seat_6h. If you see the D in the crop to the left of Hero (seat_8h), then button_seat is seat_8h. And so on.

Also count how many seats show an active player (name/stack; exclude "Sitting Out").

Respond with ONLY a valid JSON with exactly these keys:
- "button_seat": string, one of: seat_12h, seat_2h, seat_4h, seat_6h, seat_8h, seat_10h (the seat crop IN WHICH you see the dealer button D).
- "total_number_of_players": integer (2–6).

Output only the JSON object. No explanation."""


# Ordem dos assentos no sentido horário (12h → 2h → 4h → 6h → 8h → 10h); posições 6-max na mesma ordem a partir do BTN
_ORDEM_SEATS = ("seat_12h", "seat_2h", "seat_4h", "seat_6h", "seat_8h", "seat_10h")
_POSICOES_6MAX = ("BTN", "SB", "BB", "UTG", "UTG+1", "CO")


def _posicao_hero_from_button_seat(button_seat: str) -> str:
    """
    Dado o assento que tem o botão dealer (BTN), retorna a posição do Hero (sempre seat_6h).
    Ordem horária: BTN → SB → BB → UTG → UTG+1 → CO.
    """
    button_seat = (button_seat or "").strip().lower()
    if not button_seat or button_seat not in _ORDEM_SEATS:
        return "BTN"
    btn_idx = _ORDEM_SEATS.index(button_seat)
    hero_idx = _ORDEM_SEATS.index("seat_6h")
    # Posição do Hero = deslocamento a partir do BTN no sentido horário
    pos_idx = (hero_idx - btn_idx) % 6
    return _POSICOES_6MAX[pos_idx]


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


def round_from_community_cards(community_cards: list) -> str:
    """
    Define o round de forma determinística pelo número de cartas no board (OCR).
    preflop = 0 cartas; flop = 3; turn = 4; river = 5.
    """
    n = len(community_cards) if community_cards else 0
    return {0: "preflop", 3: "flop", 4: "turn", 5: "river"}.get(n, "preflop")


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
    # round não é extraído pelo OCR; é definido por round_from_community_cards abaixo
    if "player_cards" in bruto and isinstance(bruto["player_cards"], list):
        out["player_cards"] = [str(c).strip() for c in bruto["player_cards"] if str(c).strip()][:2]
    if "community_cards" in bruto and isinstance(bruto["community_cards"], list):
        out["community_cards"] = [str(c).strip() for c in bruto["community_cards"] if str(c).strip()][:5]
    # Round definido deterministicamente pela contagem de community_cards (OCR)
    out["round"] = round_from_community_cards(out["community_cards"])
    if out["round"] == "preflop":
        out["community_cards"] = []
    # pot: aceita "pot" (oficial) ou "money_beted" (legado) do LLM
    for key in ("pot", "money_beted"):
        if key in bruto:
            try:
                out["pot"] = float(bruto[key])
                break
            except (TypeError, ValueError):
                pass
    if "risk_based_on_position_player" in bruto:
        out["risk_based_on_position_player"] = str(bruto["risk_based_on_position_player"]).strip()
    return out


def _extrair_posicao_por_assentos(caminho_imagem: str, llm_kwargs: dict) -> dict:
    """
    Monta a imagem composta dos 6 assentos + dealer_button, chama o LLM uma vez
    e retorna dict com position (do Hero) e total_number_of_players.
    """
    from image_regions import montar_imagem_assentos_composite

    composite = montar_imagem_assentos_composite(caminho_imagem)
    fd, path_composite = tempfile.mkstemp(suffix=".png", prefix="poker_seats_")
    os.close(fd)
    try:
        composite.save(path_composite, "PNG")
        raw = _chamar_vision_llm(PROMPT_SEATS, path_composite, **llm_kwargs)
        data = _extrair_json_da_resposta(raw)
        button_seat = (data.get("button_seat") or "").strip().lower()
        total = data.get("total_number_of_players")
        position = _posicao_hero_from_button_seat(button_seat)
        out = {"position": position}
        if total is not None:
            try:
                out["total_number_of_players"] = int(total)
            except (TypeError, ValueError):
                out["total_number_of_players"] = 2
        return out
    finally:
        try:
            if os.path.isfile(path_composite):
                os.remove(path_composite)
        except OSError:
            pass


def _extrair_por_regioes(
    caminho_imagem: str,
    llm_kwargs: dict,
    use_seat_crops: bool = True,
) -> dict:
    """
    Recorta a imagem em regiões e chama o LLM por etapa. Se use_seat_crops=True,
    primeiro usa a imagem composta dos 6 assentos + D para obter position e
    total_number_of_players; depois usa position (pot/risk), community_cards e hole_cards.
    """
    from image_regions import salvar_regioes_em_temp

    paths_por_regiao = {nome: path for nome, path in salvar_regioes_em_temp(caminho_imagem)}
    try:
        merged = dict(SCHEMA_EXTRACAO)

        if use_seat_crops:
            # 0) Assentos + dealer button → position e total_number_of_players (mais preciso)
            seat_data = _extrair_posicao_por_assentos(caminho_imagem, llm_kwargs)
            merged["position"] = seat_data.get("position", "BTN")
            if "total_number_of_players" in seat_data:
                merged["total_number_of_players"] = seat_data["total_number_of_players"]
            # 1) Região position só para pot e risk (position já veio dos assentos)
            path_ctx = paths_por_regiao["position"]
            raw_ctx = _chamar_vision_llm(PROMPT_REGIAO_CONTEXTO, path_ctx, **llm_kwargs)
            ctx = _extrair_json_da_resposta(raw_ctx)
            for key in ("pot", "risk_based_on_position_player"):
                if key in ctx:
                    merged[key] = ctx[key]
            if "total_number_of_players" not in merged and "total_number_of_players" in ctx:
                merged["total_number_of_players"] = ctx["total_number_of_players"]
        else:
            # 1) Região position (contexto completo: position, pot, total, risk)
            path_ctx = paths_por_regiao["position"]
            raw_ctx = _chamar_vision_llm(PROMPT_REGIAO_CONTEXTO, path_ctx, **llm_kwargs)
            ctx = _extrair_json_da_resposta(raw_ctx)
            for key in ("total_number_of_players", "position", "pot", "risk_based_on_position_player"):
                if key in ctx:
                    merged[key] = ctx[key]

        # 2) Região central → community_cards
        path_comm = paths_por_regiao["community_cards"]
        raw_comm = _chamar_vision_llm(PROMPT_REGIAO_COMMUNITY, path_comm, **llm_kwargs)
        comm = _extrair_json_da_resposta(raw_comm)
        if "community_cards" in comm and isinstance(comm["community_cards"], list):
            merged["community_cards"] = [str(c).strip() for c in comm["community_cards"] if str(c).strip()][:5]

        # 3) Região hole cards → player_cards
        path_hole = paths_por_regiao["hole_cards"]
        raw_hole = _chamar_vision_llm(PROMPT_REGIAO_HOLE, path_hole, **llm_kwargs)
        hole = _extrair_json_da_resposta(raw_hole)
        if "player_cards" in hole and isinstance(hole["player_cards"], list):
            merged["player_cards"] = [str(c).strip() for c in hole["player_cards"] if str(c).strip()][:2]

        # Round definido deterministicamente pela contagem de community_cards (OCR)
        merged["round"] = round_from_community_cards(merged.get("community_cards") or [])
        if merged["round"] == "preflop":
            merged["community_cards"] = []

        return _normalizar_dados(merged)
    finally:
        for _nome, path in paths_por_regiao.items():
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass


def extrair_json_da_imagem(
    caminho_imagem: str,
    *,
    username_player: Optional[str] = None,
    position_manual: Optional[str] = None,
    use_regions: bool = False,
    use_seat_crops: bool = True,
    use_api: Optional[bool] = None,
    api_base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    api_model: Optional[str] = None,
    use_openai: Optional[bool] = None,
    openai_api_key: Optional[str] = None,
    openai_model: Optional[str] = None,
    modelo_ollama: str = "llama3.2-vision",
) -> dict:
    """
    Analisa uma imagem da mesa de poker com um LLM de visão e retorna um dict
    com: total_number_of_players, position, round, player_cards, community_cards, pot, risk_based_on_position_player.

    position_manual: se informado (ex.: "BTN", "SB"), substitui a position extraída pelo OCR.
    use_regions: se True, recorta a imagem em regiões e analisa cada uma com schema correspondente.
    use_seat_crops: se True e use_regions=True, usa primeiro a imagem composta dos 6 assentos + D para
                    determinar com precisão quem é o BTN e a posição do Hero (recomendado).
    username_player: nome do jogador na mesa (usado no prompt único quando use_regions=False).
    """
    if not os.path.isfile(caminho_imagem):
        raise FileNotFoundError(f"Imagem não encontrada: {caminho_imagem}")

    llm_kwargs = {
        "use_api": use_api,
        "api_base_url": api_base_url,
        "api_key": api_key,
        "api_model": api_model,
        "use_openai": use_openai,
        "openai_api_key": openai_api_key,
        "openai_model": openai_model,
        "modelo": modelo_ollama,
    }

    if use_regions:
        out = _extrair_por_regioes(caminho_imagem, llm_kwargs, use_seat_crops=use_seat_crops)
    else:
        prompt = _montar_prompt_extracao(username_player)
        raw = _chamar_vision_llm(
            prompt,
            caminho_imagem,
            **llm_kwargs,
        )
        bruto = _extrair_json_da_resposta(raw)
        out = _normalizar_dados(bruto)

    if position_manual and str(position_manual).strip():
        out["position"] = str(position_manual).strip().upper()
    return out
