# AI Poker Player

Assistente de poker com IA que sugere a **melhor jogada** no Texas Hold'em com base em:

- **Posição** na mesa (UTG, CO, BTN, SB, BB, etc.)
- **Cartas da mesa** (flop, turn, river)
- **Probabilidade de vitória** (equity) calculada por simulação Monte Carlo
- **Contexto** opcional: tamanho do pote, stack, ações anteriores

**Provedores suportados (por prioridade):**

1. **Groq** — Llama 4 Scout (`meta-llama/llama-4-scout-17b-16e-instruct`), texto e imagem (vision), via API Groq  
2. **API OpenAI-compatible** — ex.: Llama 3.2 11B Vision (`meta-llama/Llama-3.2-11B-Vision-Instruct`), NVIDIA NIM, OpenLLM  
3. **Ollama (local)** — Llama 3.2 Vision (`llama3.2-vision`) ou outro modelo

---

## Requisitos

- **Python 3.8+**
- **Groq (recomendado):** chave em [console.groq.com](https://console.groq.com); modelo `meta-llama/llama-4-scout-17b-16e-instruct` (Llama 4 Scout, com vision)
- **Ollama (local):** [Ollama](https://ollama.com) e `ollama pull llama3.2-vision` (Llama 3.2 Vision)
- **Outra API:** endpoint OpenAI-compatible (chat + opcionalmente imagem)

---

## Instalação

```bash
# Clone o repositório (ou baixe e extraia)
git clone https://github.com/SEU_USUARIO/AI_poker_player.git
cd AI_poker_player

# Crie o ambiente virtual (recomendado)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
# source venv/bin/activate

# Instale as dependências
pip install -r requirements.txt

# Configure as variáveis de ambiente (copie o exemplo e preencha)
# Windows: copy .env.example .env
# Linux/macOS: cp .env.example .env
# Depois edite .env com suas chaves de API (ou use config_ui.py).
```

O arquivo `.env` não é commitado; use `.env.example` como modelo.

---

## Configuração da API (interface gráfica)

Para definir as variáveis de ambiente da API sem usar o terminal, use o frontend em Python (tkinter):

```bash
python config_ui.py
```

Abre uma janela com duas seções:

- **Groq (Llama 4 Scout):** chave da API Groq e modelo `meta-llama/llama-4-scout-17b-16e-instruct`. Se preenchida, tem prioridade.
- **Outra API:** URL base, chave e modelo (ex.: `meta-llama/Llama-3.2-11B-Vision-Instruct`). Usada se Groq não estiver configurada.

Clique em **Salvar em .env** para gravar em `.env`. O `main.py` carrega esse arquivo ao rodar. Se nada estiver definido, usa **Ollama local**.

---

## Uso

### Linha de comando

Exemplo **preflop**, posição no botão, cartas As e Kh:

```bash
python main.py --posicao BTN --cartas "As Kh"
```

Exemplo no **flop** com mesa Ah Ks 7d:

```bash
python main.py --posicao CO --cartas "Ad Kc" --mesa "Ah Ks 7d" --oponentes 2
```

Com **imagem** da mesa (screenshot) como contexto extra para o consultor:

```bash
python main.py --posicao BTN --cartas "As Kh" --mesa "Ah Ks 7d 2c" --imagem C:\caminho\mesa.png
```

### Extrair tudo da imagem (OCR + consultor) — dois LLMs

O sistema pode **ler uma imagem** da mesa (screenshot), usar um **LLM com visão** para extrair um JSON com posição, cartas, número de jogadores, BBs apostadas e risco pela posição, e em seguida passar esse JSON para o **segundo LLM** (consultor), que devolve a probabilidade de vitória e a recomendação.

**Requisito:** para a etapa de extração é necessário um modelo com visão: Groq `meta-llama/llama-4-scout-17b-16e-instruct` (Llama 4 Scout), Ollama `llama3.2-vision` ou API (`LLAMA_VISION_API_*`). O consultor pode ser o mesmo modelo Groq ou outro backend.

```bash
python main.py --extrair --imagem C:\caminho\screenshot_mesa.png
```

O JSON extraído segue o formato:

```json
{
  "quantos_player_na_mesa": 2,
  "posicao": "BTN",
  "suas_cartas": ["As", "Kh"],
  "cartas_mesa": ["Ah", "Ks", "7d"],
  "bbs_apostadas": 5.0,
  "risco_baseado_na_posicao": "button, last to act"
}
```

- **Etapa 1:** LLM de visão analisa a imagem e devolve esse JSON.  
- **Etapa 2:** O consultor (Groq ou outro) recebe os dados, calcula a equity e devolve a recomendação.

Exemplo com Groq (modelo `meta-llama/llama-4-scout-17b-16e-instruct` faz extração e consulta):

```bash
set GROQ_API_KEY=sua-chave
python main.py --extrair --imagem mesa.png
```

Alternativa com Ollama para visão e Groq para consultor:

```bash
set GROQ_API_KEY=sua-chave
ollama pull llama3.2-vision
python main.py --extrair --imagem mesa.png
```

### Interface para envio de imagem

Para usar com uma janela em vez da linha de comando:

```bash
python front_imagem.py
```

Abra uma imagem da mesa (screenshot ou foto), clique em **Analisar imagem** e aguarde. O resultado (JSON extraído, probabilidade de vitória e recomendação) aparece na própria janela. As variáveis de ambiente (Groq, API, etc.) são lidas do `.env`.

Opções úteis:

- `--pote 50` — tamanho do pote  
- `--stack 200` — seu stack  
- `--blind 1` — big blind  
- `--acoes "Villain bet 2bb"` — resumo das ações  
- `--simulacoes 1500` — mais simulações = equity mais estável  

### Groq (Llama 4 Scout) — recomendado

Defina a chave no `.env` (via `config_ui.py`) ou na linha de comando:

```bash
set GROQ_API_KEY=sua-chave-groq
python main.py --posicao BTN --cartas "As Kh" --mesa "Ah Ks 7d"
```

Ou explicitamente:

```bash
python main.py --groq --groq-key SUA_CHAVE --posicao CO --cartas "Ad Kc" --mesa "Ah Ks 7d"
```

Stream da resposta (texto saindo em tempo real):

```bash
python main.py --groq --groq-stream --posicao BTN --cartas "As Kh"
```

Modelo padrão: `meta-llama/llama-4-scout-17b-16e-instruct`. Para outro modelo: `--groq-model nome-do-modelo` ou variável `GROQ_MODEL`.

### Outra API (OpenAI-compatible)

Use um endpoint compatível com a API OpenAI (ex.: Llama 3.2 11B Vision, modelo `meta-llama/Llama-3.2-11B-Vision-Instruct`).

**Variáveis de ambiente:**

```bash
set LLAMA_VISION_API_BASE_URL=https://seu-servidor.com/v1
set LLAMA_VISION_API_KEY=sua-chave
set LLAMA_VISION_MODEL=meta-llama/Llama-3.2-11B-Vision-Instruct
python main.py --posicao BTN --cartas "As Kh" --mesa "Ah Ks 7d"
```

**Ou pela linha de comando:**

```bash
python main.py --api --api-url https://seu-servidor.com/v1 --api-key SUA_CHAVE --posicao CO --cartas "Ad Kc" --mesa "Ah Ks 7d"
```

### No seu código Python

```python
from advisor import melhor_jogada

# Usa Groq se GROQ_API_KEY estiver no .env; senão API ou Ollama
resultado = melhor_jogada(
    posicao="BTN",
    suas_cartas=["As", "Kh"],
    cartas_mesa=["Ah", "Ks", "7d"],
    num_oponentes=1,
    tamanho_pote=10,
    sua_stack=100,
    blind=1.0,
)

# Forçar Groq (Llama 4 Scout)
resultado = melhor_jogada(
    posicao="BTN",
    suas_cartas=["As", "Kh"],
    cartas_mesa=["Ah", "Ks", "7d"],
    use_groq=True,
    groq_api_key="sua-chave-groq",
    groq_model="meta-llama/llama-4-scout-17b-16e-instruct",
    groq_stream=False,
)

# Forçar outra API (OpenAI-compatible)
resultado = melhor_jogada(
    posicao="BTN",
    suas_cartas=["As", "Kh"],
    cartas_mesa=["Ah", "Ks", "7d"],
    use_api=True,
    api_base_url="https://seu-servidor.com/v1",
    api_key="sua-chave",
    api_model="meta-llama/Llama-3.2-11B-Vision-Instruct",
)

print("Equity:", resultado["probabilidade_vitoria"])
print("Recomendação:", resultado["recomendacao"])
```

---

## Formato das cartas

- **Valores:** `2`–`9`, `T` (10), `J`, `Q`, `K`, `A`  
- **Naipes:** `s` (espadas), `h` (copas), `d` (ouros), `c` (paus)  
- Exemplos: `As`, `Kh`, `Td`, `7c`  

---

## Posições

| Código | Nome        | Descrição breve      |
|--------|-------------|----------------------|
| UTG    | Under the Gun | Primeira a agir     |
| UTG+1  |              | Segunda a agir      |
| HJ     | Hijack      | Meio da mesa        |
| CO     | Cutoff      | Uma antes do botão  |
| BTN    | Button      | Melhor posição      |
| SB     | Small Blind | Cego pequeno        |
| BB     | Big Blind   | Cego grande         |

---

## Estrutura do projeto

- `poker_engine.py` — baralho, ranking de mãos, **probabilidade de vitória (Monte Carlo)**
- `posicao.py` — posições da mesa e descrições
- `advisor.py` — monta o prompt e chama o LLM consultor (Groq, API ou Ollama)
- `extractor.py` — LLM de visão para extrair JSON da mesa a partir de uma imagem (OCR)
- `pipeline.py` — encadeia extração (imagem → JSON) e consultor (JSON → probabilidade + recomendação)
- `main.py` — CLI: entrada manual (--posicao, --cartas) ou modo --extrair (imagem → JSON → recomendação)
- `config_ui.py` — interface gráfica para variáveis de ambiente (`.env`)
- `front_imagem.py` — interface gráfica para enviar uma imagem da mesa e ver JSON + recomendação

---

## Notas

- A **equity** é estimada por simulação; mais `--simulacoes` aumenta a precisão e o tempo.
- Os modelos (Llama 4 Scout, Llama 3.2 Vision) respondem em **inglês**; o prompt é em inglês para melhor resultado.
- Se não passar `--imagem`, a recomendação usa só **texto** (posição, cartas, equity, pote, etc.).
- **Ollama:** certifique-se de que está rodando (`ollama serve` ou abrindo o app) antes de usar no modo local.  
- **API:** o endpoint deve suportar o formato OpenAI para chat completions e conteúdo multimodal (`image_url` com base64 ou URL).

---

## Licença

[MIT](LICENSE)
