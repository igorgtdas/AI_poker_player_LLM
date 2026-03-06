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
from typing import Any, List, Tuple

# Regiões em proporção (0–1): (left, top, width, height)
# Funcionam para qualquer resolução; apenas o tamanho absoluto varia.

# Referência em pixels para conversão dos assentos (mesa típica)
_REF_W, _REF_H = 953, 663


def _px_to_prop(x: float, y: float, w: float, h: float) -> Tuple[float, float, float, float]:
    """Converte (left, top, width, height) em pixels para proporção 0–1 (ref 953×663)."""
    return (x / _REF_W, y / _REF_H, w / _REF_W, h / _REF_H)


# Regiões dos 6 assentos e do botão dealer em pixels (x, y, width, height) ref 953×663;
# convertidas para proporção para funcionar em qualquer resolução.
REGIOES_ASSENTOS = {
    "seat_12h": _px_to_prop(330, 65, 290, 115),   # topo
    "seat_2h": _px_to_prop(655, 110, 270, 120),   # topo-direita
    "seat_4h": _px_to_prop(665, 285, 260, 125),   # direita
    "seat_6h": _px_to_prop(350, 385, 280, 135),   # baixo (Hero)
    "seat_8h": _px_to_prop(30, 290, 260, 130),    # baixo-esquerda
    "seat_10h": _px_to_prop(25, 85, 250, 115),    # topo-esquerda
}
REGIAO_DEALER_BUTTON = _px_to_prop(365, 388, 55, 55)  # botão D

REGIOES = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "position": (0.25, 0.40, 0.50, 0.55),  # centro: minha área + vizinhos
    "community_cards": (0.18, 0.16, 0.64, 0.30),
    "hole_cards": (0.36, 0.50, 0.28, 0.18),
    "dealer_button": REGIAO_DEALER_BUTTON,
    **REGIOES_ASSENTOS,
}

# Hero está sempre no assento 6h (baixo centro)
SEAT_HERO = "seat_6h"

# Ordem dos assentos no sentido horário a partir do topo (12h): 12h → 2h → 4h → 6h → 8h → 10h
ORDEM_ASSENTOS_RELOJ = ("seat_12h", "seat_2h", "seat_4h", "seat_6h", "seat_8h", "seat_10h")

# Ordem sugerida para extração: contexto (position) → board → minhas cartas
ORDEM_REGIOES = ("position", "community_cards", "hole_cards")

# Todas as regiões de assentos + dealer_button para extração de posições
ORDEM_REGIOES_ASSENTOS = tuple(ORDEM_ASSENTOS_RELOJ) + ("dealer_button",)


def _carregar_imagem(caminho: str):
    """Carrega imagem com Pillow."""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Para recortar regiões, instale: pip install Pillow")
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
           | "seat_12h" … "seat_6h" (Hero) … "seat_10h" | "dealer_button"
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
        raise ImportError("Para recortar regiões, instale: pip install Pillow")
    img = _carregar_imagem(caminho_imagem)
    out = {}
    for nome, (left, top, w, h) in REGIOES.items():
        bbox = _proporcao_para_pixels(img, left, top, w, h)
        out[nome] = img.crop(bbox)
    return out


def recortar_assentos_e_botao(caminho_imagem: str) -> dict[str, Any]:
    """
    Recorta apenas as 6 regiões de assentos (nome/stack de cada jogador) e a região
    do botão dealer (D). Útil para o LLM identificar quem é cada jogador e onde está
    o BTN, e assim inferir posições relativas (Hero está sempre em seat_6h).
    Retorna dict com chaves: seat_12h, seat_2h, seat_4h, seat_6h, seat_8h, seat_10h, dealer_button.
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
    Recorta as regiões dos assentos e monta uma única imagem em grid com labels.
    Se apenas_seis_assentos=True (padrão): usa só os 6 assentos — o botão dealer (D)
    deve ser identificado DENTRO de um desses recortes (onde o D aparece ao lado do nome/stack).
    Se False: inclui também o crop isolado dealer_button (legado).
    Layout 6 assentos: linha 1 = seat_12h, seat_2h, seat_4h; linha 2 = seat_6h (Hero), seat_8h, seat_10h.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError("Para montar composite, instale: pip install Pillow")
    crops = recortar_assentos_e_botao(caminho_imagem)
    ordem = list(ORDEM_ASSENTOS_RELOJ) if apenas_seis_assentos else list(ORDEM_REGIOES_ASSENTOS)
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
        if nome == "dealer_button":
            x = (total_w - img.size[0]) // 2
        else:
            x = col * cell_w + pad
        y = row * cell_h + label_h + pad
        composite.paste(img, (x, y))
        label = "Hero" if nome == SEAT_HERO else nome.replace("seat_", "").replace("dealer_button", "D")
        draw.text((x, row * cell_h + 2), label, fill=(220, 220, 220), font=font)
    return composite


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
