# -*- coding: utf-8 -*-
"""
Frontend básico para configurar as variáveis de ambiente (Groq, API ou Ollama).
Salva em .env na pasta do projeto; main.py carrega esse arquivo ao rodar.
"""
from __future__ import annotations
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

# Caminho do .env na pasta do projeto
DIR_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ENV = os.path.join(DIR_PROJETO, ".env")

# Groq tem prioridade: se GROQ_API_KEY estiver definida, usa Llama 4 Scout
VARIAVEIS_GROQ = [
    ("GROQ_API_KEY", "Chave da API Groq (obrigatório para Groq)", ""),
    ("GROQ_MODEL", "Modelo Groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
]
# API OpenAI-compatible (ex.: Llama Vision); usada se GROQ_API_KEY não estiver definida
VARIAVEIS_API = [
    ("LLAMA_VISION_API_BASE_URL", "URL base da API (outros provedores)", "https://api.exemplo.com/v1"),
    ("LLAMA_VISION_API_KEY", "Chave da API (opcional)", ""),
    ("LLAMA_VISION_MODEL", "Nome do modelo na API", "meta-llama/Llama-3.2-11B-Vision-Instruct"),
]
VARIAVEIS = VARIAVEIS_GROQ + VARIAVEIS_API


def carregar_env() -> dict[str, str]:
    """Lê o .env atual e retorna um dict nome -> valor."""
    result = {}
    if not os.path.isfile(ARQUIVO_ENV):
        return result
    with open(ARQUIVO_ENV, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def salvar_env(valores: dict[str, str]) -> None:
    """Escreve o .env com os valores informados."""
    with open(ARQUIVO_ENV, "w", encoding="utf-8") as f:
        f.write("# AI Poker Player - Groq (Llama 4 Scout) e/ou API OpenAI-compatible\n")
        f.write("# Gerado pela interface de configuração.\n\n")
        f.write("# --- Groq (prioridade) ---\n")
        for nome, _, _ in VARIAVEIS_GROQ:
            valor = valores.get(nome, "")
            if "\n" in valor or " " in valor or not valor:
                valor = f'"{valor}"'
            f.write(f"{nome}={valor}\n")
        f.write("\n# --- Outra API (se GROQ_API_KEY não estiver definida) ---\n")
        for nome, _, _ in VARIAVEIS_API:
            valor = valores.get(nome, "")
            if "\n" in valor or " " in valor or not valor:
                valor = f'"{valor}"'
            f.write(f"{nome}={valor}\n")


def criar_janela() -> tk.Tk:
    """Cria e retorna a janela principal de configuração."""
    root = tk.Tk()
    root.title("AI Poker Player — Configuração (Groq / API / Ollama)")
    root.geometry("560x340")
    root.resizable(True, True)

    # Carregar valores atuais (env do sistema + .env)
    env_atual = dict(os.environ)
    env_atual.update(carregar_env())

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frame, text="Variáveis de ambiente", font=("", 10, "bold")).pack(anchor=tk.W)
    ttk.Label(frame, text="Salvas em .env e usadas ao rodar main.py. Groq tem prioridade se GROQ_API_KEY estiver definida.", foreground="gray").pack(anchor=tk.W)
    ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

    entries = {}
    ttk.Label(frame, text="Groq (Llama 4 Scout)", font=("", 9, "bold")).pack(anchor=tk.W, pady=(4, 2))
    for nome, label, placeholder in VARIAVEIS_GROQ:
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=38, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 8))
        var = tk.StringVar(value=env_atual.get(nome, "" if nome == "GROQ_API_KEY" else placeholder))
        entry = ttk.Entry(row, textvariable=var, width=42)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entries[nome] = var

    ttk.Label(frame, text="Outra API (OpenAI-compatible)", font=("", 9, "bold")).pack(anchor=tk.W, pady=(12, 2))
    for nome, label, placeholder in VARIAVEIS_API:
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=38, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 8))
        var = tk.StringVar(value=env_atual.get(nome, placeholder if nome != "LLAMA_VISION_API_KEY" else ""))
        entry = ttk.Entry(row, textvariable=var, width=42)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entries[nome] = var

    ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)

    def on_salvar():
        valores = {nome: entries[nome].get().strip() for nome, _, _ in VARIAVEIS}
        if not valores.get("GROQ_API_KEY") and not valores.get("LLAMA_VISION_API_BASE_URL"):
            messagebox.showwarning("Aviso", "Nenhuma API configurada. Defina GROQ_API_KEY (Groq) ou URL base (outra API); caso contrário será usado Ollama local.")
        salvar_env(valores)
        messagebox.showinfo("Salvo", f"Configuração salva em:\n{ARQUIVO_ENV}")

    def on_abrir_pasta():
        if sys.platform == "win32":
            os.startfile(DIR_PROJETO)
        elif sys.platform == "darwin":
            subprocess.run(["open", DIR_PROJETO], check=False)
        else:
            subprocess.run(["xdg-open", DIR_PROJETO], check=False)

    botoes = ttk.Frame(frame)
    botoes.pack(fill=tk.X, pady=4)
    ttk.Button(botoes, text="Salvar em .env", command=on_salvar).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(botoes, text="Abrir pasta do projeto", command=on_abrir_pasta).pack(side=tk.LEFT)
    ttk.Label(frame, text="", font=("", 8), foreground="gray").pack(anchor=tk.W)
    ttk.Label(frame, text="Dica: preencha GROQ_API_KEY para usar Llama 4 Scout na Groq. Senão, use URL base ou Ollama local.", font=("", 8), foreground="gray").pack(anchor=tk.W)

    return root


def main():
    root = criar_janela()
    root.mainloop()


if __name__ == "__main__":
    main()
