# RAG Methods Section — Companion Notes

## 1. Detailed Outline (as implemented in rag_methods_section.tex)

```
3.X  Retrieval-Augmented Generation System
  3.X.1  Data Acquisition and Paired Exercise–Correction Structure
  3.X.2  Mathematical Document Digitization
    3.X.2.1  Tool Selection: Mathpix versus Gemini
    3.X.2.2  Digitization Pipeline (digitize.py)
    3.X.2.3  Bug Discovery and Fix
  3.X.3  Database Construction and Indexing
    3.X.3.1  From JSON Vector Store to ChromaDB
    3.X.3.2  Text Normalization
    3.X.3.3  Adaptive Chunking Strategy
    3.X.3.4  Metadata Extraction
    3.X.3.5  Incremental Indexing and Manifest Tracking
  3.X.4  Embedding Model Selection
    3.X.4.1  Initial Experience with Google Embedding Models
    3.X.4.2  Migration to BGE-M3
  3.X.5  RAG Retrieval and Generation Engine
    3.X.5.1  Two-Stage Retrieval
    3.X.5.2  Similarity Thresholds
    3.X.5.3  Context Compilation
    3.X.5.4  Prompt Construction and Generation
    3.X.5.5  Confidence Levels and Observability
  3.X.6  Paired Retrieval of Exercise and Correction
    3.X.6.1  Companion Fetch Mechanism
    3.X.6.2  Significance for Mathematical RAG
  3.X.7  Connection to the Tunisian Baccalaureate Context
```


## 2. Bibliography Checklist

### Claims backed by literature (with BibTeX keys)

| Claim | Citation | BibTeX Key |
|-------|----------|------------|
| RAG combines parametric and non-parametric memory for knowledge-intensive tasks | Lewis et al., NeurIPS 2020 | `lewis2020rag` |
| RAG survey categorizing Naive/Advanced/Modular RAG and parent-document retrieval | Gao et al., 2024 | `gao2024rag_survey` |
| Dense passage retrieval outperforms BM25 for open-domain QA | Karpukhin et al., EMNLP 2020 | `karpukhin2020dpr` |
| BGE-M3 achieves SOTA on multilingual/cross-lingual retrieval benchmarks | Chen et al., 2024 | `chen2024bgem3` |
| BGE-M3 supports 100+ languages, 8192 token input, dense+sparse+multi-vector | Chen et al., 2024 | `chen2024bgem3` |
| OCRBench evaluates multimodal LLMs on OCR including math expression recognition | Wang et al., 2023 | `wang2023ocrbench` |
| Gemini achieved highest overall score on OCRBench among multimodal models tested | Wang et al., 2023 | `wang2023ocrbench` |
| Structure-aware chunking outperforms paragraph-level chunking for RAG | Zhao et al., 2024 | `zhao2024financial_chunking` |
| Dynamic granularity selection improves RAG retrieval across heterogeneous corpora | Chen et al., 2024 (MoG) | `chen2024mog` |
| Mathematical expressions have 2D spatial structure unlike linear text | Zanibbi & Blostein, 2012 | `zanibbi2016math_retrieval` |
| Math formulas can have multiple semantically equivalent forms | Mansouri et al., ICTIR 2019 | `mansouri2019tangent` |
| Standard text embeddings treat math symbols as low-frequency tokens with weak representations | Pfahler et al., Scientometrics 2020 | `pfahler2020math_embeddings` |
| Mathematical OCR faces challenges with 2D structures, symbol ambiguity, LaTeX strictness | Mahdavi et al., Applied Sciences 2023 | `mahdavi2019icdar_math` |

### Claims from own implementation (no literature citation needed)

| Claim | Type |
|-------|------|
| Paired exercise–correction acquisition strategy | Design decision |
| Mathpix was rejected due to cost constraints | Implementation constraint |
| Gemini used for digitization via Vertex AI | Implementation choice |
| Bug fix: deduplication checking wrong filename pattern | Implementation anecdote |
| Migration from JSON vector store to ChromaDB | Implementation evolution |
| Adaptive chunk sizes: 1500 for corrections, 3000 for textbook | Design decision |
| 10 metadata fields schema (type, year, session, exo_id, etc.) | Design decision |
| Manifest with GCS generation + SHA-256 double-check | Design decision |
| Google embedding model failed to distinguish v(n) from u(n) | Empirical observation |
| Two-stage retrieval: corrections first, textbook fallback | Design decision |
| SIMILARITY_GOOD_THRESHOLD = 1.2, FALLBACK = 1.6 | Empirically calibrated |
| Companion fetch mechanism for exercise–correction pairing | Design contribution |
| Confidence levels (fort/moyen/faible) based on distance + context size | Design decision |
| UI-agnostic engine architecture | Design decision |
| Derja sandwich pedagogical convention | Domain adaptation |
| Syllabus guard forbidding out-of-program methods | Domain adaptation |
| Anti-injection rules in system prompt | Security design |
| Temperature = 0.15 for generation | Implementation choice |


## 3. Weak Evidence Areas

### Areas where evidence relies on implementation reasoning rather than literature

1. **Paired exercise–correction acquisition.** No paper directly studies
   this for mathematical RAG. The argument is constructed by analogy from
   structure-aware chunking literature (Zhao et al., Chen et al.) and from
   pedagogical reasoning about mathematical documents. This is the weakest
   link in the literature grounding. *Mitigation:* The section clearly states
   this is a domain-specific contribution, not a literature-backed claim.

2. **Google embedding model failure on v(n)/u(n).** This is a qualitative
   observation, not a controlled experiment. We did not measure recall@k or
   MRR before and after the switch. *Mitigation:* The text explicitly
   acknowledges this is an empirical observation and not a systematic ablation.

3. **Similarity thresholds (1.2 and 1.6).** These are empirically chosen
   with no formal optimization (e.g., grid search on a labeled retrieval
   dataset). *Mitigation:* The text honestly presents them as empirically
   calibrated parameters, not theoretical constants.

4. **Gemini vs. Mathpix comparison.** No peer-reviewed study directly
   compares these two tools for math digitization. *Mitigation:* The text
   explicitly states this and frames the decision as a cost constraint.

5. **ChromaDB as optimal vector store choice.** ChromaDB is open-source
   software, not a peer-reviewed contribution. The citation is to the
   project documentation. *Mitigation:* The argument is framed around
   architectural requirements (persistence, metadata filtering, local
   operation) rather than claiming ChromaDB is academically validated.

6. **Two-stage retrieval strategy.** No prior work describes exactly this
   pattern (corrections-first, textbook-fallback). The closest concept is
   multi-stage retrieval or cascaded retrieval in IR literature, but those
   typically involve re-ranking rather than source-type prioritization.
   *Mitigation:* Framed as a pedagogical design decision specific to this
   domain.

7. **Companion fetch mechanism.** No prior work implements exercise–correction
   pairing in RAG. The closest concept is parent-document retrieval from the
   Gao et al. survey. *Mitigation:* Explicitly framed as a novel
   implementation contribution, with the analogy to parent-document retrieval
   clearly stated.


## 4. BibTeX Entries to Add

All BibTeX entries are included at the bottom of `rag_methods_section.tex`
as comments. Copy them into your main `.bib` file. Summary:

1. `lewis2020rag` — Lewis et al., NeurIPS 2020 (original RAG paper)
2. `gao2024rag_survey` — Gao et al., 2024 (comprehensive RAG survey)
3. `karpukhin2020dpr` — Karpukhin et al., EMNLP 2020 (DPR)
4. `chen2024bgem3` — Chen et al., 2024 (BGE-M3 paper)
5. `wang2023ocrbench` — Wang et al., 2023 (OCRBench)
6. `zhao2024financial_chunking` — Zhao et al., 2024 (structure-aware chunking)
7. `chen2024mog` — Mix-of-Granularity, COLING 2025
8. `chromadb2024` — ChromaDB project (software citation)
9. `mathpix2024` — Mathpix (software citation)
10. `mansouri2019tangent` — Mansouri et al., ICTIR 2019 (Tangent-CFT math embeddings)
11. `zanibbi2016math_retrieval` — Zanibbi & Blostein, 2012 (math IR survey)
12. `pfahler2020math_embeddings` — Pfahler et al., 2020 (math-word embedding)
13. `mahdavi2019icdar_math` — Mahdavi et al., 2023 (image-to-LaTeX OCR)


## 5. Suggestions to Strengthen the Section

### Suggestion 1: Add a retrieval quality micro-evaluation

Run 10–15 representative queries through the RAG engine and report the
retrieval results in a small table: query, retrieved document, distance,
relevance (yes/no as judged by you). This would provide quantitative backing
for the similarity thresholds and demonstrate that the two-stage retrieval
works as described. Even without a formal benchmark, a small manual evaluation
adds credibility.

### Suggestion 2: Include a pipeline architecture diagram

A figure showing the full pipeline (Scan → Gemini → .tex → build_db → ChromaDB
→ query → two-stage retrieval → companion fetch → prompt → Gemini → answer)
would make the section much more accessible. Number the steps to match the
subsection structure.

### Suggestion 3: Show a concrete example of companion pairing

Include a worked example: "The student asks X. The first pass retrieves
Correction Y (Bac 2019, Exercice 3, Complexes). The companion fetch
retrieves the exercise statement for Bac 2019 Ex3. The context sent to the
LLM contains both." This makes the companion fetch mechanism tangible for
the reader.

### Suggestion 4: Discuss limitations explicitly

Add a short subsection at the end discussing known limitations:
- The corpus is finite and may not cover all exercise types
- Thresholds are empirically tuned, not optimized
- Gemini digitization may introduce transcription errors
- The system does not currently support figure/diagram retrieval
- BGE-M3 dense retrieval may still miss symbolic distinctions in edge cases

This shows academic maturity and preempts reviewer criticism.

### Suggestion 5: Connect to the evaluation methodology

Add a forward reference to the evaluation chapter, stating that the three
systems (RAG, Prompt-Only, Hybrid) are evaluated on the same set of questions
using the same LLM and temperature settings, so that the only variable is the
retrieval component. This sets up the comparative evaluation cleanly.
