"""LLM 입력 압축 방식 비교 실험.

  py -m services.recommendation.bench.compare_compression            # LLM 없이: 크기·정보 보존율
  py -m services.recommendation.bench.compare_compression --llm local  # + 정확도 (로컬 LLM, 비용 없음)
  py -m services.recommendation.bench.compare_compression --llm claude # + 정확도 (ANTHROPIC_API_KEY, 비용 발생)

방식
- json      : 압축 전. 후보 필드를 JSON 으로 그대로 (원래 랭커 방식)
- toon      : TOON 포맷 (pip install toon-format). 같은 필드를 표 형태로
- llmlingua2: JSON 을 LLMLingua-2 로 토큰 삭제 압축 (pip install llmlingua, 모델 다운로드 필요)
- compact   : 우리 방식 (compress.py). 짧은 번호, 한 줄 표, 주요성분, 열 정의는 시스템 프롬프트에

모든 방식에 같은 후보(알레르기 통과)를 같은 순서로 넣습니다. 결과는 bench/results/ 에 JSON 으로 저장하고
EXPERIMENT_LOG.md 에 한 줄 요약을 덧붙입니다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from datetime import datetime
from pathlib import Path

from ..allergens import assess, split_ingredients
from ..compress import _FILLER, _clean_ing
from ..contracts import CollectedProduct, UserProfile
from ..embedders import HashEmbedder, document_text
from ..rankers import render_candidates

HERE = Path(__file__).resolve().parent
# 이름 -> (형식, compact 옵션). 같은 후보 집합에서 형식/압축 강도만 바꿔 비교
VARIANTS = {
    "json": ("json", {}),
    "toon": ("toon", {}),
    "llmlingua2": ("llmlingua2", {}),
    "compact": ("compact", {}),                                   # 12개, 주요성분 3, 분류 포함
    "compact8": ("compact", {"max_items": 8}),                    # 후보 수 줄이기
    "compact8_lean": ("compact", {"max_items": 8, "ing_limit": 2, "show_category": False}),
}
METHODS = list(VARIANTS)


def load(dataset="bench"):
    """bench: 기본 24개/8질의, hard: 헷갈리는 44개/13질의 (5차부터)."""
    products = [CollectedProduct.from_dict(json.loads(l)) for l in
                (HERE / f"foods.{dataset}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    queries = json.loads((HERE / f"queries.{dataset}.json").read_text(encoding="utf-8"))
    return products, queries


def candidates(products, q, emb):
    """실제 흐름과 같게: 알레르기 통과 + 유사도 순."""
    prof = UserProfile.from_dict(q["user"])
    qv = emb.embed_query(f"{q['query']} {prof.preferences}")
    out = []
    for p in products:
        if assess(p, prof).safe:
            dv = emb.embed_documents([document_text(p)])[0]
            out.append((p, sum(a * b for a, b in zip(qv, dv))))
    out.sort(key=lambda x: -x[1])
    return prof, out


_lingua = None


def render(method, prof, q, items, top_k=3):
    fmt, opts = VARIANTS[method]
    if fmt == "llmlingua2":
        global _lingua
        from llmlingua import PromptCompressor  # 없으면 ImportError -> 건너뜀

        if _lingua is None:
            _lingua = PromptCompressor(model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
                                       use_llmlingua2=True, device_map="cpu")
        system, user, id_map = render_candidates("json", prof, q, items, top_k)
        head, body = user.split("후보:\n", 1)
        body = _lingua.compress_prompt(body, rate=0.5, force_tokens=["\n", "id", "c"],
                                       force_reserve_digit=True)["compressed_prompt"]
        return system.replace("json 형식", "압축된 json 형식"), head + "후보:\n" + body, id_map
    return render_candidates(fmt, prof, q, items, top_k, **opts)


def retention(text, items, id_map, keywords):
    """LLM 없이 잴 수 있는 정보 보존율 (0~1). 고르기에 필요한 사실이 텍스트에 남아 있는지."""
    by = {p.product_id: p for p, _ in items}
    checks = []
    for cid, pid in id_map.items():
        p = by[pid]
        core = re.sub(r"[\d.]+\s*(g|ml|L|입|봉|팩)|x|\d+", "", p.name).split()
        checks.append(("id", re.search(rf"\b{cid}\b", text) is not None))
        checks.append(("name", all(w in text for w in core[:2])))
        if p.price:
            digits = str(int(float(p.price)))
            checks.append(("price", digits in text.replace(",", "")))
        raw = split_ingredients(p.ingredients_raw) if p.ingredients_raw else []
        top = [t for t in (_clean_ing(x) for x in raw) if t and t.lower() not in _FILLER][:3]
        for t in top:
            checks.append(("ingredient", t in text))
        for t in (_clean_ing(x) for x in raw):
            if t and any(k in t for k in keywords):
                checks.append(("query_ingredient", t in text))
    by_kind = {}
    for k, ok in checks:
        by_kind.setdefault(k, []).append(ok)
    return {k: round(sum(v) / len(v), 3) for k, v in by_kind.items()}, round(sum(ok for _, ok in checks) / len(checks), 3)


def count_tokens(client, model, system, user):
    r = client.messages.count_tokens(model=model, system=system, messages=[{"role": "user", "content": user}])
    return r.input_tokens


def run(args):
    products, queries = load(args.dataset)
    emb = HashEmbedder()
    client, ranker, model = None, None, None
    if args.tokens or args.llm == "claude":
        import anthropic

        client = anthropic.Anthropic()
        model = os.getenv("RECO_LLM_MODEL", "claude-opus-5-5")
    if args.llm == "claude":
        from ..rankers import ClaudeRanker

        ranker = ClaudeRanker(model=model, client=client)
    elif args.llm == "local":
        from ..rankers import LocalLLMRanker

        ranker = LocalLLMRanker()
        model = f"local:{ranker.model}"
    rows, skipped = [], {}
    import sys

    if "llmlingua2" in args.methods:  # 압축 모델 로딩은 압축 시간에서 뺌 (서버에서는 한 번만 로딩)
        try:
            p0, i0 = candidates(products, queries[0], emb)
            render("llmlingua2", p0, queries[0]["query"], i0)
        except Exception:
            pass

    for qi, q in enumerate(queries, 1):
        print(f"[{qi}/{len(queries)}] {q['qid']} {q['query']}", file=sys.stderr, flush=True)
        prof, items = candidates(products, q, emb)
        keywords = {w for w in re.findall(r"[가-힣\w]{2,}", f"{q['query']} {prof.preferences}")}
        for m in args.methods:
            t_c = time.perf_counter()
            try:
                system, user, id_map = render(m, prof, q["query"], items)
            except ImportError as e:
                skipped[m] = f"설치 안 됨: {e.name}"
                continue
            except Exception as e:  # 모델 다운로드 실패 등
                skipped[m] = f"{type(e).__name__}: {str(e)[:120]}"
                continue
            times = [time.perf_counter() - t_c]
            for _ in range(args.repeat - 1):  # 같은 입력으로 반복해서 중앙값 (첫 실행 흔들림 제거)
                t1 = time.perf_counter()
                render(m, prof, q["query"], items)
                times.append(time.perf_counter() - t1)
            compress_ms = round(statistics.median(times) * 1000, 2)  # 압축(입력 만들기)에 걸린 시간
            per_kind, ret = retention(user, items, id_map, keywords)
            row = {"qid": q["qid"], "method": m, "chars": len(system) + len(user),
                   "bytes": len((system + user).encode()), "user_bytes": len(user.encode()),
                   "retention": ret, "retention_by_kind": per_kind, "n_candidates": len(id_map),
                   "compress_ms": compress_ms}
            if client:
                row["input_tokens_counted"] = count_tokens(client, model, system, user)
            if ranker:
                if args.pace:
                    time.sleep(args.pace)
                gold = set(q["gold"])
                t0 = time.time()
                try:
                    picks = [pid for pid, _ in ranker.rank_rendered(system, user, id_map)]
                except Exception as e:
                    picks, row["error"] = [], f"{type(e).__name__}: {str(e)[:200]}"
                valid = [p for p in picks if not p.startswith("unknown:")]
                hit = len(set(valid[:3]) & gold)
                usage = ranker.last_usage or (None, None)
                llm_s = time.time() - t0
                row.update({"latency_s": round(llm_s, 2), "total_s": round(llm_s + compress_ms / 1000, 2),
                            "picks": picks,
                            "precision@3": round(hit / len(valid[:3]), 3) if valid else 0.0,
                            "recall@3": round(hit / min(3, len(gold)), 3),
                            "gold_in_candidates": round(len(gold & set(id_map.values())) / len(gold), 3),
                            "invalid_ids": len(picks) - len(valid),
                            "input_tokens": usage[0], "output_tokens": usage[1]})
            rows.append(row)
    return rows, skipped, model


def summarize(rows):
    out = {}
    for m in METHODS:
        allr = [x for x in rows if x["method"] == m]
        if not allr:
            continue
        r = [x for x in allr if not x.get("error")]  # 서버 오류 난 질의는 정확도 평균에서 뺌
        if not r:
            out[m] = {"queries": 0, "errors": len(allr)}
            continue
        s = {"queries": len(r), "errors": len(allr) - len(r), "avg_bytes": round(statistics.mean(x["bytes"] for x in r)),
             "avg_user_bytes": round(statistics.mean(x["user_bytes"] for x in r)),
             "avg_retention": round(statistics.mean(x["retention"] for x in r), 3)}
        for k in ("compress_ms", "total_s", "input_tokens_counted", "input_tokens", "output_tokens", "precision@3",
                  "recall@3", "latency_s",
                  "invalid_ids", "gold_in_candidates"):
            v = [x[k] for x in r if x.get(k) is not None]
            if v:
                s["avg_" + k] = round(statistics.mean(v), 3)
        out[m] = s
    if "json" in out:
        base = out["json"]
        for m, s in out.items():
            s["bytes_vs_json"] = round(s["avg_bytes"] / base["avg_bytes"], 3)
            for k in ("avg_input_tokens_counted", "avg_input_tokens"):
                if k in s and k in base:
                    s["tokens_vs_json"] = round(s[k] / base[k], 3)
    return out


def save_per_method(out: dict) -> None:
    """방식(모델)별로 따로 저장: results/by_method/<방식>/<시각>.json + results/INDEX.md 에 한 줄씩 누적."""
    root = HERE / "results"
    for m, summ in out["summary"].items():
        d = root / "by_method" / m
        d.mkdir(parents=True, exist_ok=True)
        rows = [r for r in out["rows"] if r["method"] == m]
        (d / f"{out['time']}.json").write_text(json.dumps(
            {"time": out["time"], "model": out["model"], "note": out["note"], "summary": summ, "rows": rows},
            ensure_ascii=False, indent=1), encoding="utf-8")
    idx = root / "INDEX.md"
    if not idx.exists():
        idx.write_text("| 시각 | LLM | 방식 | 유효 질의 | 오류 | 입력 토큰 | JSON 대비 | P@3 | R@3 | 압축 ms | 전체 초 | 메모 |\n"
                       "|---|---|---|---|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    with idx.open("a", encoding="utf-8") as f:
        for m, s in out["summary"].items():
            f.write(f"| {out['time']} | {out['model'] or '-'} | {m} | {s.get('queries', 0)} | {s.get('errors', 0)} | "
                    f"{s.get('avg_input_tokens', s.get('avg_input_tokens_counted', '-'))} | "
                    f"{s.get('tokens_vs_json', s.get('bytes_vs_json', '-'))} | {s.get('avg_precision@3', '-')} | "
                    f"{s.get('avg_recall@3', '-')} | {s.get('avg_compress_ms', '-')} | {s.get('avg_total_s', '-')} | "
                    f"{out['note']} |\n")
        for m, why in out.get("skipped", {}).items():
            f.write(f"| {out['time']} | {out['model'] or '-'} | {m} | 0 | - | - | - | - | - | - | - | 건너뜀: {why} |\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", choices=["local", "claude"], help="정확도 측정에 쓸 LLM (local: LOCAL_LLM_BASE_URL)")
    ap.add_argument("--tokens", action="store_true", help="count_tokens API 로 정확한 입력 토큰만 측정")
    ap.add_argument("--methods", nargs="+", default=METHODS, choices=METHODS)
    ap.add_argument("--note", default="", help="실험 로그에 남길 메모")
    ap.add_argument("--repeat", type=int, default=3, help="압축 시간 측정 반복 횟수 (중앙값)")
    ap.add_argument("--dataset", default="bench", choices=["bench", "hard"], help="실험 데이터셋")
    ap.add_argument("--pace", type=float, default=0.0, help="LLM 호출 사이 대기(초). 학교 서버는 2.5 권장")
    a = ap.parse_args(argv)
    rows, skipped, model = run(a)
    summary = summarize(rows)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (HERE / "results").mkdir(exist_ok=True)
    out = {"time": stamp, "model": model if (a.llm or a.tokens) else None, "llm": a.llm, "tokens": a.tokens,
           "dataset": a.dataset, "skipped": skipped, "summary": summary, "rows": rows, "note": a.note}
    path = HERE / "results" / f"compression-{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    save_per_method(out)
    print(json.dumps({"summary": summary, "skipped": skipped}, ensure_ascii=False, indent=1))
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
