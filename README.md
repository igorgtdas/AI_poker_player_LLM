# AI Poker Player

**Agente de IA** para Texas Hold'em que analisa posição, cartas e contexto da mesa e sugere a **melhor jogada** (FOLD, CHECK, CALL, RAISE). Suporta entrada manual ou **extração a partir de imagem** da mesa (screenshot) via LLM com visão.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Visão geral

- **Entrada:** posição na mesa, suas cartas (hole cards), cartas comunitárias (flop/turn/river), número de oponentes, pote e stack.
- **Saída:** probabilidade de vitória (equity, Monte Carlo) e **recomendação** em texto (modelo de linguagem).
- **Modo imagem:** envia uma foto/screenshot da mesa → um LLM com visão extrai um JSON (posição, `player_cards`, `community_cards`, etc.) → um segundo LLM (consultor) devolve equity e recomendação.
- **Mão vazia:** se não houver cartas na mão (`player_cards: []`), o sistema não retorna erro; a equity é 0% e o consultor pode recomendar FOLD.

### Provedores de modelo (prioridade)

| Ordem | Provedor | Modelo | Uso |
|-------|----------|--------|-----|
| 1 | **Groq** | `meta-llama/llama-4-scout-17b-16e-instruct` (Llama 4 Scout) | Texto e **imagem (vision)** — extração e consulta |
| 2 | **OpenAI** | `gpt-4o`, `gpt-4o-mini` | Texto e **imagem (vision)** — extração e consulta |
| 3 | API OpenAI-compatible | ex.: `meta-llama/Llama-3.2-11B-Vision-Instruct` | Visão e/ou texto |
| 4 | **Ollama** (local) | `llama3.2-vision` | Visão local |

---

## Requisitos

- **Python 3.8+**
- **Groq (recomendado):** chave em [console.groq.com](https://console.groq.com) — Llama 4 Scout com vision
- **OpenAI:** chave em [platform.openai.com](https://platform.openai.com) — use `gpt-4o` ou `gpt-4o-mini` (com vision)
- **Opcional:** Ollama com `llama3.2-vision` ou outra API com suporte a imagem

---

## Instalação

```bash
git clone https://github.com/SEU_USUARIO/AI_poker_player.git
cd AI_poker_player

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt
```

Configure as variáveis de ambiente (o `.env` **não** é commitado):

```bash
# Windows
copy .env.example .env

# Linux/macOS
cp .env.example .env
```

Edite o `.env` com suas chaves ou use a interface gráfica (`python config_ui.py`).

---

## Configuração

### Interface gráfica (recomendado)

```bash
python config_ui.py
```

- **Groq:** `GROQ_API_KEY` e `GROQ_MODEL` (padrão: Llama 4 Scout)
- **OpenAI:** `OPENAI_API_KEY` e `OPENAI_MODEL` (padrão: `gpt-4o-mini`) — para usar GPT-4o ou gpt-4o-mini
- **Outra API:** `LLAMA_VISION_API_BASE_URL`, `LLAMA_VISION_API_KEY`, `LLAMA_VISION_MODEL`

Salve em `.env`. Ordem de uso: Groq > OpenAI > outra API > Ollama local.

### Variáveis de ambiente (referência)

| Variável | Descrição |
|----------|-----------|
| `GROQ_API_KEY` | Chave da API Groq (prioridade) |
| `GROQ_MODEL` | Modelo Groq (padrão: `meta-llama/llama-4-scout-17b-16e-instruct`) |
| `OPENAI_API_KEY` | Chave da API OpenAI (para GPT-4o, gpt-4o-mini) |
| `OPENAI_MODEL` | Modelo OpenAI (padrão: `gpt-4o-mini`) |
| `LLAMA_VISION_API_BASE_URL` | URL base de API OpenAI-compatible |
| `LLAMA_VISION_API_KEY` | Chave dessa API |
| `LLAMA_VISION_MODEL` | Nome do modelo (ex.: `meta-llama/Llama-3.2-11B-Vision-Instruct`) |

---

## Uso

### 1. Linha de comando (entrada manual)

```bash
# Preflop, posição BTN, cartas A♠ K♥
python main.py --posicao BTN --cartas "As Kh"

# Flop com mesa A♥ K♠ 7♦, 2 oponentes
python main.py --posicao CO --cartas "Ad Kc" --mesa "Ah Ks 7d" --oponentes 2

# Com pote e blind
python main.py --posicao BTN --cartas "As Kh" --mesa "Ah Ks 7d" --pote 50 --blind 1
```

Parâmetros úteis: `--mesa`, `--oponentes`, `--pote`, `--stack`, `--blind`, `--acoes`, `--simulacoes`.

### 2. Extrair da imagem (screenshot da mesa)

Um LLM com visão extrai os dados da mesa; o consultor devolve equity e recomendação. **Não retorna erro** se não houver cartas na mão (`player_cards: []`).

```bash
python main.py --extrair --imagem C:\caminho\screenshot_mesa.png
```

Com Groq (um único modelo faz extração e consulta):

```bash
set GROQ_API_KEY=sua-chave
python main.py --extrair --imagem mesa.png
```

Para usar **OpenAI** (GPT-4o ou gpt-4o-mini):

```bash
set OPENAI_API_KEY=sk-sua-chave
set OPENAI_MODEL=gpt-4o-mini
python main.py --extrair --imagem mesa.png
```

Ou na linha de comando: `python main.py --openai --openai-model gpt-4o --extrair --imagem mesa.png`

**Extração por regiões (quadrantes):** a imagem pode ser dividida em 3 áreas com proporções fixas (válidas para qualquer tamanho):

1. **Foto inteira** — contexto: total de jogadores, position, round, pot.
2. **Parte central** — apenas as cartas do board (`community_cards`), sem as suas cartas.
3. **Suas cartas** — apenas o recorte das suas hole cards (`player_cards`).

Cada região é analisada pelo LLM com um prompt/schema específico; os resultados são mesclados em um único JSON. Use `--regioes` na linha de comando ou marque "Extrair por regiões" na interface gráfica. As proporções são definidas em `image_regions.py` (podem ser ajustadas conforme o layout da mesa).

```bash
python main.py --extrair --imagem mesa.png --regioes
```

### 3. Interface gráfica para imagem

```bash
python front_imagem.py
```

- Selecione a imagem da mesa
- Opcional: informe o **username** do jogador (para o modelo identificar suas cartas)
- Clique em **Analisar imagem (extrair + recomendar)**
- O resultado (JSON extraído, equity e recomendação) aparece na janela

---

## JSON extraído da imagem (schema)

O extrator devolve um objeto com as chaves abaixo. O pipeline aceita tanto esses nomes quanto os antigos (ex.: `suas_cartas`).

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `total_number_of_players` | int | Número de jogadores na mão |
| `position` | string | Sua posição: UTG, UTG+1, HJ, CO, BTN, SB, BB |
| `round` | string | Rodada atual: `preflop`, `flop`, `turn`, `river` |
| `player_cards` | array | **0 ou 2** cartas (hole cards). Vazio `[]` se sem cartas na mão, fold ou não visível |
| `community_cards` | array | Cartas do board. **Vazio `[]` no preflop** (nenhuma carta na mesa). Depois: 3 (flop), 4 (turn), 5 (river) |
| `pot` | number | Pot (pote) — valor já no pote / aposta a pagar (em BB ou valor absoluto) |
| `risk_based_on_position_player` | string | Breve avaliação do risco pela posição |

Exemplo:

```json
{
  "total_number_of_players": 2,
  "position": "BTN",
  "round": "flop",
  "player_cards": ["As", "Kh"],
  "community_cards": ["Ah", "Ks", "7d"],
  "pot": 5.0,
  "risk_based_on_position_player": "button, last to act"
}
```

Preflop (sem cartas na mesa — `community_cards` vazio):

```json
{
  "position": "BTN",
  "round": "preflop",
  "player_cards": ["As", "Kh"],
  "community_cards": [],
  "pot": 2.0,
  "risk_based_on_position_player": ""
}
```

Mão vazia (sem erro):

```json
{
  "position": "BTN",
  "round": "flop",
  "player_cards": [],
  "community_cards": ["Ah", "Ks", "7d"],
  "pot": 2.0,
  "risk_based_on_position_player": ""
}
```

---

## Formato das cartas

- **Valores:** `2`–`9`, `T` (10), `J`, `Q`, `K`, `A`
- **Naipes:** `s` (espadas), `h` (copas), `d` (ouros), `c` (paus)
- Exemplos: `As`, `Kh`, `Td`, `7c`

---

## Posições

| Código | Nome | Descrição |
|--------|------|-----------|
| UTG | Under the Gun | Primeira a agir |
| UTG+1 | | Segunda a agir |
| HJ | Hijack | Meio da mesa |
| CO | Cutoff | Uma antes do botão |
| BTN | Button | Melhor posição |
| SB | Small Blind | Cego pequeno |
| BB | Big Blind | Cego grande |

---

## Uso como biblioteca

```python
from advisor import melhor_jogada
from pipeline import imagem_para_recomendacao

# Entrada manual
resultado = melhor_jogada(
    posicao="BTN",
    suas_cartas=["As", "Kh"],
    cartas_mesa=["Ah", "Ks", "7d"],
    num_oponentes=1,
    tamanho_pote=10,
    blind=1.0,
)
print(resultado["probabilidade_vitoria"], resultado["recomendacao"])

# A partir de imagem (player_cards pode ser [])
resultado = imagem_para_recomendacao("screenshot_mesa.png", username_player="MeuNick")
print(resultado["dados_extraidos"]["player_cards"])
print(resultado["probabilidade_vitoria"], resultado["recomendacao"])
```

---

## Estrutura do projeto

| Arquivo | Função |
|---------|--------|
| `poker_engine.py` | Baralho, ranking de mãos, equity (Monte Carlo). Aceita 0 ou 2 hole cards. |
| `posicao.py` | Posições da mesa (UTG, BTN, etc.) |
| `advisor.py` | Monta o prompt e chama o LLM (Groq, API ou Ollama). Suporta mão vazia. |
| `extractor.py` | LLM de visão: imagem → JSON (`player_cards`, `community_cards`, etc.). |
| `pipeline.py` | Fluxo: imagem → extração → unificação de chaves → consultor. Aceita `player_cards: []`. |
| `main.py` | CLI: entrada manual ou `--extrair --imagem` |
| `config_ui.py` | Interface para configurar `.env` (Groq, API) |
| `front_imagem.py` | Interface para enviar imagem e ver JSON + recomendação |
| `image_regions.py` | Recorte proporcional da imagem em full, community_cards e hole_cards |

---

## Versão e publicação

- **Versão atual:** definida em `pyproject.toml` (ex.: `0.1.0`).
- Para **nova versão:** altere `version` em `pyproject.toml`, faça commit e crie uma tag:

```bash
# Edite pyproject.toml (campo version)
git add .
git commit -m "Release v0.2.0"
git tag v0.2.0
git push origin main --tags
```

No GitHub, em **Releases**, crie um release a partir da tag e descreva as mudanças.

---

## Notas

- **Equity:** estimada por Monte Carlo; `--simulacoes` aumenta precisão e tempo.
- **Idioma:** os prompts estão em inglês; as respostas dos modelos costumam vir em inglês.
- **Mão vazia:** `player_cards: []` não gera erro; equity = 0% e o consultor pode recomendar FOLD.
- **Groq:** Llama 4 Scout suporta visão; uma única chave basta para extração e consulta.
- **Ollama:** deve estar em execução (`ollama serve` ou app) quando for usado.

---

## Licença

[MIT](LICENSE)
