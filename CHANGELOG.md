# Changelog

## [0.4.0]

### Adicionado

- **6 regiões de assentos** (`image_regions.py`): recortes por assento (seat_12h … seat_10h) e região do botão dealer, com coordenadas ajustáveis (ref 953×663 px)
- **Identificação do BTN pelos assentos**: extração de posição usando imagem composta só dos 6 assentos; o botão dealer (D) é identificado **dentro** do recorte do assento onde aparece (evita confusão BTN/CO)
- **`recortar_assentos_e_botao()`** e **`montar_imagem_assentos_composite()`** para o extrator; parâmetro **`use_seat_crops`** na extração por regiões (padrão True)
- Pipeline e front: opção de extração por regiões passa a usar os 6 assentos + board + hole cards

### Alterado

- Regiões dos assentos definidas por retângulos em pixels convertidos para proporção (permite ajuste fino por mesa)
- Prompt de assentos (PROMPT_SEATS) passa a usar apenas os 6 crops; D deve ser visto em um dos recortes de assento

---

## [0.3.0]

### Adicionado

- Documentação de deploy (`DEPLOY.md`): passo a passo para release no GitHub, publicação no PyPI e deploy em servidor

---

## [0.2.0]

### Adicionado

- Extração por imagem com schema em inglês: `player_cards`, `community_cards`, `position`, `total_number_of_players`, `money_beted`, `risk_based_on_position_player`
- **Mão vazia:** `player_cards` pode ser `[]` (sem cartas na mão); não retorna erro, equity 0% e consultor segue com recomendação
- Campo **username (jogador)** no front de imagem para o LLM identificar as cartas do jogador
- Suporte a **Llama 4 Scout (Groq)** com vision para extração e consulta no mesmo modelo
- Unificação de chaves no pipeline (aceita schema novo e antigo)

### Alterado

- Prompt do extrator: `player_cards` com 0 ou 2 cartas; instrução para usar `[]` quando não houver cartas visíveis
- README reestruturado com visão geral, schema do JSON, preparação para release e uso como agente

### Corrigido

- Uso do modelo correto na Groq (`meta-llama/llama-4-scout-17b-16e-instruct`) em vez de nome do Ollama
- Tratamento de resposta inesperada da API Groq (evita `'str' object has no attribute 'choices'`)

---

## [0.1.0]

- Versão inicial: motor de poker, posições, advisor (Groq/API/Ollama), extrator por imagem, pipeline, CLI e interfaces (config_ui, front_imagem)
