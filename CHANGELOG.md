# Changelog

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
