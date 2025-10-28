# Trello Agentic

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-1.0.0-blue)

## 📌 Introdução

**Trello Agentic** é uma ferramenta em Python que usa um *LLM via Ollama* para **gerar cards profissionais no Trello a partir de um prompt em linguagem natural**.  
Você descreve o que quer (ex.: “gere um sistema de autenticação JWT em FastAPI”) e o agente:

- Gera **título** curto e objetivo;
- Redige **descrição técnica** estruturada (objetivos, entregáveis, critérios de aceite, riscos);
- Cria **checklists** práticos (um ou mais);
- Define **prazo** se você escrever em linguagem natural (ex.: “amanhã 18:00-03:00”);
- Cria o card **diretamente no Trello**, na lista informada (ou nos *defaults* do `.env`).

## ✨ Funcionalidades

- Entrada via **CLI** com `argparse`;
- Leitura de **DEFAULT_BOARD** e **DEFAULT_LIST** do `.env` com **override por flags** `--board` e `--list`;
- Conversão de **data/hora natural → RFC3339** (ex.: “amanhã 18:00-03:00”);
- Resolução de **idList** a partir de **board (URL/shortlink)** + **nome da lista**;
- Criação de **card**, **descrição** e **checklists** via API do Trello;
- Configurável: **modelo/temperatura** (`--model`, `--temperature`).

## ✅ Pré-requisitos

- **Python 3.10+**
- **Ollama** instalado e rodando (com o modelo desejado baixado, ex.: `gpt-oss:20b` ou `llama3.1`)
- Uma conta Trello com **API Key** e **Token** (fluxo rápido em `https://trello.com/app-key`)
- Acesso à Internet para chamar a API do Trello

## 📦 Instalação

```bash
git clone https://github.com/IMNascimento/trello_agentic.git
cd trello_agentic

python -m venv venv
# Linux/Mac
source venv/bin/activate
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

Se você não tiver um `requirements.txt`, estas são as dependências mínimas:

```bash
pip install langchain langchain-ollama langgraph python-dotenv httpx
```

> Observação: versões podem variar; se preferir, fixe versões no `requirements.txt` do seu projeto.

## 🔐 Configuração do Trello

No Trello (logado), pegue sua **Key** e gere um **Token** em: `https://trello.com/app-key`  
Crie um arquivo `.env` na raiz do projeto com:

```env
# Credenciais do Trello
TRELLO_KEY=coloque_sua_key_aqui
TRELLO_TOKEN=coloque_seu_token_aqui

# Defaults (opcional: usados se você não passar --board/--list)
DEFAULT_BOARD=https://trello.com/b/SEU_SHORTLINK/nome-do-board
DEFAULT_LIST=Backlog

# LLM (opcionais)
OLLAMA_MODEL=gpt-oss:20b
LLM_TEMPERATURE=0
```

> O `DEFAULT_BOARD` pode ser **URL completa** ou apenas o **shortlink** do board (o trecho entre `/b/` e a próxima `/`).  
> O `DEFAULT_LIST` deve ser o **nome visível** da lista dentro do board.

## ▶️ Uso (CLI)

```bash
# modo simples usando defaults do .env
python agentic.py "gere um sistema de autenticação JWT em fastapi"
```

```bash
# sobrescrevendo board/list e informando prazo natural
python agentic.py "implementar pipeline CI/CD dockerizado para FastAPI" \
  --board "https://trello.com/b/AbCd1234/minha-equipe" \
  --list "Em progresso" \
  --due "amanhã 18:00-03:00"
```

```bash
# trocando modelo e temperatura
python agentic.py "especificar arquitetura DDD para módulo de pagamentos" \
  --model "llama3.1" \
  --temperature 0.2
```

### Parâmetros da CLI

- `prompt` (posicional): pedido em linguagem natural (ex.: “crie um card para…”).
- `--board`: URL ou shortlink do board do Trello. Se omitido, usa `DEFAULT_BOARD` do `.env`.
- `--list`: nome da lista do board. Se omitido, usa `DEFAULT_LIST` do `.env`.
- `--due`: prazo em linguagem natural (ex.: “amanhã 18:00-03:00”). Opcional.
- `--model`: modelo Ollama (padrão: `gpt-oss:20b` ou valor em `OLLAMA_MODEL`).
- `--temperature`: temperatura do LLM (padrão: `0` ou valor em `LLM_TEMPERATURE`).
- `--verbose`: (opcional) exibe logs detalhados do agente.

## 🧠 Como funciona

1. O agente lê o **prompt** e gera: **título**, **descrição técnica** e **checklists** (1–3 listas, 4–10 itens cada).
2. Detecta e converte **prazo natural** (se houver) para **RFC3339**.
3. Resolve **idList** consultando o Trello com **board** (URL/shortlink) + **nome da lista**.
4. Cria o **card** (com descrição) e, na sequência, cria os **checklists** no Trello.
5. Imprime a **URL do card** criado.

## 🪪 Segurança

- **NUNCA** commite seu `.env` com `TRELLO_KEY` e `TRELLO_TOKEN`.
- Restrinja *scopes* do token ao necessário (`read`, `write`) e **revogue** se vazar.
- Tokens são equivalentes a senha de API — trate como segredo.

## 🛠️ Troubleshooting

- **`401 unauthorized` / `invalid key`**: verifique `TRELLO_KEY`/`TRELLO_TOKEN` e se está logado certo ao criar o token.
- **`Lista 'X' não encontrada`**: confirme o *nome visível* da lista; tente sem acentos/variações; garanta que o board está correto.
- **`Ollama não encontrado`**: instale e rode `ollama serve`; baixe o modelo (`ollama run gpt-oss:20b` etc.).
- **`dotenv` não carrega**: garanta que o `.env` está na **mesma pasta** de execução ou passe o caminho explicitamente no código.

## 🧩 Estrutura (sugerida)

```
.
├── agentic.py
├── README.md
├── requirements.txt
└── .env.example
```

## 🤝 Contribuindo

Contribuições são bem-vindas!  
Abra uma *issue* ou envie um *pull request* com melhorias (ex.: suporte a múltiplos checklists nomeados, `--dry-run`, `--print-json`, logs estruturados etc.).

## 📄 Licença

Distribuído sob a licença **GPL**. Veja `LICENSE` para mais informações.

## 👨‍💻 Autor

Igor (Nascimento) — Senior Engineer/AI Enginner  
GitHub: https://github.com/IMNascimento

## 🙏 Agradecimentos

- Comunidade **LangChain**, **LangGraph** e **Ollama**
- **Trello API** e documentação Atlassian
- Bibliotecas: `python-dotenv`, `httpx`

---

> Dica: Se quiser um `--dry-run` para visualizar descrição e checklists antes de criar, ou `--print-json` para logar a payload do Trello, abra uma issue — dá para incluir fácil.
