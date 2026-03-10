# -*- coding: utf-8 -*-
"""
Motor de decisão pré-flop: usa dados estruturados (cartas, posição, tamanho da mesa, stack, cenário)
para recomendar ação (fold, raise, raise_mix) com base em ranges, mix e cenários típicos.
"""
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

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
    facing_bet_to_call: bool = False


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
    """Classifica a mão em categorias para ranges e mix (premium, strong, playable, small_pair, suited_connector, suited_wheel, weak_suited, offsuit_connector, trash_offsuit)."""
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

    # Pares baixos (66, 55, 44, 33, 22)
    if len(hand) == 2:
        return "small_pair"

    if len(hand) != 3:
        return "unknown"

    r1, r2, suited = hand[0], hand[1], hand[2]

    # Suited connectors fortes (98s, 87s, 76s, 65s)
    if suited == "s" and r1 + r2 in {"98", "87", "76", "65"}:
        return "suited_connector"

    # Suited wheel (Axs)
    if suited == "s" and r1 == "A":
        return "suited_wheel"

    # Suited broadway + carta baixa (Q4s, J5s, K3s)
    if suited == "s" and r1 in "KQJ" and r2 in "23456":
        return "weak_suited_highcard"

    # Suited fracos (ex.: 52s, 73s, T6s)
    if suited == "s":
        return "weak_suited"

    # Offsuit: carta alta + kicker baixo (K6o, Q5o), conector (diff==1), trash
    if suited == "o":
        diff = abs(RANK_ORDER.index(r1) - RANK_ORDER.index(r2))
        if r1 in "AKQJ" and r2 in "23456789":
            return "weak_offsuit_highcard"
        if diff == 1:
            return "offsuit_connector"
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
    "HJ": {"premium", "strong", "playable", "small_pair", "suited_connector"},
    "CO": {
        "premium", "strong", "playable", "small_pair",
        "suited_connector", "suited_wheel",
    },
    "BTN": {
        "premium", "strong", "playable", "small_pair",
        "suited_connector", "suited_wheel", "weak_suited_highcard", "weak_suited",
        "offsuit_connector", "weak_offsuit_highcard",
    },
    "BB": {
        "premium", "strong", "playable", "small_pair",
        "suited_connector", "suited_wheel", "weak_suited_highcard", "weak_suited",
        "offsuit_connector", "weak_offsuit_highcard",
    },
}

# SB: lógica específica — open amplo quando folded to hero (só BB atrás)
SB_OPEN = {
    "premium", "strong", "playable", "small_pair",
    "suited_connector", "suited_wheel", "weak_suited_highcard", "weak_suited",
    "offsuit_connector", "weak_offsuit_highcard",
}

# BTN short-handed (4-handed ou menos): open muito mais amplo
BTN_OPEN_SHORTHANDED = {
    "premium", "strong", "playable", "small_pair",
    "suited_connector", "suited_wheel", "weak_suited",
    "offsuit_connector", "weak_offsuit_highcard",
}

# Estratégia mix: raise com frequência X, fold (1-X).
MIXED_OPEN: Dict[str, Dict[str, float]] = {
    "CO": {"weak_suited_highcard": 0.25, "weak_suited": 0.10},
    "BTN": {"weak_suited_highcard": 0.45, "weak_suited": 0.30},
    "SB": {"weak_suited_highcard": 0.40, "weak_suited": 0.25},
    "BB": {"weak_suited_highcard": 0.35, "weak_suited": 0.20},
}


# Charts reais por posição: decisão por mão exata (prioridade sobre OPEN_RANGES por classe).
OPEN_HANDS_BY_POSITION: Dict[str, set] = {
    "CO": {
        "AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66",
        "AKs", "AQs", "AJs", "ATs", "A9s", "A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s",
        "KQs", "KJs", "KTs", "QJs", "QTs", "JTs", "T9s", "98s", "87s",
        "AKo", "AQo", "AJo", "KQo", "QJo",
    },
    "BTN": {
        "AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66", "55", "44", "33", "22",
        "AKs", "AQs", "AJs", "ATs", "A9s", "A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s",
        "KQs", "KJs", "KTs", "QJs", "QTs", "JTs", "T9s", "98s", "87s", "76s", "65s", "54s",
        "AKo", "AQo", "AJo", "KQo", "QJo", "KJo", "JTo", "T9o", "98o", "87o",
    },
}
OPEN_RANGE_HANDS: Dict[str, set] = OPEN_HANDS_BY_POSITION


def mixed_decision(position: str, hand_class: str) -> Tuple[Optional[str], Optional[float]]:
    """Se a mão está em MIXED_OPEN para a posição, retorna ('raise', freq) ou ('fold', 1-freq). Caso contrário (None, None)."""
    if position not in MIXED_OPEN:
        return None, None
    if hand_class not in MIXED_OPEN[position]:
        return None, None
    freq = MIXED_OPEN[position][hand_class]
    if random.random() < freq:
        return "raise", freq
    return "fold", 1.0 - freq


def confidence_from_class(hand_class: str) -> float:
    """Confiança da decisão conforme a força da classe (fold claro = alta confiança)."""
    if hand_class == "premium":
        return 0.95
    if hand_class == "strong":
        return 0.85
    if hand_class == "playable":
        return 0.75
    if hand_class in {"suited_connector", "suited_wheel"}:
        return 0.65
    if hand_class == "weak_suited_highcard":
        return 0.58
    if hand_class == "weak_suited":
        return 0.55
    if hand_class == "small_pair":
        return 0.70
    if hand_class == "offsuit_connector":
        return 0.62
    if hand_class == "weak_offsuit_highcard":
        return 0.58
    # trash_offsuit e desconhecidos: alta confiança no fold
    return 0.90


def confidence_label(score: float) -> str:
    """Converte score numérico (0–1) em rótulo padronizado para exibição e prompts."""
    if score >= 0.8:
        return "High"
    if score >= 0.6:
        return "Medium"
    if score >= 0.4:
        return "Low-Medium"
    return "Low"


def reasoning_for_open(hand_class: str, position: str) -> List[str]:
    """Gera razões para open/fold por classe e posição."""
    reasons = []
    if position in {"CO", "BTN", "SB"}:
        reasons.append("Late position increases opening opportunities.")
    if hand_class == "suited_connector":
        reasons.append("Hand has good straight and flush potential.")
    if hand_class == "suited_wheel":
        reasons.append("Wheel suited hands can make strong nut flushes.")
    if hand_class == "weak_suited_highcard":
        reasons.append("Suited high card with low kicker has some flush potential but is marginal.")
    if hand_class == "weak_suited":
        reasons.append("Suitedness adds some playability but the hand is still weak.")
    if hand_class == "offsuit_connector":
        reasons.append("Connected offsuit has reasonable playability.")
    if hand_class == "weak_offsuit_highcard":
        reasons.append("Offsuit high card with low kicker has limited playability.")
    if hand_class == "trash_offsuit":
        reasons.append("Hand has poor playability and domination risk.")
    if hand_class == "small_pair":
        reasons.append("Set mining value with sufficient stack.")
    if hand_class in {"premium", "strong", "playable"}:
        reasons.append(f"Hand class ({hand_class}) is in the open range for {position}.")
    return reasons if reasons else [f"Hand class {hand_class} for position {position}."]


def _reasoning_sb_open(hand_class: str, hand: str) -> List[str]:
    """Razões específicas para open no SB (folded to hero = sb_vs_bb)."""
    reasons = [
        "Only the big blind remains to act.",
        "Small blind opening ranges are wide in folded pots.",
    ]
    if hand_class == "offsuit_connector":
        reasons.append(f"{hand} has reasonable playability as a connected hand.")
    elif hand_class == "weak_offsuit_highcard":
        reasons.append(f"{hand} has some playability as high card with low kicker.")
    elif hand_class in {"suited_connector", "suited_wheel"}:
        reasons.append(f"{hand} has straight and flush potential.")
    elif hand_class in {"weak_suited_highcard", "weak_suited"}:
        reasons.append(f"{hand} has some suited playability from the small blind.")
    else:
        reasons.append(f"{hand} is in the SB open range for this scenario.")
    return reasons


def recommend_open_action(
    position: str, hand_class: str, hand: str, stack_bb: float, table_size: int = 6
) -> Dict:
    """Recomenda ação para cenário folded_to_hero: SB usa SB_OPEN; BTN short-handed usa BTN_OPEN_SHORTHANDED; depois chart, mix, OPEN_RANGES."""
    reasons = reasoning_for_open(hand_class, position)
    conf = confidence_from_class(hand_class)

    # Mãos lixo explícitas
    if hand in {"72o", "73o", "82o", "92o", "T2o", "J2o", "Q2o", "32o", "42o"}:
        return {
            "action": "fold",
            "confidence": 0.95,
            "reasons": ["Mão extremamente fraca para open raise."],
            "frequency": None,
        }

    # SB: lógica específica (folded to hero = sb_vs_bb)
    if position == "SB":
        if hand_class in SB_OPEN:
            return {
                "action": "raise",
                "confidence": 0.72,
                "reasons": _reasoning_sb_open(hand_class, hand),
                "frequency": None,
            }
        return {
            "action": "fold",
            "confidence": 0.72,
            "reasons": ["Hand is outside the SB open range for this scenario."],
            "frequency": None,
        }

    # Chart real: decisão por mão exata (prioridade)
    if position in OPEN_RANGE_HANDS and hand in OPEN_RANGE_HANDS[position]:
        return {
            "action": "raise",
            "confidence": min(0.90, conf + 0.05),
            "reasons": reasons or [f"Mão {hand} está no chart de open para {position}."],
            "frequency": None,
        }

    # Mix: weak_suited (e outras) com frequência
    mix_action, mix_freq = mixed_decision(position, hand_class)
    if mix_action is not None and mix_freq is not None:
        if mix_action == "raise":
            return {
                "action": "raise_mix",
                "confidence": round(conf + 0.03, 2),
                "reasons": reasons + [f"Open com frequência {mix_freq:.0%} nesta posição."],
                "frequency": mix_freq,
            }
        return {
            "action": "fold",
            "confidence": round(conf, 2),
            "reasons": reasons + [f"Mix fold (1 - {1 - mix_freq:.0%}) nesta posição."],
            "frequency": 1.0 - mix_freq,
        }

    # BTN short-handed (4-handed ou menos): range mais amplo
    if position == "BTN" and table_size <= 4:
        allowed_classes = BTN_OPEN_SHORTHANDED
    else:
        allowed_classes = OPEN_RANGES.get(position, {"premium", "strong"})  # SB já tratado acima

    if hand_class in allowed_classes:
        if stack_bb <= 12 and hand_class in {"small_pair", "suited_connector", "suited_wheel", "weak_suited_highcard", "weak_suited", "offsuit_connector", "weak_offsuit_highcard"}:
            return {
                "action": "fold",
                "confidence": 0.72,
                "reasons": reasons + ["Com stack curto, mãos especulativas perdem valor para open."],
                "frequency": None,
            }
        return {
            "action": "raise",
            "confidence": round(conf, 2),
            "reasons": reasons,
            "frequency": None,
        }

    return {
        "action": "fold",
        "confidence": round(conf, 2),
        "reasons": reasons + [f"Classe ({hand_class}) fora do range de open para {position}."],
        "frequency": None,
    }


def recommend_vs_limp(position: str, hand_class: str, hand: str, stack_bb: float) -> Dict:
    conf = confidence_from_class(hand_class)
    if hand_class in {"premium", "strong"}:
        return {"action": "raise_iso", "confidence": 0.86, "reasons": ["Mão forte para isolar limper."], "frequency": None}
    if hand_class in {"playable", "offsuit_connector", "weak_offsuit_highcard"} and position in {"CO", "BTN", "SB"}:
        return {"action": "raise_iso", "confidence": 0.68, "reasons": ["Boa chance de isolar com posição ou iniciativa."], "frequency": None}
    if hand_class in {"small_pair", "suited_connector", "suited_wheel", "weak_suited_highcard", "weak_suited"} and stack_bb >= 20:
        return {"action": "call", "confidence": 0.60, "reasons": ["Mão especulativa com stack suficiente para implied odds."], "frequency": None}
    return {"action": "fold", "confidence": round(conf, 2), "reasons": ["Mão fraca para continuar contra limp sem boas condições."], "frequency": None}


def recommend_vs_open(
    position: str, hand_class: str, hand: str,
    stack_bb: float, to_call_bb: float
) -> Dict:
    if hand_class == "premium":
        if stack_bb <= 20:
            return {
                "action": "shove_or_3bet",
                "confidence": 0.90,
                "reasons": ["Mão premium contra open raise."],
                "frequency": None,
            }
        return {
            "action": "3bet",
            "confidence": 0.88,
            "reasons": ["Mão premium contra open raise."],
            "frequency": None,
        }

    if hand_class == "strong":
        if position in {"BTN", "BB"}:
            return {
                "action": "call_or_3bet_mix",
                "confidence": 0.66,
                "reasons": ["Mão forte o suficiente para continuar em parte dos cenários."],
                "frequency": None,
            }
        return {
            "action": "fold_or_3bet_mix",
            "confidence": 0.55,
            "reasons": ["Fora de posição, a mão fica mais difícil de realizar."],
            "frequency": None,
        }

    if hand_class in {"small_pair", "suited_connector", "suited_wheel", "weak_suited_highcard", "weak_suited", "offsuit_connector", "weak_offsuit_highcard"} and stack_bb >= 25 and position in {"BTN", "BB"}:
        return {
            "action": "call",
            "confidence": 0.58,
            "reasons": ["Mão especulativa pode continuar com stack efetivo confortável e posição melhor."],
            "frequency": None,
        }

    return {
        "action": "fold",
        "confidence": 0.82,
        "reasons": ["Faixa insuficiente para continuar contra open raise neste cenário."],
        "frequency": None,
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

    # Conflito: há aposta para pagar (Call visível) mas cenário detectado como folded_to_hero
    if state.facing_bet_to_call and scenario == "folded_to_hero":
        issues.append(
            "Conflito: há aposta para pagar (facing_bet_to_call), mas cenário detectado como folded_to_hero."
        )

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
            state.hero_position, hand_class, hand, state.effective_stack_bb, state.table_size
        )
        # SB open = sb_vs_bb (só BB atrás)
        if state.hero_position == "SB":
            scenario = "sb_vs_bb"
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

    out: Dict[str, Any] = {
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
    if result.get("frequency") is not None:
        out["frequency"] = result["frequency"]
    return out


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

    facing_bet_to_call = bool(dados.get("facing_bet_to_call", False))

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
        facing_bet_to_call=facing_bet_to_call,
    )
