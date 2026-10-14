# Dependências e licenças

Este repositório contém código próprio sob MIT e um exemplo de arte com declaração separada em src/mascot_studio/assets/ART_LICENSE.md.

- PySide6-Essentials / Qt for Python e shiboken6: licenças e avisos do projeto Qt, incluindo LGPL-3.0/GPL-3.0 ou licença comercial conforme componente. https://doc.qt.io/qtforpython-6/licenses.html
- Pillow: licença HPND e avisos específicos dos componentes. https://github.com/python-pillow/Pillow/blob/main/LICENSE
- pytest: MIT; pytest-qt: MIT; ruff: MIT; build: MIT; setuptools: MIT. São ferramentas de desenvolvimento, não código copiado para o aplicativo.

As dependências são instaladas dos próprios pacotes, preservando seus avisos. O pacote-fonte não inclui uma cópia do runtime Qt. Se criar um executável no futuro, revise e acompanhe os avisos e obrigações de redistribuição de todas as dependências; não remova licenças nem apresente o runtime Qt como MIT.

Hermes/Petdex são alvos de interoperabilidade. Este projeto não é produto oficial desses projetos nem distribui seu código. O formato de atlas foi implementado independentemente. Nenhum segredo, OAuth ou assinatura da mantenedora é compartilhado.
