# -*- coding: utf-8 -*-
"""
Motor de decisão pré-flop: usa dados estruturados (cartas, posição, tamanho da mesa, stack, cenário)
para recomendar ação (fold, call, raise, etc.) com base em ranges e cenários típicos.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

RANK_ORDER = "23456789TJQKA"


@dataclass
class PreflopState:
    hero_cards: List[str]
    hero_position: str
    table_size: int
    hero_stack_bb: float
    effective_stack_bb: float
    pot_bb: float
    to_call_bb: float
    action_sequence: List[Dict]
    game_type: str = "cash"


def normalize_hand(cards: List[str]) -> str:
    """
    Converte ['Qd', '9s'] em 'Q9o'
    Converte ['Ah', 'Kh'] em 'AKs'
    Converte ['7h', '7c'] em '77'
    """
    if not cards or len(cards) < 2:
        return ""
    c1, c2 = cards[0].strip().upper(), cards[1].strip().upper()
    if len(c1) < 2 or len(c2) < 2:
        return ""
    r1, s1 = c1[0] if c1[0] != "1" else "T", c1[-1].lower()
    r2, s2 = c2[0] if c2[0] != "1" else "T", c2[-1].lower()
    if r1 not in RANK_ORDER or r2 not in RANK_ORDER:
        return ""
    if s1 not in "shdc" or s2 not in "shdc":
        s1, s2 = "s", "s"

    if r1 == r2:
        return r1 + r2

    if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
        r1, r2 = r2, r1
        s1, s2 = s2, s1

    suited = "s" if s1 == s2 else "o"
    return f"{r1}{r2}{suited}"


def is_connector(r1: str, r2: str) -> bool:
    return abs(RANK_ORDER.index(r1) - RANK_ORDER.index(r2)) == 1


def classify_hand(hand: str) -> str:
    premium = {"AA", "KK", "QQ", "JJ", "AKs", "AKo"}
    strong = {"TT", "99", "AQs", "AQo", "AJs", "KQs"}
    playable = {
        "88", "77", "ATs", "AJo", "KJs", "KQo", "QJs", "JTs", "T9s", "98s"
    }

    if hand in premium:
        return "premium"
    if hand in strong:
        return "strong"
    if hand in playable:
        return "playable"

    if len(hand) == 2:
        pair_rank = hand[0]
        if pair_rank in "23456":
            return "small_pair"
        return "medium_pair"

    if len(hand) != 3:
        return "unknown"

    r1, r2, suited_flag = hand[0], hand[1], hand[2]

    if suited_flag == "s":
        if is_connector(r1, r2):
            return "suited_connector"
        return "suited_speculative"

    if suited_flag == "o":
        if is_connector(r1, r2):
            return "weak_offsuit_connector"
        if r1 in "AKQJ" and r2 in "TJ98":
            return "offsuit_broadwayish"
        return "trash_offsuit"

    return "unknown"


def detect_scenario(action_sequence: List[Dict]) -> str:
    non_blind_actions = [
        a for a in action_sequence
        if a.get("action") not in {"post_sb", "post_bb"}
    ]

    if not non_blind_actions:
        return "folded_to_hero"

    if any(a.get("action") == "raise" for a in non_blind_actions):
        return "facing_open_raise"

    if any(a.get("action") == "limp" for a in non_blind_actions):
        return "facing_limp"

    return "unknown"


OPEN_RANGES = {
    "UTG": {"premium", "strong", "playable"},
    "UTG+1": {"premium", "strong", "playable", "small_pair"},
    "HJ": {"premium", "strong", "playable", "small_pair", "suited_speculative"},
    "CO": {
        "premium", "strong", "playable", "small_pair",
        "suited_speculative", "offsuit_broadwayish"
    },
    "BTN": {
        "premium", "strong", "playable", "small_pair",
        "suited_speculative", "offsuit_broadwayish"
    },
    "SB": {
        "premium", "strong", "playable", "small_pair",
        "suited_speculative", "offsuit_broadwayish"
    },
    "BB": {
        "premium", "strong", "playable", "small_pair",
        "suited_speculative", "offsuit_broadwayish"
    },
}


def recommend_open_action(position: str, hand_class: str, hand: str, stack_bb: float) -> Dict:
    allowed_classes = OPEN_RANGES.get(position, {"premium", "strong"})

    if hand in {"72o", "73o", "82o", "92o", "T2o", "J2o", "Q2o", "32o", "42o"}:
        return {
            "action": "fold",
            "confidence": 0.95,
            "reasons": ["Mão extremamente fraca para open raise."]
        }

    if hand_class in allowed_classes:
        if stack_bb <= 12 and hand_class in {"small_pair", "suited_speculative"}:
            return {
                "action": "fold",
                "confidence": 0.72,
                "reasons": ["Com stack curto, mãos especulativas perdem valor para open."]
            }
        return {
            "action": "raise",
            "confidence": 0.80,
            "reasons": [f"A classe da mão ({hand_class}) entra no range de open para {position}."]
        }

    return {
        "action": "fold",
        "confidence": 0.84,
        "reasons": [f"A classe da mão ({hand_class}) fica fora do range padrão de open para {position}."]
    }


def recommend_vs_limp(position: str, hand_class: str, hand: str, stack_bb: float) -> Dict:
    if hand_class in {"premium", "strong"}:
        return {
            "action": "raise_iso",
            "confidence": 0.86,
            "reasons": ["Mão forte para isolar limper."]
        }

    if hand_class in {"playable", "offsuit_broadwayish"} and position in {"CO", "BTN", "SB"}:
        return {
            "action": "raise_iso",
            "confidence": 0.68,
            "reasons": ["Boa chance de isolar com posição ou iniciativa."]
        }

    if hand_class in {"small_pair", "suited_speculative"} and stack_bb >= 20:
        return {
            "action": "call",
            "confidence": 0.60,
            "reasons": ["Mão especulativa com stack suficiente para implied odds."]
        }

    return {
        "action": "fold",
        "confidence": 0.75,
        "reasons": ["Mão fraca para continuar contra limp sem boas condições."]
    }


def recommend_vs_open(
    position: str, hand_class: str, hand: str,
    stack_bb: float, to_call_bb: float
) -> Dict:
    if hand_class == "premium":
        if stack_bb <= 20:
            return {
                "action": "shove_or_3bet",
                "confidence": 0.90,
                "reasons": ["Mão premium contra open raise."]
            }
        return {
            "action": "3bet",
            "confidence": 0.88,
            "reasons": ["Mão premium contra open raise."]
        }

    if hand_class == "strong":
        if position in {"BTN", "BB"}:
            return {
                "action": "call_or_3bet_mix",
                "confidence": 0.66,
                "reasons": ["Mão forte o suficiente para continuar em parte dos cenários."]
            }
        return {
            "action": "fold_or_3bet_mix",
            "confidence": 0.55,
            "reasons": ["Fora de posição, a mão fica mais difícil de realizar."]
        }

    if hand_class in {"small_pair", "suited_speculative"} and stack_bb >= 25 and position in {"BTN", "BB"}:
        return {
            "action": "call",
            "confidence": 0.58,
            "reasons": ["Mão especulativa pode continuar com stack efetivo confortável e posição melhor."]
        }

    return {
        "action": "fold",
        "confidence": 0.82,
        "reasons": ["Faixa insuficiente para continuar contra open raise neste cenário."]
    }


def validate_state(state: PreflopState) -> List[str]:
    issues = []

    if len(state.hero_cards) != 2:
        issues.append("Hero deve ter exatamente 2 cartas.")

    if state.hero_position not in {"UTG", "UTG+1", "HJ", "CO", "BTN", "SB", "BB"}:
        issues.append("Posição do hero inválida ou não padronizada.")

    if state.hero_stack_bb <= 0:
        issues.append("Stack do hero inválido.")

    if state.effective_stack_bb <= 0:
        issues.append("Effective stack inválido.")

    if state.to_call_bb < 0:
        issues.append("to_call_bb inválido.")

    return issues


def preflop_decision_engine(state: PreflopState) -> Dict[str, Any]:
    issues = validate_state(state)
    hand = normalize_hand(state.hero_cards)
    hand_class = classify_hand(hand)
    scenario = detect_scenario(state.action_sequence)

    if issues:
        return {
            "recommended_action": "unknown",
            "confidence": 0.10,
            "hand": hand,
            "hand_class": hand_class,
            "scenario": scenario,
            "issues": issues,
            "reasoning": ["Os dados de entrada estão inconsistentes."]
        }

    if scenario == "folded_to_hero":
        result = recommend_open_action(
            state.hero_position, hand_class, hand, state.effective_stack_bb
        )
    elif scenario == "facing_limp":
        result = recommend_vs_limp(
            state.hero_position, hand_class, hand, state.effective_stack_bb
        )
    elif scenario == "facing_open_raise":
        result = recommend_vs_open(
            state.hero_position, hand_class, hand,
            state.effective_stack_bb, state.to_call_bb
        )
    else:
        result = {
            "action": "fold",
            "confidence": 0.35,
            "reasons": ["Cenário não reconhecido com segurança; ação conservadora."]
        }

    return {
        "recommended_action": result["action"],
        "confidence": result["confidence"],
        "hand": hand,
        "hand_class": hand_class,
        "scenario": scenario,
        "hero_position": state.hero_position,
        "effective_stack_bb": state.effective_stack_bb,
        "reasoning": result["reasons"],
        "data_quality": {
            "issues_found": issues,
            "quality_score": 0.90 if not issues else 0.40
        }
    }


def preflop_state_from_schema(dados: Dict[str, Any]) -> Optional[PreflopState]:
    """
    Constrói PreflopState a partir do JSON extraído (schema do extrator).
    Campos ausentes (stack, to_call, action_sequence) usam defaults razoáveis.
    """
    cards = dados.get("player_cards") or []
    if not isinstance(cards, list) or len(cards) != 2:
        return None
    try:
        from poker_engine import normalizar_carta_str
        cards = [normalizar_carta_str(str(c).strip()) for c in cards if str(c).strip()]
    except Exception:
        cards = [str(c).strip() for c in cards if str(c).strip()]
    if len(cards) != 2:
        return None

    position = (dados.get("position") or "BTN").strip().upper()
    if position not in {"UTG", "UTG+1", "HJ", "CO", "BTN", "SB", "BB"}:
        position = "BTN"

    table_size = dados.get("total_number_of_players")
    try:
        table_size = max(2, min(9, int(table_size))) if table_size is not None else 6
    except (TypeError, ValueError):
        table_size = 6

    pot = dados.get("pot") or 0
    try:
        pot_bb = float(pot)
    except (TypeError, ValueError):
        pot_bb = 0.0
    if pot_bb < 0:
        pot_bb = 0.0

    # Stack não extraído; default 100 BB para o motor não ser restritivo demais
    default_stack = 100.0
    hero_stack_bb = default_stack
    effective_stack_bb = default_stack
    to_call_bb = 0.0  # sem ação anterior conhecida
    action_sequence = []  # schema não tem sequência de ações → cenário folded_to_hero

    return PreflopState(
        hero_cards=cards,
        hero_position=position,
        table_size=table_size,
        hero_stack_bb=hero_stack_bb,
        effective_stack_bb=effective_stack_bb,
        pot_bb=pot_bb,
        to_call_bb=to_call_bb,
        action_sequence=action_sequence,
        game_type="cash",
    )
