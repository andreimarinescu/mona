# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx", "pydantic-ai-slim[openai,openrouter]==2.52.0"]
# ///
"""T5: the extended evidence schema through pydantic-ai NativeOutput against OpenRouter."""
import argparse
import asyncio
import json
import os
import time
from typing import Literal

import httpx
import pydantic_ai
from _docs import page_texts, sample_docs, v2_definitions
from _evidence import FIELD_GUIDE, FIELDS, QUOTE_RULES, page_block, verify
from _or import API, MODEL, NO_THINK, PRIVATE, PROVIDER_PIN, RESULTS, api_key, guard, record, write_json
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
SENT: list[dict] = []


async def _capture(request: httpx.Request) -> None:
    body = json.loads(request.content or b"{}")
    rf = body.get("response_format") or {}
    SENT.append({k: v for k, v in body.items() if k not in ("messages", "response_format")}
                | {"response_format": {"type": rf.get("type"),
                                       "strict": (rf.get("json_schema") or {}).get("strict")}})


Date = str
DATE = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
QUOTE = Field(max_length=160)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextEv(Strict):
    value: str = Field(max_length=160)
    quote: str = QUOTE
    page: int = Field(ge=1)


class DateEv(Strict):
    value: Date = DATE
    quote: str = QUOTE
    page: int = Field(ge=1)


class AmountEv(Strict):
    value: float
    currency: str = Field(pattern="^[A-Z]{3}$")
    quote: str = QUOTE
    page: int = Field(ge=1)


def extraction_model(categories: list[str]) -> type[BaseModel]:
    Category = Literal[tuple(categories)]  # type: ignore[valid-type]

    class CategoryEv(Strict):
        value: Category
        quote: str = QUOTE
        page: int = Field(ge=1)

    class Extraction(Strict):
        entity_hint: TextEv | None
        category: CategoryEv
        counterparty: TextEv | None
        doc_type: TextEv | None
        doc_date: DateEv | None
        period_start: DateEv | None
        period_end: DateEv | None
        amount: AmountEv | None
        due_date: DateEv | None
        addressee: TextEv | None
        confidence: float = Field(ge=0, le=1)

    return Extraction


def openrouter_model(style: str):
    client = httpx.AsyncClient(timeout=180, event_hooks={"request": [_capture]})
    provider = OpenRouterProvider(api_key=api_key(), http_client=client)
    profile = {**provider.model_profile(MODEL), "supports_json_schema_output": True}
    if style == "openai_compat":
        oa = OpenAIProvider(base_url=API, api_key=api_key(), http_client=client)
        return OpenAIChatModel(MODEL, provider=oa, profile=profile)
    return OpenRouterModel(MODEL, provider=provider, profile=profile)


SETTINGS = {
    # Native OpenRouter settings: reasoning + provider pins as first-class keys.
    "openrouter_settings": {"temperature": 0, "max_tokens": 2000,
                            "openrouter_reasoning": NO_THINK, "openrouter_provider": PROVIDER_PIN,
                            "openrouter_usage": {"include": True}},
    # Unified pydantic-ai knob; OpenRouterModel maps thinking=False to reasoning.effort="none".
    "unified_thinking_false": {"temperature": 0, "max_tokens": 2000, "thinking": False,
                               "openrouter_provider": PROVIDER_PIN, "openrouter_usage": {"include": True}},
    # Plain OpenAI-compatible model: everything OpenRouter-specific rides in extra_body.
    # Against llama-server the same slot carries {"chat_template_kwargs": {"enable_thinking": False}}.
    "openai_compat": {"temperature": 0, "max_tokens": 2000,
                      "extra_body": {"reasoning": NO_THINK, "provider": PROVIDER_PIN,
                                     "usage": {"include": True}}},
}


async def run(style: str, docs: list[dict], v2: dict, Extraction) -> list[dict]:
    model = openrouter_model(style)
    agent = Agent(model, output_type=NativeOutput(Extraction, name="extraction", strict=True),
                  instructions=v2["SYSTEM"] + "\n" + FIELD_GUIDE + QUOTE_RULES["p1"])
    rows = []
    for d in docs:
        guard()
        pages = [p[:4000] for p in page_texts(d["path"], 3)]
        prompt = (f"Filename: {d['path'].name}\n\nDocument text, {len(pages)} page(s):\n"
                  + page_block(pages, "xml"))
        t0 = time.monotonic()
        row = {"style": style, "sha12": d["sha12"], "label": d["label"]}
        try:
            result = await agent.run(prompt, model_settings=SETTINGS[style])
        except Exception as e:  # noqa: BLE001
            rows.append({**row, "valid": False, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        wall = time.monotonic() - t0
        out = result.output
        usage = result.usage
        details = result.response.provider_details or {}
        cost = (details.get("cost") or (usage.details or {}).get("cost")
                or usage.input_tokens * 0.15e-6 + usage.output_tokens * 1.0e-6)
        record("t5", cost, provider=result.response.provider_name)
        write_json(PRIVATE / "t5" / style / f"{d['sha12']}.json",
                   {"output": out.model_dump(), "provider_details": details,
                    "messages": result.all_messages_json().decode()})
        rows.append({**row, "valid": isinstance(out, Extraction), "error": None, "request": SENT[-1],
                     "served_by": details.get("downstream_provider") or result.response.provider_name,
                     "wall_s": round(wall, 2), "input_tokens": usage.input_tokens,
                     "output_tokens": usage.output_tokens,
                     "reasoning_tokens": (usage.details or {}).get("reasoning_tokens", 0),
                     "cost": cost, "category_ok": out.category.value == d["gt"],
                     "fields": {f: verify(o.model_dump() if (o := getattr(out, f)) else None, pages)
                                for f in FIELDS}})
    return rows


async def amain(args):
    v2, docs = v2_definitions(), sample_docs()
    Extraction = extraction_model(v2["CATEGORIES"])
    rows = []
    for style in args.styles.split(","):
        rows += await run(style, docs if style == args.full else docs[: args.short], v2, Extraction)
    write_json(RESULTS / "t5_pydantic_ai.json",
               {"pydantic_ai_version": pydantic_ai.__version__, "rows": rows})
    print(f"pydantic-ai {pydantic_ai.__version__}")
    print("| style | n | valid | category ok | quotes verified | reasoning tok | median wall s | served by |")
    print("|---|---|---|---|---|---|---|---|")
    for style in args.styles.split(","):
        rs = [r for r in rows if r["style"] == style]
        ok = [r for r in rs if r["valid"]]
        stats = [s for r in ok for s in r["fields"].values() if s != "null"]
        walls = sorted(r["wall_s"] for r in ok)
        print(f"| {style} | {len(rs)} | {len(ok)} | {sum(r['category_ok'] for r in ok)} | "
              f"{stats.count('ok')}/{len(stats)} | {sum(r['reasoning_tokens'] or 0 for r in ok)} | "
              f"{walls[len(walls) // 2] if walls else '-'} | {sorted({r['served_by'] for r in ok})} |")
    for r in rows:
        if r["error"]:
            print("  error:", r["style"], r["sha12"], r["error"])
    for style in args.styles.split(","):
        sent = next((r["request"] for r in rows if r["style"] == style and r.get("request")), None)
        print(f"  request body sent by {style}: {json.dumps(sent)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--styles", default="openrouter_settings,unified_thinking_false,openai_compat")
    ap.add_argument("--full", default="openrouter_settings")
    ap.add_argument("--short", type=int, default=3)
    asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    main()
