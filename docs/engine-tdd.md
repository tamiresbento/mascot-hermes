# Motor — evidências de TDD e segurança

O contrato foi lido integralmente antes do primeiro teste. Foram alterados somente
`src/mascot_studio/core.py`, `tests/test_core.py` e este registro.
Nenhum commit ou publicação foi feito por este implementador.

## Ambiente e verificação final

Execução real em Linux, dentro do venv do projeto: Python 3.11.16,
Pillow 12.3.0, pytest 9.1.1, pytest-qt 4.5.0, PySide6-Essentials 6.12.0 e ruff 0.17.0.

- Motor após refatoração: **121 passed**, com warnings tratados como erros.
- Suite conjunta verificada enquanto desktop/CLI/eventos eram desenvolvidos em paralelo:
  um snapshot retornou **134 passed**. O último snapshot executado por este implementador
  retornou **140 passed, 3 failed**, headless, com warnings tratados como erros. As três
  falhas pertencem ao teste novo do desktop
  `test_invalid_local_events_are_nonmodal_and_keep_last_state`, nos casos
  `boolean-schema`, `unhashable-state` e `unknown-state`; cobrem eventos locais inválidos,
  não o motor. Desktop e integração não foram alterados por este implementador.
  O coordenador deve reexecutar a suite após concluir essas fatias concorrentes.
  Isso não constitui teste nativo Windows.
- Ruff nos dois arquivos Python de responsabilidade do motor: **All checks passed!**
  e **2 files already formatted**.

Comandos relativos, executados a partir da raiz do checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -p no:cacheprovider tests/test_core.py -q -W error

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -p no:cacheprovider tests -q -W error

.venv/bin/python -m ruff check --no-cache src/mascot_studio/core.py tests/test_core.py
.venv/bin/python -m ruff format --no-cache --check src/mascot_studio/core.py tests/test_core.py
```

## Ciclos RED → GREEN reais

Cada fatia recebeu testes antes da implementação. O RED inicial foi uma asserção
explícita de motor ausente, não um erro de coleta; os seguintes expuseram APIs ausentes,
aceitação indevida ou exceção fora do contrato. O GREEN executou a suite completa do motor.
A fatia 13 executou somente o novo caso no RED; seu GREEN executou todos os casos.
Alguns casos adicionais já passaram por comportamento de fatias anteriores, sem mudança
artificial de testes para provocar falha. Os resultados abaixo são resumos das execuções,
sem logs brutos ou dados do ambiente privado.

| Ciclo | Comportamento | RED observado | GREEN do motor |
|---|---|---|---|
| 01 | Estados e parâmetros finitos | 18 failed | 18 passed |
| 02 | Modelo, schema e roundtrip de metadados | 20 failed, 18 passed | 38 passed |
| 03 | Criação, imagens e limites | 9 failed, 38 passed | 47 passed |
| 04 | Salvar, duplicar e excluir | 11 failed, 47 passed | 58 passed |
| 05 | Quadros e atlas real/legado | 3 failed, 59 passed | 62 passed |
| 06 | Roundtrip do ZIP editável | 2 failed, 62 passed | 64 passed |
| 07 | ZIP malicioso e orçamento de recursos | 23 failed, 69 passed | 92 passed |
| 08 | Pacote Hermes | 2 failed, 92 passed | 94 passed |
| 09 | Escopo das mutações e IO atômico | 3 failed, 96 passed | 99 passed |
| 10 | ZIP corrompido e JSON ambíguo | 3 failed, 107 passed | 110 passed |
| 11 | Privacidade dos metadados da imagem | 1 failed, 115 passed | 116 passed |
| 12 | Chroma key e fronteiras exatas | 1 failed, 119 passed | 120 passed |
| 13 | Exportação editável dentro do limite | 1 failed | 121 passed |

## Cobertura funcional e adversarial

- Cria e reabre **12 projetos** com IDs únicos; sem teto de quantidade. Duplicação
  mantém parâmetros e pixels, troca o ID e preserva o original; exclusão não remove
  diretórios desconhecidos nem segue links.
- Parâmetros finitos e dentro dos intervalos; schema, nomes, agentes, IDs portáveis,
  estados completos e independência dos defaults. Salvar valida objetos mutáveis,
  escreve JSON com temporário + `fsync` + `os.replace` e não mantém metadados stale.
- PNG/WebP estáticos são verificados e normalizados como PNG RGBA. Imagens inválidas,
  truncadas, formatos não previstos e WebP animado são negados. Entrada de exatamente
  20 MiB e imagem de exatamente 16 MP passam; excedentes não passam.
- Chroma key preserva preto, contornos escuros e alpha pré-existente. A tolerância é
  estreita: diferença máxima de 16 por canal em relação a magenta puro. Pode ser
  desativada e não é aplicada a atlas. Metadados embutidos EXIF/ICC/texto são removidos
  na normalização, mantendo os pixels decodificados.
- Renderiza RGBA 192×208, nove estados, seis quadros, índice módulo seis e parâmetros
  atualizados. Atlas atual 8 colunas × 9 linhas e legado 9 colunas × 8 linhas são
  recortados de verdade, com teste de cor por linha/coluna.
- ZIP editável faz roundtrip de parâmetros, autoria, licença, agente e pixels. Importar
  sempre gera novo ID. Toda validação ocorre antes de criar o diretório do projeto.
- ZIP tem limite de entrada de 20 MiB, soma descompactada de 64 MiB e 16 entradas.
  Há teste real da fronteira agregada de 64 MiB e de um byte acima, com arquivos
  altamente compressíveis, sem reduzir constantes para simular orçamento.
- Nomes são uma allowlist exata: apenas `project.json` e `source.png` na raiz. Nega
  paths POSIX/Windows/UNC, drives relativos, travessia, separadores ambíguos, maiúsculas
  alternativas, duplicatas, NUL, dispositivos Windows e entradas extras/executáveis.
  Também nega symlinks, diretórios e tipos especiais, inclusive em `source.png`;
  corrupção de compressão/CRC e chaves JSON duplicadas geram `ValueError`.
- ZIP não é extraído no filesystem. JSON usa orçamento adicional de 256 KiB;
  ZIP criptografado e compressões diferentes de stored/deflate não são aceitos.
- Exportação não pode apontar para dentro da biblioteca nem seguir link no destino.
  Falha física de IO foi exercitada com destino sendo diretório: não restam temporários
  e o conteúdo anterior é preservado. Pacote editável acima de 20 MiB é recusado antes
  de sobrescrever destino, pois seria impossível reimportá-lo sob o limite acordado.
- Hermes exporta somente `<id>/pet.json` e `<id>/spritesheet.png`, RGBA 1536×1872,
  8 colunas × 9 linhas. Há comparação pixel a pixel de todas as células contra os
  frames do motor; colunas 6/7 repetem 0/1, mantendo seis quadros efetivos.

## Limites e riscos explícitos

- O legado não possui linha própria de `running`: utiliza `running-right`; `review`
  utiliza a última linha legada. Não são inventados pixels de estados inexistentes.
- FPS é armazenado para o player/editor. O pacote Hermes não anuncia FPS customizado;
  a cadência do consumidor é própria e não foi testada em uma instalação Hermes.
- A biblioteca pressupõe filesystem local pertencente ao usuário. As validações de
  links não são sandbox contra um processo hostil alterando diretórios simultaneamente
  (TOCTOU); concorrência de múltiplos escritores e queda de energia não foram validadas.
- Decodificação é em memória, dentro dos limites. Pillow/WebP devem continuar atualizados;
  limites não eliminam todas as vulnerabilidades possíveis de codecs nativos.
- Paths Windows foram testados lexicalmente e atributos ZIP Windows foram exercitados
  no Linux. ACLs, junctions, permissões para symlink e IO nativo Windows exigem validação
  nessa plataforma; testes de symlink requerem permissão de criação de links.
- Zoom/rotação grandes podem recortar conteúdo fora da célula fixa. A animação de imagem
  simples é procedural, não cria novos desenhos anatômicos para poses.
- Um WebP permitido pode expandir para PNG cuja exportação editável excede 20 MiB;
  nesse caso o motor informa erro e preserva a biblioteca/destino, exigindo imagem menor.
- Este registro documenta testes do motor e uma execução conjunta observada. Não afirma
  publicação, revisão independente, integração automática de agentes ou disponibilidade
  em produção.
