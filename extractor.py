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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    "player_bets": [],                  # list[dict]: por assento — seat, name, dealer_button (valor apostado removido: confundia com stack)
    "button_seat": "",                  # str: assento do BTN (ex.: seat_6h) para mapear posição por jogador
    "hand_sequence": "",                # str: melhor mão atual (ex.: "pair", "straight", "flush") a partir das cartas
    "dealer_button_nao_identificado": False,  # bool: True quando button_seat está vazio (dealer não identificado)
    "facing_bet_to_call": False,       # bool: True se na UI aparece "Call" (alguém apostou; hero pode Fold ou Call)
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
- "facing_bet_to_call": boolean. If you see a "Call" or "Call X" button (or similar) in the UI, it means someone has bet and hero can fold or call; set true. Otherwise false.

If unclear, use defaults: position "BTN", player_cards [], community_cards [], total_number_of_players 2, pot 0, risk_based_on_position_player "", facing_bet_to_call false.

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
- "facing_bet_to_call": boolean. If you see a "Call" or "Call X" button in the UI (someone has bet; hero can fold or call), set true. Otherwise false.

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

# Descrição do dealer button para os prompts: botão físico da mesa (não confundir com texto "D" em chips ou UI).
# Use como referência fixa para comparação; o dealer só é avaliado dentro dos crops dos assentos (não há crop isolado).
DESCRICAO_DEALER_BUTTON = (
    "The dealer button is a physical puck on the table: a circular disk, light grey or off-white, "
    "with a single bold capital letter 'D' in dark grey in the center (sans-serif). "
    "It may have a subtle darker border or shadow. It sits on the table felt (dark background). "
    "Do not confuse it with green UI buttons, chip labels, or other text; only this specific circular puck counts."
)
# Caminho da imagem de referência do dealer (para comparação, se necessário). Coloque o PNG do puck em assets/.
DEALER_BUTTON_REFERENCE_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "dealer_button_reference.png")

# Prompt para a imagem composta dos 6 assentos: dealer_button por crop e apostas; total_number_of_players é calculado depois (por nome não vazio).
PROMPT_SEATS = """You are viewing a composite image of a 6-max poker table. It has exactly 6 labeled crops, one per seat:

Row 1: seat_12h (top), seat_2h (top-right), seat_4h (right).
Row 2: seat_6h labeled "Hero" (bottom center — that is me), seat_8h (bottom-left), seat_10h (top-left).

DEALER BUTTON (check in EACH crop):
""" + DESCRICAO_DEALER_BUTTON + """

For EACH seat you must do two things:

A) dealer_button — For that seat's crop only: verify if the dealer button (as described above) is contained in this crop. If yes, set "dealer_button": true for that seat; if no, set "dealer_button": false. Check every crop: seat_12h, then seat_2h, then seat_4h, then seat_6h, then seat_8h, then seat_10h. Exactly one seat should have dealer_button true.

B) name — For that same crop: "name": the player username/nick visible (e.g. "SLOW GIN 1962", "Hero"). Use "" (empty string) if the seat is empty, "Sitting Out", or no player visible (do not count this seat as a player).

Respond with ONLY a valid JSON with exactly these keys:
- "button_seat": string, the seat whose crop contains the dealer button (one of: seat_12h, seat_2h, seat_4h, seat_6h, seat_8h, seat_10h). Must match the seat that has dealer_button true in player_bets.
- "player_bets": array of 6 objects, one per seat in this order: seat_12h, seat_2h, seat_4h, seat_6h, seat_8h, seat_10h. Each object: { "seat": "seat_12h", "name": "username or empty string", "dealer_button": true or false }. For each seat, verify if the dealer button is in THAT crop and set dealer_button accordingly; use "" for name if no player at that seat.

Example: "player_bets": [ {"seat": "seat_12h", "name": "SLOW GIN", "dealer_button": false}, {"seat": "seat_2h", "name": "", "dealer_button": false}, {"seat": "seat_4h", "name": "tiwtiv116", "dealer_button": false}, {"seat": "seat_6h", "name": "Hero", "dealer_button": true}, {"seat": "seat_8h", "name": "lav0828", "dealer_button": false}, {"seat": "seat_10h", "name": "smos203", "dealer_button": false} ]

Output only the JSON object. No explanation."""

# Prompt para um único crop de assento: extrair name e dealer_button (sem bet: confundia com stack).
def _prompt_um_assento(seat: str) -> str:
    hero_note = ' This seat is "Hero" (bottom center, the player whose perspective we use).' if seat == "seat_6h" else ""
    return f"""You are viewing the crop for a single seat at a poker table. This image shows ONLY the area for seat "{seat}".{hero_note}

DEALER BUTTON — """ + DESCRICAO_DEALER_BUTTON + """

Tasks for THIS crop only:
1) dealer_button: Verify if the dealer button (as described above) is visible in this crop. If yes set "dealer_button": true; if no set "dealer_button": false. If in doubt whether it is in the image or not, prefer false. Only one seat on the whole table can have the dealer button; when uncertain, use false.
2) "name": the player username/nick visible in this crop (e.g. "SLOW GIN 1962", "Hero"). Use "" (empty string) if the seat is empty, "Sitting Out", or no player visible.

Respond with ONLY a valid JSON with exactly these keys:
- "name": string (username or "" if empty seat)
- "dealer_button": true or false (prefer false when in doubt)

Output only the JSON object. No explanation."""


# Prompt para o recorte seat_12h (topo da mesa): extrair apenas o valor do pot
PROMPT_SEAT_12H_POT = """You are viewing a crop from the TOP of a poker table (seat at 12 o'clock position). This area often shows the pot value.

Extract the pot value if visible (e.g. "Pot: 945", "945", or a number next to "Pot").
Respond with ONLY a valid JSON with exactly this key:
- "pot": number (the pot value; use 0 if not visible or unclear).

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


def posicao_por_assento(button_seat: str) -> dict:
    """
    Retorna mapeamento seat -> posição (BTN, SB, BB, UTG, UTG+1, CO) para a LLM
    interpretar intenção por posição. Ordem horária a partir do BTN.
    """
    button_seat = (button_seat or "").strip().lower()
    if not button_seat or button_seat not in _ORDEM_SEATS:
        return {s: _POSICOES_6MAX[i] for i, s in enumerate(_ORDEM_SEATS)}
    btn_idx = _ORDEM_SEATS.index(button_seat)
    return {
        seat: _POSICOES_6MAX[(i - btn_idx) % 6]
        for i, seat in enumerate(_ORDEM_SEATS)
    }


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


def _risk_descricao_por_posicao(position: str) -> str:
    """Descrição do risco/contexto pela posição (inglês, para o schema). Sempre derivada da position, não do LLM."""
    pos = (position or "").strip().upper()
    d = {
        "BTN": "button, last to act post-flop",
        "SB": "small blind, first to act post-flop",
        "BB": "big blind, already invested in pot",
        "UTG": "early position, first to act preflop",
        "UTG+1": "early position, second to act",
        "HJ": "middle position, hijack",
        "CO": "cutoff, late position, one before button",
    }
    return d.get(pos, "")


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
    if "button_seat" in bruto and str(bruto["button_seat"]).strip():
        out["button_seat"] = str(bruto["button_seat"]).strip().lower()
    if "dealer_button_nao_identificado" in bruto:
        out["dealer_button_nao_identificado"] = bool(bruto["dealer_button_nao_identificado"])
    # Garantir: button_seat vazio → dealer não identificado
    if not (out.get("button_seat") or "").strip():
        out["dealer_button_nao_identificado"] = True
    if "hand_sequence" in bruto and str(bruto["hand_sequence"]).strip():
        out["hand_sequence"] = str(bruto["hand_sequence"]).strip().lower()
    if "facing_bet_to_call" in bruto:
        val = bruto["facing_bet_to_call"]
        out["facing_bet_to_call"] = bool(val) if not isinstance(val, str) else str(val).strip().lower() in ("true", "1", "yes")
    # risk_based_on_position_player sempre derivado da position (não do LLM)
    out["risk_based_on_position_player"] = _risk_descricao_por_posicao(out.get("position", ""))
    if "player_bets" in bruto and isinstance(bruto["player_bets"], list):
        out["player_bets"] = []
        for x in bruto["player_bets"][:6]:
            if not isinstance(x, dict):
                continue
            db = x.get("dealer_button", False)
            if isinstance(db, str):
                db = db.strip().lower() in ("true", "1", "yes")
            else:
                db = bool(db)
            out["player_bets"].append({
                "seat": str(x.get("seat", "")),
                "name": str(x.get("name", "")),
                "dealer_button": db,
            })
    return out


def _extrair_posicao_por_assentos(caminho_imagem: str, llm_kwargs: dict) -> dict:
    """
    Monta a imagem composta apenas dos 6 assentos (sem crop isolado do dealer).
    O LLM avalia cada crop de assento e seta dealer_button true no assento onde
    o puck do dealer (circular, cinza claro, D escuro) aparece. Retorna position e total_number_of_players.
    """
    from image_regions import montar_imagem_assentos_composite

    composite = montar_imagem_assentos_composite(caminho_imagem)
    fd, path_composite = tempfile.mkstemp(suffix=".png", prefix="poker_seats_")
    os.close(fd)
    try:
        composite.save(path_composite, "PNG")
        raw = _chamar_vision_llm(PROMPT_SEATS, path_composite, **llm_kwargs)
        data = _extrair_json_da_resposta(raw)
        # Monta player_bets com dealer_button; deriva button_seat e total_number_of_players
        button_seat_from_bets = ""
        if "player_bets" in data and isinstance(data["player_bets"], list):
            out_bets = []
            for item in data["player_bets"][:6]:
                if not isinstance(item, dict):
                    continue
                seat = (item.get("seat") or "").strip().lower()
                name = (item.get("name") or "").strip()
                dealer_btn = item.get("dealer_button", False)
                if isinstance(dealer_btn, str):
                    dealer_btn = dealer_btn.strip().lower() in ("true", "1", "yes")
                else:
                    dealer_btn = bool(dealer_btn)
                if seat in _ORDEM_SEATS:
                    out_bets.append({"seat": seat, "name": name, "dealer_button": dealer_btn})
                    if dealer_btn:
                        button_seat_from_bets = seat
            out = {"player_bets": out_bets}
        else:
            out = {"player_bets": []}
        # total_number_of_players: contagem determinística — só assentos com name não vazio estão na mesa
        total_players = sum(1 for p in out["player_bets"] if (p.get("name") or "").strip())
        out["total_number_of_players"] = max(2, min(6, total_players)) if total_players else 2
        # Garantir só um dealer_button true (primeiro na ordem vence)
        idx_first = next((i for i, p in enumerate(out["player_bets"]) if p.get("dealer_button")), None)
        if idx_first is not None:
            for i, p in enumerate(out["player_bets"]):
                p["dealer_button"] = i == idx_first
        # Position definida pelo assento com dealer_button=true; fallback para button_seat do LLM
        button_seat = button_seat_from_bets or (data.get("button_seat") or "").strip().lower()
        if button_seat not in _ORDEM_SEATS:
            button_seat = ""
        if idx_first is not None:
            button_seat = out["player_bets"][idx_first]["seat"]
        position = _posicao_hero_from_button_seat(button_seat)
        out["position"] = position
        out["button_seat"] = button_seat
        out["dealer_button_nao_identificado"] = (button_seat == "")
        return out
    finally:
        try:
            if os.path.isfile(path_composite):
                os.remove(path_composite)
        except OSError:
            pass


def _processar_um_crop_assento(seat: str, path: str, llm_kwargs: dict) -> dict:
    """Processa um único crop de assento (para execução paralela). Retorna dict com seat, name, dealer_button."""
    if not path or not os.path.isfile(path):
        return {"seat": seat, "name": "", "dealer_button": False}
    try:
        prompt = _prompt_um_assento(seat)
        raw = _chamar_vision_llm(prompt, path, **llm_kwargs)
        data = _extrair_json_da_resposta(raw)
    except Exception:
        return {"seat": seat, "name": "", "dealer_button": False}
    name = (data.get("name") or "").strip()
    dealer_btn = data.get("dealer_button", False)
    if isinstance(dealer_btn, str):
        dealer_btn = dealer_btn.strip().lower() in ("true", "1", "yes")
    else:
        dealer_btn = bool(dealer_btn)
    return {"seat": seat, "name": name, "dealer_button": dealer_btn}


def _extrair_posicao_por_assentos_crop_a_crop(paths_por_regiao: dict, llm_kwargs: dict) -> dict:
    """
    Monta player_bets avaliando cada crop de assento em paralelo (6 chamadas LLM simultâneas).
    Usa paths_por_regiao (seat_12h -> path, etc.). Retorna position, total_number_of_players, button_seat e player_bets.
    """
    results_by_seat = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_processar_um_crop_assento, seat, paths_por_regiao.get(seat) or "", llm_kwargs): seat
            for seat in _ORDEM_SEATS
        }
        for future in as_completed(futures):
            seat = futures[future]
            try:
                results_by_seat[seat] = future.result()
            except Exception:
                results_by_seat[seat] = {"seat": seat, "name": "", "dealer_button": False}
    # Manter ordem dos assentos
    out_bets = [results_by_seat.get(seat, {"seat": seat, "name": "", "dealer_button": False}) for seat in _ORDEM_SEATS]
    # Garantir que só um assento tenha dealer_button true: primeiro true na ordem dos assentos vence
    idx_first_true = None
    for i, p in enumerate(out_bets):
        if p.get("dealer_button"):
            idx_first_true = i
            break
    if idx_first_true is not None:
        for i, p in enumerate(out_bets):
            p["dealer_button"] = i == idx_first_true
        button_seat_from_bets = out_bets[idx_first_true]["seat"]
    else:
        button_seat_from_bets = ""
    total_players = sum(1 for p in out_bets if (p.get("name") or "").strip())
    out = {
        "player_bets": out_bets,
        "total_number_of_players": max(2, min(6, total_players)) if total_players else 2,
        "button_seat": button_seat_from_bets if button_seat_from_bets in _ORDEM_SEATS else "",
        "position": _posicao_hero_from_button_seat(button_seat_from_bets),
        "dealer_button_nao_identificado": not button_seat_from_bets,
    }
    return out


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
    from image_regions import salvar_regioes_em_temp, salvar_regioes_para_debug

    # Debug: salvar os crops em capturas/debug_regions/<timestamp> para inspecionar position
    if os.environ.get("DEBUG_SAVE_REGIONS", "").strip().lower() in ("1", "true", "yes"):
        try:
            pasta_debug = salvar_regioes_para_debug(caminho_imagem)
            import sys
            print(f"[DEBUG] Regiões salvas em: {pasta_debug}", file=sys.stderr)
        except Exception:
            pass

    paths_por_regiao = {nome: path for nome, path in salvar_regioes_em_temp(caminho_imagem)}
    try:
        merged = dict(SCHEMA_EXTRACAO)

        if use_seat_crops:
            # 0) Assentos → position, total_number_of_players e player_bets (um LLM por crop, maior acurácia)
            seat_data = _extrair_posicao_por_assentos_crop_a_crop(paths_por_regiao, llm_kwargs)
            merged["position"] = seat_data.get("position", "BTN")
            if "total_number_of_players" in seat_data:
                merged["total_number_of_players"] = seat_data["total_number_of_players"]
            if "player_bets" in seat_data and isinstance(seat_data["player_bets"], list):
                merged["player_bets"] = seat_data["player_bets"]
            if seat_data.get("button_seat"):
                merged["button_seat"] = seat_data["button_seat"]
            # button_seat vazio = dealer não identificado → dealer_button_nao_identificado True no schema final
            merged["dealer_button_nao_identificado"] = not bool((merged.get("button_seat") or "").strip())
            # 1a) Pot a partir do recorte seat_12h (topo da mesa), mais confiável que o geral
            path_seat_12h = paths_por_regiao.get("seat_12h")
            if path_seat_12h:
                try:
                    raw_pot = _chamar_vision_llm(PROMPT_SEAT_12H_POT, path_seat_12h, **llm_kwargs)
                    pot_data = _extrair_json_da_resposta(raw_pot)
                    if "pot" in pot_data:
                        try:
                            merged["pot"] = float(pot_data["pot"])
                        except (TypeError, ValueError):
                            pass
                except Exception:
                    pass
            # 1b) Região position só para risk e total (pot já veio do seat_12h)
            path_ctx = paths_por_regiao["position"]
            raw_ctx = _chamar_vision_llm(PROMPT_REGIAO_CONTEXTO, path_ctx, **llm_kwargs)
            ctx = _extrair_json_da_resposta(raw_ctx)
            for key in ("risk_based_on_position_player", "facing_bet_to_call"):
                if key in ctx:
                    merged[key] = ctx[key]
            if "total_number_of_players" not in merged and "total_number_of_players" in ctx:
                merged["total_number_of_players"] = ctx["total_number_of_players"]
            # Se o pot do seat_12h não veio, usa o da região position como fallback
            if ("pot" not in ctx or merged.get("pot", 0) == 0) and "pot" in ctx:
                try:
                    merged["pot"] = float(ctx["pot"])
                except (TypeError, ValueError):
                    pass
        else:
            # 1) Região position (contexto completo: position, pot, total, risk)
            path_ctx = paths_por_regiao["position"]
            raw_ctx = _chamar_vision_llm(PROMPT_REGIAO_CONTEXTO, path_ctx, **llm_kwargs)
            ctx = _extrair_json_da_resposta(raw_ctx)
            for key in ("total_number_of_players", "position", "pot", "risk_based_on_position_player", "facing_bet_to_call"):
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

        # Sequência da mão (pair, straight, flush, etc.) a partir das cartas
        try:
            from poker_engine import nome_sequencia
            seq = nome_sequencia(
                merged.get("player_cards") or [],
                merged.get("community_cards") or [],
            )
            if seq:
                merged["hand_sequence"] = seq
        except Exception:
            pass

        # Schema final: button_seat vazio = dealer não identificado
        merged["dealer_button_nao_identificado"] = not bool((merged.get("button_seat") or "").strip())
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
    use_groq: Optional[bool] = None,
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
        "use_groq": use_groq,
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
