# -*- coding: utf-8 -*-
"""
Front simples para enviar uma imagem da mesa e obter extração (JSON) + recomendação.
Suporta atalho Ctrl+Shift+P para capturar a área da mesa (pré-definida) e analisar automaticamente.
"""
from __future__ import annotations
import csv
import json
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, scrolledtext

# Pasta e arquivo de log das análises (CSV)
LOG_DIR = "logs"
LOG_CSV = "analyses.csv"

# Versão exibida na interface (alinhada a pyproject.toml)
VERSION = "0.5.0"


def _caminho_log_csv() -> str:
    """Caminho do CSV de log (na pasta do projeto / logs / analyses.csv)."""
    base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(base, LOG_DIR), exist_ok=True)
    return os.path.join(base, LOG_DIR, LOG_CSV)


def _salvar_log_analise(path_imagem: str, resultado: dict | None = None, erro: str | None = None) -> None:
    """
    Append uma linha no CSV de log a cada análise (sucesso ou erro).
    Colunas: timestamp, image_path, position, pot, round, player_cards, community_cards,
    hand_sequence, probability, recommendation, player_bets_json, error.
    """
    path_csv = _caminho_log_csv()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path_imagem = path_imagem or ""

    if resultado:
        dados = resultado.get("dados_extraidos") or {}
        prob = resultado.get("probabilidade_vitoria", 0)
        rec = (resultado.get("recomendacao") or "").strip().replace("\n", " ")
        veredito = (resultado.get("veredito") or "").strip()
        position = dados.get("position", "")
        pot = dados.get("pot", "")
        round_ = dados.get("round", "")
        player_cards = json.dumps(dados.get("player_cards") or [], ensure_ascii=False)
        community_cards = json.dumps(dados.get("community_cards") or [], ensure_ascii=False)
        hand_seq = dados.get("hand_sequence", "")
        player_bets_json = json.dumps(dados.get("player_bets") or [], ensure_ascii=False)
        error_cell = ""
    else:
        position = pot = round_ = player_cards = community_cards = hand_seq = ""
        player_bets_json = ""
        rec = ""
        prob = ""
        veredito = ""
        error_cell = (erro or "").strip().replace("\n", " ")

    row = [now, path_imagem, position, pot, round_, player_cards, community_cards, hand_seq, prob, veredito, rec, player_bets_json, error_cell]
    file_exists = os.path.isfile(path_csv)
    try:
        with open(path_csv, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not file_exists:
                w.writerow([
                    "timestamp", "image_path", "position", "pot", "round", "player_cards", "community_cards",
                    "hand_sequence", "probability", "veredito", "recommendation", "player_bets", "error",
                ])
            w.writerow(row)
    except OSError:
        pass

# Carrega .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass


def _definir_area_mesa(root: tk.Tk, lbl_status: ttk.Label) -> None:
    """Abre overlay para o usuário desenhar a área da mesa e salva no config (runs in main thread)."""
    lbl_status.config(text="Selecione a área da mesa na tela (arraste o retângulo). ESC para cancelar.", foreground="gray")
    root.update_idletasks()
    try:
        from screen_capture import selecionar_regiao_interativa, salvar_regiao
        bbox = selecionar_regiao_interativa()
    except Exception as e:
        messagebox.showerror("Erro", f"Falha ao abrir seleção: {e}")
        lbl_status.config(text="", foreground="gray")
        return
    if bbox is None:
        lbl_status.config(text="Seleção cancelada.", foreground="gray")
        return
    left, top, right, bottom = bbox
    salvar_regiao(left, top, right - left, bottom - top)
    lbl_status.config(text="Área definida. Use Ctrl+Shift+P para capturar e analisar.", foreground="green")
    messagebox.showinfo("Área da mesa", "Área salva. Pressione Ctrl+Shift+P para capturar e analisar.")


def _aplicar_captura_e_analisar(
    root: tk.Tk,
    path: str,
    caminho_var: tk.StringVar,
    lbl_path: ttk.Label,
    username_var: tk.StringVar,
    position_var: tk.StringVar,
    use_regions_var: tk.BooleanVar,
    txt: scrolledtext.ScrolledText,
    btn: ttk.Button,
) -> None:
    """Define o path da imagem capturada e dispara a análise."""
    caminho_var.set(path)
    # Mostra caminho completo para você saber onde está a imagem (ex.: .../capturas/ultima_captura.png)
    lbl_path.config(text=path if len(path) <= 80 else path[:37] + "..." + path[-40:], foreground="")
    _rodar_analise(root, caminho_var, username_var, position_var, use_regions_var, txt, btn)


def _iniciar_listener_atalho(root: tk.Tk, refs: dict) -> None:
    """Registra atalho Ctrl+Shift+P: captura região salva e dispara análise no front."""
    def do_captura_e_analise():
        try:
            from screen_capture import capturar_regiao_salva
            path = capturar_regiao_salva()
        except Exception:
            path = None

        def no_main():
            if path is None:
                messagebox.showwarning(
                    "Área não definida",
                    "Defina a área da mesa primeiro (botão \"Definir área da mesa\").\nDepois use Ctrl+Shift+P para capturar e analisar."
                )
                return
            _aplicar_captura_e_analisar(
                root,
                path,
                refs["caminho_imagem"],
                refs["lbl_path"],
                refs["username_player"],
                refs["position_manual"],
                refs["use_regions"],
                refs["txt_resultado"],
                refs["btn_analisar"],
            )

        try:
            root.after(0, no_main)
        except tk.TclError:
            pass  # janela já fechada

    # Biblioteca 'keyboard' funciona melhor para atalho global no Windows
    try:
        import keyboard
        keyboard.add_hotkey("ctrl+shift+p", do_captura_e_analise, suppress=False)
        return
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: pynput (pode não reagir ao atalho em alguns Windows)
    try:
        from pynput import keyboard as kbd
        hotkey = kbd.HotKey(kbd.HotKey.parse("<ctrl>+<shift>+p"), do_captura_e_analise)
        listener = kbd.Listener(
            on_press=lambda key: hotkey.press(listener.canonical(key)),
            on_release=lambda key: hotkey.release(listener.canonical(key)),
        )
        listener.start()
        root._hotkey_listener = listener  # manter referência para não ser coletado
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

    # Área da mesa + atalho (Fase 2 e 3)
    frame_captura = ttk.Frame(frame_topo)
    frame_captura.pack(fill=tk.X, pady=6)
    lbl_captura_status = ttk.Label(frame_captura, text="", font=("", 8), foreground="gray")
    ttk.Button(frame_captura, text="Definir área da mesa", command=lambda: _definir_area_mesa(root, lbl_captura_status)).pack(side=tk.LEFT, padx=(0, 8))
    lbl_captura_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
    try:
        from screen_capture import carregar_regiao
        if carregar_regiao() is not None:
            lbl_captura_status.config(text="Área definida. Use Ctrl+Shift+P para capturar e analisar.", foreground="green")
    except Exception:
        pass
    ttk.Label(frame_captura, text="Na primeira vez: defina a área. Depois use Ctrl+Shift+P para capturar e analisar.", font=("", 8), foreground="gray").pack(anchor=tk.W)

    # Botão Analisar
    btn_analisar = ttk.Button(frame_topo, text="Analisar imagem (extrair + recomendar)", command=lambda: _rodar_analise(root, caminho_imagem, username_player, position_manual, use_regions, txt_resultado, btn_analisar))
    btn_analisar.pack(pady=4)

    # Área de resultado (rolável)
    ttk.Label(root, text="Resultado", font=("", 9, "bold")).pack(anchor=tk.W, padx=10, pady=(8, 0))
    txt_resultado = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=18, font=("Consolas", 9), state=tk.DISABLED, padx=8, pady=8)
    txt_resultado.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

    # Rodapé: só a versão
    ttk.Label(root, text=f"v{VERSION}", font=("", 8), foreground="gray").pack(anchor=tk.E, padx=10, pady=(0, 6))

    # Refs para o atalho Ctrl+Shift+P (captura e analisa)
    root._captura_refs = {
        "caminho_imagem": caminho_imagem,
        "lbl_path": lbl_path,
        "username_player": username_player,
        "position_manual": position_manual,
        "use_regions": use_regions,
        "txt_resultado": txt_resultado,
        "btn_analisar": btn_analisar,
    }
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

        _salvar_log_analise(path, resultado=resultado, erro=erro)

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
                veredito = resultado.get("veredito", "")
                preflop = resultado.get("preflop_engine")
                texto = "--- Dados extraídos (JSON) ---\n"
                texto += json.dumps(dados, indent=2, ensure_ascii=False) + "\n\n"
                texto += "--- Probabilidade de vitória ---\n"
                texto += f"  {prob:.1%}\n\n"
                if preflop:
                    texto += "--- Motor pré-flop ---\n"
                    texto += f"  Ação: {preflop.get('recommended_action', '')} | Mão: {preflop.get('hand', '')} ({preflop.get('hand_class', '')}) | Cenário: {preflop.get('scenario', '')}\n"
                    texto += f"  Confiança: {preflop.get('confidence', 0)}\n\n"
                if veredito:
                    texto += "--- Veredito ---\n"
                    texto += f"  {veredito}\n\n"
                texto += "--- Recomendação ---\n"
                texto += rec
                txt.insert(tk.END, texto)
            txt.see(tk.END)
            txt.config(state=tk.DISABLED)

        root.after(0, atualizar_ui)

    btn.config(state=tk.DISABLED)
    txt.config(state=tk.NORMAL)
    txt.delete("1.0", tk.END)
    txt.insert(tk.END, "Processando... (extração + consultor). Aguarde.\n")
    txt.see(tk.END)
    txt.config(state=tk.DISABLED)
    thread = threading.Thread(target=tarefa, daemon=True)
    thread.start()


def main():
    root = criar_janela()
    _iniciar_listener_atalho(root, root._captura_refs)
    root.mainloop()


if __name__ == "__main__":
    main()
