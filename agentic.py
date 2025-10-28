from __future__ import annotations

import os
import re
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dotenv import load_dotenv

from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent  # sua versão suporta este import

# ========= Env =========
load_dotenv()
TRELLO_KEY = os.getenv("TRELLO_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
if not TRELLO_KEY or not TRELLO_TOKEN:
    raise RuntimeError("Defina TRELLO_KEY e TRELLO_TOKEN no .env ou ambiente.")

# ========= Defaults (usados se o prompt não trouxer board/lista) =========
DEFAULT_BOARD = "https://trello.com/b/S33WAXxl/nocapital"  # pode ser só o shortlink também
DEFAULT_LIST = "A fazer"  # ajuste para o nome exato da lista no seu board

# ========= Helpers =========
def _to_rfc3339_from_text(text: str) -> str:
    """
    Converte 'amanhã 18:00-03:00' ou 'YYYY-MM-DD HH:MM-03:00' para RFC3339.
    - timezone: se não vier, usa -03:00
    - hora: se não vier, usa 09:00
    - 'amanhã' = hoje + 1
    - YYYY-MM-DD reconhecido
    """
    s = text.strip().lower()
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
        dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + tz

def _board_shortlink(board_ref: str) -> str:
    """Aceita URL (https://trello.com/b/<short>/<nome>) ou shortlink. Retorna o shortlink."""
    m = re.search(r"/b/([A-Za-z0-9]+)/", board_ref)
    return m.group(1) if m else board_ref

def _get_list_id(board_ref: str, list_name: str) -> str:
    """Busca o id da lista pelo nome dentro do board (shortlink/URL). Case-insensitive."""
    short = _board_shortlink(board_ref)
    r = httpx.get(
        f"https://api.trello.com/1/boards/{short}/lists",
        params={"fields": "name,id", "key": TRELLO_KEY, "token": TRELLO_TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    lists = r.json()
    for lst in lists:
        if lst["name"].strip().lower() == list_name.strip().lower():
            return lst["id"]
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
    'board' pode ser URL do board ou shortlink.
    """
    # Se vier vazio, usa defaults
    if not board:
        board = DEFAULT_BOARD
    if not list_name:
        list_name = DEFAULT_LIST
    return _get_list_id(board, list_name)

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

# ========= LLM + Agente =========
llm = ChatOllama(model="gpt-oss:20b", temperature=0)
agent = create_react_agent(
    llm,
    tools=[to_rfc3339, resolve_list_id, trello_create_card, trello_set_desc, trello_add_checklist],
)

if __name__ == "__main__":
    # Exemplo de uso super simples: só passe o que você quer que a IA gere.
    # Se não mencionar board/lista, serão usados os defaults acima.
    user_prompt = (
        "gere um sistema de autenticação JWT em fastapi "
        "(use o board/lista padrão caso eu não informe) "
        "com prazo amanhã 18:00-03:00"
    )

    system_msg = (
        "Você é um agente de produtividade. NÃO peça key/token; já estão no ambiente. "
        f"Se o usuário não informar board/lista, use board {DEFAULT_BOARD} e lista '{DEFAULT_LIST}'. "
        "Fluxo: "
        "1) Gere um TÍTULO curto do card. "
        "2) Redija uma DESCRIÇÃO TÉCNICA estruturada (bullets), com entregáveis, critérios de aceite e notas de segurança. "
        "3) Monte 1–3 CHECKLISTS com 4–10 itens cada, práticos e verificáveis. "
        "4) Se houver data/hora natural, converta com 'to_rfc3339' e use como 'due'; se não houver, crie sem due. "
        "5) Resolva o 'idList' com 'resolve_list_id' (board URL/shortlink + nome da lista, ou defaults). "
        "6) Crie o card chamando 'trello_create_card' já com a descrição. "
        "7) Crie os checklists com 'trello_add_checklist'. "
        "Retorne no final SOMENTE a URL do card."
    )

    msgs = [
        ("system", system_msg),
        ("user", user_prompt),
    ]

    result = agent.invoke({"messages": msgs})
    print(result["messages"][-1].content)
