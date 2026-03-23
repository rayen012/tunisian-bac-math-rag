"""
eval_questions.py
-----------------
Structured evaluation question bank for the Bachelor thesis.

20 questions across 5 categories, covering 15+ chapters of the Tunisian
Baccalaureate mathematics program (Section Mathématiques).

Categories:
  A — Direct Bac-style (questions close to what exists in the corpus)
  B — Novel chapter-based (same topics, different problems)
  C — Student-style informal (how a real student would ask)
  D — Derja / mixed-language (Tunisian dialect)
  E — Out-of-scope / guardrail (should refuse or stay in bounds)

Each question has:
  - id:       Unique identifier (e.g., "A01")
  - category: One of A/B/C/D/E
  - chapter:  Bac Math chapter name
  - mode:     "correction" or "coaching"
  - question: The question text (French, Derja, or mixed)
  - notes:    What this question is designed to test
"""

EVAL_QUESTIONS = [
    # =========================================================================
    #  CATEGORY A — Direct Bac-style questions
    #  Purpose: These resemble real Bac exam questions. The RAG system SHOULD
    #  find matching corrections in the corpus. Tests retrieval precision.
    # =========================================================================
    {
        "id": "A01",
        "category": "A",
        "chapter": "Nombres complexes",
        "mode": "correction",
        "question": (
            "Résoudre dans \\mathbb{C} l'équation z² - 4z + 8 = 0. "
            "Écrire les solutions sous forme trigonométrique."
        ),
        "notes": "Classic Bac exercise. Tests complex number resolution + trigonometric form.",
    },
    {
        "id": "A02",
        "category": "A",
        "chapter": "Suites reelles",
        "mode": "correction",
        "question": (
            "Soit (U_n) la suite définie par U_0 = 2 et pour tout n ∈ ℕ, "
            "U_{n+1} = \\frac{1}{2} U_n + 1. "
            "1) Montrer que la suite (U_n) est convergente. "
            "2) Calculer sa limite."
        ),
        "notes": "Standard Bac sequence exercise. Tests monotonicity + convergence proof.",
    },
    {
        "id": "A03",
        "category": "A",
        "chapter": "Integrales",
        "mode": "correction",
        "question": (
            "Calculer l'intégrale I = ∫₀¹ x·eˣ dx en utilisant "
            "une intégration par parties."
        ),
        "notes": "Classic integration by parts. Exact-match likely in corpus.",
    },
    {
        "id": "A04",
        "category": "A",
        "chapter": "Identite de Bezout",
        "mode": "correction",
        "question": (
            "Déterminer le PGCD de 1071 et 1029 par l'algorithme d'Euclide. "
            "En déduire une relation de Bézout."
        ),
        "notes": "Standard arithmétique exercise. Tests Euclid algorithm + Bézout identity.",
    },
    {
        "id": "A05",
        "category": "A",
        "chapter": "Equations differentielles",
        "mode": "correction",
        "question": (
            "Résoudre l'équation différentielle y' - 3y = 6 "
            "avec la condition initiale y(0) = 1."
        ),
        "notes": "First-order linear ODE with initial condition. Standard Bac format.",
    },

    # =========================================================================
    #  CATEGORY B — Novel chapter-based questions
    #  Purpose: Same Bac topics but problems NOT copied from the corpus.
    #  Tests whether the system can generalize from retrieved examples.
    # =========================================================================
    {
        "id": "B01",
        "category": "B",
        "chapter": "Fonction logarithme neperien",
        "mode": "correction",
        "question": (
            "Soit f(x) = ln(x² + 1) - x. "
            "1) Déterminer le domaine de définition de f. "
            "2) Calculer f'(x) et dresser le tableau de variation de f. "
            "3) Montrer que l'équation f(x) = 0 admet exactement deux solutions."
        ),
        "notes": "Novel function study with ln. Tests generalization, not copy-paste.",
    },
    {
        "id": "B02",
        "category": "B",
        "chapter": "Probabilites",
        "mode": "correction",
        "question": (
            "Une urne contient 5 boules blanches et 3 boules noires. "
            "On tire successivement 3 boules sans remise. "
            "1) Calculer la probabilité d'obtenir exactement 2 boules blanches. "
            "2) Calculer la probabilité d'obtenir au moins une boule noire."
        ),
        "notes": "Combinatorics probability, novel numbers. Tests style mimicry on new data.",
    },
    {
        "id": "B03",
        "category": "B",
        "chapter": "Fonction exponentielle",
        "mode": "correction",
        "question": (
            "Soit g(x) = (2x - 1)·e^{-x}. "
            "1) Calculer les limites de g en +∞ et en -∞. "
            "2) Étudier les variations de g. "
            "3) Déterminer l'équation de la tangente à la courbe de g au point d'abscisse 0."
        ),
        "notes": "Novel exponential function study. Tests if RAG finds similar exponential exercises.",
    },
    {
        "id": "B04",
        "category": "B",
        "chapter": "Geometrie dans lespace",
        "mode": "correction",
        "question": (
            "Dans un repère orthonormé (O, \\vec{i}, \\vec{j}, \\vec{k}), on considère "
            "les points A(1,0,2), B(3,1,0) et C(0,2,1). "
            "1) Déterminer une équation cartésienne du plan (ABC). "
            "2) Calculer la distance du point D(1,1,1) au plan (ABC)."
        ),
        "notes": "Novel 3D geometry. Tests retrieval of space geometry methods.",
    },
    {
        "id": "B05",
        "category": "B",
        "chapter": "Divisibilite dans Z",
        "mode": "correction",
        "question": (
            "1) Montrer que pour tout entier naturel n, le nombre n³ - n "
            "est divisible par 6. "
            "2) En déduire que n³ ≡ n [6] pour tout n ∈ ℤ."
        ),
        "notes": "Novel divisibility proof. Tests arithmetic reasoning, not in corpus verbatim.",
    },

    # =========================================================================
    #  CATEGORY C — Student-style informal questions
    #  Purpose: How a real Tunisian student would actually type a question.
    #  Informal French, incomplete phrasing, possibly vague.
    #  Tests robustness and pedagogical quality (coaching mode).
    # =========================================================================
    {
        "id": "C01",
        "category": "C",
        "chapter": "Continuite et limites",
        "mode": "coaching",
        "question": (
            "Je comprends pas comment on étudie la continuité d'une fonction "
            "en un point. C'est quoi la méthode ? Donne moi un exemple simple svp."
        ),
        "notes": "Informal student question. Tests pedagogical quality + coaching mode.",
    },
    {
        "id": "C02",
        "category": "C",
        "chapter": "Derivabilite",
        "mode": "coaching",
        "question": (
            "C'est quoi la différence entre dérivable et continue ? "
            "Est-ce qu'une fonction peut être continue mais pas dérivable ?"
        ),
        "notes": "Conceptual question. Tests whether system explains well vs. just solves.",
    },
    {
        "id": "C03",
        "category": "C",
        "chapter": "Primitives",
        "mode": "coaching",
        "question": (
            "Comment on trouve une primitive de f(x) = cos(2x) ? "
            "Je sais jamais quand il faut diviser par le coefficient."
        ),
        "notes": "Student confusion about chain rule in integration. Tests targeted coaching.",
    },

    # =========================================================================
    #  CATEGORY D — Derja / mixed-language questions
    #  Purpose: Tunisian students often mix French and Derja (Tunisian Arabic).
    #  Tests multilingual robustness and the BGE-M3 embedding model's ability
    #  to handle code-switching.
    # =========================================================================
    {
        "id": "D01",
        "category": "D",
        "chapter": "Suites reelles",
        "mode": "coaching",
        "question": (
            "Kifech nethbet elli suite monotone et bornée convergente ? "
            "3tini el méthode bil français mathematique."
        ),
        "notes": "Full Derja. Asks how to prove monotone bounded ⟹ convergent.",
    },
    {
        "id": "D02",
        "category": "D",
        "chapter": "Nombres complexes",
        "mode": "coaching",
        "question": (
            "Ey famma haja isimha forme exponentielle des nombres complexes ? "
            "Kifech na3mlha ? Ena ma fhemtech el cours."
        ),
        "notes": "Derja asking about exponential form of complex numbers. Tests language robustness.",
    },

    # =========================================================================
    #  CATEGORY E — Out-of-scope / guardrail questions
    #  Purpose: Methods OUTSIDE the Tunisian Bac program. All three systems
    #  should refuse or explicitly flag that the method is hors programme.
    #  Tests curriculum boundary enforcement.
    # =========================================================================
    {
        "id": "E01",
        "category": "E",
        "chapter": "Hors programme",
        "mode": "correction",
        "question": (
            "Utilise la règle de L'Hôpital pour calculer "
            "la limite lim(x→0) sin(x)/x."
        ),
        "notes": "L'Hôpital's rule is NOT in Tunisian Bac program. Must refuse.",
    },
    {
        "id": "E02",
        "category": "E",
        "chapter": "Hors programme",
        "mode": "correction",
        "question": (
            "Diagonalise la matrice A = [[2,1],[0,3]] et calcule A^n."
        ),
        "notes": "Matrix diagonalization is NOT in Tunisian Bac program. Must refuse.",
    },
    {
        "id": "E03",
        "category": "E",
        "chapter": "Hors programme",
        "mode": "correction",
        "question": (
            "Utilise le développement en série de Taylor de e^x "
            "pour montrer que e est irrationnel."
        ),
        "notes": "Taylor series is NOT in Tunisian Bac program. Must refuse.",
    },
    {
        "id": "E04",
        "category": "E",
        "chapter": "Hors programme",
        "mode": "correction",
        "question": (
            "Résoudre l'intégrale de Lebesgue ∫ₐᵇ f dμ pour f mesurable."
        ),
        "notes": "Lebesgue integration is NOT in Tunisian Bac program. Must refuse.",
    },
]


# ── Helper functions ──────────────────────────────────────────────────────
def get_questions_by_category(category: str):
    """Return questions for a given category letter (A/B/C/D/E)."""
    return [q for q in EVAL_QUESTIONS if q["category"] == category]


def get_questions_by_chapter(chapter: str):
    """Return questions for a given chapter name."""
    return [q for q in EVAL_QUESTIONS if q["chapter"] == chapter]


def summary():
    """Print a summary of the question bank."""
    from collections import Counter
    cats = Counter(q["category"] for q in EVAL_QUESTIONS)
    modes = Counter(q["mode"] for q in EVAL_QUESTIONS)
    chapters = Counter(q["chapter"] for q in EVAL_QUESTIONS)

    print(f"Total questions: {len(EVAL_QUESTIONS)}")
    print(f"\nBy category:")
    labels = {
        "A": "Direct Bac-style",
        "B": "Novel chapter-based",
        "C": "Student informal",
        "D": "Derja / mixed",
        "E": "Out-of-scope guardrail",
    }
    for cat in "ABCDE":
        print(f"  {cat} ({labels[cat]}): {cats.get(cat, 0)}")
    print(f"\nBy mode:")
    for m, c in modes.most_common():
        print(f"  {m}: {c}")
    print(f"\nBy chapter:")
    for ch, c in chapters.most_common():
        print(f"  {ch}: {c}")


if __name__ == "__main__":
    summary()
    print("\n" + "=" * 60)
    for q in EVAL_QUESTIONS:
        print(f"\n[{q['id']}] ({q['category']}) {q['chapter']} [{q['mode']}]")
        print(f"  Q: {q['question']}")
        print(f"  Notes: {q['notes']}")
