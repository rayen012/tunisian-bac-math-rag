#!/usr/bin/env python3
"""
run_evaluation.py
-----------------
Run all evaluation questions through all three systems (RAG, Prompt-Only, Hybrid).

Outputs:
  evaluation/results/eval_results_YYYYMMDD_HHMMSS.json
    → Full structured results for every question × every system.

Usage:
  python evaluation/run_evaluation.py                    # run all 20 questions
  python evaluation/run_evaluation.py --category A       # run only category A
  python evaluation/run_evaluation.py --ids A01 B03 E01  # run specific questions
  python evaluation/run_evaluation.py --dry-run           # show questions without calling APIs
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.eval_questions import EVAL_QUESTIONS
import config


def init_engines():
    """Initialize all three engines. Returns (rag, prompt_only, hybrid)."""
    from rag_engine import TunisianMathRAG
    from prompt_only_engine import TunisianMathPromptOnly
    from hybrid_engine import TunisianMathHybrid

    print("Initializing engines...")

    t0 = time.monotonic()
    rag = TunisianMathRAG()
    print(f"  RAG engine ready in {time.monotonic() - t0:.1f}s | {rag.chunk_count:,} chunks")

    t0 = time.monotonic()
    po = TunisianMathPromptOnly()
    print(f"  Prompt-only engine ready in {time.monotonic() - t0:.1f}s")

    t0 = time.monotonic()
    hybrid = TunisianMathHybrid()
    print(f"  Hybrid engine ready in {time.monotonic() - t0:.1f}s | {hybrid.chunk_count:,} chunks")

    return rag, po, hybrid


def run_rag(engine, question: str, mode: str) -> dict:
    """Run a query through the RAG engine and extract structured data."""
    result = engine.query(question, mode=mode)
    best_dist = None
    if result.selected_docs:
        # Skip companion docs (distance = -1 or 0 for companions)
        real_docs = [d for d in result.selected_docs if d.distance > 0]
        if real_docs:
            best_dist = round(min(d.distance for d in real_docs), 4)

    return {
        "system": "RAG",
        "answer": result.answer or "",
        "error": result.error,
        "retrieval_case": result.retrieval_case,
        "confidence": result.confidence,
        "n_selected_docs": len(result.selected_docs),
        "n_first_pass_docs": len(result.first_pass_docs),
        "n_second_pass_docs": len(result.second_pass_docs),
        "best_distance": best_dist,
        "retrieval_time_s": round(result.retrieval_time, 3),
        "generation_time_s": round(result.generation_time, 3),
        "total_time_s": round(result.total_time, 3),
        "answer_length": len(result.answer or ""),
        "retrieved_sources": [
            {
                "rank": d.rank,
                "distance": round(d.distance, 4),
                "type": d.metadata.get("type", ""),
                "chapter": d.metadata.get("chapter", ""),
                "year": d.metadata.get("year", ""),
                "is_solution": d.metadata.get("is_solution", ""),
                "filename": d.metadata.get("filename", ""),
            }
            for d in (result.selected_docs or [])[:8]
        ],
    }


def run_prompt_only(engine, question: str, mode: str) -> dict:
    """Run a query through the Prompt-Only engine and extract structured data."""
    result = engine.query(question, mode=mode)
    return {
        "system": "PROMPT_ONLY",
        "answer": result.answer or "",
        "error": result.error,
        "retrieval_case": "PROMPT_ONLY",
        "confidence": result.confidence,
        "n_selected_docs": 0,
        "n_first_pass_docs": 0,
        "n_second_pass_docs": 0,
        "best_distance": None,
        "retrieval_time_s": 0.0,
        "generation_time_s": round(result.generation_time, 3),
        "total_time_s": round(result.total_time, 3),
        "answer_length": len(result.answer or ""),
        "system_prompt_tokens_approx": result.system_prompt_tokens_approx,
        "retrieved_sources": [],
    }


def run_hybrid(engine, question: str, mode: str) -> dict:
    """Run a query through the Hybrid engine and extract structured data."""
    result = engine.query(question, mode=mode)
    return {
        "system": "HYBRID",
        "answer": result.answer or "",
        "error": result.error,
        "retrieval_case": result.retrieval_case,
        "knowledge_source": result.knowledge_source,
        "confidence": result.confidence,
        "n_selected_docs": len(result.selected_docs),
        "n_first_pass_docs": len(result.first_pass_docs),
        "n_second_pass_docs": len(result.second_pass_docs),
        "best_distance": round(result.best_distance, 4) if result.best_distance else None,
        "retrieval_time_s": round(result.retrieval_time, 3),
        "generation_time_s": round(result.generation_time, 3),
        "total_time_s": round(result.total_time, 3),
        "answer_length": len(result.answer or ""),
        "system_prompt_tokens_approx": result.system_prompt_tokens_approx,
        "retrieved_sources": [
            {
                "rank": d.rank,
                "distance": round(d.distance, 4),
                "type": d.metadata.get("type", ""),
                "chapter": d.metadata.get("chapter", ""),
                "year": d.metadata.get("year", ""),
                "is_solution": d.metadata.get("is_solution", ""),
                "filename": d.metadata.get("filename", ""),
            }
            for d in (result.selected_docs or [])[:8]
        ],
    }


def run_evaluation(questions: list, dry_run: bool = False):
    """Run the full evaluation pipeline."""
    # ── Setup ──
    results_dir = PROJECT_ROOT / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = results_dir / f"eval_results_{timestamp}.json"

    print(f"\n{'=' * 70}")
    print(f"  EVALUATION RUN — {len(questions)} questions × 3 systems")
    print(f"  Timestamp: {timestamp}")
    print(f"  Output: {output_path}")
    print(f"{'=' * 70}\n")

    if dry_run:
        for q in questions:
            print(f"  [{q['id']}] ({q['category']}) {q['chapter']} [{q['mode']}]")
            print(f"    {q['question'][:80]}...")
        print(f"\n  (dry-run: no API calls made)")
        return

    # ── Initialize engines ──
    rag_engine, po_engine, hybrid_engine = init_engines()

    # ── Run queries ──
    INTER_QUERY_DELAY = 5  # seconds between questions (rate limit protection)
    INTER_SYSTEM_DELAY = 2  # seconds between systems

    all_results = []

    for i, q in enumerate(questions, 1):
        print(f"\n{'─' * 70}")
        print(f"  [{i}/{len(questions)}] {q['id']} | {q['chapter']} | {q['mode']}")
        print(f"  Q: {q['question'][:100]}{'...' if len(q['question']) > 100 else ''}")
        print(f"{'─' * 70}")

        entry = {
            "question_id": q["id"],
            "category": q["category"],
            "chapter": q["chapter"],
            "mode": q["mode"],
            "question": q["question"],
            "notes": q["notes"],
            "systems": {},
        }

        # ── RAG ──
        print(f"  [1/3] RAG...", end="", flush=True)
        try:
            entry["systems"]["RAG"] = run_rag(rag_engine, q["question"], q["mode"])
            r = entry["systems"]["RAG"]
            print(f" case={r['retrieval_case']} conf={r['confidence']} "
                  f"docs={r['n_selected_docs']} dist={r['best_distance']} "
                  f"t={r['total_time_s']}s len={r['answer_length']}")
        except Exception as e:
            print(f" ERROR: {e}")
            entry["systems"]["RAG"] = {"system": "RAG", "error": str(e), "answer": ""}

        time.sleep(INTER_SYSTEM_DELAY)

        # ── Prompt-Only ──
        print(f"  [2/3] Prompt-Only...", end="", flush=True)
        try:
            entry["systems"]["PROMPT_ONLY"] = run_prompt_only(po_engine, q["question"], q["mode"])
            r = entry["systems"]["PROMPT_ONLY"]
            print(f" conf={r['confidence']} "
                  f"t={r['total_time_s']}s len={r['answer_length']}")
        except Exception as e:
            print(f" ERROR: {e}")
            entry["systems"]["PROMPT_ONLY"] = {"system": "PROMPT_ONLY", "error": str(e), "answer": ""}

        time.sleep(INTER_SYSTEM_DELAY)

        # ── Hybrid ──
        print(f"  [3/3] Hybrid...", end="", flush=True)
        try:
            entry["systems"]["HYBRID"] = run_hybrid(hybrid_engine, q["question"], q["mode"])
            r = entry["systems"]["HYBRID"]
            print(f" case={r['retrieval_case']} src={r.get('knowledge_source','')} "
                  f"conf={r['confidence']} dist={r['best_distance']} "
                  f"t={r['total_time_s']}s len={r['answer_length']}")
        except Exception as e:
            print(f" ERROR: {e}")
            entry["systems"]["HYBRID"] = {"system": "HYBRID", "error": str(e), "answer": ""}

        all_results.append(entry)

        if i < len(questions):
            print(f"  [delay] {INTER_QUERY_DELAY}s before next query...")
            time.sleep(INTER_QUERY_DELAY)

    # ── Build output ──
    output = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gemini_model": config.CHAT_MODEL_ID,
            "embedding_model": config.EMBEDDING_MODEL_NAME,
            "temperature": 0.15,
            "max_tokens": 4096,
            "rag_chunks": rag_engine.chunk_count,
            "thresholds": {
                "good": config.SIMILARITY_GOOD_THRESHOLD,
                "fallback": config.SIMILARITY_FALLBACK_THRESHOLD,
            },
            "n_questions": len(questions),
            "categories": list(set(q["category"] for q in questions)),
        },
        "results": all_results,
    }

    # ── Save ──
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n{'=' * 70}")
    print(f"  Results saved to: {output_path}")
    print(f"  {len(all_results)} questions × 3 systems = {len(all_results) * 3} total evaluations")
    print(f"{'=' * 70}")

    # ── Also save a "latest" symlink for convenience ──
    latest_path = results_dir / "eval_results_latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  Also saved as: {latest_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Run thesis evaluation")
    parser.add_argument("--category", type=str, default=None,
                        help="Run only questions from this category (A/B/C/D/E)")
    parser.add_argument("--ids", nargs="+", default=None,
                        help="Run only specific question IDs (e.g., A01 B03 E01)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show questions without calling APIs")
    args = parser.parse_args()

    # Filter questions
    questions = EVAL_QUESTIONS
    if args.ids:
        ids_set = set(args.ids)
        questions = [q for q in questions if q["id"] in ids_set]
        if not questions:
            print(f"No questions found for IDs: {args.ids}")
            sys.exit(1)
    elif args.category:
        questions = [q for q in questions if q["category"] == args.category.upper()]
        if not questions:
            print(f"No questions found for category: {args.category}")
            sys.exit(1)

    run_evaluation(questions, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
