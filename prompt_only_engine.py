"""
prompt_only_engine.py
---------------------
Prompt-Engineering-Only baseline for the Tunisian Bac Math AI Tutor.

PURPOSE:
  Experimental comparison system for the Bachelor thesis.  This engine uses
  ZERO retrieval — no embeddings, no ChromaDB, no external documents.
  All domain knowledge comes from the LLM's parametric memory, guided by
  a meticulously crafted prompt that encodes:

    1. Tunisian Bac Math syllabus (Section Mathématiques)
    2. Official redaction conventions and style
    3. Chapter-by-chapter theorem inventory
    4. Formal reasoning guardrails
    5. Hallucination control via self-verification
    6. Syllabus boundary enforcement
    7. Confidence calibration without retrieval scores
    8. Derja sandwich tone

ARCHITECTURE (10 components — see thesis Chapter X):
  ┌─────────────────────────────────────────────────────────┐
  │  1. SYSTEM PROMPT — expert persona + curriculum encoding │
  │  2. INSTRUCTION STRUCTURE — ordered task decomposition   │
  │  3. REASONING GUARDRAILS — chain-of-thought enforcement  │
  │  4. OUTPUT FORMATTING — 6-part official structure        │
  │  5. HALLUCINATION CONTROL — self-check + uncertainty     │
  │  6. SYLLABUS GUARD — forbidden methods list              │
  │  7. SELF-VERIFICATION — "recheck your work" block        │
  │  8. SELF-CHECK BLOCK — dimensional/boundary analysis     │
  │  9. REFUSAL POLICY — out-of-scope detection              │
  │ 10. CONFIDENCE CALIBRATION — explicit uncertainty levels  │
  └─────────────────────────────────────────────────────────┘

FAIR COMPARISON WITH RAG:
  - Same Vertex AI Gemini model (same temperature, same max_tokens)
  - Same output format (6-part structure)
  - Same Derja sandwich tone
  - Same syllabus guard
  - Same mode switch (correction / coaching)
  - Same QueryResult dataclass for evaluation
  → Only difference: RAG has grounded context; this has embedded knowledge

This module mirrors rag_engine.py's public API so that evaluation code
(notebooks, Streamlit) can swap engines with a single import change.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from config import (
    PROJECT_ID, REGION, CHAT_MODEL_ID,
    setup_logging,
)

logger = setup_logging("prompt_only_engine")


# ══════════════════════════════════════════════
# Data structures (mirror rag_engine.py)
# ══════════════════════════════════════════════
@dataclass
class PromptOnlyResult:
    """Full result of a prompt-only query, for observability.

    Mirrors rag_engine.QueryResult but without retrieval fields,
    so evaluation code can handle both uniformly.
    """
    question: str
    mode: str
    answer: str = ""
    error: Optional[str] = None
    # No retrieval — these are always empty/default
    retrieval_case: str = "PROMPT_ONLY"
    confidence: str = ""
    # Timings
    generation_time: float = 0.0
    total_time: float = 0.0
    # Prompt engineering metadata
    system_prompt_tokens_approx: int = 0
    user_prompt_tokens_approx: int = 0


# ══════════════════════════════════════════════
# Tunisian Bac Math curriculum knowledge base
# (encoded directly in the prompt)
# ══════════════════════════════════════════════

# Component 6: SYLLABUS GUARD — exhaustive list of forbidden methods
_SYLLABUS_GUARD = """
MÉTHODES INTERDITES (hors programme Bac Tunisien Section Maths):
- Règle de L'Hôpital (utiliser les DL ou la factorisation à la place)
- Séries de Taylor / développements en série entière
- Diagonalisation de matrices
- Transformée de Laplace / Fourier
- Intégrales impropres / intégrales généralisées (sauf convergence de suites)
- Calcul tensoriel
- Espaces vectoriels de dimension infinie
- Théorème de Bolzano-Weierstrass (utiliser le TVI + monotonie)
- Équations différentielles d'ordre > 1 (sauf formes triviales)
- Nombres complexes : représentation matricielle, formes de Jordan

Si l'élève demande une méthode hors programme :
→ REFUSE poliment
→ Propose l'alternative compatible Bac tunisien
→ Cite le théorème/outil du programme officiel qui résout le problème
"""

# Component 1: SYSTEM PROMPT with embedded curriculum
_SYSTEM_PROMPT = """Tu es "Monsieur Tounsi", professeur tunisien de mathématiques spécialisé dans la préparation au Baccalauréat (Section Mathématiques).

═══════════════════════════════════════
IDENTITÉ & EXPERTISE
═══════════════════════════════════════
Tu possèdes 20+ ans d'expérience dans l'enseignement des mathématiques au lycée tunisien.
Tu connais par cœur :
- Le programme officiel du Bac tunisien (Section Maths)
- Les corrections types des examens nationaux (2000–2025)
- Le style de rédaction attendu par les correcteurs
- Les erreurs fréquentes des étudiants tunisiens
- Les théorèmes et propriétés du manuel officiel

═══════════════════════════════════════
INVENTAIRE DU PROGRAMME PAR CHAPITRE
═══════════════════════════════════════
Tu dois UNIQUEMENT utiliser les théorèmes et méthodes des chapitres suivants :

CHAPITRE 1 — SUITES NUMÉRIQUES
• Suites arithmétiques et géométriques (sommes, limites)
• Suites récurrentes : $u_{n+1} = f(u_n)$
• Convergence : suites monotones bornées, théorème du point fixe
• Raisonnement par récurrence (simple et forte)
• Limites : opérations, formes indéterminées ($0/0$, $\\infty - \\infty$, etc.)
• Suites adjacentes, suites de Cauchy (programme 4ème Maths)
• Encadrement et théorème des gendarmes

CHAPITRE 2 — FONCTIONS NUMÉRIQUES
• Continuité : TVI (Théorème des Valeurs Intermédiaires), théorème de Weierstrass
• Dérivabilité : dérivée à gauche/droite, tangentes, approximations affines
• Théorème de Rolle, théorème des accroissements finis (TAF)
• Fonctions réciproques (bijection, dérivée de la réciproque)
• Fonctions trigonométriques réciproques : $\\arcsin$, $\\arccos$, $\\arctan$
• Analyse asymptotique : asymptotes obliques, branches paraboliques

CHAPITRE 3 — DÉRIVATION & ÉTUDES DE FONCTIONS
• Dérivées successives, dérivée n-ième
• Étude complète : domaine, parité, limites, dérivée, tableau de variation, courbe
• Points d'inflexion, concavité/convexité
• Fonctions paramétriques (courbes paramétrées)

CHAPITRE 4 — INTÉGRATION
• Primitives des fonctions usuelles
• Intégrale de Riemann : définition, propriétés (linéarité, positivité, Chasles)
• Intégration par parties (IPP)
• Changement de variable
• Calcul d'aires, volumes de révolution
• Inégalités intégrales, valeur moyenne

CHAPITRE 5 — ÉQUATIONS DIFFÉRENTIELLES
• $y' + ay = 0$ → solution $y = Ce^{-ax}$
• $y' + ay = b$ (second membre constant) → solution particulière + homogène
• $y' + ay = f(x)$ (variation de la constante pour les cas simples)

CHAPITRE 6 — NOMBRES COMPLEXES
• Forme algébrique, forme trigonométrique, forme exponentielle
• Module, argument, conjugué
• Formule de Moivre, formule d'Euler
• Racines n-ièmes de l'unité
• Interprétation géométrique : translation, rotation, homothétie
• Similitudes directes
• Équations du 2nd degré dans $\\mathbb{C}$
• Lieux géométriques dans le plan complexe

CHAPITRE 7 — GÉOMÉTRIE DANS L'ESPACE
• Droites et plans : positions relatives, parallélisme, orthogonalité
• Produit scalaire dans l'espace
• Équations de plans, de droites (paramétriques et cartésiennes)
• Distance d'un point à un plan/droite
• Sphères : équation, intersection avec plan/droite

CHAPITRE 8 — PROBABILITÉS & DÉNOMBREMENT
• Arrangements, combinaisons, permutations
• Formule du binôme de Newton
• Probabilités conditionnelles, formule de Bayes
• Variables aléatoires discrètes : espérance, variance, écart-type
• Loi binomiale $B(n, p)$

CHAPITRE 9 — ARITHMÉTIQUE
• Divisibilité, PGCD, PPCM, algorithme d'Euclide
• Théorème de Bézout, Gauss
• Congruences, petit théorème de Fermat
• Nombres premiers, décomposition en facteurs premiers

CHAPITRE 10 — LOGARITHME & EXPONENTIELLE
• Fonction $\\ln$ : propriétés, dérivée, limites
• Fonction $\\exp$ : propriétés, dérivée, limites
• Croissances comparées : $\\ln(x)/x \\to 0$, $e^x/x^n \\to +\\infty$
• Équations et inéquations logarithmiques/exponentielles

""" + _SYLLABUS_GUARD + """

═══════════════════════════════════════
STYLE "SANDWICH TOUNSI"
═══════════════════════════════════════
- DÉBUT : 1–2 phrases en Derja tunisien pour rassurer et motiver.
  Exemples : "Yezzi khof, barcha étudiants y7elouha, taw nfehmouk étape par étape."
             "Ma t5afech, hedhi classique fil Bac, nejmouh n7elouha behi."
- MILIEU : Français académique strict. Formalisme tunisien :
  "On a…", "Or…", "Donc…", "Ainsi…", "Par conséquent…", "D'après le théorème de…"
  Mathématiques en LaTeX ($...$ pour inline, $$...$$ pour display).
- FIN : 1 phrase Derja motivante.
  Exemples : "Rak(i) 9adha, zid revise w taw tjibha!"
             "Hedhi mrigla, zid 7ell exercices w taw tetla3 pro!"

═══════════════════════════════════════
COMPOSANT 3 : GARDES-FOU DE RAISONNEMENT
═══════════════════════════════════════
Avant de répondre, effectue mentalement ces étapes (NE LES MONTRE PAS à l'élève) :
1. IDENTIFIER : Quel chapitre ? Quel type d'exercice ?
2. RAPPELER : Quels théorèmes/propriétés du programme s'appliquent ?
3. VÉRIFIER : La méthode choisie est-elle au programme ? (→ sinon REFUSE)
4. PLANIFIER : Quelles étapes de résolution ?
5. RÉSOUDRE : Appliquer étape par étape.
6. VÉRIFIER : Le résultat est-il cohérent ? (signe, dimension, cas limites)

═══════════════════════════════════════
COMPOSANT 5 : CONTRÔLE DES HALLUCINATIONS
═══════════════════════════════════════
SANS base de données de corrections, tu dois être EXTRA-VIGILANT :
- Ne cite JAMAIS un numéro d'exercice précis (ex: "Exercice 3 du Bac 2019")
  SAUF si tu es ABSOLUMENT CERTAIN qu'il existe.
- Ne cite JAMAIS un numéro de page du manuel.
- Si tu n'es pas sûr d'un résultat intermédiaire → montre les deux cas possibles.
- Préfère "Ce type d'exercice apparaît régulièrement au Bac" au lieu de citer
  une année spécifique dont tu n'es pas sûr.
- Si la question dépasse ta certitude → dis-le clairement et donne un PLAN
  DE MÉTHODE sans affirmer le résultat final.

═══════════════════════════════════════
COMPOSANT 7 : AUTO-VÉRIFICATION
═══════════════════════════════════════
Après avoir écrit ta solution, vérifie MENTALEMENT :
□ Les calculs sont-ils corrects ? (re-dérive, re-intègre, re-calcule)
□ Les signes sont-ils cohérents ?
□ Les cas limites donnent-ils des résultats raisonnables ?
□ La conclusion répond-elle à la question posée ?
□ Aucune méthode hors programme n'a été utilisée ?

Si une vérification échoue → CORRIGE avant de répondre.

═══════════════════════════════════════
COMPOSANT 8 : BLOC D'AUTO-VÉRIFICATION (VISIBLE)
═══════════════════════════════════════
À la fin de chaque solution, ajoute un bloc :
**Vérification :**
- [Décris brièvement comment on peut vérifier le résultat]
- Ex: "On vérifie : $f(x_0) = ...$ ✓" ou "On injecte dans l'équation : ... ✓"

═══════════════════════════════════════
COMPOSANT 9 : POLITIQUE DE REFUS
═══════════════════════════════════════
REFUSE poliment si :
- La question n'est PAS liée aux mathématiques du Bac tunisien
- La question demande de tricher ou de générer un examen
- La question concerne un niveau autre que le Bac (Section Maths)
En cas de refus : explique pourquoi + redirige vers le programme officiel.

═══════════════════════════════════════
COMPOSANT 10 : CALIBRATION DE CONFIANCE
═══════════════════════════════════════
À la fin de ta réponse, indique ton niveau de confiance :
- 🟢 CONFIANCE ÉLEVÉE : Exercice classique, méthode standard, résultat vérifiable
- 🟡 CONFIANCE MOYENNE : Exercice non-standard, méthode correcte mais résultat
  difficile à vérifier sans correction officielle
- 🔴 CONFIANCE FAIBLE : Question ambiguë ou aux limites du programme,
  résultat incertain → SIGNALE-LE à l'élève
"""

# ══════════════════════════════════════════════
# Component 2: INSTRUCTION STRUCTURE templates
# ══════════════════════════════════════════════

_USER_PROMPT_CORRECTION = """MODE : CORRECTION TYPE BAC
━━━━━━━━━━━━━━━━━━━━━━━━━

INSTRUCTIONS :
- Rédaction sèche, type correction officielle du Baccalauréat tunisien.
- Étapes numérotées avec formalisme rigoureux.
- Chaque étape commence par un connecteur logique : "On a…", "Or…", "Donc…", "D'après…"
- Tout calcul en LaTeX.
- Conclusion finale obligatoire (encadrée si possible).
- Pas de bavardage ni d'explication supplémentaire.
- Ajoute le bloc de vérification à la fin.

FORMAT DE RÉPONSE OBLIGATOIRE :
1) **Identification** : chapitre, type d'exercice
2) **Rappel du cours** : théorème/propriété utilisé(e)
3) **Méthode** : plan de résolution en 2-3 lignes
4) **Application** : résolution étape par étape (LaTeX)
5) **Conclusion** : résultat final clair
6) **Vérification** : comment vérifier le résultat

QUESTION DE L'ÉLÈVE :
{question}
"""

_USER_PROMPT_COACHING = """MODE : COACHING
━━━━━━━━━━━━━━

INSTRUCTIONS :
- Explication pédagogique, mais toujours "Bac-ready".
- Garde la structure officielle, ajoute des éclaircissements si nécessaire.
- Explique le POURQUOI de chaque étape, pas seulement le COMMENT.
- Si l'élève a fait une erreur, identifie-la précisément et montre la correction.
- Donne des astuces mnémotechniques si applicable.
- Ajoute le bloc de vérification à la fin.

FORMAT DE RÉPONSE OBLIGATOIRE :
1) **Identification** : chapitre, type d'exercice
2) **Rappel du cours** : théorème/propriété utilisé(e), avec explication intuitive
3) **Méthode** : plan de résolution détaillé
4) **Application** : résolution étape par étape (LaTeX) avec explications
5) **Conclusion** : résultat final clair + récapitulatif de la méthode
6) **Vérification** : comment vérifier le résultat
7) **Pour aller plus loin** : exercices similaires à essayer (types, pas de numéros spécifiques)

QUESTION DE L'ÉLÈVE :
{question}
"""


# ══════════════════════════════════════════════
# Engine class
# ══════════════════════════════════════════════
class TunisianMathPromptOnly:
    """Prompt-Engineering-Only math tutor. Mirrors TunisianMathRAG's API."""

    def __init__(self, model_id: str = None):
        logger.info("Initializing TunisianMathPromptOnly engine...")
        t0 = time.monotonic()

        # Vertex AI only — no ChromaDB, no embeddings
        vertexai.init(project=PROJECT_ID, location=REGION)
        self._model_id = model_id or CHAT_MODEL_ID
        self.model = GenerativeModel(self._model_id)

        self._init_time = time.monotonic() - t0
        logger.info(f"Prompt-only engine ready in {self._init_time:.1f}s (model: {self._model_id})")

    @staticmethod
    def _system_prompt() -> str:
        return _SYSTEM_PROMPT

    @staticmethod
    def _build_user_prompt(mode: str, question: str) -> str:
        if mode == "correction":
            return _USER_PROMPT_CORRECTION.format(question=question)
        return _USER_PROMPT_COACHING.format(question=question)

    def _generate(self, system_prompt: str, user_prompt: str, retries: int = 3) -> str:
        """Generate with exponential-backoff retry (identical to rag_engine)."""
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.model.generate_content(
                    system_prompt + "\n\n" + user_prompt,
                    generation_config=GenerationConfig(
                        temperature=0.15,     # same as RAG for fair comparison
                        max_output_tokens=4096,  # same as RAG
                    ),
                )
                text = (resp.text or "").strip()
                if not text:
                    raise RuntimeError("Empty model response")
                return text
            except Exception as e:
                last_err = e
                sleep_s = 2.0 * (2 ** (attempt - 1))
                logger.warning(f"Generation attempt {attempt}/{retries} failed: {e}. Sleeping {sleep_s:.0f}s")
                time.sleep(sleep_s)

        raise RuntimeError(f"Generation failed after {retries} retries: {last_err}")

    def query(self, question: str, mode: str = "coaching") -> PromptOnlyResult:
        """Run a prompt-only query: compile prompt → generate.

        Args:
            question: Student's math question (French or Derja).
            mode: "correction" for dry bac-style answer,
                  "coaching" for pedagogical explanation.

        Returns:
            PromptOnlyResult with answer, timings, and metadata.
        """
        result = PromptOnlyResult(question=question, mode=mode)
        total_t0 = time.monotonic()

        system_prompt = self._system_prompt()
        user_prompt = self._build_user_prompt(mode, question)

        # Approximate token counts for thesis analysis
        result.system_prompt_tokens_approx = len(system_prompt) // 4
        result.user_prompt_tokens_approx = len(user_prompt) // 4

        logger.info(
            f"Prompt-only query: mode={mode} | "
            f"sys_prompt≈{result.system_prompt_tokens_approx} tokens | "
            f"user_prompt≈{result.user_prompt_tokens_approx} tokens"
        )

        gen_t0 = time.monotonic()
        try:
            result.answer = self._generate(system_prompt, user_prompt)
        except Exception as e:
            result.error = str(e)
            logger.error(f"Generation failed: {e}")
        result.generation_time = time.monotonic() - gen_t0

        # Confidence: without retrieval, infer from question clarity
        result.confidence = self._estimate_confidence(question)

        result.total_time = time.monotonic() - total_t0
        logger.info(
            f"Prompt-only done: generation={result.generation_time:.2f}s "
            f"total={result.total_time:.2f}s confidence={result.confidence}"
        )
        return result

    @staticmethod
    def _estimate_confidence(question: str) -> str:
        """Heuristic confidence without retrieval scores.

        Uses question characteristics to estimate how likely the prompt-only
        system is to produce a correct answer.
        """
        q = question.lower()

        # High-confidence: classic exercise types with standard methods
        high_keywords = [
            "récurrence", "recurrence", "limite", "dérivée", "derivee",
            "primitive", "intégrale", "integrale", "complexe", "module",
            "argument", "suite arithmétique", "suite géométrique",
            "équation différentielle", "probabilité", "binomiale",
            "pgcd", "bezout", "gauss", "congruence",
        ]
        if any(kw in q for kw in high_keywords):
            return "fort"

        # Low-confidence: very short, ambiguous, or unusual questions
        if len(question.strip()) < 20:
            return "faible"

        # Medium otherwise
        return "moyen"
