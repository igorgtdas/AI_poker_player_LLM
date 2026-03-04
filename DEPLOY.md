# Passo a passo para deploy — AI Poker Player

Este projeto pode ser “entregue” de três formas principais. Escolha conforme seu objetivo.

---

## 1. Release no GitHub (recomendado para abrir o projeto)

Para versionar e divulgar o código (tags, Releases, changelog).

### Passos

1. **Atualize a versão** em `pyproject.toml`:
   ```toml
   version = "0.2.0"   # altere para 0.3.0, 1.0.0, etc.
   ```

2. **Atualize o CHANGELOG.md** (opcional mas recomendado) com as mudanças da versão.

3. **Commit e push**:
   ```powershell
   git add .
   git status
   git commit -m "Release v0.3.0"
   git push origin main
   ```

4. **Crie a tag e envie**:
   ```powershell
   git tag v0.3.0
   git push origin v0.3.0
   ```

5. **Crie o Release no GitHub**:
   - Repositório → **Releases** → **Create a new release**
   - Escolha a tag (ex.: `v0.3.0`)
   - Título: `v0.3.0` (ou o que preferir)
   - Descreva as mudanças (pode copiar do CHANGELOG)
   - **Publish release**

---

## 2. Publicar no PyPI (para instalar com `pip install`)

Para que qualquer pessoa instale o pacote com `pip install ai-poker-player`.

### Pré-requisitos

- Conta no [PyPI](https://pypi.org) (e opcionalmente [TestPyPI](https://test.pypi.org) para testes)
- Ferramenta de build: `pip install build twine`

### Passos

1. **Garanta que `pyproject.toml` está correto** (nome, versão, dependências). Já está configurado.

2. **Gere os arquivos de distribuição**:
   ```powershell
   cd c:\Users\igor_\PROJETOS\AI_poker_player_LLM
   python -m build
   ```
   Isso gera a pasta `dist/` com `.whl` e `.tar.gz`.

3. **Teste no TestPyPI** (opcional):
   ```powershell
   python -m twine upload --repository testpypi dist/*
   ```
   Use seu usuário/senha do TestPyPI (ou token).

4. **Publicar no PyPI**:
   ```powershell
   python -m twine upload dist/*
   ```
   Use usuário e senha (ou token de API) do PyPI.

5. **Instalação por terceiros**:
   ```bash
   pip install ai-poker-player
   ```

---

## 3. Deploy em servidor (web/API)

O projeto hoje é **CLI + interfaces gráficas (tkinter)**. Não há servidor HTTP. Para “subir” em um servidor acessível pela web você precisaria:

1. **Criar uma API** (ex.: FastAPI ou Flask) que chame `advisor.melhor_jogada` e `pipeline.imagem_para_recomendacao`.
2. **Configurar variáveis de ambiente** no provedor (Groq/OpenAI keys).
3. **Escolher uma plataforma**:
   - **Render / Railway / Fly.io**: app Python, definir comando (ex.: `uvicorn app:app`) e env vars.
   - **VPS (DigitalOcean, etc.)**: instalar Python, clonar o repo, configurar `.env` e rodar a API com gunicorn/uvicorn atrás de nginx.

Se quiser, posso esboçar um `app.py` mínimo com FastAPI para expor as funções atuais como endpoints e um passo a passo para um provedor específico (ex.: Render).

---

## Resumo rápido

| Objetivo                    | Use                          |
|----------------------------|------------------------------|
| Só versionar e divulgar    | **1. Release no GitHub**     |
| Distribuir como pacote pip | **2. PyPI**                  |
| App/site na internet       | **3. Deploy em servidor** (criar API antes) |

---

## Checklist antes de qualquer deploy

- [ ] Versão em `pyproject.toml` atualizada
- [ ] `.env` **não** está no repositório (está no `.gitignore`)
- [ ] `api_key_groq.txt` e chaves **não** commitados
- [ ] Testes básicos passando (se tiver): `pytest`
