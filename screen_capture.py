# -*- coding: utf-8 -*-
"""
Captura de tela: região fixa (bbox) ou seleção interativa por overlay.
Usado pelo front para "Definir área da mesa" e atalho Ctrl+Shift+P.
"""
from __future__ import annotations
import os
import tempfile
from typing import Optional, Tuple

# Bbox: (left, top, right, bottom) em pixels, ou (left, top, width, height) conforme contexto
CONFIG_FILENAME = "poker_capture_region.json"
# Pasta e arquivo fixos para a última captura (para você comparar e achar o caminho)
CAPTURAS_DIR = "capturas"
ULTIMA_CAPTURA_FILENAME = "ultima_captura.png"


def _get_config_path() -> str:
    """Caminho do arquivo de config da região (na pasta do projeto)."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, CONFIG_FILENAME)


def _get_ultima_captura_path() -> str:
    """Caminho fixo da última captura (pasta do projeto / capturas / ultima_captura.png)."""
    base = os.path.dirname(os.path.abspath(__file__))
    dir_path = os.path.join(base, CAPTURAS_DIR)
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, ULTIMA_CAPTURA_FILENAME)


def carregar_regiao() -> Optional[Tuple[int, int, int, int]]:
    """
    Carrega a região salva (left, top, width, height).
    Retorna (left, top, right, bottom) para uso em grab(bbox), ou None se não houver config.
    """
    path = _get_config_path()
    if not os.path.isfile(path):
        return None
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        left = int(d["left"])
        top = int(d["top"])
        width = int(d["width"])
        height = int(d["height"])
        if width <= 0 or height <= 0:
            return None
        return (left, top, left + width, top + height)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def salvar_regiao(left: int, top: int, width: int, height: int) -> None:
    """Salva a região no config (left, top, width, height) em pixels."""
    import json
    path = _get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"left": left, "top": top, "width": width, "height": height}, f, indent=2)


def capturar_bbox(bbox: Tuple[int, int, int, int], salvar_em_projeto: bool = True) -> str:
    """
    Captura a região da tela dada por bbox (left, top, right, bottom) e salva em PNG.
    Se salvar_em_projeto=True, salva também em <projeto>/capturas/ultima_captura.png
    e retorna esse path (assim você sempre sabe onde está e pode comparar com outra imagem).
    Caso contrário retorna path em temp.
    """
    try:
        from PIL import ImageGrab
    except ImportError:
        raise ImportError("Para captura de tela, instale: pip install Pillow")
    img = ImageGrab.grab(bbox=bbox)
    if salvar_em_projeto:
        path = _get_ultima_captura_path()
        img.save(path, "PNG")
        return path
    fd, path = tempfile.mkstemp(suffix=".png", prefix="poker_capture_")
    os.close(fd)
    img.save(path, "PNG")
    return path


def capturar_regiao_salva() -> Optional[str]:
    """
    Captura usando a região já salva no config. Retorna path do PNG em temp ou None se não houver região.
    """
    bbox = carregar_regiao()
    if bbox is None:
        return None
    return capturar_bbox(bbox)


def selecionar_regiao_interativa() -> Optional[Tuple[int, int, int, int]]:
    """
    Abre uma overlay fullscreen para o usuário desenhar a área da mesa.
    Retorna (left, top, right, bottom) quando o usuário solta o mouse, ou None se cancelar (Escape).
    """
    import tkinter as tk

    result: Optional[Tuple[int, int, int, int]] = None

    root = tk.Tk()
    root.title("Selecione a área da mesa")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.35)
    root.configure(bg="black")
    # Fullscreen em todos os monitores (simplificado: primary)
    root.geometry("{0}x{1}+0+0".format(root.winfo_screenwidth(), root.winfo_screenheight()))
    root.state("zoomed")

    lbl = tk.Label(root, text="Arraste para selecionar a área da mesa • ESC para cancelar", font=("", 12, "bold"), fg="white", bg="black")
    lbl.pack(pady=20)
    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    start_x = start_y = end_x = end_y = None
    rect_id = None

    def on_press(event):
        nonlocal start_x, start_y, rect_id
        start_x, start_y = event.x, event.y
        if rect_id is not None:
            canvas.delete(rect_id)
        rect_id = canvas.create_rectangle(start_x, start_y, start_x, start_y, outline="lime", width=3)

    def on_motion(event):
        nonlocal rect_id
        if start_x is None or rect_id is None:
            return
        canvas.coords(rect_id, start_x, start_y, event.x, event.y)

    def on_release(event):
        nonlocal result, end_x, end_y
        end_x, end_y = event.x, event.y
        if start_x is not None and start_y is not None:
            x1, x2 = min(start_x, end_x), max(start_x, end_x)
            y1, y2 = min(start_y, end_y), max(start_y, end_y)
            if x2 - x1 > 10 and y2 - y1 > 10:  # mínimo 10px
                # Coordenadas eram do canvas; o canvas fica abaixo do label, então
                # precisamos converter para coordenadas de tela (senão a captura desloca pra cima)
                root.update_idletasks()
                cx = canvas.winfo_rootx()
                cy = canvas.winfo_rooty()
                result = (cx + x1, cy + y1, cx + x2, cy + y2)
        root.quit()
        root.destroy()

    def on_escape(event):
        root.quit()
        root.destroy()

    def on_key(event):
        if event.keysym == "Escape":
            on_escape(event)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_motion)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)
    root.bind("<Key>", on_key)

    root.focus_force()
    root.mainloop()
    return result
