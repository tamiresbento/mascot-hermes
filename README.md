# Mascot Hermes

Editor desktop local em Python para criar, editar e exibir mascotes independentes para agentes.

O projeto permite importar uma arte própria, configurar estados e movimentos, associar cada mascote a um identificador de agente e mantê-lo visível sobre outros aplicativos, inclusive quando o editor é minimizado.

> **Status:** MVP 0.1. O projeto é código-fonte Python/PySide6. Esta versão ainda não é um `.exe` standalone; no Windows, o arquivo `iniciar-windows.cmd` funciona como lançador e prepara o ambiente automaticamente.

## O que ele faz

- Cria uma biblioteca local com vários mascotes, sem limite artificial de quantidade.
- Importa PNG, WebP e atlas compatível com o formato Hermes/Petdex.
- Permite editar nome, agente, autoria, licença e parâmetros por estado.
- Exibe vários mascotes simultaneamente em janelas nativas transparentes, arrastáveis e sempre no topo.
- Mantém os mascotes independentes do editor: minimizar ou fechar o editor não os minimiza.
- Suporta bandeja do sistema para reabrir o editor ou sair explicitamente.
- Salva posições, tamanho, visibilidade e estado para restaurar a sessão.
- Permite controle manual ou atualização por eventos locais de agentes.
- Exporta um projeto editável e um pacote Hermes.
- Funciona offline depois da instalação das dependências; não exige conta, backend ou chave de IA.

A quantidade prática depende da memória, CPU, GPU, tamanho das artes e do sistema operacional. O código não impõe um limite de dez mascotes, por exemplo: a biblioteca pode conter dez ou mais projetos e o runtime pode exibir vários deles.

## O aplicativo é um `.exe`?

Ainda não. O MVP é um aplicativo Python executado por PySide6:

- **Windows:** `iniciar-windows.cmd` cria o ambiente virtual, instala as dependências quando necessário e abre o editor usando `pythonw.exe`.
- **Linux:** o editor é iniciado pelo ambiente virtual com `python -m mascot_studio`.
- **Distribuição futura:** um `.exe` standalone pode ser gerado posteriormente com PyInstaller ou ferramenta equivalente. Essa etapa ainda não faz parte deste commit.

## Como abrir no Windows

### Opção recomendada: lançador

1. Baixe ou clone este repositório.
2. Abra a pasta do projeto.
3. Execute duas vezes:

```text
iniciar-windows.cmd
```

O lançador:

1. verifica se existe Python;
2. cria `.venv` se necessário;
3. instala o projeto e suas dependências;
4. abre o Mascot Studio sem abrir uma janela de terminal.

Requisito: Python 3.11 ou superior disponível no `PATH`.

### Opção pelo terminal

No PowerShell ou no Prompt de Comando, a partir da raiz do projeto:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m mascot_studio gui
```

Para instalar também as ferramentas de desenvolvimento:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

A biblioteca padrão do Windows fica em:

```text
%LOCALAPPDATA%\DevPyTech\MascotStudio\library
```

É possível escolher outra biblioteca com `--library` ou com a variável `MASCOT_STUDIO_HOME`.

## Como ativar um mascote

### Pelo editor

1. Abra `iniciar-windows.cmd`.
2. Clique em **Abrir exemplo** ou em **Novo / importar imagem…**.
3. Selecione o projeto na lista.
4. Clique em **Mostrar mascote**.
5. Escolha o estado, o tamanho e os parâmetros desejados.
6. Clique em **Salvar alterações**.

Para mostrar todos os projetos da biblioteca, use **Mostrar todos os mascotes**.

Cada mascote é uma janela independente. Você pode arrastá-lo para outro ponto da tela ou para outro monitor. Fechar/minimizar a janela do editor não desativa os mascotes que já estão visíveis.

### Pela linha de comando

O argumento `--library` vem antes do comando:

```powershell
$ms = "$env:LOCALAPPDATA\DevPyTech\MascotStudio\library"
$py = ".\.venv\Scripts\python.exe"

& $py -m mascot_studio --library $ms gui --show all
```

Para iniciar somente os mascotes e manter o editor fechado:

```powershell
& $py -m mascot_studio --library $ms gui --show all --no-editor
```

A opção `--no-editor` continua dependendo da bandeja do sistema ou de um mascote visível para recuperação. Se a bandeja não estiver disponível e nenhum mascote estiver visível, o editor será reaberto para que o aplicativo não fique inacessível.

## Como desativar ou ocultar

Há três ações diferentes:

### Ocultar somente o editor

Clique no botão de fechar ou minimize o editor. Os mascotes permanecem na tela. Esse é o comportamento intencional para trabalhar em outro aplicativo.

### Ocultar um mascote

No editor, selecione o projeto e clique em **Ocultar mascote**. Também é possível clicar com o botão direito no mascote e escolher **Ocultar mascote**.

### Encerrar tudo

Use uma das opções:

- botão **Sair do aplicativo** no editor;
- menu da bandeja do sistema → **Sair do aplicativo**;
- menu de contexto de um mascote → **Mostrar editor** e depois **Sair do aplicativo**.

Sair grava a geometria e a visibilidade para a próxima sessão. Para que um mascote não volte automaticamente, oculte-o antes de sair.

Para desativar somente o controle automático de um projeto, selecione **Controle do estado → Manual** e salve. O mascote continuará podendo ser mostrado manualmente.

## Como adicionar outros agentes

Cada projeto pode receber um identificador de agente, como `backend`, `qa`, `gohan` ou `agente-documentacao`. O identificador é apenas uma associação local: nesta versão não concede acesso a contas, processos, conversas ou credenciais.

### Pelo editor

1. Clique em **Novo / importar imagem…**.
2. Selecione PNG, WebP ou atlas.
3. Informe o nome do mascote.
4. Preencha **Identificador do agente**.
5. Preencha autoria e licença da imagem.
6. Escolha **Manual** ou **Eventos locais (automático)**.
7. Salve e clique em **Mostrar mascote**.

Repita o processo para cada agente. Para criar uma variação sem alterar o original, selecione um projeto e clique em **Duplicar…**.

### Pela linha de comando

Exemplo com dois agentes:

```powershell
$ms = "$env:LOCALAPPDATA\DevPyTech\MascotStudio\library"
$py = ".\.venv\Scripts\python.exe"

& $py -m mascot_studio --library $ms create "Mascote do backend" `
  --image "C:\Projetos\artes\backend.png" `
  --agent "backend"

& $py -m mascot_studio --library $ms create "Mascote de QA" `
  --image "C:\Projetos\artes\qa.png" `
  --agent "qa"

& $py -m mascot_studio --library $ms list --json
& $py -m mascot_studio --library $ms gui --show all
```

O diretório pode conter quantos projetos forem necessários. A capacidade simultânea depende dos recursos do computador.

## Estados e eventos locais

Os estados disponíveis são:

```text
idle             parado
running-right    correndo à direita
running-left     correndo à esquerda
waving           acenando
jumping          pulando
failed           falha
waiting          aguardando
running          trabalhando
review           revisando
```

O editor pode operar em modo manual. Para usar eventos locais:

1. associe um `agent_id` ao projeto;
2. selecione **Eventos locais (automático)**;
3. grave estados na raiz da biblioteca, no arquivo `agent-states.json`.

Exemplo:

```json
{
  "schema_version": 1,
  "agents": {
    "backend": "running",
    "qa": "review"
  }
}
```

A atualização pode ser feita pela CLI:

```powershell
& $py -m mascot_studio --library $ms status backend running
& $py -m mascot_studio --library $ms status qa review
```

O arquivo é local, limitado a 64 KiB e lido no máximo uma vez por segundo. Não há conexão automática com Hermes, Codex, serviços externos ou contas de agentes; um adaptador explícito deve escrever o estado.

Atalhos aceitos pelo comando `status`:

```text
run   → running
wave  → waving
jump  → jumping
```

## Animação e edição

Para cada estado, o editor permite ajustar:

- quadros por segundo;
- salto vertical;
- balanço horizontal;
- rotação;
- zoom da animação.

Um PNG achatado permite movimento global da imagem. Ele não separa automaticamente braços, cabelo, roupa ou outras partes do personagem. Para editar membros de forma independente, importe uma arte em camadas, vetorial ou um atlas preparado para isso.

O FPS salvo no Mascot Studio controla o editor e a prévia. O pacote Hermes exportado usa a cadência do consumidor Hermes; não há promessa de que o FPS personalizado seja aplicado pelo runtime externo.

## Importação e exportação

Formatos aceitos:

- PNG;
- WebP estático;
- atlas Hermes/Petdex compatível.

Exportações:

```powershell
& $py -m mascot_studio --library $ms export ID projeto.zip --format project
& $py -m mascot_studio --library $ms export ID pacote-hermes.zip --format hermes
```

O projeto editável preserva `project.json` e `source.png`. O pacote Hermes contém `pet.json` e `spritesheet.png` em atlas RGBA 1536×1872, com células de 192×208.

Importação de projeto:

```powershell
& $py -m mascot_studio --library $ms import projeto.zip
```

Os arquivos importados são validados contra travessia de diretório, links simbólicos, ZIP bombs, tipos especiais, imagens inválidas e limites de tamanho. Nenhum arquivo importado é executado.

## Biblioteca e comandos úteis

```powershell
# Criar o exemplo original
& $py -m mascot_studio --library $ms sample --name Orbi --agent assistente

# Listar projetos
& $py -m mascot_studio --library $ms list --json

# Validar todos os estados e quadros
& $py -m mascot_studio --library $ms validate ID

# Duplicar um projeto
& $py -m mascot_studio --library $ms duplicate ID --name "Outra variação"

# Registrar estado local de um agente
& $py -m mascot_studio --library $ms status assistente review
```

No Prompt de Comando, use a mesma estrutura com `%LOCALAPPDATA%`:

```bat
set MS_HOME=%LOCALAPPDATA%\DevPyTech\MascotStudio\library
.venv\Scripts\python.exe -m mascot_studio --library "%MS_HOME%" gui --show all
```

## Desenvolvimento

Requisitos:

- Python 3.11+;
- Pillow;
- PySide6-Essentials;
- pytest e pytest-qt para testes;
- ruff para lint e formatação.

Instalação:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Testes em Linux sem display:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

Smoke test Windows real:

```powershell
.venv\Scripts\python.exe scripts\windows_smoke.py --output evidencias-windows.json
```

O smoke test cria temporariamente dez mascotes e uma janela de diagnóstico própria. Ele verifica visibilidade, transparência, `WS_EX_TOPMOST`, independência do editor, animação e segundo monitor quando disponível. Não manipula janelas de outros aplicativos.

## Segurança e privacidade

- O MVP é local e offline.
- Não há servidor obrigatório, porta de rede, login ou credencial.
- Não coloque senhas, tokens, dados pessoais ou artes sem licença em Issues e Pull Requests.
- O identificador do agente não é uma credencial.
- Arte importada continua sob os direitos do respectivo titular.
- Consulte `SECURITY.md`, `THIRD_PARTY.md` e `CONTRIBUTING.md` antes de contribuir.

## Licença

O código é disponibilizado sob MIT. Dependências e arte de exemplo possuem suas próprias condições, documentadas em `THIRD_PARTY.md` e `src/mascot_studio/assets/ART_LICENSE.md`.

A licença do código não concede direitos sobre personagens, marcas ou imagens importadas por usuários.
