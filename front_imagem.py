# -*- coding: utf-8 -*-
"""
Front simples para enviar uma imagem da mesa e obter extração (JSON) + recomendação.
"""
from __future__ import annotations
import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# Carrega .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass


def criar_janela() -> tk.Tk:
    root = tk.Tk()
    root.title("AI Poker Player — Enviar imagem da mesa")
    root.geometry("640x520")
    root.minsize(480, 400)

    # Variáveis
    caminho_imagem = tk.StringVar(value="")
    username_player = tk.StringVar(value="")
    position_manual = tk.StringVar(value="")
    use_regions = tk.BooleanVar(value=False)

    # Topo: instrução + botão de seleção
    frame_topo = ttk.Frame(root, padding=10)
    frame_topo.pack(fill=tk.X)

    ttk.Label(frame_topo, text="Selecione uma imagem da mesa (screenshot ou foto)", font=("", 10, "bold")).pack(anchor=tk.W)
    ttk.Label(frame_topo, text="O sistema extrai os dados com um LLM de visão e depois gera a recomendação.", foreground="gray").pack(anchor=tk.W)

    frame_bt = ttk.Frame(frame_topo)
    frame_bt.pack(fill=tk.X, pady=8)
    ttk.Button(frame_bt, text="Selecionar imagem...", command=lambda: _escolher_imagem(caminho_imagem, lbl_path)).pack(side=tk.LEFT, padx=(0, 8))
    lbl_path = ttk.Label(frame_bt, text="Nenhuma imagem selecionada", foreground="gray")
    lbl_path.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # Campo: username do jogador (identifica "suas cartas" na mesa)
    frame_user = ttk.Frame(frame_topo)
    frame_user.pack(fill=tk.X, pady=4)
    ttk.Label(frame_user, text="Username (jogador):", width=18, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 8))
    entry_username = ttk.Entry(frame_user, textvariable=username_player, width=32)
    entry_username.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(frame_user, text="Opcional. Seu nome na mesa para o modelo identificar suas cartas.", font=("", 8), foreground="gray").pack(anchor=tk.W, padx=(0, 0))

    # Posição manual (sobrescreve OCR se preenchido)
    frame_pos = ttk.Frame(frame_topo)
    frame_pos.pack(fill=tk.X, pady=4)
    ttk.Label(frame_pos, text="Posição (manual):", width=18, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 8))
    combo_pos = ttk.Combobox(frame_pos, textvariable=position_manual, values=["", "UTG", "UTG+1", "HJ", "CO", "BTN", "SB", "BB"], width=10, state="readonly")
    combo_pos.pack(side=tk.LEFT, fill=tk.X)
    ttk.Label(frame_pos, text="Opcional. Se o OCR não acertar, escolha sua posição aqui.", font=("", 8), foreground="gray").pack(anchor=tk.W, padx=(0, 0))

    # Opção: extrair por regiões (quadrantes)
    frame_regioes = ttk.Frame(frame_topo)
    frame_regioes.pack(fill=tk.X, pady=4)
    ck_regioes = ttk.Checkbutton(frame_regioes, text="Extrair por regiões (6 assentos + D, contexto, board e minhas cartas)", variable=use_regions)
    ck_regioes.pack(anchor=tk.W)
    ttk.Label(frame_regioes, text="Usa recortes dos 6 jogadores e do botão D para posição; depois board e suas cartas.", font=("", 8), foreground="gray").pack(anchor=tk.W, padx=(0, 0))

    # Botão Analisar
    btn_analisar = ttk.Button(frame_topo, text="Analisar imagem (extrair + recomendar)", command=lambda: _rodar_analise(root, caminho_imagem, username_player, position_manual, use_regions, txt_resultado, btn_analisar))
    btn_analisar.pack(pady=4)

    # Área de resultado (rolável)
    ttk.Label(root, text="Resultado", font=("", 9, "bold")).pack(anchor=tk.W, padx=10, pady=(8, 0))
    txt_resultado = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=18, font=("Consolas", 9), state=tk.DISABLED, padx=8, pady=8)
    txt_resultado.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

    return root


def _escolher_imagem(caminho_var: tk.StringVar, lbl: ttk.Label) -> None:
    path = filedialog.askopenfilename(
        title="Selecionar imagem da mesa",
        filetypes=[
            ("Imagens", "*.png *.jpg *.jpeg *.gif *.webp"),
            ("PNG", "*.png"),
            ("JPEG", "*.jpg *.jpeg"),
            ("Todos", "*.*"),
        ],
    )
    if path:
        caminho_var.set(path)
        lbl.config(text=os.path.basename(path), foreground="")


def _rodar_analise(root: tk.Tk, caminho_var: tk.StringVar, username_var: tk.StringVar, position_var: tk.StringVar, use_regions_var: tk.BooleanVar, txt: scrolledtext.ScrolledText, btn: ttk.Button) -> None:
    path = caminho_var.get().strip()
    if not path or not os.path.isfile(path):
        messagebox.showwarning("Aviso", "Selecione uma imagem válida antes de analisar.")
        return

    username = username_var.get().strip() or None
    position_manual = position_var.get().strip() or None
    use_reg = bool(use_regions_var.get())

    def tarefa():
        try:
            from pipeline import imagem_para_recomendacao
            resultado = imagem_para_recomendacao(path, username_player=username, position_manual=position_manual, use_regions=use_reg)
        except Exception as e:
            resultado = None
            erro = str(e)
        else:
            erro = None

        def atualizar_ui():
            btn.config(state=tk.NORMAL)
            txt.config(state=tk.NORMAL)
            txt.delete("1.0", tk.END)
            if erro:
                txt.insert(tk.END, f"Erro:\n{erro}")
                messagebox.showerror("Erro", erro)
            else:
                dados = resultado["dados_extraidos"]
                prob = resultado["probabilidade_vitoria"]
                rec = resultado["recomendacao"]
                texto = "--- Dados extraídos (JSON) ---\n"
                texto += json.dumps(dados, indent=2, ensure_ascii=False) + "\n\n"
                texto += "--- Probabilidade de vitória ---\n"
                texto += f"  {prob:.1%}\n\n"
                texto += "--- Recomendação ---\n"
                texto += rec
                txt.insert(tk.END, texto)
            txt.config(state=tk.DISABLED)

        root.after(0, atualizar_ui)

    btn.config(state=tk.DISABLED)
    txt.config(state=tk.NORMAL)
    txt.delete("1.0", tk.END)
    txt.insert(tk.END, "Processando... (extração + consultor). Aguarde.\n")
    txt.config(state=tk.DISABLED)
    thread = threading.Thread(target=tarefa, daemon=True)
    thread.start()


def main():
    root = criar_janela()
    root.mainloop()


if __name__ == "__main__":
    main()
