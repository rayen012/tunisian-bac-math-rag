"""
chat_hybrid.py — Minimal Jupyter chat for the Hybrid engine.

Usage (in a notebook cell):
    from chat_hybrid import chat
    chat()                    # coaching mode (default)
    chat(mode="correction")   # correction mode

Type your question, press Enter. Type 'q' to quit.

Displays routing info (case, knowledge_source, confidence, best_distance)
below each answer so you can observe the three-case router behavior.
"""

from hybrid_engine import TunisianMathHybrid
from IPython.display import display, Markdown

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        print("Loading Hybrid engine (BGE-M3 + ChromaDB + curriculum)...")
        _engine = TunisianMathHybrid()
        print(f"Ready. Chunks: {_engine.chunk_count}\n")
    return _engine


def ask(question: str, mode: str = "coaching"):
    """Ask a single question and display the answer + routing info."""
    engine = _get_engine()
    result = engine.query(question, mode=mode)

    if result.error:
        print(f"ERROR: {result.error}")
    else:
        display(Markdown(result.answer))

    bd = f"{result.best_distance:.4f}" if result.best_distance is not None else "N/A"
    print(f"\n--- ROUTING: case={result.retrieval_case} | "
          f"source={result.knowledge_source} | "
          f"confidence={result.confidence} | "
          f"best_dist={bd} | "
          f"docs={len(result.selected_docs)} | "
          f"ret={result.retrieval_time:.1f}s | "
          f"gen={result.generation_time:.1f}s | "
          f"total={result.total_time:.1f}s ---\n")
    return result


def chat(mode: str = "coaching"):
    """Interactive chat loop. Type 'q' to quit, 'm' to toggle mode."""
    engine = _get_engine()
    print(f"=== Hybrid Chat (mode={mode}) | {engine.chunk_count} chunks ===")
    print("Routing: A=retrieval | B=hybrid | C=parametric")
    print("Type 'q' to quit, 'm' to toggle mode.\n")

    while True:
        try:
            q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not q:
            continue
        if q.lower() == "q":
            break
        if q.lower() == "m":
            mode = "correction" if mode == "coaching" else "coaching"
            print(f"  → mode switched to: {mode}\n")
            continue

        result = engine.query(q, mode=mode)

        if result.error:
            print(f"\nERROR: {result.error}\n")
        else:
            display(Markdown(result.answer))

        bd = f"{result.best_distance:.4f}" if result.best_distance is not None else "N/A"
        print(f"\n--- ROUTING: case={result.retrieval_case} | "
              f"source={result.knowledge_source} | "
              f"confidence={result.confidence} | "
              f"best_dist={bd} | "
              f"docs={len(result.selected_docs)} | "
              f"ret={result.retrieval_time:.1f}s | "
              f"gen={result.generation_time:.1f}s | "
              f"total={result.total_time:.1f}s ---\n")
