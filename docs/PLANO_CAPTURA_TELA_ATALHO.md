# Plano: Captura de área da tela + atalho para o front

Objetivo: **pressionar um atalho** → **capturar uma área da tela** (ou tela inteira) → **o front recebe o “print”** e **executa a análise (extração + recomendação) automaticamente**.

---

## 1. Visão geral do fluxo

```
[Usuário pressiona atalho] → [Captura da tela/região] → [Salva em arquivo temp]
       → [Front recebe o path] → [Preenche “imagem” e dispara análise]
```

Duas formas de o front “receber” o print:

- **A) Front já aberto**: o atalho está registrado pelo próprio front; ao pressionar, ele captura, define o path na interface e chama “Analisar” internamente.
- **B) Front pode estar fechado**: um processo em segundo plano (tray ou daemon) escuta o atalho; ao pressionar, captura, salva e abre o front passando o path (e opcionalmente já dispara a análise).

Recomendação: começar com **A** (tudo no front, atalho só funciona com a janela aberta) e depois evoluir para **B** se quiser atalho global mesmo com o front fechado.

---

## 2. Componentes

### 2.1 Captura de tela

| Modo              | Descrição                    | Biblioteca / API                    |
|-------------------|-----------------------------|-------------------------------------|
| Tela inteira      | Screenshot do monitor       | `PIL.ImageGrab.grab()` (Windows) ou `mss` |
| Região fixa       | Retângulo configurável (ex.: mesa) | `ImageGrab.grab(bbox=(x1,y1,x2,y2))` ou `mss` |
| Região selecionada| Usuário desenha o retângulo na tela | Overlay (tkinter ou PyQt) + `ImageGrab.grab(bbox)` |

- **Windows**: `PIL.ImageGrab` é simples e suficiente.
- **Cross-platform**: `mss` (vários monitores, performático).
- Região selecionada: janela fullscreen transparente; mouse down = início, mouse up = fim; com as coordenadas chama `grab(bbox)`.

### 2.2 Atalho global

- **pynput**: `keyboard.Listener` com combinação (ex.: `Ctrl+Shift+P`), funciona em segundo plano; não costuma precisar de admin.
- **keyboard** (pip `keyboard`): `add_hotkey("ctrl+shift+p", callback)`; em alguns Windows pode pedir elevação para hook global.
- Recomendação: **pynput** para atalho global em thread separada, sem bloquear o mainloop do tkinter.

### 2.3 Integração com o front

- O front já tem: `caminho_imagem` (StringVar), botão “Analisar” que chama `_rodar_analise(root, caminho_imagem, ...)`.
- Ao capturar: salvar em arquivo temporário (ex.: `tempfile.gettempdir() + "/poker_capture.png"`), fazer `caminho_imagem.set(path)` e chamar a mesma função `_rodar_analise(...)` (e atualizar o label do path).
- Atalho deve ser tratado em thread (pynput); a atualização da UI (set path, chamar análise) deve ser feita com `root.after(0, ...)` para rodar no thread do tkinter.

---

## 3. Fases de implementação

### Fase 1 – Atalho + captura de tela inteira (mínimo viável)

1. Adicionar dependência: `pynput` (e manter `Pillow` para `ImageGrab`).
2. No front (`front_imagem.py`):
   - Ao iniciar (ou ao clicar em “Ativar atalho”), iniciar em thread um `pynput.keyboard.Listener` com atalho ex.: `Ctrl+Shift+P`.
   - Callback do atalho: chamar função `capturar_tela_inteira()` que usa `ImageGrab.grab()`, salva em `tempfile.gettempdir() + "/poker_capture.png"`, retorna o path.
   - No callback (em thread): usar `root.after(0, lambda: _aplicar_captura_e_analisar(...))` para no main thread: setar `caminho_imagem.set(path)`, atualizar label, chamar `_rodar_analise(...)` (e marcar “extrair por regiões” se for o padrão desejado).
3. Opção na interface: “Atalho: Ctrl+Shift+P — captura tela inteira e analisa” (checkbox ou botão “Ativar atalho” para ligar/desligar o listener).

Resultado: com o front aberto, usuário pressiona Ctrl+Shift+P → tela inteira é capturada → front recebe o path e roda a análise automaticamente.

### Fase 2 – Captura de região selecionada

1. Ao pressionar o atalho (ou um segundo atalho, ex.: `Ctrl+Shift+R`):
   - Abrir janela fullscreen transparente (ou quase) sobre toda a tela.
   - Mouse down: guardar (x0, y0).
   - Mouse move: desenhar retângulo de (x0,y0) até (x,y) atual (apagar o anterior).
   - Mouse up: guardar (x1, y1), fechar overlay, chamar `ImageGrab.grab(bbox=(min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1)))`, salvar em temp, e então `root.after(0, ...)` para setar path e rodar análise (como na Fase 1).
2. Ajustes: garantir que a overlay não capture a si mesma (capturar depois de fechar a overlay ou usar outro monitor/coordenadas).

Resultado: atalho → usuário desenha a área da mesa → solta o mouse → captura só essa região e o front recebe e analisa.

### Fase 3 – Região fixa configurável (opcional)

- Guardar em config (json/ini) as coordenadas da região “mesa” (ex.: x, y, largura, altura).
- Opção no front: “Usar região fixa para captura” + botão “Definir região” (abre overlay uma vez para o usuário desenhar; salva x,y,w,h).
- No atalho: se “região fixa” estiver ativa, capturar direto com `grab(bbox=...)` sem abrir overlay.

Resultado: um único atalho captura sempre a mesma área (a mesa), sem desenhar cada vez.

### Fase 4 – Atalho com front fechado (opcional)

- Script separado (ex.: `captura_atalho.py`) ou entry point no pacote:
  - Roda em background (tray ou só loop); registra o mesmo atalho com pynput.
  - Ao pressionar: captura (tela inteira ou região, conforme config), salva em path fixo (ex.: temp + `poker_capture.png`).
  - Abre o front passando o path como argumento: `python front_imagem.py --capture /path/to/poker_capture.png`.
  - O front, ao iniciar, lê `sys.argv`; se tiver `--capture <path>`, seta o path, mostra a janela e dispara `_rodar_analise(...)` uma vez após 100 ms (para a janela já estar visível).
- Alternativa: o daemon apenas salva o arquivo e coloca o path em um “arquivo de pedido” (ex.: `poker_capture_request.txt`); um front que fique rodando minimizado faz polling e, ao ver novo path, carrega e analisa.

---

## 4. Dependências

- **Já existentes**: `Pillow` (ImageGrab no Windows).
- **Novas**:
  - `pynput` – atalho global (recomendado).
  - Opcional: `mss` se quiser captura cross-platform ou multi-monitor mais robusta.

Em `requirements.txt` (ou pyproject.toml):

```
pynput>=1.7.0
```

---

## 5. Estrutura de código sugerida

- **front_imagem.py**:
  - `capturar_tela_inteira() -> str` (path do temp).
  - `capturar_regiao_interativa(root) -> str | None` (overlay, retorna path ou None se cancelar).
  - `_aplicar_captura_e_analisar(path, ...)` (set path, atualizar label, chamar `_rodar_analise`).
  - No `criar_janela()`: botão “Ativar atalho (Ctrl+Shift+P)” e início do listener em thread; variável/estado para “analisar automaticamente ao capturar” (checkbox).
- **Opcional**: `screen_capture.py` no projeto com `capture_fullscreen()` e `capture_region(bbox)` para desacoplar da UI e reutilizar em CLI/daemon.

---

## 6. Resumo

| Item                         | Sugestão                                                |
|-----------------------------|---------------------------------------------------------|
| Onde o atalho é registrado  | No próprio front (Fase 1); depois opcionalmente daemon |
| Captura                     | PIL `ImageGrab` (Windows); opcional `mss`              |
| Atalho                      | `Ctrl+Shift+P` (captura + analisa)                     |
| Como o front “recebe” o print | Path em temp → `caminho_imagem.set(path)` → `_rodar_analise()` |
| Região                      | Fase 2: overlay para desenhar; Fase 3: região fixa salva |

Com isso você tem um plano claro: Fase 1 já entrega “atalho → captura tela inteira → front recebe e executa o código automaticamente”; Fases 2 e 3 acrescentam captura por área (selecionada ou fixa).

Se quiser, na próxima etapa podemos implementar só a **Fase 1** (atalho + tela inteira + front já aberto) em cima do seu `front_imagem.py` e do fluxo atual de análise.
