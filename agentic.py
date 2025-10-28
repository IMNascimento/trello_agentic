from __future__ import annotations

import os
import re
import sys
import httpx
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dotenv import load_dotenv

from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent  # compatível com sua versão

# ========= Carrega .env =========
load_dotenv()  # lê .env do diretório atual

TRELLO_KEY = os.getenv("TRELLO_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

# Defaults opcionais (podem vir do .env)
ENV_DEFAULT_BOARD = os.getenv("DEFAULT_BOARD", "").strip()
ENV_DEFAULT_LIST = os.getenv("DEFAULT_LIST", "").strip()

# ========= Helpers =========
def _to_rfc3339_from_text(text: str) -> str:
    """
    Converte 'amanhã 18:00-03:00' ou 'YYYY-MM-DD HH:MM-03:00' para RFC3339.
    Regras:
      - timezone: se não vier no texto, usa -03:00
      - hora: se não vier, usa 09:00
      - 'amanhã' = hoje + 1
      - 'YYYY-MM-DD' reconhecido
    """
    s = (text or "").strip().lower()
    if not s:
        raise ValueError("Texto de data/hora vazio.")

    m_tz = re.search(r"([+-]\d{2}:\d{2})", s)
    tz = m_tz.group(1) if m_tz else "-03:00"

    m_hm = re.search(r"(\d{1,2}):(\d{2})", s)
    hh, mm = (int(m_hm.group(1)), int(m_hm.group(2))) if m_hm else (9, 0)

    now = datetime.now()
    if "amanhã" in s:
        dt = (now + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    elif re.search(r"\d{4}-\d{2}-\d{2}", s):
        y, m, d = map(int, re.search(r"(\d{4})-(\d{2})-(\d{2})", s).groups())
        dt = datetime(y, m, d, hh, mm, 0)
    else:
        # "hoje" ou texto sem data vira hoje
        dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    return dt.strftime("%Y-%m-%dT%H:%M:%S") + tz

def _board_shortlink(board_ref: str) -> str:
    """Aceita URL (https://trello.com/b/<short>/<nome>) ou shortlink. Retorna o shortlink."""
    m = re.search(r"/b/([A-Za-z0-9]+)/", board_ref)
    return m.group(1) if m else board_ref

def _get_list_id(board_ref: str, list_name: str) -> str:
    """Busca o id da lista pelo nome dentro do board (shortlink/URL). Case-insensitive, tenta exact e contains."""
    short = _board_shortlink(board_ref)
    r = httpx.get(
        f"https://api.trello.com/1/boards/{short}/lists",
        params={"fields": "name,id", "key": TRELLO_KEY, "token": TRELLO_TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    lists = r.json()
    # exact
    for lst in lists:
        if lst["name"].strip().lower() == list_name.strip().lower():
            return lst["id"]
    # contains
    for lst in lists:
        if list_name.strip().lower() in lst["name"].strip().lower():
            return lst["id"]
    raise ValueError(f"Lista '{list_name}' não encontrada no board {board_ref}")

# ========= Tools =========
@tool
def to_rfc3339(datetime_text: str) -> str:
    """Converte uma expressão de data/hora (ex: 'amanhã 18:00-03:00') para RFC3339."""
    return _to_rfc3339_from_text(datetime_text)

@tool
def resolve_list_id(board: str, list_name: str) -> str:
    """
    Retorna o idList a partir de (board, list_name).
    'board' pode ser URL do board ou shortlink. Se algum vier vazio, usa defaults do host.
    """
    _board = board.strip() or ENV_DEFAULT_BOARD
    _list = list_name.strip() or ENV_DEFAULT_LIST
    if not _board or not _list:
        raise ValueError(
            "Board e lista não informados. Passe via CLI (--board/--list) ou defina DEFAULT_BOARD/DEFAULT_LIST no .env."
        )
    return _get_list_id(_board, _list)

@tool
def trello_create_card(list_id: str, name: str, desc: str = "", due: str | None = None) -> Dict[str, Any]:
    """
    Cria um card no Trello. Args: list_id, name, desc, due (RFC3339).
    Retorna {'id': <card_id>, 'url': <card_url>}.
    """
    params = {"key": TRELLO_KEY, "token": TRELLO_TOKEN, "idList": list_id, "name": name, "desc": desc}
    if due:
        params["due"] = due
    r = httpx.post("https://api.trello.com/1/cards", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return {"id": data.get("id"), "url": data.get("url")}

@tool
def trello_set_desc(card_id: str, desc: str) -> str:
    """Atualiza a descrição de um card existente."""
    r = httpx.put(
        f"https://api.trello.com/1/cards/{card_id}",
        params={"key": TRELLO_KEY, "token": TRELLO_TOKEN, "desc": desc},
        timeout=30,
    )
    r.raise_for_status()
    return "Descrição atualizada"

@tool
def trello_add_checklist(card_id: str, checklist_name: str, items: List[str]) -> str:
    """
    Cria um checklist no card e adiciona itens.
    - checklist_name: nome do checklist (ex.: 'Tarefas')
    - items: lista de itens (strings)
    """
    rc = httpx.post(
        "https://api.trello.com/1/checklists",
        params={"key": TRELLO_KEY, "token": TRELLO_TOKEN, "idCard": card_id, "name": checklist_name},
        timeout=30,
    )
    rc.raise_for_status()
    checklist_id = rc.json().get("id")

    for it in items:
        it = (it or "").strip()
        if not it:
            continue
        ri = httpx.post(
            f"https://api.trello.com/1/checklists/{checklist_id}/checkItems",
            params={"key": TRELLO_KEY, "token": TRELLO_TOKEN, "name": it},
            timeout=30,
        )
        ri.raise_for_status()

    return f"Checklist '{checklist_name}' criado com {len(items)} itens"

# ========= CLI =========
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Agente Trello: gera cards profissionais (título, descrição e checklists) a partir de um prompt."
    )
    p.add_argument("prompt", help="Pedido em linguagem natural (ex.: 'gere um sistema de autenticação JWT em FastAPI').")
    p.add_argument("--board", help="URL ou shortlink do board. Se ausente, usa DEFAULT_BOARD do .env.", default=None)
    p.add_argument("--list", dest="list_name", help="Nome da lista. Se ausente, usa DEFAULT_LIST do .env.", default=None)
    p.add_argument("--due", help="Prazo em linguagem natural (ex.: 'amanhã 18:00-03:00').", default=None)
    p.add_argument("--model", help="Modelo Ollama (default: gpt-oss:20b).", default=os.getenv("OLLAMA_MODEL", "gpt-oss:20b"))
    p.add_argument("--temperature", type=float, help="Temperatura do LLM (default: 0).", default=float(os.getenv("LLM_TEMPERATURE", "0")))
    p.add_argument("--verbose", action="store_true", help="Exibe logs do agente (útil para debug).")
    return p.parse_args()

# ========= Runner =========
def main():
    if not TRELLO_KEY or not TRELLO_TOKEN:
        print("ERRO: Defina TRELLO_KEY e TRELLO_TOKEN no .env ou ambiente.")
        sys.exit(1)

    args = parse_args()

    # prepara LLM
    llm = ChatOllama(model=args.model, temperature=args.temperature)

    # agenda ferramentas
    tools = [to_rfc3339, resolve_list_id, trello_create_card, trello_set_desc, trello_add_checklist]
    agent = create_react_agent(llm, tools=tools)

    # system message profissional
    system_msg = (
        "Você é um agente de produtividade. NÃO peça key/token; já estão no ambiente. "
        f"Se o usuário não informar board/lista nas mensagens, use board '{args.board or ENV_DEFAULT_BOARD}' "
        f"e lista '{args.list_name or ENV_DEFAULT_LIST}'. "
        "Fluxo: "
        "1) Gere um TÍTULO curto e claro do card. "
        "2) Redija uma DESCRIÇÃO TÉCNICA estruturada (bullets), com objetivos, entregáveis, critérios de aceite, riscos/notas de segurança. "
        "3) Monte 1–3 CHECKLISTS com 4–10 itens cada, práticos e verificáveis (por área, ex. Planejamento/Backend/QA). "
        "4) Se houver data/hora natural no texto do usuário ou passada separadamente, converta com 'to_rfc3339' e use como 'due'; se não houver, crie sem due. "
        "5) Resolva 'idList' com 'resolve_list_id' usando board/lista fornecidos (mensagem/CLI) ou defaults. "
        "6) Crie o card com 'trello_create_card' (inclua a descrição). "
        "7) Crie os checklists com 'trello_add_checklist'. "
        "Responda por fim SOMENTE a URL do card."
    )

    # monta prompt do usuário
    user_prompt = args.prompt.strip()
    if args.due:
        # sugerimos explicitamente um due extra, mas o agente também consegue detectar do user_prompt
        user_prompt += f" | prazo: {args.due.strip()}"

    # injeta, se o usuário quiser forçar board/list via CLI
    if args.board:
        user_prompt += f" | board: {args.board.strip()}"
    if args.list_name:
        user_prompt += f" | lista: {args.list_name.strip()}"

    messages = [
        ("system", system_msg),
        ("user", user_prompt),
    ]

    # executa
    result = agent.invoke({"messages": messages})
    print(result["messages"][-1].content)

if __name__ == "__main__":
    main()
