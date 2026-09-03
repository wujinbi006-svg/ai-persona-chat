import asyncio
import json
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


async def one_request(client: AsyncOpenAI, request_id: str):
    t0 = time.perf_counter()
    first = None
    count = 0
    try:
        stream = await client.chat.completions.create(
            model=os.environ["OPENAI_MODEL"],
            messages=[{"role": "user", "content": "请用一句简短的话回答：性能测试。"}],
            stream=True,
            temperature=0,
        )
        connection_ms = (time.perf_counter() - t0) * 1000
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                count += 1
                if first is None:
                    first = time.perf_counter()
        end = time.perf_counter()
        return {
            "request_id": request_id,
            "success": True,
            "connection_ms": round(connection_ms, 2),
            "llm_ttft_ms": round(((first or end) - t0) * 1000, 2),
            "full_response_ms": round((end - t0) * 1000, 2),
            "chunks": count,
        }
    except Exception as exc:
        return {"request_id": request_id, "success": False, "error": str(exc)[:200]}


def summary(rows):
    out = {}
    for key in ("connection_ms", "llm_ttft_ms", "full_response_ms"):
        vals = sorted(r[key] for r in rows if r.get("success") and key in r)
        if not vals:
            out[key] = {}
            continue
        def pct(p):
            k = (len(vals) - 1) * p / 100
            f, c = int(k), min(int(k) + 1, len(vals) - 1)
            return round(vals[f] + (vals[c] - vals[f]) * (k - f), 2)
        out[key] = {
            "min": vals[0], "p50": pct(50), "p90": pct(90),
            "p95": pct(95), "max": vals[-1],
            "mean": round(statistics.mean(vals), 2),
        }
    return out


async def main():
    kwargs = {
        "api_key": os.environ["OPENAI_API_KEY"],
        "base_url": os.environ.get("OPENAI_BASE_URL"),
        "timeout": float(os.environ.get("LLM_TIMEOUT", "120")),
    }
    results = {"new_client": [], "shared_client": []}
    for i in range(10):
        client = AsyncOpenAI(**kwargs)
        results["new_client"].append(await one_request(client, f"new_{i+1:02d}"))
        await client.close()
    shared = AsyncOpenAI(**kwargs)
    for i in range(10):
        results["shared_client"].append(await one_request(shared, f"shared_{i+1:02d}"))
    await shared.close()
    output = {
        "new_client": {"runs": results["new_client"], "summary": summary(results["new_client"])},
        "shared_client": {"runs": results["shared_client"], "summary": summary(results["shared_client"])},
    }
    path = ROOT / "backend" / "perf_client_ab_20260903.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
