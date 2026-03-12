#!/usr/bin/env python3
"""
app_hybrid.py — Streamlit UI for the Hybrid RAG + Prompt-Only system
---------------------------------------------------------------------
Mirrors app.py and app_prompt_only.py but uses TunisianMathHybrid.
Shows routing case (A/B/C) and knowledge source in the debug panel.

Usage:
  streamlit run app_hybrid.py --server.port 8503
"""

import streamlit as st
from hybrid_engine import TunisianMathHybrid, HybridResult

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Bac Math Tounsi - Hybrid",
    page_icon="\U0001F504",  # arrows (cycle)
    layout="wide",
)

# ──────────────────────────────────────────────
# CSS (green theme — completing Tunisia flag trio)
# ──────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #f0faf0; }
    h1, h2, h3 { color: #1b5e20; font-family: 'Helvetica Neue', sans-serif; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 2px solid #eee; }
    .stChatMessage { border-radius: 14px; padding: 10px; margin-bottom: 10px; }
    .badge-fort { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#d4edda; color:#155724; border:1px solid #c3e6cb; }
    .badge-moyen { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#fff3cd; color:#856404; border:1px solid #ffeeba; }
    .badge-faible { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:13px; background:#f8d7da; color:#721c24; border:1px solid #f5c6cb; }
    .system-tag { display:inline-block; padding:4px 12px; border-radius:999px;
        font-size:11px; background:#e8f5e9; color:#1b5e20; border:1px solid #a5d6a7;
        margin-bottom: 8px; }
    .case-tag { display:inline-block; padding:4px 10px; border-radius:8px;
        font-size:12px; font-weight:bold; margin-right:6px; }
    .case-a { background:#d4edda; color:#155724; }
    .case-b { background:#fff3cd; color:#856404; }
    .case-c { background:#e8eaf6; color:#283593; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Cache the engine (loads once)
# ──────────────────────────────────────────────
@st.cache_resource
def get_engine() -> TunisianMathHybrid:
    return TunisianMathHybrid()


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


def case_badge(case: str, knowledge_source: str) -> str:
    case_labels = {
        "A": ("CAS A — Retrieval fort", "case-a"),
        "B": ("CAS B — Hybride", "case-b"),
        "C": ("CAS C — Parametrique", "case-c"),
    }
    label, css = case_labels.get(case, ("Inconnu", "case-c"))
    return f'<span class="case-tag {css}">{label}</span> <small>({knowledge_source})</small>'


def render_debug(result: HybridResult):
    """Render debug/observability panel."""
    st.markdown("---")
    st.markdown("**Debug / Observability**")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Retrieval", f"{result.retrieval_time:.2f}s")
    col2.metric("Generation", f"{result.generation_time:.2f}s")
    col3.metric("Total", f"{result.total_time:.2f}s")
    col4.metric("Case", result.retrieval_case)
    col5.metric("Source", result.knowledge_source)

    st.markdown(f"**Confidence:** {result.confidence}")
    st.markdown(f"**Best distance:** {result.best_distance:.4f}" if result.best_distance else "**Best distance:** N/A")
    st.markdown(f"**Selected docs:** {len(result.selected_docs)}")
    st.markdown(f"**System prompt:** ~{result.system_prompt_tokens_approx} tokens")
    st.markdown(f"**User prompt:** ~{result.user_prompt_tokens_approx} tokens")

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
        with st.expander(f"Second pass (textbook): {len(result.second_pass_docs)} docs"):
            for d in result.second_pass_docs[:8]:
                st.markdown(
                    f"- **Rank {d.rank}** | dist={d.distance:.3f} | "
                    f"type={d.metadata.get('type','')} | "
                    f"chapter={d.metadata.get('chapter','')}"
                )


def render_sources(result: HybridResult):
    """Render source transparency section (Cases A and B only)."""
    if result.retrieval_case == "C":
        with st.expander("Sources"):
            st.markdown("_Aucun document pertinent trouvé — réponse basée sur les connaissances du programme._")
        return

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
    with st.spinner("Demarrage du moteur Hybride..."):
        engine = get_engine()
except Exception as e:
    st.error(f"Erreur de chargement: {e}")
    st.stop()


# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("Hybrid Engine")
    st.markdown('<div class="system-tag">RAG + PROMPT-ONLY</div>', unsafe_allow_html=True)
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
    st.caption("Systeme: Hybride (RAG + Prompt-Only)")
    st.caption("Routage: A (retrieval) / B (hybride) / C (parametrique)")


# ──────────────────────────────────────────────
# Main chat UI
# ──────────────────────────────────────────────
st.title("Bac Math Tounsi - Hybrid")
st.markdown(
    "Pose ta question en **Francais** ou en **Derja**. "
    "Ce systeme **combine RAG et prompt engineering** selon la qualite du retrieval."
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
        placeholder.markdown("_Recherche et analyse en cours..._")

        result = engine.query(user_msg, mode=mode_key)

        # Case badge + confidence badge
        st.markdown(
            case_badge(result.retrieval_case, result.knowledge_source),
            unsafe_allow_html=True,
        )
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
