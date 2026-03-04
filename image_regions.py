# -*- coding: utf-8 -*-
"""
Regiões proporcionais da imagem da mesa de poker para OCR em quadrantes.
Mantém as mesmas proporções independente do tamanho da imagem.
"""
from __future__ import annotations
import os
import tempfile
from typing import Any, List, Tuple

# Regiões em proporção (0–1): (left, top, width, height)
# Funcionam para qualquer resolução; apenas o tamanho absoluto varia.

REGIOES = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "position": (0.25, 0.40, 0.50, 0.55),  # centro da imagem: minha área + vizinhos (meio horizontal, meio-inferior vertical)
    "community_cards": (0.18, 0.16, 0.64, 0.30),
    "hole_cards": (0.36, 0.50, 0.28, 0.18),
}

# Ordem sugerida para extração: contexto (position) → board → minhas cartas
ORDEM_REGIOES = ("position", "community_cards", "hole_cards")


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
