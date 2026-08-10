"""
Rhetorical-role classifier (Phase 4 / RQ5).

Direct label propagation was checked and ruled out: the Law-AI
semantic-segmentation dataset (50 labeled Supreme Court judgments) has ZERO
text overlap with the loaded AILA corpus (2,914 judgments) -- verified with
a strict multi-sentence substring check across all 50 files, not assumed.
So instead of matching documents, a classifier is
trained on the 50 labeled documents' sentences and applied to our corpus's
chunks -- the same train-on-one-set/apply-to-another approach the
rhetorical-role-labeling literature itself uses.

TF-IDF + multinomial Logistic Regression, not a neural model: the labeled
set is small (9,380 sentences across 7 classes, smallest class ~260
sentences), and a linear bag-of-words model is both a defensible baseline
for this task size and fast enough to run on chunk text with zero GPU cost.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

RHETORICAL_ROLES_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "rhetorical_roles"
MODEL_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "rhetorical_role_model.joblib"

# The subset of roles most useful for precedent/statute retrieval boosting
# (RQ5's actual use) -- procedural framing (lower/present court rulings) and
# narrative facts are not what a "find the applicable law/precedent" query
# is looking for.
RETRIEVAL_RELEVANT_ROLES = frozenset({"Ratio of the decision", "Precedent", "Statute"})


@dataclass
class LabeledSentence:
    text: str
    label: str
    doc_id: str


def load_labeled_sentences() -> list[LabeledSentence]:
    out: list[LabeledSentence] = []
    for f in sorted(RHETORICAL_ROLES_DIR.glob("*.txt")):
        for line in f.read_text(encoding="utf-8", errors="ignore").split("\n"):
            if "\t" not in line:
                continue
            text, label = line.rsplit("\t", 1)
            text = text.strip()
            label = label.strip()
            if text and label:
                out.append(LabeledSentence(text=text, label=label, doc_id=f.stem))
    return out


def train_and_evaluate(test_fraction: float = 0.2, seed: int = 13) -> dict:
    """
    Document-level train/test split -- splitting by sentence would leak
    stylistic tells from the same judgment (a specific judge's phrasing,
    a specific case's recurring terms) across train and test, inflating
    accuracy. Returns the honest held-out accuracy, not a training-set
    number, and saves the model fit on ALL labeled data for actual use
    (the held-out split exists only to report a trustworthy number).
    """
    import joblib
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, classification_report

    sentences = load_labeled_sentences()
    doc_ids = sorted({s.doc_id for s in sentences})
    rng = np.random.RandomState(seed)
    rng.shuffle(doc_ids)
    n_test_docs = max(1, int(len(doc_ids) * test_fraction))
    test_docs = set(doc_ids[:n_test_docs])

    train = [s for s in sentences if s.doc_id not in test_docs]
    test = [s for s in sentences if s.doc_id in test_docs]

    vectorizer = TfidfVectorizer(max_features=20000, ngram_range=(1, 2), min_df=2)
    X_train = vectorizer.fit_transform([s.text for s in train])
    y_train = [s.label for s in train]
    X_test = vectorizer.transform([s.text for s in test])
    y_test = [s.label for s in test]

    clf = LogisticRegression(max_iter=1000, class_weight="balanced", C=2.0)
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    report = {
        "held_out_accuracy": accuracy_score(y_test, y_pred),
        "n_train_sentences": len(train),
        "n_test_sentences": len(test),
        "n_test_docs": len(test_docs),
        "per_class_report": classification_report(y_test, y_pred, zero_division=0, output_dict=True),
    }

    # Refit on all labeled data for the model actually used to label our
    # corpus -- the held-out split above exists only to measure honestly,
    # not to withhold data from the deployed classifier.
    X_all = vectorizer.fit_transform([s.text for s in sentences])
    y_all = [s.label for s in sentences]
    final_clf = LogisticRegression(max_iter=1000, class_weight="balanced", C=2.0)
    final_clf.fit(X_all, y_all)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"vectorizer": vectorizer, "classifier": final_clf}, MODEL_PATH)

    return report


_model_cache: dict[str, object] = {}


def _sentence_split(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]


def predict_chunk_role(chunk_text: str) -> str:
    """
    Predicts the majority rhetorical role for a chunk by classifying each of
    its sentences and taking the mode -- a chunk is a paragraph, and a
    paragraph is rarely purely one role, but its dominant role is still
    informative for retrieval boosting.
    """
    import joblib
    from collections import Counter

    if "model" not in _model_cache:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"{MODEL_PATH} not found -- run train_and_evaluate() first")
        _model_cache["model"] = joblib.load(MODEL_PATH)

    bundle = _model_cache["model"]
    sentences = _sentence_split(chunk_text)
    if not sentences:
        return "Facts"

    X = bundle["vectorizer"].transform(sentences)
    preds = bundle["classifier"].predict(X)
    return Counter(preds).most_common(1)[0][0]
