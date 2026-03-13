"""
chat_rag.py — Minimal Jupyter chat for the RAG engine.

Usage (in a notebook cell):
    from chat_rag import chat
    chat()                    # coaching mode (default)
    chat(mode="correction")   # correction mode

Type your question, press Enter. Type 'q' to quit.
"""

from rag_engine import TunisianMathRAG
from IPython.display import display, Markdown

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        print("Loading RAG engine (BGE-M3 + ChromaDB)...")
        _engine = TunisianMathRAG()
        print(f"Ready. Chunks: {_engine.chunk_count}\n")
    return _engine


def ask(question: str, mode: str = "coaching"):
    """Ask a single question and display the answer."""
    engine = _get_engine()
    result = engine.query(question, mode=mode)

    if result.error:
        print(f"ERROR: {result.error}")
    else:
        display(Markdown(result.answer))

    best_dist = result.selected_docs[0].distance if result.selected_docs else None
    print(f"\n--- case={result.retrieval_case} | "
          f"confidence={result.confidence} | "
          f"docs={len(result.selected_docs)} | "
          f"best_dist={f'{best_dist:.4f}' if best_dist else 'N/A'} | "
          f"ret={result.retrieval_time:.1f}s | "
          f"gen={result.generation_time:.1f}s | "
          f"total={result.total_time:.1f}s ---\n")
    return result


def chat(mode: str = "coaching"):
    """Interactive chat loop. Type 'q' to quit, 'm' to toggle mode."""
    engine = _get_engine()
    print(f"=== RAG Chat (mode={mode}) | {engine.chunk_count} chunks ===")
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

        best_dist = result.selected_docs[0].distance if result.selected_docs else None
        print(f"\n--- case={result.retrieval_case} | "
              f"confidence={result.confidence} | "
              f"docs={len(result.selected_docs)} | "
              f"best_dist={f'{best_dist:.4f}' if best_dist else 'N/A'} | "
              f"ret={result.retrieval_time:.1f}s | "
              f"gen={result.generation_time:.1f}s | "
              f"total={result.total_time:.1f}s ---\n")
