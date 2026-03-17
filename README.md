# AI Poker Player

**Agente de IA** para Texas Hold'em que analisa posição, cartas e contexto da mesa e sugere a **melhor jogada** (FOLD, CHECK, CALL, RAISE). Suporta entrada manual ou **extração a partir de imagem** da mesa (screenshot) via LLM com visão.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Custom-blue.svg)](LICENSE)

---

## Visão geral

- **Entrada:** posição na mesa, suas cartas (hole cards), cartas comunitárias (flop/turn/river), número de oponentes, pote e stack.
- **Saída:** probabilidade de vitória (equity, Monte Carlo), **recomendação estruturada** (motivos, limitações, nota estratégica) e **veredito** (FOLD, CHECK, CALL, RAISE X BB).
- **Motor pré-flop:** quando `round == "preflop"`, um motor determinístico classifica a mão (premium/strong/playable, suited connector, etc.) e sugere ação por cenário (folded to hero, facing limp, facing open raise) e por posição.
- **Modo imagem:** envia uma foto/screenshot da mesa → um LLM com visão extrai um JSON (posição, `player_cards`, `community_cards`, etc.) → motor pré-flop (se preflop) e consultor devolvem equity e recomendação.
- **Mão vazia:** se não houver cartas na mão (`player_cards: []`), o sistema não retorna erro; a equity é 0% e o consultor pode recomendar FOLD.

### Provedores de modelo (prioridade)

| Ordem | Provedor | Modelo | Uso |
|-------|----------|--------|-----|
| 1 | **Groq** | `meta-llama/llama-4-scout-17b-16e-instruct` (Llama 4 Scout) | Texto e **imagem (vision)** — extração e consulta |
| 2 | **OpenAI** | `gpt-4.1`, `gpt-4o`, `gpt-4o-mini` | Texto e **imagem (vision)** — extração e consulta |
| 3 | API OpenAI-compatible | ex.: `meta-llama/Llama-3.2-11B-Vision-Instruct` | Visão e/ou texto |
| 4 | **Ollama** (local) | `llama3.2-vision` | Visão local |

---

## Requisitos

- **Python 3.8+** (testado em 3.11, 3.12, 3.13 e 3.14). Em 3.13/3.14 use `pip install --upgrade pip` e depois `pip install -r requirements.txt` para obter wheels compatíveis.
- **Groq (recomendado):** chave em [console.groq.com](https://console.groq.com) — Llama 4 Scout com vision
- **OpenAI:** chave em [platform.openai.com](https://platform.openai.com) — use `gpt-4.1`, `gpt-4o` ou `gpt-4o-mini` (com vision)
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

# Python 3.13/3.14: atualize o pip antes para obter wheels compatíveis
pip install --upgrade pip
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
- **OpenAI:** `OPENAI_API_KEY` e `OPENAI_MODEL` (padrão: `gpt-4o-mini`) — para usar gpt-4.1, gpt-4o ou gpt-4o-mini
- **Outra API:** `LLAMA_VISION_API_BASE_URL`, `LLAMA_VISION_API_KEY`, `LLAMA_VISION_MODEL`

Salve em `.env`. Ordem de uso: Groq > OpenAI > outra API > Ollama local.

### Variáveis de ambiente (referência)

| Variável | Descrição |
|----------|-----------|
| `GROQ_API_KEY` | Chave da API Groq (prioridade) |
| `GROQ_MODEL` | Modelo Groq (padrão: `meta-llama/llama-4-scout-17b-16e-instruct`) |
| `OPENAI_API_KEY` | Chave da API OpenAI (para gpt-4.1, gpt-4o, gpt-4o-mini) |
| `OPENAI_MODEL` | Modelo OpenAI (padrão: `gpt-4o-mini`; ex.: `gpt-4.1`, `gpt-4o`) |
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

Para usar **OpenAI** (gpt-4.1, gpt-4o ou gpt-4o-mini):

```bash
set OPENAI_API_KEY=sk-sua-chave
set OPENAI_MODEL=gpt-4.1
python main.py --extrair --imagem mesa.png
```

Ou na linha de comando: `python main.py --openai --openai-model gpt-4.1 --extrair --imagem mesa.png`

**Extração por regiões:** a imagem é dividida em regiões com proporções fixas (válidas para qualquer tamanho):

1. **Foto inteira** — contexto: total de jogadores, round, pot.
2. **Parte central** — apenas as cartas do board (`community_cards`), sem as suas cartas.
3. **Suas cartas** — apenas o recorte das suas hole cards (`player_cards`).
4. **6 regiões de assentos** — um crop por assento (seat_12h … seat_10h); o **botão dealer (D)** é identificado dentro do recorte do assento onde aparece. As chamadas ao LLM para os 6 assentos são feitas **em paralelo** para reduzir o tempo total.

O `total_number_of_players` é calculado de forma determinística (contagem de assentos com nome não vazio). O `risk_based_on_position_player` é derivado da posição (não mais pelo LLM). Apenas um assento pode ter `dealer_button: true`; se o botão não for identificado, o schema inclui `dealer_button_nao_identificado`. Use `--regioes` na linha de comando ou marque "Extrair por regiões" na interface gráfica. Proporções e coordenadas dos assentos em `image_regions.py`. Com `DEBUG_SAVE_REGIONS=1` os crops são salvos em `capturas/debug_regions/<timestamp>/`.

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
- O resultado (JSON extraído, equity, recomendação estruturada e veredito FOLD/CHECK/CALL/RAISE) aparece na janela. As análises são registradas em `logs/analyses.csv`.

---

## JSON extraído da imagem (schema)

O extrator devolve um objeto com as chaves abaixo. O pipeline aceita tanto esses nomes quanto os antigos (ex.: `suas_cartas`).

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `total_number_of_players` | int | Número de jogadores na mão (calculado pela contagem de assentos com nome não vazio) |
| `position` | string | Sua posição: UTG, UTG+1, HJ, CO, BTN, SB, BB (derivada dos assentos e do botão dealer) |
| `round` | string | Rodada atual: `preflop`, `flop`, `turn`, `river` |
| `player_cards` | array | **0 ou 2** cartas (hole cards). Vazio `[]` se sem cartas na mão, fold ou não visível |
| `community_cards` | array | Cartas do board. **Vazio `[]` no preflop** (nenhuma carta na mesa). Depois: 3 (flop), 4 (turn), 5 (river) |
| `pot` | number | Pot (pote) — valor já no pote / aposta a pagar (em BB ou valor absoluto) |
| `risk_based_on_position_player` | string | Avaliação do risco pela posição (derivada da posição, não do LLM) |
| `player_bets` | array | Por assento: `seat`, `name`, `dealer_button` (apenas um assento com `dealer_button: true`) |
| `dealer_button_nao_identificado` | bool | Presente quando o botão dealer não pôde ser identificado nos crops dos assentos |

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
# Recomendação estruturada e veredito (FOLD, CHECK, CALL, RAISE X BB)
print(resultado.get("veredito"), resultado.get("recommendation"))  # se disponíveis
```

---

## Estrutura do projeto

| Arquivo | Função |
|---------|--------|
| `poker_engine.py` | Baralho, ranking de mãos, equity (Monte Carlo). Aceita 0 ou 2 hole cards. |
| `preflop_engine.py` | Motor pré-flop: classificação de mão (premium/strong/playable, suited connector, etc.), cenários (folded to hero, facing limp, open raise), ranges por posição. |
| `posicao.py` | Posições da mesa (UTG, BTN, etc.) |
| `advisor.py` | Monta o prompt e chama o LLM (Groq, API ou Ollama). Integra motor pré-flop quando `round == "preflop"`. Suporta mão vazia. |
| `extractor.py` | LLM de visão: imagem → JSON. Extração por regiões com 6 crops de assentos em paralelo (ThreadPoolExecutor), board e hole cards. |
| `pipeline.py` | Fluxo: imagem → extração → unificação de chaves → motor pré-flop (se preflop) → consultor. Aceita `player_cards: []`. Retorna recomendação estruturada e veredito (FOLD, CHECK, CALL, RAISE). |
| `main.py` | CLI: entrada manual ou `--extrair --imagem` |
| `config_ui.py` | Interface para configurar `.env` (Groq, API) |
| `front_imagem.py` | Interface para enviar imagem e ver JSON + recomendação + veredito (rodapé com versão) |
| `image_regions.py` | Recorte proporcional: full, board, hole cards e 6 assentos (seat_12h … seat_10h); coordenadas ajustáveis |

---

## Versão e publicação

- **Versão atual:** definida em `pyproject.toml` e no rodapé da interface (`front_imagem.py`, constante `VERSION`). Ex.: `0.5.0`.
- Para **nova versão:** altere `version` em `pyproject.toml` e `VERSION` em `front_imagem.py`, atualize o `CHANGELOG.md`, faça commit e crie uma tag anotada:

```bash
# Edite pyproject.toml e front_imagem.py (version / VERSION)
git add .   # não inclua .env, api_key*.txt, capturas/, logs/
git commit -m "Release v0.5.0: ..."
git tag -a v0.5.0 -m "v0.5.0: descrição"
git push origin main
git push origin v0.5.0
```

No GitHub, em **Releases**, crie um release a partir da tag e descreva as mudanças.

---

## Notas

- **Equity:** estimada por Monte Carlo; `--simulacoes` aumenta precisão e tempo.
- **Pré-flop:** o motor em `preflop_engine.py` classifica a mão e sugere ação por cenário e posição; o consultor recebe essa análise no prompt.
- **Recomendação:** formato estruturado (motivos, limitações, nota estratégica) e veredito enum (FOLD, CHECK, CALL, RAISE X BB) extraído por um segundo agente.
- **Log:** análises da interface são registradas em `logs/analyses.csv` (timestamp, path, position, pot, round, cartas, probability, recommendation, veredito, etc.).
- **Idioma:** os prompts estão em inglês; as respostas dos modelos costumam vir em inglês.
- **Mão vazia:** `player_cards: []` não gera erro; equity = 0% e o consultor pode recomendar FOLD.
- **Groq:** Llama 4 Scout suporta visão; uma única chave basta para extração e consulta.
- **Ollama:** deve estar em execução (`ollama serve` ou app) quando for usado.

---

## Problemas com o venv (Python 3.13 / 3.14)

Se aparecer **`cannot import name '_imaging' from 'PIL'`** ou **`No module named 'pydantic_core._pydantic_core'`**:

1. Atualize o pip e reinstale as dependências (garante wheels compatíveis com 3.13/3.14):
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt --upgrade --force-reinstall
   ```
2. Se ainda falhar, recrie o venv e instale de novo:
   ```bash
   # Windows
   Remove-Item -Recurse -Force venv
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. Confirme: `python -c "from openai import OpenAI; from PIL import Image; print('OK')"`

---

## Licença

[Licença personalizada](LICENSE) — uso pessoal, educacional e de pesquisa; uso comercial requer permissão do autor.
