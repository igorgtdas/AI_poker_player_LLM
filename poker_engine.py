# -*- coding: utf-8 -*-
"""
Motor de poker: representação de cartas, ranking de mãos e avaliação.
Texas Hold'em - 7 cartas (2 hole + 5 board).
"""
from __future__ import annotations
import random
from collections import Counter
from typing import List, Tuple

# Naipes e valores
NAIPES = "shdc"  # spades, hearts, diamonds, clubs
VALORES = "23456789TJQKA"
VALOR_ORDEM = {v: i for i, v in enumerate(VALORES)}


def normalizar_carta_str(s: str) -> str:
    """
    Garante formato valor+naipe. Se o LLM retornar só o valor (ex: '9' ou 'K'),
    completa com naipe 's'. Ex: '9' -> '9s', 'Kh' -> 'Kh'.
    """
    s = str(s).strip()
    if len(s) >= 2:
        return s
    if len(s) == 1 and s.upper() in VALORES:
        return s.upper() + "s"
    return s


def parse_carta(s: str) -> Tuple[str, str]:
    """Converte string tipo 'As' ou 'Kh' em (valor, naipe)."""
    s = normalizar_carta_str(s)
    s = s.strip().upper()
    if len(s) < 2:
        raise ValueError(f"Carta inválida: {s}")
    valor, naipe = s[0], s[1].lower()
    if valor == "1" and len(s) >= 2 and s[1] == "0":
        valor = "T"
        naipe = s[2].lower() if len(s) > 2 else "s"
    if valor not in VALORES or naipe not in NAIPES:
        raise ValueError(f"Carta inválida: {s}")
    return (valor, naipe)


def carta_to_str(valor: str, naipe: str) -> str:
    """(valor, naipe) -> string legível (ex: As, Kh)."""
    return f"{valor}{naipe}"


def baralho_completo() -> List[Tuple[str, str]]:
    """Lista de 52 cartas como (valor, naipe)."""
    return [(v, n) for v in VALORES for n in NAIPES]


def remover_cartas(baralho: List[Tuple[str, str]], cartas: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Retorna cópia do baralho sem as cartas dadas."""
    conj = set(cartas)
    return [c for c in baralho if c not in conj]


def valor_num(v: str) -> int:
    return VALOR_ORDEM[v]


def rank_7cartas(cartas: List[Tuple[str, str]]) -> Tuple[int, List[int]]:
    """
    Avalia a melhor mão de 5 cartas entre 7.
    Retorna (rank_principal, lista_de_desempate).
    Rank: 9=straight flush, 8=quadra, 7=full, 6=flush, 5=sequência, 4=trinca, 3=dois pares, 2=par, 1=high card.
    """
    if len(cartas) != 7:
        raise ValueError("Precisa de exatamente 7 cartas")
    from itertools import combinations
    melhor = (0, [])
    for cinco in combinations(cartas, 5):
        r, desempate = rank_5cartas(list(cinco))
        if (r, desempate) > melhor:
            melhor = (r, desempate)
    return melhor


def rank_5cartas(cartas: List[Tuple[str, str]]) -> Tuple[int, List[int]]:
    """Avalia 5 cartas. Retorna (rank_principal, lista para desempate)."""
    valores = [valor_num(c[0]) for c in cartas]
    naipes = [c[1] for c in cartas]
    contagem = Counter(valores)
    vals_ord = sorted(valores, reverse=True)
    is_flush = len(set(naipes)) == 1
    min_v, max_v = min(valores), max(valores)
    is_straight = (max_v - min_v == 4 and len(set(valores)) == 5) or (set(valores) == {12, 11, 10, 9, 0})  # A-5

    # Straight flush
    if is_flush and is_straight:
        if set(valores) == {12, 11, 10, 9, 0}:
            return (9, [5])  # A-5 straight flush
        return (9, [max_v])

    # Quadra
    for v, count in contagem.most_common():
        if count == 4:
            kicker = max(x for x in valores if x != v)
            return (8, [v, kicker])
    # Full house
    tres_val = None
    dois_val = None
    for v, count in contagem.most_common():
        if count >= 3 and tres_val is None:
            tres_val = v
        elif count >= 2 and v != tres_val and dois_val is None:
            dois_val = v
    if tres_val is not None and dois_val is not None:
        return (7, [tres_val, dois_val])

    # Flush
    if is_flush:
        return (6, sorted(vals_ord, reverse=True))
    # Sequência
    if is_straight:
        if set(valores) == {12, 11, 10, 9, 0}:
            return (5, [5])
        return (5, [max_v])
    # Trinca
    for v, count in contagem.most_common():
        if count == 3:
            kickers = sorted([x for x in valores if x != v], reverse=True)[:2]
            return (4, [v] + kickers)
    # Dois pares
    pares = [v for v, c in contagem.items() if c == 2]
    if len(pares) >= 2:
        pares.sort(reverse=True)
        kicker = max(x for x in valores if x not in pares[:2])
        return (3, pares[:2] + [kicker])
    # Par
    for v, count in contagem.items():
        if count == 2:
            kickers = sorted([x for x in valores if x != v], reverse=True)[:3]
            return (2, [v] + kickers)
    # High card
    return (1, sorted(vals_ord, reverse=True))


RANK_NAMES = {
    9: "straight flush",
    8: "four of a kind",
    7: "full house",
    6: "flush",
    5: "straight",
    4: "three of a kind",
    3: "two pair",
    2: "pair",
    1: "high card",
}


def melhor_mao_5_entre_n(cartas: List[Tuple[str, str]]) -> Tuple[int, List[int]]:
    """Dado 5, 6 ou 7 cartas, retorna o rank da melhor mão de 5 (rank_principal, desempate)."""
    from itertools import combinations
    if len(cartas) == 5:
        return rank_5cartas(cartas)
    if len(cartas) == 6:
        return max((rank_5cartas(list(c)) for c in combinations(cartas, 5)), key=lambda x: (x[0], x[1]))
    if len(cartas) == 7:
        return rank_7cartas(cartas)
    raise ValueError("Precisa de 5, 6 ou 7 cartas")


def nome_sequencia(suas_cartas: List[str], cartas_mesa: List[str]) -> str:
    """
    Retorna o nome da melhor mão atual (ex: "pair", "straight", "flush").
    suas_cartas: 0 ou 2 cartas; cartas_mesa: 0, 3, 4 ou 5 cartas.
    Se não houver cartas suficientes, retorna "".
    """
    if len(suas_cartas) != 2 or len(cartas_mesa) < 3:
        return ""
    try:
        suas = [parse_carta(c) for c in suas_cartas]
        mesa = [parse_carta(c) for c in cartas_mesa]
    except (ValueError, TypeError):
        return ""
    todas = suas + mesa
    if len(todas) < 5:
        return ""
    rank_num, _ = melhor_mao_5_entre_n(todas)
    return RANK_NAMES.get(rank_num, "high card")


def comparar_maos(mao1: List[Tuple[str, str]], mao2: List[Tuple[str, str]]) -> int:
    """
    Compara duas mãos de 5+ cartas (usa as melhores 5 de cada).
    Retorna -1 se mao1 ganha, 1 se mao2 ganha, 0 empate.
    """
    from itertools import combinations
    def melhor_5(cartas):
        if len(cartas) == 5:
            return rank_5cartas(cartas)
        return max(rank_5cartas(list(c)) for c in combinations(cartas, 5))
    r1, d1 = melhor_5(mao1)
    r2, d2 = melhor_5(mao2)
    if (r1, d1) > (r2, d2):
        return -1
    if (r1, d1) < (r2, d2):
        return 1
    return 0


def probabilidade_vitoria_monte_carlo(
    suas_cartas: List[str],
    cartas_mesa: List[str],
    num_oponentes: int = 1,
    simulacoes: int = 1000,
    seed: int | None = None,
) -> float:
    """
    Estima probabilidade de vitória com Monte Carlo.
    suas_cartas: 2 cartas (ex: ["As", "Kh"]) ou [] se sem cartas na mão
    cartas_mesa: 0, 3 (flop), 4 (turn) ou 5 (river) cartas
    num_oponentes: número de oponentes (cada um com 2 cartas aleatórias).
    """
    if len(suas_cartas) != 2:
        return 0.0
    if seed is not None:
        random.seed(seed)
    suas = [parse_carta(c) for c in suas_cartas]
    mesa = [parse_carta(c) for c in cartas_mesa]
    baralho = baralho_completo()
    usadas = set(suas + mesa)
    baralho = [c for c in baralho if c not in usadas]
    n_mesa_faltam = 5 - len(mesa)
    wins = 0
    for _ in range(simulacoes):
        random.shuffle(baralho)
        # Completar mesa
        mesa_completa = mesa + baralho[:n_mesa_faltam]
        resto = baralho[n_mesa_faltam:]
        # Cartas dos oponentes (cada um 2)
        oponentes_cartas = [resto[i * 2:(i + 1) * 2] for i in range(num_oponentes)]
        minha_mao = suas + mesa_completa
        minha_rank = rank_7cartas(minha_mao)
        pontos = 0.0  # 1=vitória, 0.5=empate, 0=derrota
        perdi = False
        empate_count = 0
        for op in oponentes_cartas:
            op_mao = op + mesa_completa
            op_rank = rank_7cartas(op_mao)
            if op_rank > minha_rank:
                perdi = True
                break
            if op_rank == minha_rank:
                empate_count += 1
        if perdi:
            pontos = 0.0
        elif empate_count == num_oponentes:
            pontos = 0.5  # empate com todos
        else:
            pontos = 1.0
        wins += pontos
    return wins / simulacoes
