# Segurança

O MVP trabalha com arquivos locais. Não abre portas de rede e não executa conteúdo de projetos importados.

Nunca anexe arquivos com tokens, senhas ou dados pessoais em Issues. Para vulnerabilidades, use um canal privado combinado com os mantenedores. Antes da publicação pública, os mantenedores devem habilitar o reporte privado de vulnerabilidades do GitHub.

Importações rejeitam travessia de diretório, links simbólicos e pacotes/imagens acima dos limites documentados. A validação não substitui manter Python, Pillow e Qt atualizados. Imagens são decodificadas por bibliotecas de terceiros.

O identificador de agente apenas associa estados. Ele não concede acesso a contas, processos ou conversas do agente. Integrações devem escrever somente estados explícitos, nunca prompts privados ou credenciais.
