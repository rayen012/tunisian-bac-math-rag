#!/usr/bin/env python3
"""
app.py — Streamlit UI for the Tunisian Bac Math AI Tutor
---------------------------------------------------------
Thin presentation layer that delegates all RAG logic to rag_engine.py.

Features:
  - Caches the RAG engine (embedding model, ChromaDB, Vertex AI) via
    st.cache_resource so they load exactly once across reruns.
  - Two modes: Correction Type Bac / Coaching.
  - Debug toggle: shows retrieval scores, selected docs, timings.
  - Source transparency: expandable section with doc URIs and excerpts.
  - Confidence badge based on retrieval quality.

Usage:
  streamlit run app.py
  streamlit run app.py -- --debug   # start with debug on
"""

import streamlit as st
from rag_engine import TunisianMathRAG, QueryResult

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Bac Math Tounsi AI",
    page_icon="\U0001F1F9\U0001F1F3",  # Tunisia flag
    layout="wide",
)

# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    h1, h2, h3 { color: #c8102e; font-family: 'Helvetica Neue', sans-serif; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 2px solid #eee; }
    .stChatMessage { border-radius: 14px; padding: 10px; margin-bottom: 10px; }
    .badge-fort { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#d4edda; color:#155724; border:1px solid #c3e6cb; }
    .badge-moyen { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#fff3cd; color:#856404; border:1px solid #ffeeba; }
    .badge-faible { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#f8d7da; color:#721c24; border:1px solid #f5c6cb; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Cache the RAG engine (loads once)
# ──────────────────────────────────────────────
@st.cache_resource
def get_rag_engine() -> TunisianMathRAG:
    return TunisianMathRAG()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def confidence_badge(level: str) -> str:
    labels = {
        "fort": ("Contexte fort", "badge-fort"),
        "moyen": ("Contexte moyen", "badge-moyen"),
        "faible": ("Contexte faible", "badge-faible"),
    }
    text, css = labels.get(level, ("Inconnu", "badge-faible"))
    return f'<div class="{css}">{text}</div>'


def render_debug(result: QueryResult):
    """Render debug/observability panel."""
    st.markdown("---")
    st.markdown("**Debug / Observability**")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Retrieval", f"{result.retrieval_time:.2f}s")
    col2.metric("Generation", f"{result.generation_time:.2f}s")
    col3.metric("Total", f"{result.total_time:.2f}s")
    col4.metric("Case", result.retrieval_case)

    st.markdown(f"**Confidence:** {result.confidence}")
    st.markdown(f"**Selected docs:** {len(result.selected_docs)}")

    if result.first_pass_docs:
        with st.expander(f"First pass (corrections): {len(result.first_pass_docs)} docs"):
            for d in result.first_pass_docs[:8]:
                st.markdown(
                    f"- **Rank {d.rank}** | dist={d.distance:.3f} | "
                    f"type={d.metadata.get('type','')} | "
                    f"chapter={d.metadata.get('chapter','')} | "
                    f"file={d.metadata.get('filename','')}"
                )

    if result.second_pass_docs:
        with st.expander(f"Second pass (cours): {len(result.second_pass_docs)} docs"):
            for d in result.second_pass_docs[:8]:
                st.markdown(
                    f"- **Rank {d.rank}** | dist={d.distance:.3f} | "
                    f"type={d.metadata.get('type','')} | "
                    f"chapter={d.metadata.get('chapter','')}"
                )


def render_sources(result: QueryResult):
    """Render source transparency section."""
    with st.expander("Sources utilisees"):
        if not result.selected_docs:
            st.markdown("_Aucune source trouvee._")
            return

        for doc in result.selected_docs:
            meta = doc.metadata
            st.markdown(f"**Source {doc.rank}** (distance: {doc.distance:.3f})")
            st.markdown(
                f"- **Type:** {meta.get('type', '')} | "
                f"**Chapitre:** {meta.get('chapter', '')} | "
                f"**Annee:** {meta.get('year', '')} | "
                f"**Solution:** {meta.get('is_solution', '')}"
            )
            st.markdown(f"- **URI:** `{meta.get('source', '')}`")
            st.markdown("**Extrait:**")
            st.code(doc.content[:800], language="latex")
            st.markdown("---")


# ──────────────────────────────────────────────
# Load engine
# ──────────────────────────────────────────────
try:
    with st.spinner("Demarrage du moteur RAG..."):
        engine = get_rag_engine()
except Exception as e:
    st.error(f"Erreur de chargement du moteur RAG: {e}")
    st.stop()


# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("Bac Math Coach")
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
    st.caption(f"Chunks indexes: {engine.chunk_count}")


# ──────────────────────────────────────────────
# Main chat UI
# ──────────────────────────────────────────────
st.title("Bac Math Tounsi AI")
st.markdown(
    "Pose ta question en **Francais** ou en **Derja**. "
    "Je reponds avec la **redaction officielle tunisienne**."
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
    # Show user message
    st.session_state.messages.append({"role": "user", "content": user_msg})
    with st.chat_message("user"):
        st.markdown(user_msg)

    # Generate answer
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("_Recherche en cours..._")

        result = engine.query(user_msg, mode=mode_key)

        # Confidence badge
        st.markdown(confidence_badge(result.confidence), unsafe_allow_html=True)

        if result.error:
            placeholder.error(f"Erreur: {result.error}")
        else:
            placeholder.markdown(result.answer)

        # Sources
        render_sources(result)

        # Debug
        if debug_mode:
            render_debug(result)

        # Save to history
        if result.answer:
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.answer,
            })
