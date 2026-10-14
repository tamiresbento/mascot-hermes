# Como contribuir

Obrigado por ajudar a tornar a criação de mascotes acessível.

1. Faça um fork após a publicação do repositório e crie uma branch curta.
2. Instale Python 3.11+ e `python -m pip install -e ".[dev]"` em um ambiente virtual.
3. Escreva um teste que falhe antes da implementação. Rode os testes e o linter.
4. Envie um Pull Request com objetivo, capturas sem dados privados e evidências dos testes.
5. Aguarde revisão antes do merge. Contribuições não dão permissão para publicar releases.

## Testes
`QT_QPA_PLATFORM=offscreen python -m pytest` testa a lógica e as janelas sem display no Linux. No Windows, execute também `python scripts/windows_smoke.py --output evidencias.json`; o teste cria temporariamente dez mascotes e uma janela de diagnóstico própria, minimiza o editor e verifica o estado real das janelas Win32. Não altere janelas de outros aplicativos para passar nos testes.

## Artes e exemplos
Envie autoria, origem e licença explícita. Não compartilhe personagens de terceiros sem os direitos necessários. Não envie credenciais, bibliotecas pessoais nem diretórios inteiros do Hermes. Artes de IA devem ser identificadas, com ferramenta/modelo e ausência de garantia de exclusividade.

## Compatibilidade
Mantenha importação de projetos antigos e atlas Hermes. Mudanças de schema exigem plano de migração, testes e atualização de documentação. A exportação não pode alterar contas ou instalações do usuário automaticamente.

## Conduta
Seja respeitoso, inclusivo e objetivo. Não publique dados pessoais, material sem permissão, assédio ou instruções maliciosas em exemplos. Reporte problemas de segurança em canal privado dos mantenedores, nunca com segredos em Issues públicas.
