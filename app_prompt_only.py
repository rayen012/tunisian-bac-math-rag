#!/usr/bin/env python3
"""
app_prompt_only.py — Streamlit UI for the Prompt-Only baseline
---------------------------------------------------------------
Mirrors app.py but uses TunisianMathPromptOnly instead of TunisianMathRAG.
Side-by-side comparison: run both apps on different ports.

Usage:
  streamlit run app_prompt_only.py --server.port 8502
"""

import streamlit as st
from prompt_only_engine import TunisianMathPromptOnly, PromptOnlyResult

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Bac Math Tounsi - Prompt Only",
    page_icon="\U0001F4DD",  # memo
    layout="wide",
)

# ──────────────────────────────────────────────
# CSS (same as app.py for visual consistency)
# ──────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #f0f4ff; }
    h1, h2, h3 { color: #1a237e; font-family: 'Helvetica Neue', sans-serif; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 2px solid #eee; }
    .stChatMessage { border-radius: 14px; padding: 10px; margin-bottom: 10px; }
    .badge-fort { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#d4edda; color:#155724; border:1px solid #c3e6cb; }
    .badge-moyen { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#fff3cd; color:#856404; border:1px solid #ffeeba; }
    .badge-faible { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#f8d7da; color:#721c24; border:1px solid #f5c6cb; }
    .system-tag { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:11px; background:#e8eaf6; color:#283593; border:1px solid #c5cae9;
        margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Cache the engine (loads once)
# ──────────────────────────────────────────────
@st.cache_resource
def get_engine() -> TunisianMathPromptOnly:
    return TunisianMathPromptOnly()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def confidence_badge(level: str) -> str:
    labels = {
        "fort": ("Confiance forte", "badge-fort"),
        "moyen": ("Confiance moyenne", "badge-moyen"),
        "faible": ("Confiance faible", "badge-faible"),
    }
    text, css = labels.get(level, ("Inconnu", "badge-faible"))
    return f'<div class="{css}">{text}</div>'


def render_debug(result: PromptOnlyResult):
    """Render debug panel."""
    st.markdown("---")
    st.markdown("**Debug / Observability**")

    col1, col2, col3 = st.columns(3)
    col1.metric("Generation", f"{result.generation_time:.2f}s")
    col2.metric("Total", f"{result.total_time:.2f}s")
    col3.metric("System", result.retrieval_case)

    st.markdown(f"**Confidence:** {result.confidence}")
    st.markdown(f"**System prompt:** ~{result.system_prompt_tokens_approx} tokens")
    st.markdown(f"**User prompt:** ~{result.user_prompt_tokens_approx} tokens")


# ──────────────────────────────────────────────
# Load engine
# ──────────────────────────────────────────────
try:
    with st.spinner("Demarrage du moteur Prompt-Only..."):
        engine = get_engine()
except Exception as e:
    st.error(f"Erreur de chargement: {e}")
    st.stop()


# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("Prompt-Only Baseline")
    st.markdown('<div class="system-tag">SANS RETRIEVAL</div>', unsafe_allow_html=True)
    st.markdown("---")

    mode = st.radio("Mode :", ["Chatbot Tounsi", "Correction Type Bac"])
    mode_key = "correction" if "Correction" in mode else "coaching"

    st.markdown("---")
    debug_mode = st.checkbox("Mode debug", value=False)

    st.markdown("---")
    if st.button("Effacer l'historique"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.caption("Systeme: Prompt-Engineering Only")
    st.caption("Pas de ChromaDB / Pas d'embeddings")


# ──────────────────────────────────────────────
# Main chat UI
# ──────────────────────────────────────────────
st.title("Bac Math Tounsi - Prompt Only")
st.markdown(
    "Pose ta question en **Francais** ou en **Derja**. "
    "Ce systeme utilise **uniquement le prompt engineering** (pas de RAG)."
)

if "messages" not in st.session_state:
    st.session_state.messages = []

# Render history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_msg = st.chat_input("Ex: Comment montrer qu'une suite est convergente ?")
if user_msg:
    st.session_state.messages.append({"role": "user", "content": user_msg})
    with st.chat_message("user"):
        st.markdown(user_msg)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("_Generation en cours..._")

        result = engine.query(user_msg, mode=mode_key)

        # Confidence badge
        st.markdown(confidence_badge(result.confidence), unsafe_allow_html=True)

        if result.error:
            placeholder.error(f"Erreur: {result.error}")
        else:
            placeholder.markdown(result.answer)

        # Debug
        if debug_mode:
            render_debug(result)

        # Save to history
        if result.answer:
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.answer,
            })
