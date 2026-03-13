"""
chat_prompt_only.py — Minimal Jupyter chat for the Prompt-Only engine.

Usage (in a notebook cell):
    from chat_prompt_only import chat
    chat()                    # coaching mode (default)
    chat(mode="correction")   # correction mode

Type your question, press Enter. Type 'q' to quit.
"""

from prompt_only_engine import TunisianMathPromptOnly
from IPython.display import display, Markdown

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        print("Loading Prompt-Only engine...")
        _engine = TunisianMathPromptOnly()
        print("Ready.\n")
    return _engine


def ask(question: str, mode: str = "coaching"):
    """Ask a single question and display the answer."""
    engine = _get_engine()
    result = engine.query(question, mode=mode)

    if result.error:
        print(f"ERROR: {result.error}")
    else:
        display(Markdown(result.answer))

    print(f"\n--- confidence={result.confidence} | "
          f"time={result.total_time:.1f}s | "
          f"mode={mode} ---\n")
    return result


def chat(mode: str = "coaching"):
    """Interactive chat loop. Type 'q' to quit, 'm' to toggle mode."""
    engine = _get_engine()
    print(f"=== Prompt-Only Chat (mode={mode}) ===")
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

        print(f"\n--- confidence={result.confidence} | "
              f"time={result.total_time:.1f}s ---\n")
