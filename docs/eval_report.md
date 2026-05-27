# FabYield Insight — Evaluation Report

## Evaluation Dataset

**35 hand-crafted semiconductor engineering questions** across five question types
and three difficulty levels.

| Question Type | Count | Easy | Medium | Hard |
|--------------|-------|------|--------|------|
| concept_qa | 15 | 8 | 4 | 3 |
| sample_analysis | 8 | 2 | 4 | 2 |
| cohort_analysis | 5 | 1 | 2 | 2 |
| report_generation | 4 | 1 | 2 | 1 |
| unknown | 2 | 2 | 0 | 0 |
| **Total** | **35** | **14** | **12** | **9** |

## Evaluation Metrics

### 1. Question Routing Accuracy

**Definition**: Percentage of questions routed to the correct `question_type`.

**Measurement**: Compare `route_question()` output against `expected_question_type`
in the eval dataset.

**Target**: >90%

**Current**: Evaluated against dataset ground truth. Live routing accuracy
requires Ollama running with DeepSeek-R1 (35 LLM calls).

```
Expected distribution:
  concept_qa:        15 (43%)
  sample_analysis:    8 (23%)
  cohort_analysis:    5 (14%)
  report_generation:  4 (11%)
  unknown:            2 ( 6%)
  other:              1 ( 3%)
```

### 2. Sample Analysis Success Rate

**Definition**: Percentage of `sample_analysis` requests that produce a valid
`SampleAnalysisResult` with non-empty conclusion and feature list.

**Measurement**: Execute `analyze_sample()` for all sample_analysis questions.
Count successes (valid structured output) vs failures (exceptions, empty output).

**Target**: >85%

**Current**: 8/8 sample_analysis questions have well-formed expected outputs
in evaluation dataset. Live success rate depends on data availability.

### 3. SOP Source Hit Rate

**Definition**: Percentage of queries where FTS5 retrieval returns at least one
relevant SOP chunk (content from the correct SOP document).

**Measurement**: For each `need_sop=true` question, run `retriever.retrieve()`.
Check if any returned chunk comes from the expected SOP document.

**Target**: >80%

**Current**: 35/35 questions have `need_sop` field specified in the eval dataset.
28 questions require SOP retrieval (need_sop=true). All have corresponding
SOP content available in `docs/sop/`.

### 4. Unsupported Claim Rate

**Definition**: Percentage of generated answers that incorrectly claim to know
the physical identity of an anonymized SECOM feature.

**Measurement**: Run `_claims_sensor_identity()` on each generated answer.
Count matches against total answers.

**Target**: <5% (ideally 0%)

**Detection patterns**:
- "Sensor_N is the [physical quantity] sensor"
- "Sensor_N measures [physical quantity]"
- "Sensor_N corresponds to [equipment type]"

**Current**: Guard rules correctly detect these patterns in test cases.
Live measurement requires full pipeline execution.

### 5. Refusal Correctness

**Definition**: For out-of-domain questions (expected `unknown`), the system
should state its limitations rather than fabricate an answer.

**Measurement**: Count how many `unknown`-type questions receive a refusal
or limitation statement vs a fabricated answer.

**Refusal markers**:
- "cannot answer", "not able to"
- "insufficient information", "beyond my knowledge"
- "outside the scope", "not covered"
- "please provide more", "not enough context"

**Target**: 100% (all out-of-domain questions should be refused)

**Current**: 2/2 unknown-type questions in the eval dataset (Q031 "hello",
Q032 "What is the Co-Authored-By field used for?").

## Difficulty Distribution

| Difficulty | Count | Description |
|-----------|-------|-------------|
| Easy | 14 | Direct queries with clear intent and no ambiguity |
| Medium | 13 | Requires cross-referencing or multi-step reasoning |
| Hard | 8 | Domain-specific knowledge, indirect intent, or multi-sample |

## Running Evaluation

### Offline (fast, no LLM required)
```bash
python src/eval/workflow_eval.py
```
Prints aggregate metrics based on dataset ground truth.

### Live (requires Ollama + DeepSeek-R1)
```bash
python -c "
from src.eval.workflow_eval import run_full_evaluation, print_eval_report
result = run_full_evaluation(live_router=True)
print_eval_report(result)
"
```

## Limitations of Current Evaluation

1. **No live answer quality metrics yet**: `unsupported_claim_rate` and
   `refusal_correctness` require full pipeline execution with LLM generation.
   These are measured offline via heuristics until the pipeline is integrated.

2. **SOP coverage is limited**: Only 4 simulated SOP documents. Real deployment
   would need domain-specific evaluation sets.

3. **No human baseline**: "Relevance" for SOP retrieval is currently binary
   (found/not found). A human-annotated relevance scale (0-3) would enable
   NDCG evaluation.
