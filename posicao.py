# -*- coding: utf-8 -*-
"""
Posições na mesa de Texas Hold'em e influência na decisão.
Ordem de ação pré-flop (da esquerda do dealer): UTG, UTG+1, HJ, CO, BTN, SB, BB.
"""
from __future__ import annotations
from enum import Enum
from typing import List


class Posicao(Enum):
    """Posições padrão (mesa de 9 max). Para 6 max podem ser usadas subset."""
    UTG = "UTG"           # Under the Gun - primeira a agir
    UTG_1 = "UTG+1"
    HJ = "HJ"             # Hijack
    CO = "CO"             # Cutoff
    BTN = "BTN"           # Button - última a agir (melhor posição)
    SB = "SB"             # Small Blind
    BB = "BB"             # Big Blind

    @property
    def descricao(self) -> str:
        d = {
            Posicao.UTG: "Primeira a agir pré-flop. Posição fraca.",
            Posicao.UTG_1: "Segunda a agir. Ainda early position.",
            Posicao.HJ: "Hijack. Meio da mesa.",
            Posicao.CO: "Cutoff. Boa posição, uma antes do botão.",
            Posicao.BTN: "Botão. Melhor posição - age por último no pós-flop.",
            Posicao.SB: "Small Blind. Age primeiro pós-flop.",
            Posicao.BB: "Big Blind. Já investiu no pote.",
        }
        return d.get(self, "")

    @property
    def forca_relativa(self) -> str:
        """Early / Middle / Late para o modelo usar no raciocínio."""
        if self in (Posicao.UTG, Posicao.UTG_1):
            return "early"
        if self in (Posicao.HJ, Posicao.CO):
            return "middle"
        return "late"


def posicao_from_string(s: str) -> Posicao:
    """Converte string (ex: 'BTN', 'btn', 'Button') em Posicao."""
    m = {
        "utg": Posicao.UTG,
        "utg+1": Posicao.UTG_1,
        "utg_1": Posicao.UTG_1,
        "hj": Posicao.HJ,
        "hijack": Posicao.HJ,
        "co": Posicao.CO,
        "cutoff": Posicao.CO,
        "btn": Posicao.BTN,
        "button": Posicao.BTN,
        "sb": Posicao.SB,
        "small blind": Posicao.SB,
        "bb": Posicao.BB,
        "big blind": Posicao.BB,
    }
    key = s.strip().lower().replace(" ", "_")
    if key not in m:
        raise ValueError(f"Posição desconhecida: {s}. Use uma de: {list(m.keys())}")
    return m[key]


def todas_posicoes_9max() -> List[Posicao]:
    return [Posicao.UTG, Posicao.UTG_1, Posicao.HJ, Posicao.CO, Posicao.BTN, Posicao.SB, Posicao.BB]
