# Claim-support checker comparison

Pairs: 348 labelled (223 train / 125 test), from 75 live pipeline runs. Gold labels: Gemini as a strict judge (agreement with an LLM judge, not a lawyer).
Support rate in gold: 65%. Unknown-label claims (e.g. a section number written as `[S45]`): 0/388 (0.0% of all claims).

| Checker (test split) | Precision | Recall | F1 | Accuracy | Accepted |
|---|---|---|---|---|---|
| lexical | 0.72 | 0.77 | 0.74 | 0.69 | 78/125 |
| nli (threshold 0.05) | 0.78 | 0.64 | 0.71 | 0.69 | 60/125 |
| LLM judge `groq:openai/gpt-oss-20b` (125/125 judged) | 0.93 | 0.70 | 0.80 | 0.79 | 55/125 |
