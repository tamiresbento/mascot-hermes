# Interface desktop — TDD e limites de validação

## Resultado registrado

- **34 testes desktop aprovados**, com `QT_QPA_PLATFORM=offscreen`, Qt/PySide6 real e `pytest-qt`.
- **161 testes aprovados** na execução integrada da suíte inteira.
- `ruff check` aprovado; os dois arquivos Python foram formatados com `ruff format`.
- Ambiente de validação: Python 3.11, PySide6-Essentials 6.12.0 e Pillow 12.3.0.
- Apenas `src/mascot_studio/desktop.py`, `tests/test_desktop.py` e este documento pertencem a esta entrega. Sem commit ou publicação.

Esses resultados são de execução Linux **offscreen**, não de uma sessão gráfica Windows. Não são evidência de sobreposição nativa a aplicativos, fullscreen exclusivo, UAC ou todos os desktops virtuais.

## Comandos reproduzíveis

Executar a partir da raiz do checkout, com o ambiente virtual e dependências de desenvolvimento já instalados:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m pytest tests/test_desktop.py -q
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/ruff check src/mascot_studio/desktop.py tests/test_desktop.py
.venv/bin/ruff format --check src/mascot_studio/desktop.py tests/test_desktop.py
```

Não executar os testes desktop sem `QT_QPA_PLATFORM=offscreen` em uma máquina sem servidor gráfico.

## Ciclos RED → GREEN observados

Foram feitos incrementos verticais: adicionar teste, executá-lo antes da implementação, corrigir a funcionalidade e reexecutar a suíte desktop. Resumo das falhas observadas, sem logs brutos:

| Incremento | RED observado | GREEN verificado |
| --- | --- | --- |
| Aplicação e janelas independentes | Módulo/classe desktop ausentes | Aplicação reutilizada; `parent=None`, Tool, frameless, topmost e transparência |
| Animação e interação | Cache ausente; arrasto não mudava posição | Seis QPixmaps por estado, timer real, coordenadas globais e menu não bloqueante |
| Editor e vários mascotes | Editor/mostrar todos ausentes; campos vazios; metadados longos eram truncados | Editor PT-BR, 12 projetos distintos, um pet por projeto e autoria/licença sem perda |
| Estados e parâmetros | Campos não carregavam o projeto | Edição de vários estados, salvar/reabrir, FPS e prévia sem zerar estado manual |
| Importação e exportação | Botões ainda não criavam projetos | PNG, duplicação, ZIP editável, roundtrip e pacote Hermes reais |
| Exemplo e eventos locais | Exemplo e polling ausentes | Recurso empacotado aberto sem CLI; associação explícita por `agent_id` |
| Validação de eventos | Schema booleano aceito; lista como estado levantava TypeError; estado desconhecido sem diagnóstico | Arquivo inválido ignorado, estado preservado e diagnóstico não modal |
| Persistência e sincronização | Persistência ausente; menu do pet não sincronizava o editor | JSON atômico, geometria/visibilidade/tamanho/estado, restauração e clamp |
| Bandeja e runtime | Bandeja/entrypoint ausentes; segundo runtime entrava no loop | Ações da bandeja, loop Qt real e saída explícita; lock por biblioteca |
| Inicialização direta | Construtor sem QApplication abortava o processo | Bootstrap em subprocesso novo com referência forte à aplicação |
| Recarga com erro de imagem | Cache era apagado antes de renderizar; paintEvent levantava KeyError | Recarga transacional preserva os quadros válidos anteriores |
| Robustez da UI | Timer de polling era CoarseTimer; botões/menu propagavam erro de imagem; runtime sem bandeja ficava inacessível | PreciseTimer, erros tratados e recuperação do editor sem bandeja |

Enquanto o core era construído em paralelo, os primeiros testes de janela usaram temporariamente um double mínimo do contrato. Esse double **foi removido**: a suíte final cria projetos com `Library` real, gera imagens PNG reais e lê os ZIPs/JSONs produzidos. Somente as respostas dos diálogos de arquivo/nome são substituídas no teste de importação/exportação; widgets, sinais, renderização, armazenamento e exportadores são reais.

## O que os testes comprovam

- Doze mascotes simultâneos, IDs distintos, sem limite artificial na UI e sem janela-pai do editor.
- Minimizar/fechar o editor não minimiza nem oculta seus mascotes.
- Frames renderizados uma vez por estado visitado; ticks e pintura usam QPixmaps em memória. `reload_project()` invalida o cache somente após uma recarga bem-sucedida.
- Estado escolhido no mascote sincroniza o editor; rascunhos de metadados e parâmetros de outros estados não são descartados ao trocar seleção/estado.
- Salvar/reabrir metadados, parâmetros e associação de agente; preview animado dos parâmetros salvos.
- Importação, duplicação e exportações com arquivos reais; exemplo encontrado via `importlib.resources`.
- Polling real de arquivo local com intervalo de 1.000 ms e PreciseTimer; somente mascotes em modo automático com `agent_id` correspondente são atualizados. Socket de rede bloqueado em teste.
- Arquivo de eventos corrupto, acima de 64 KiB, com schema/estados inválidos ou valores não hasháveis não bloqueia Qt nem abre modal.
- Persistência e restauração de estado, visibilidade, tamanho e coordenadas; arquivo desktop inválido é ignorado com mensagem clara. Clamp também testado com retângulos de monitores negativos/desconectados.
- QSystemTrayIcon/ícone padrão, acionamento para reabrir, saída explícita e parada dos timers. O teste do entrypoint entra de verdade em `QApplication.exec()` e sai por uma ação de bandeja; possui watchdog para não pendurar.
- Segunda execução de `run_desktop()` para a mesma biblioteca retorna **2**, sem criar outro editor. A trava é `QLockFile` e não expira somente por idade do processo.

## Uso e persistência

A API do contrato permanece: `ensure_app()`, `MascotWindow(library, project_id, *, on_changed=None)`, `StudioWindow(library)` e `run_desktop(library, show_ids=None, *, editor=True)`.

- **Salvar alterações** grava metadados e parâmetros pelo core e atualiza pet/prévia. Campos não salvos são rascunhos em memória; sair não os grava automaticamente.
- **Atualizar lista** preserva os rascunhos e não retorna um pet manual para `idle`.
- **Mostrar/Ocultar** controla cada pet. Arrasto usa coordenadas globais, inclusive negativas; o clamp ocorre ao restaurar, sem impedir travessia entre monitores.
- **Tamanho** no menu do pet escala sua janela. **Zoom da animação** altera a arte renderizada no projeto; são controles distintos.
- **Fechar editor** oculta apenas o editor. **Sair do aplicativo** salva o desktop antes de ocultar os pets, para restaurar a mesma visibilidade no próximo lançamento.
- Sem bandeja de sistema disponível, o editor é mantido/reaberto quando não sobra nenhum pet visível; não há runtime deliberadamente inacessível.

`desktop.json` na raiz da biblioteca contém `schema_version: 1`, `editor` (`x`, `y`, `width`, `height`) e `mascots`, um mapa por ID com `x`, `y`, `scale`, `visible`, `state` e `automatic`. A escrita usa arquivo temporário na mesma biblioteca e substituição atômica. A leitura aceita no máximo 1 MiB, valida tipos/valores, ignora IDs ausentes e normaliza a geometria para telas conectadas. `StudioWindow` carrega a configuração, mas só `restore_desktop()`/`run_desktop()` reabre os pets salvos; criar o editor isoladamente não abre janelas inesperadas. IDs explícitos em `run_desktop()` substituem a seleção de visibilidade salva.

Para eventos, grave `agent-states.json` **localmente** na raiz da biblioteca, preferencialmente por substituição atômica:

```json
{"schema_version": 1, "agents": {"worker-a": "review", "worker-b": "running"}}
```

O identificador deve coincidir com o `agent_id` **salvo** do projeto. Ative **Eventos locais (automático)** para cada projeto desejado. O padrão é **Manual**. Não há leitura de credenciais, HTTP, conexão ao Hermes/Codex ou detecção automática de agentes. Este arquivo é um adaptador genérico explícito.

## Riscos e verificação ainda externa

- Offscreen não fornece compositor, bandeja de sistema física, monitores reais ou HWNDs. Os testes de sinais e geometria não substituem a homologação Windows nativa do coordenador.
- A checagem nativa deve confirmar ownership/topmost/IsIconic após minimizar o editor e ativar uma janela de diagnóstico, além de arrasto entre monitores, escala de DPI e uso da bandeja.
- Não há garantia para fullscreen exclusivo, UAC, todos os desktops virtuais ou políticas de window manager/Wayland que limitem topmost/posicionamento.
- Abrir/carregar/exportar quadros ocorre no thread da UI; bibliotecas grandes ou atlas em armazenamento lento podem pausar a interface nessas operações. O timer de animação não faz esse IO.
- O cache cresce por estados efetivamente visitados e quantidade de pets; não existe teto artificial de projetos, mas memória/GPU do equipamento continuam sendo limites reais.
- A trava impede duplicar o runtime da mesma biblioteca; não implementa IPC para reabrir a primeira instância. Bibliotecas diferentes podem ter runtimes próprios.
- O pacote Hermes contém sprites reais, mas a cadência final do Hermes é própria: FPS customizado do editor não é anunciado como suportado pelo consumidor.
