# -*- coding: utf-8 -*-
"""
Interface principal: recebe posição, cartas e opcionalmente imagem da mesa
e exibe a probabilidade de vitória + recomendação da IA (Llama 3.2 Vision).
"""
from __future__ import annotations
import argparse
import json
import os
import sys

# Carrega .env da pasta do projeto (definido pela interface config_ui.py)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from advisor import melhor_jogada
from pipeline import imagem_para_recomendacao


def parse_cartas(s: str) -> list[str]:
    """Aceita 'As Kh' ou 'As,Kh' e retorna lista ['As','Kh']."""
    return [c.strip() for c in s.replace(",", " ").split() if c.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="Assistente de poker: melhor jogada por posição/cartas ou por imagem da mesa (OCR + consultor)."
    )
    parser.add_argument("--extrair", "-e", action="store_true", help="Extrair dados da mesa a partir de uma imagem (LLM visão) e depois obter recomendação (segundo LLM)")
    parser.add_argument("--imagem", "-i", default="", help="Caminho da imagem da mesa. Obrigatório com --extrair.")
    parser.add_argument("--posicao", "-p", default="", help="Posição: UTG, HJ, CO, BTN, SB, BB (obrigatório sem --extrair)")
    parser.add_argument("--cartas", "-c", default="", help="Suas 2 cartas. Ex: 'As Kh' (obrigatório sem --extrair)")
    parser.add_argument("--mesa", "-m", default="", help="Cartas da mesa (flop/turn/river). Ex: 'Ah Ks 7d'")
    parser.add_argument("--oponentes", "-o", type=int, default=1, help="Número de oponentes (default: 1)")
    parser.add_argument("--simulacoes", "-s", type=int, default=800, help="Simulações Monte Carlo (default: 800)")
    parser.add_argument("--pote", type=float, default=0, help="Tamanho do pote")
    parser.add_argument("--stack", type=float, default=0, help="Seu stack")
    parser.add_argument("--blind", type=float, default=1.0, help="Big blind (default: 1)")
    parser.add_argument("--acoes", "-a", default="", help="Resumo das ações anteriores (texto livre)")
    parser.add_argument("--modelo", default="llama3.2-vision", help="Modelo Ollama (visão) ou nome na API")
    parser.add_argument("--api", action="store_true", help="Usar API em vez de Ollama local (use com --api-url)")
    parser.add_argument("--api-url", default="", help="URL base da API (OpenAI-compatible). Ou use env LLAMA_VISION_API_BASE_URL")
    parser.add_argument("--api-key", default="", help="Chave da API. Ou use env LLAMA_VISION_API_KEY")
    parser.add_argument("--api-model", default="", help="Nome do modelo na API. Ou env LLAMA_VISION_MODEL")
    parser.add_argument("--groq", action="store_true", help="Usar Groq (Llama 4 Scout). Ou defina env GROQ_API_KEY")
    parser.add_argument("--groq-key", default="", help="Chave da API Groq. Ou env GROQ_API_KEY")
    parser.add_argument("--groq-model", default="", help="Modelo Groq (default: meta-llama/llama-4-scout-17b-16e-instruct). Ou env GROQ_MODEL")
    parser.add_argument("--groq-stream", action="store_true", help="Stream da resposta da Groq")
    args = parser.parse_args()
    imagem_path = args.imagem.strip() or None
    acoes = args.acoes.strip() or None

    use_groq = args.groq or bool(args.groq_key or os.environ.get("GROQ_API_KEY"))
    groq_key = args.groq_key.strip() or os.environ.get("GROQ_API_KEY")
    groq_model = args.groq_model.strip() or os.environ.get("GROQ_MODEL")
    use_api = args.api or bool(args.api_url or os.environ.get("LLAMA_VISION_API_BASE_URL"))
    api_url = args.api_url.strip() or os.environ.get("LLAMA_VISION_API_BASE_URL")
    api_key = args.api_key.strip() or os.environ.get("LLAMA_VISION_API_KEY")
    api_model = args.api_model.strip() or os.environ.get("LLAMA_VISION_MODEL")

    # Modo: extrair da imagem (LLM visão → JSON → LLM consultor)
    if args.extrair:
        if not imagem_path or not os.path.isfile(imagem_path):
            print("Erro: com --extrair é obrigatório informar --imagem com um arquivo de imagem existente.", file=sys.stderr)
            sys.exit(1)
        print("Etapa 1: Extraindo dados da mesa com LLM de visão (OCR)...")
        try:
            resultado = imagem_para_recomendacao(
                imagem_path,
                use_vision_api=use_api,
                vision_api_base_url=api_url,
                vision_api_key=api_key,
                vision_api_model=api_model,
                vision_model_ollama=args.modelo,
                use_groq=use_groq,
                groq_api_key=groq_key,
                groq_model=groq_model,
                groq_stream=args.groq_stream,
                use_api=use_api,
                api_base_url=api_url,
                api_key=api_key,
                api_model=api_model,
                simulacoes=args.simulacoes,
                blind=args.blind,
            )
        except Exception as e:
            print(f"Erro: {e}", file=sys.stderr)
            sys.exit(1)
        print()
        print("--- Dados extraídos da imagem (JSON) ---")
        print(json.dumps(resultado["dados_extraidos"], indent=2, ensure_ascii=False))
        print()
        print("--- Probabilidade de vitória (equity) ---")
        print(f"  {resultado['probabilidade_vitoria']:.1%}")
        print()
        print("--- Recomendação (consultor) ---")
        print(resultado["recomendacao"])
        return 0

    # Modo: entrada manual (posição + cartas)
    if not args.posicao or not args.cartas:
        print("Erro: informe --posicao e --cartas, ou use --extrair com --imagem para extrair da imagem.", file=sys.stderr)
        sys.exit(1)
    cartas = parse_cartas(args.cartas)
    if len(cartas) != 2:
        print("Erro: informe exatamente 2 cartas (suas hole cards).", file=sys.stderr)
        sys.exit(1)
    mesa = parse_cartas(args.mesa) if args.mesa else []
    if len(mesa) not in (0, 3, 4, 5):
        print("Erro: mesa deve ter 0 (preflop), 3 (flop), 4 (turn) ou 5 (river) cartas.", file=sys.stderr)
        sys.exit(1)

    print("Calculando probabilidade de vitória e consultando a IA...")
    if use_groq:
        print("Modo: Groq (Llama 4 Scout)")
    elif use_api:
        print("Modo: API (OpenAI-compatible)")
    else:
        print("Modo: Ollama local")
    try:
        resultado = melhor_jogada(
            posicao=args.posicao,
            suas_cartas=cartas,
            cartas_mesa=mesa,
            num_oponentes=args.oponentes,
            simulacoes=args.simulacoes,
            tamanho_pote=args.pote,
            sua_stack=args.stack,
            blind=args.blind,
            acoes_anteriores=acoes,
            caminho_imagem=imagem_path,
            modelo=args.modelo,
            use_groq=use_groq,
            groq_api_key=groq_key or None,
            groq_model=groq_model or None,
            groq_stream=args.groq_stream,
            use_api=use_api,
            api_base_url=api_url or None,
            api_key=api_key or None,
            api_model=api_model or None,
        )
    except Exception as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)

    print()
    print("--- Probabilidade de vitória (equity) ---")
    print(f"  {resultado['probabilidade_vitoria']:.1%}")
    print()
    print("--- Recomendação ---")
    print(resultado["recomendacao"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
