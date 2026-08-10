# 06 — Confidence, Evidence & Source Reliability

## 1. Why this is the differentiating layer

Any competent team can build transcript → embeddings → chatbot in a fortnight. What cannot be
copied quickly is a corpus where **every assertion carries a defensible confidence score with
a traceable evidentiary basis.**

The lash industry has an unusually high folklore-to-fact ratio: confidently-stated,
widely-repeated, entirely unevidenced claims coexisting with real chemistry and real
dermatology. A system that cannot tell them apart will launder folklore into
authoritative-sounding prose — which is worse than not building it, because professionals
will act on it.

---

## 2. Evidence tiers

Every claim is assigned exactly one tier. This is the strongest single input to confidence.

| Tier | Name | Weight | Examples |
| --- | --- | --- | --- |
| T1 | Peer-reviewed research | 1.00 | Dermatology/ophthalmology literature, materials science |
| T2 | Regulatory / standards body | 0.92 | Safety data sheets, board regulation, ISO |
| T3 | Manufacturer technical specification | 0.85 | Adhesive TDS, fibre spec sheets |
| T4 | Controlled practitioner testing | 0.75 | Documented side-by-side test, stated methodology, n reported |
| T5 | Structured practitioner experience | 0.60 | "Across ~2,000 clients over 6 years I consistently see…" |
| T6 | Expert assertion | 0.50 | Credentialed educator states it without evidence |
| T7 | Anecdote | 0.30 | "One client had this happen" |
| T8 | Hearsay / repetition | 0.15 | "I heard that…", "everyone says…" |
| T9 | Marketing claim | 0.10 | Brand-sponsored assertion about own product |

**Tier assignment is done at S2 by the extractor**, from `evidence_offered`, `sample_basis`,
`is_reported_from_other` and `commercial_context`. It is not a judgement about the person —
a world-class artist making an unevidenced assertion is T6, and that is correct.

---

## 3. Source reliability

```
reliability(source) = 0.40 · creator_domain_expertise[domain]
                    + 0.20 · creator_track_record
                    + 0.15 · transcript_quality
                    + 0.15 · format_factor
                    + 0.10 · citation_behaviour
                    − commercial_penalty
```

| Component | Definition | Range |
| --- | --- | --- |
| `creator_domain_expertise[domain]` | Per-domain, not global. Credentials + years + peer recognition **in that domain** | 0–1 |
| `creator_track_record` | Historical agreement with high-tier evidence; corrections issued; debunk rate | 0–1 |
| `transcript_quality` | verbatim 1.0 / good 0.85 / fair 0.6 / poor 0.35 | 0–1 |
| `format_factor` | lecture 0.9, interview 0.8, panel 0.85, monologue 0.75, demo 0.9, IG short 0.55 | 0–1 |
| `citation_behaviour` | Does the creator cite sources and distinguish opinion from fact? | 0–1 |
| `commercial_penalty` | own_product 0.20, sponsored 0.12, affiliate 0.08, organic 0 | 0–0.20 |

**Per-domain expertise is non-negotiable.** The failure it prevents is specific and common:
a technically brilliant artist's business advice inheriting their technical authority. In a
knowledge base spanning chemistry, physiology, technique, psychology and finance, a single
reliability number is actively harmful.

`creator_track_record` is bootstrapped at 0.5 and updated as the corpus grows: when a
creator's claims are repeatedly corroborated by T1–T3 evidence, their score rises; when they
are on the losing side of resolved contradictions, it falls. This makes reliability
**earned from the corpus** rather than assigned by reputation.

---

## 4. Card confidence formula

```
raw = w_E · evidence_strength
    + w_S · source_quality
    + w_C · consensus
    + w_R · corroboration
    + w_T · recency
    + w_P · specificity

confidence = clamp(raw − penalties, 0, 1)
```

**Default weights** (`conf@1.2`, tuned against a human-scored gold set):

| Component | Weight |
| --- | --- |
| `evidence_strength` | 0.28 |
| `source_quality` | 0.18 |
| `consensus` | 0.20 |
| `corroboration` | 0.16 |
| `recency` | 0.10 |
| `specificity` | 0.08 |

### 4.1 Components

**Evidence strength** — top-heavy, so a single T1 source is not diluted by 40 T6 assertions:

```
evidence_strength = 0.6 · max(tier_weight) + 0.4 · weighted_mean(tier_weight, by claim count)
```

**Source quality** — reliability-weighted mean across contributing sources.

**Consensus** — agreement among claims, weighted by tier and reliability:

```
consensus = (W_support − W_contradict) / (W_support + W_contradict), mapped to [0,1]
```

**Corroboration** — independent groups, not raw source count (see doc 05 §7):

```
corroboration = 1 − exp(−independent_groups / 3)
```

**Recency** — domain-specific half-life, because knowledge ages at different rates:

```
recency = exp(−ln(2) · age_years / halflife[domain])
```

| Domain | Half-life | Rationale |
| --- | --- | --- |
| ANA (anatomy) | 15 y | Physiology does not change |
| HLT (health) | 8 y | Slow-moving clinical understanding |
| ADH (adhesive) | 5 y | Formulations genuinely change |
| APP, MAP (technique) | 6 y | Evolves, but fundamentals persist |
| RET (retention) | 6 y | Mixed physics and product |
| PRD (products) | 2.5 y | Product-specific, churns fast |
| STY (styling) | 2 y | Trend-driven |
| BIZ, MKT | 3 y | Platform and market dependent |
| IND (industry) | 1.5 y | Fastest-moving |

Age is measured from the **most recent supporting claim**, not the mean — a concept
continuously reaffirmed stays fresh.

**Specificity** — does the card say something precise and falsifiable?

```
specificity = 0.4 · has_parameters + 0.3 · has_conditions
            + 0.2 · has_mechanism  + 0.1 · has_implementation_steps
```

"Humidity affects retention" and "cyanoacrylate cures optimally at 45–55% RH; above 65% the
bond becomes brittle" are not equally useful. Specificity rewards the second.

### 4.2 Penalties

| Penalty | Magnitude | Trigger |
| --- | --- | --- |
| Hedging | up to 0.08 | Mean `hedge_level` across supporting claims |
| Commercial bias | up to 0.10 | Share of claims from commercially-interested sources |
| Single-source | 0.15 | Only one independent group |
| Single-creator | 0.10 | All claims from one person |
| Contradiction unresolved | 0.12 | Open contradiction with balanced weight |
| ASR quality | up to 0.06 | Low transcript confidence on key claims |
| Extraction uncertainty | up to 0.05 | Low model certainty at S2 |

### 4.3 Bands

| Band | Range | Meaning | AI permission |
| --- | --- | --- | --- |
| `very_high` | 0.85–1.00 | Well-established, multi-source, high tier | Assert directly |
| `high` | 0.70–0.84 | Solid consensus | Assert with soft qualifier |
| `moderate` | 0.55–0.69 | Reasonable support, some uncertainty | Assert with explicit qualifier + citation |
| `low` | 0.35–0.54 | Weak or thin | Present as one view; citation required |
| `very_low` | 0.00–0.34 | Anecdotal or contested | Do not assert; retrievable for research only |

---

## 5. Worked example

`kc_ADH_humidity-cure-window`, 47 claims:

| Input | Value |
| --- | --- |
| Tiers | 4×T3 (0.85), 7×T4 (0.75), 29×T6 (0.50), 7×T7 (0.30) |
| Independent groups | 9 |
| Distinct creators | 22 |
| Supporting / contradicting | 41 / 6 |
| Mean source reliability | 0.81 |
| Most recent claim | 2026-05-11 (0.25 y, ADH half-life 5 y) |
| Parameters, conditions, mechanism, steps | all present |
| Mean hedge level | 0.14 |
| Commercial share | 0.11 |

```
evidence_strength = 0.6(0.85) + 0.4(0.548)          = 0.729
source_quality                                       = 0.810
consensus         = (41·0.66 − 6·0.55)/(41·0.66 + 6·0.55) → 0.780
corroboration     = 1 − e^(−9/3)                     = 0.950
recency           = e^(−0.693·0.25/5)                = 0.966
specificity       = 0.4+0.3+0.2+0.1                  = 1.000

raw = 0.28(0.729) + 0.18(0.810) + 0.20(0.780)
    + 0.16(0.950) + 0.10(0.966) + 0.08(1.000)
    = 0.2041 + 0.1458 + 0.1560 + 0.1520 + 0.0966 + 0.0800
    = 0.8345

penalties = hedging 0.011 + commercial 0.011         = 0.022

confidence = 0.812  →  band: high
```

Note the shape of the result: strong corroboration and specificity carry it, while the
mid-tier evidence base (mostly T6 expert assertion) caps it below `very_high`. That is
exactly the right answer for this claim — it is well-agreed and practically reliable, but
the industry has not actually measured it rigorously, and the score should say so.

---

## 6. Confidence propagation through the graph

Traversed conclusions are less certain than their weakest link:

```
path_confidence = ∏(edge.confidence × node.confidence) over the path
```

A three-hop chain of 0.85-confidence steps yields ~0.44 — correctly `low`. This is why
diagnostic traversal prunes at cumulative 0.05 and why the AI must present long causal
chains as hypotheses rather than conclusions.

**Multiple independent paths to the same conclusion combine noisy-OR:**

```
combined = 1 − ∏(1 − path_confidence_i)
```

Two independent 0.44 paths give 0.69. That is the correct behaviour: converging weak
evidence is genuinely stronger than either strand, and this is how the diagnostic assistant
builds a defensible conclusion from several partial signals.

---

## 7. Risk-tier gating

**Risk tier overrides confidence.** High confidence never authorises medical advice.

| Tier | Human review | Citation | Assertion permitted | Extra |
| --- | --- | --- | --- | --- |
| 0 informational | No | No | Yes | — |
| 1 operational | No | No | Yes | — |
| 2 client safety | Sampled | **Required** | Only if conf ≥ 0.70 | No unqualified imperatives |
| 3 medical adjacent | **Mandatory** | **Required** | Never diagnostic | Must include referral language |
| 4 regulatory | **Mandatory** | **Required** | Jurisdiction-scoped only | Disclaimer mandatory; "verify locally" |

Enforced in three independent places, because a single point of enforcement will eventually
be bypassed by a new feature:

1. **Retrieval** — tier-3/4 cards carry mandatory handling metadata in their payload
2. **Synthesis** — the prompt assembler injects required framing before generation
3. **Output validation** — a post-generation check rejects diagnostic phrasing on tier-3
   content and blocks the response

---

## 8. Calibration

A confidence score nobody has validated is decoration. The system measures its own calibration:

- **Gold set:** 300 cards independently scored by 3 domain experts on a 5-point scale.
- **Metric:** Spearman correlation between computed confidence and expert consensus.
  Target ρ ≥ 0.75. Weights are re-fitted when it drops below 0.65.
- **Reliability diagrams** per band: of cards scored `high`, what fraction do experts endorse?
  A well-calibrated `high` band should be endorsed ~75–85% of the time.
- **Adversarial set:** 50 deliberately-planted folklore claims. Requirement: none score above
  `moderate`. This is the sharpest test of the whole system, and it should be run on every
  weight change.
- **Drift monitoring:** mean confidence by domain over time. A sudden rise usually means
  echo-chamber inflation, not improving knowledge — and should be investigated as a bug.
