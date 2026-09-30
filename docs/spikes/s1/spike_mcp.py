# /// script
# requires-python = ">=3.12"
# dependencies = ["fastmcp>=2.12", "uvicorn"]
# ///
"""Spike MCP server for S1/S2: synthetic tools shaped like the C4 catalog, bearer-key protected."""
import json
import os
import sys
import time

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

KEY = os.environ["MONA_SERVICE_KEY"]
LOG = os.environ.get("SPIKE_LOG", "/tmp/hermes-s1/mcp-calls.jsonl")

DOCS = {
    "d_urssaf_q3": {"title": "URSSAF appel de cotisation T3", "entity": "Cabinet Marchand", "amount": 1284.00, "due": "2026-10-14"},
    "d_agipi_per": {"title": "AGIPI PER avis d'échéance", "entity": "Personnel", "amount": 520.00, "due": None},
    "d_agipi_av": {"title": "AGIPI Assurance Vie relevé annuel", "entity": "Personnel", "amount": 1200.00, "due": None},
    "d_edf_sept": {"title": "EDF facture septembre", "entity": "Cabinet Marchand", "amount": 214.37, "due": "2026-10-05"},
}

mcp = FastMCP("mona-spike")


def _log(tool, args):
    with open(LOG, "a") as f:
        f.write(json.dumps({"t": time.time(), "tool": tool, "args": args}) + "\n")


@mcp.tool
def search_documents(query: str, entity: str | None = None, year: int | None = None) -> dict:
    """Search the practice archive. Returns matching document ids with titles; use get_document for details."""
    _log("search_documents", {"query": query, "entity": entity, "year": year})
    q = query.lower()
    hits = [{"id": k, "title": v["title"]} for k, v in DOCS.items()
            if any(w in v["title"].lower() for w in q.split()) and (not entity or entity.lower() in v["entity"].lower())]
    return {"document_ids": [h["id"] for h in hits], "results": hits, "count": len(hits)}


@mcp.tool
def get_document(document_id: str) -> dict:
    """Fetch one document's fields (title, entity, amount in EUR, due date)."""
    _log("get_document", {"document_id": document_id})
    if document_id not in DOCS:
        return {"error": "not_found", "document_id": document_id}
    return {"id": document_id, **DOCS[document_id]}


@mcp.tool
def sum_amounts(document_ids: list[str]) -> dict:
    """Sum the EUR amounts of the given documents. Returns the total and the ids used."""
    _log("sum_amounts", {"document_ids": document_ids})
    used = [d for d in document_ids if d in DOCS]
    return {"total": round(sum(DOCS[d]["amount"] for d in used), 2), "currency": "EUR", "document_ids": used}


@mcp.tool
def list_deadlines(within_days: int = 30) -> dict:
    """List upcoming payment deadlines."""
    _log("list_deadlines", {"within_days": within_days})
    items = [{"id": k, "title": v["title"], "due": v["due"], "amount": v["amount"]} for k, v in DOCS.items() if v["due"]]
    return {"deadline_document_ids": [i["id"] for i in items], "items": items}


class KeyAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("authorization") != f"Bearer {KEY}":
            _log("_auth_rejected", {"path": request.url.path})
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


if __name__ == "__main__":
    import uvicorn
    app = mcp.http_app(path="/mcp", middleware=[Middleware(KeyAuth)])
    uvicorn.run(app, host="0.0.0.0", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8799)
