# Guia rápido — Mascot Studio

## Criar e editar
Abra o aplicativo, importe sua imagem PNG/WebP ou um projeto ZIP, dê um nome e associe opcionalmente o identificador de um agente. Edite cada estado e salve. Use Duplicar para criar outro projeto independente. Não existe uma cobrança ou limite artificial de quantidade nesta versão; disco e recursos do computador são os limites práticos.

## Deixar na área de trabalho
Exiba o mascote no desktop e minimize o editor. O personagem deve continuar numa janela transparente independente, sobre os aplicativos normais. Arraste para mudar de lugar ou monitor. Use o menu do mascote para mudar o estado manualmente. O ícone na bandeja reabre o editor ou encerra o aplicativo.

Fechar explicitamente o aplicativo encerra todos os mascotes. Minimizar ou fechar apenas o editor não deve encerrar os companheiros. Não há execução enquanto o computador está desligado, nem promessa de aparecer sobre UAC ou em todos os desktops virtuais.

## Criar para dez agentes
Crie dez projetos, cada um com seu nome, arte e identificador de agente. Eles podem aparecer ao mesmo tempo. Ter dez projetos salvos não obriga a exibir os dez simultaneamente.

## Compartilhar
Exportar projeto: leva arte e configuração para outra pessoa reabrir e editar no Studio.
Exportar Hermes: cria o ZIP de instalação de mascote. O projeto editável e o pacote de instalação têm finalidades diferentes.

## Automático e manual
Estados podem ser escolhidos manualmente. O modo por eventos usa `agent-states.json` local. O comando `mascot-studio status ID_DO_AGENTE review` é um exemplo de evento. A integração com o agente deve chamar o comando; não há monitoramento secreto de outros aplicativos.
