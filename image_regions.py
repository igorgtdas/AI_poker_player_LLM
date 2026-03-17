# -*- coding: utf-8 -*-
"""
Regiões proporcionais da imagem da mesa de poker para OCR em quadrantes.
Mantém as mesmas proporções independente do tamanho da imagem.

Inclui 6 regiões de assentos (seat_12h … seat_6h) baseadas em centros típicos
em mesa 953×663 px, para identificar jogadores e posições relativas ao Hero (6h) e ao BTN (D).
"""
from __future__ import annotations
import os
import tempfile
from datetime import datetime
from typing import Any, List, Tuple

# Regiões em proporção (0–1): (left, top, width, height)
# Funcionam para qualquer resolução; apenas o tamanho absoluto varia.

# Referência em pixels para conversão dos assentos (mesa típica)
_REF_W, _REF_H = 953, 663


def _px_to_prop(x: float, y: float, w: float, h: float) -> Tuple[float, float, float, float]:
    """Converte (left, top, width, height) em pixels para proporção 0–1 (ref 953×663)."""
    return (x / _REF_W, y / _REF_H, w / _REF_W, h / _REF_H)


# Regiões dos 6 assentos em pixels (x, y, width, height) ref 953×663.
# O dealer button NÃO é recortado separadamente; é avaliado apenas dentro dos crops dos assentos.
REGIOES_ASSENTOS = {
    "seat_12h": _px_to_prop(330, 65, 290, 165),   # topo (altura maior para baixo para pegar o D)
    "seat_2h": _px_to_prop(655, 110, 270, 120),   # topo-direita
    "seat_4h": _px_to_prop(665, 285, 260, 125),   # direita
    "seat_6h": _px_to_prop(350, 355, 280, 165),   # baixo (Hero); estendido para cima para pegar sua aposta
    "seat_8h": _px_to_prop(30, 290, 260, 130),    # baixo-esquerda
    "seat_10h": _px_to_prop(25, 85, 310, 160),    # topo-esquerda (maior para direita e baixo)
}

REGIOES = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "position": (0.25, 0.40, 0.50, 0.55),  # centro: minha área + vizinhos
    "community_cards": (0.18, 0.16, 0.64, 0.30),
    "hole_cards": (0.36, 0.50, 0.28, 0.18),
    **REGIOES_ASSENTOS,
}

# Hero está sempre no assento 6h (baixo centro)
SEAT_HERO = "seat_6h"

# Ordem dos assentos no sentido horário a partir do topo (12h): 12h → 2h → 4h → 6h → 8h → 10h
ORDEM_ASSENTOS_RELOJ = ("seat_12h", "seat_2h", "seat_4h", "seat_6h", "seat_8h", "seat_10h")

# Ordem sugerida para extração: contexto (position) → board → minhas cartas
ORDEM_REGIOES = ("position", "community_cards", "hole_cards")

# Apenas os 6 assentos (dealer é identificado dentro do crop do assento, não recortado separadamente)
ORDEM_REGIOES_ASSENTOS = ORDEM_ASSENTOS_RELOJ


def _pil_import_error() -> str:
    import sys
    return (
        "Pillow (PIL) não encontrado. Instale com: pip install Pillow. "
        f"Python em uso: {getattr(sys, 'executable', '?')} — confira se é o do seu venv."
    )


def _carregar_imagem(caminho: str):
    """Carrega imagem com Pillow."""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(_pil_import_error())
    img = Image.open(caminho).convert("RGB")
    return img


def _proporcao_para_pixels(
    img, left: float, top: float, width: float, height: float
) -> Tuple[int, int, int, int]:
    """Converte (left, top, width, height) em 0–1 para bbox em pixels (left, upper, right, lower)."""
    w, h = img.size
    return (
        int(left * w),
        int(top * h),
        int((left + width) * w),
        int((top + height) * h),
    )


def recortar_regiao(caminho_imagem: str, regiao: str):
    """
    Recorta uma região da imagem e retorna um novo Image (PIL).
    regiao: "full" | "position" | "community_cards" | "hole_cards"
           | "seat_12h" … "seat_6h" (Hero) … "seat_10h"
    """
    if regiao not in REGIOES:
        raise ValueError(f"Região inválida: {regiao}. Use: {list(REGIOES)}")
    img = _carregar_imagem(caminho_imagem)
    left, top, w, h = REGIOES[regiao]
    bbox = _proporcao_para_pixels(img, left, top, w, h)
    return img.crop(bbox)


def recortar_todas_as_regioes(caminho_imagem: str) -> dict[str, Any]:
    """Recorta todas as regiões e retorna um dict regiao -> PIL Image."""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(_pil_import_error())
    img = _carregar_imagem(caminho_imagem)
    out = {}
    for nome, (left, top, w, h) in REGIOES.items():
        bbox = _proporcao_para_pixels(img, left, top, w, h)
        out[nome] = img.crop(bbox)
    return out


def recortar_assentos_e_botao(caminho_imagem: str) -> dict[str, Any]:
    """
    Recorta apenas as 6 regiões de assentos (nome/stack de cada jogador).
    O dealer button não é recortado; o LLM identifica o D dentro do crop do assento
    onde ele aparece. Retorna dict com chaves: seat_12h, seat_2h, seat_4h, seat_6h, seat_8h, seat_10h.
    """
    img = _carregar_imagem(caminho_imagem)
    out = {}
    for nome in ORDEM_REGIOES_ASSENTOS:
        left, top, w, h = REGIOES[nome]
        bbox = _proporcao_para_pixels(img, left, top, w, h)
        out[nome] = img.crop(bbox)
    return out


def montar_imagem_assentos_composite(caminho_imagem: str, apenas_seis_assentos: bool = True):
    """
    Recorta as regiões dos 6 assentos e monta uma única imagem em grid com labels.
    O dealer button (D) é identificado pelo LLM dentro do crop do assento onde aparece,
    não há crop isolado do D. Layout: linha 1 = seat_12h, seat_2h, seat_4h; linha 2 = seat_6h (Hero), seat_8h, seat_10h.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError(_pil_import_error())
    crops = recortar_assentos_e_botao(caminho_imagem)
    ordem = list(ORDEM_ASSENTOS_RELOJ)
    imgs = [crops[n] for n in ordem]
    w_max = max(i.size[0] for i in imgs)
    h_max = max(i.size[1] for i in imgs)
    pad = 4
    label_h = 16
    cell_w = w_max + pad * 2
    cell_h = h_max + pad * 2 + label_h
    cols = 3
    total_w = 3 * cell_w
    num_rows = (len(ordem) + cols - 1) // cols
    total_h = cell_h * num_rows
    composite = Image.new("RGB", (total_w, total_h), (40, 40, 40))
    draw = ImageDraw.Draw(composite)
    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except OSError:
        font = ImageFont.load_default()
    for idx, nome in enumerate(ordem):
        img = crops[nome]
        row = idx // cols
        col = idx % cols
        x = col * cell_w + pad
        y = row * cell_h + label_h + pad
        composite.paste(img, (x, y))
        label = "Hero" if nome == SEAT_HERO else nome.replace("seat_", "")
        draw.text((x, row * cell_h + 2), label, fill=(220, 220, 220), font=font)
    return composite


def salvar_regioes_para_debug(
    caminho_imagem: str,
    pasta_base: str | None = None,
    incluir_regioes_gerais: bool = True,
) -> str:
    """
    Salva em disco os recortes usados para extração (apenas os 6 assentos + composite) para debug.
    Útil para inspecionar por que a position não está saindo correta (ex.: D fora do crop).

    Cria uma subpasta com timestamp em pasta_base (default: capturas/debug_regions).
    Salva: seat_12h.png … seat_10h.png, composite.png e, se incluir_regioes_gerais,
    position.png, community_cards.png, hole_cards.png. O dealer não é recortado separadamente.

    Retorna o caminho da pasta criada.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if not pasta_base:
        pasta_base = os.path.join(base_dir, "capturas", "debug_regions")
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    pasta = os.path.join(pasta_base, ts)
    os.makedirs(pasta, exist_ok=True)

    # Apenas os 6 assentos (o LLM identifica o D dentro do crop do assento)
    crops = recortar_assentos_e_botao(caminho_imagem)
    for nome, img in crops.items():
        path_out = os.path.join(pasta, f"{nome}.png")
        img.save(path_out, "PNG")

    # Composite enviado ao LLM para identificar BTN e posições
    composite = montar_imagem_assentos_composite(caminho_imagem)
    composite.save(os.path.join(pasta, "composite.png"), "PNG")

    if incluir_regioes_gerais:
        regioes = recortar_todas_as_regioes(caminho_imagem)
        for nome in ("position", "community_cards", "hole_cards"):
            if nome in regioes:
                regioes[nome].save(os.path.join(pasta, f"{nome}.png"), "PNG")

    return pasta


def salvar_regioes_em_temp(caminho_imagem: str, prefixo: str = "poker_") -> List[Tuple[str, str]]:
    """
    Recorta todas as regiões, salva em arquivos temporários e retorna
    lista de (nome_regiao, caminho_arquivo). O chamador deve apagar os arquivos depois.
    """
    regioes = recortar_todas_as_regioes(caminho_imagem)
    ext = os.path.splitext(caminho_imagem)[1].lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg"):
        ext = ".png"
    resultado = []
    for nome, img in regioes.items():
        fd, path = tempfile.mkstemp(suffix=ext, prefix=prefixo + nome + "_")
        os.close(fd)
        img.save(path, "PNG" if ext == ".png" else "JPEG", quality=95)
        resultado.append((nome, path))
    return resultado
