# Worked Example — Transcript to Knowledge Card

A single concept traced through all ten pipeline stages, so the architecture can be checked
against something concrete rather than assessed in the abstract.

---

## S0 · Raw input

```
File:     jane_doe_summer_retention.vtt
Platform: YouTube
URL:      https://youtube.com/watch?v=EXAMPLE
Creator:  Jane Doe (@janedoelashes)
Date:     2024-03-14
Duration: 57:00
```

Excerpt (verbatim ASR, 21:28–21:52):

```
00:21:28.400 --> 00:21:52.100
so like i said um the biggest thing that nobody talks about is your your room
right if you're above sixty percent humidity your glue is curing before it even
touches the lash and that's why your bonds are brittle i had a student in florida
she was losing like everything by day four and it was just her room
```

**S0 output**

```yaml
source_id: src_yt_202403_a3f9c1d2
content_hash: blake3:9f2e...           # no existing match → new source
platform: youtube
asr_confidence: 0.91
transcript_quality: good
commercial_context: sponsored           # sponsor read detected at 02:14
independence_group: ig_russian-volume-lineage
reliability_score: 0.78                 # creator 0.85 (ADH) − sponsorship penalty
```

---

## S1 · Clean & segment

Hedges retained (`like i said`, `um` removed but `just` kept), sentence boundaries repaired,
domain lexicon applied.

```yaml
chunk_id: chk_a3f9c1d2_00147
t_start: 1288.4
t_end: 1312.1
speaker_id: crt_jane-doe-lashes
segment_type: explanation
salience: 0.88                          # → passes to S2
text: >
  The biggest thing that nobody talks about is your room. If you're above sixty percent
  humidity your glue is curing before it even touches the lash, and that's why your bonds
  are brittle. I had a student in Florida — she was losing everything by day four, and it
  was just her room.
raw_text: >
  so like i said um the biggest thing that nobody talks about is your your room right
  if you're above sixty percent humidity your glue is curing before it even touches the
  lash and that's why your bonds are brittle i had a student in florida she was losing
  like everything by day four and it was just her room
```

---

## S2 · Claim extraction

One chunk yields **two** claims — a general causal assertion and a supporting anecdote. They
receive different evidence tiers, which is the entire point of splitting them.

```json
{
  "chunk_id": "chk_a3f9c1d2_00147",
  "claims": [
    {
      "verbatim_quote": "if you're above sixty percent humidity your glue is curing before it even touches the lash and that's why your bonds are brittle",
      "normalized_statement": "Relative humidity above 60% causes cyanoacrylate lash adhesive to cure prematurely, producing brittle bonds.",
      "claim_type": "causal",
      "subject": "relative_humidity",
      "predicate": "causes",
      "object": "premature_adhesive_cure",
      "polarity": "positive",
      "scope": "conditional",
      "conditions": [{"variable": "relative_humidity", "operator": ">", "value": 60, "unit": "%RH"}],
      "parameters": [{"name": "brittle_bond_threshold", "value": 60, "unit": "%RH",
                      "bound": "lower", "precision": "stated"}],
      "hedge_level": 0.05,
      "certainty_language": "assertive",
      "evidence_tier": "expert_assertion",
      "evidence_offered": "none",
      "is_first_person_experience": false,
      "is_reported_from_other": false,
      "candidate_entities": ["relative_humidity", "cyanoacrylate", "bond_brittleness"],
      "suggested_domain": "ADH",
      "risk_signal": 0,
      "extraction_certainty": 0.94
    },
    {
      "verbatim_quote": "i had a student in florida she was losing like everything by day four and it was just her room",
      "normalized_statement": "A student in a high-humidity Florida environment experienced near-total extension loss by day four, attributed to studio conditions.",
      "claim_type": "experiential",
      "scope": "personal",
      "hedge_level": 0.15,
      "certainty_language": "confident",
      "evidence_tier": "anecdote",
      "evidence_offered": "anecdote",
      "is_first_person_experience": true,
      "suggested_domain": "RET",
      "extraction_certainty": 0.91
    }
  ]
}
```

**Validators applied:** verbatim substring match ✓ · timestamps within chunk ✓ ·
unit `%RH` in vocabulary ✓ · RH value 60 within plausible range [0,100] ✓ · claim type in enum ✓

Claim IDs assigned: `clm_7d2e9f10b4a3`, `clm_c81a4b3f0d92`.

---

## S3 · Entity recognition & linking

| Mention | Resolved | Method |
| --- | --- | --- |
| "humidity" | `ent_env_relative-humidity` | gazetteer exact |
| "your glue" | `ent_chem_cyanoacrylate` | embedding 0.91 |
| "brittle bonds" | `ent_phen_bond-brittleness` | embedding 0.89 |
| "Florida" | `ent_region_us-fl` | gazetteer, attributes: `typical_climate_band: tropical` |

The Florida link matters downstream: it turns an anecdote into evidence with a *climate
context*, which the retention model can use.

---

## S4 · Concept resolution

```
query: "Relative humidity above 60% causes cyanoacrylate to cure prematurely..."

candidates:
  cpt_ADH_humidity-cure-window     score 0.89   ← existing, 46 claims
  cpt_ADH_flash-cure               score 0.74
  cpt_RET_environmental-factors    score 0.71

0.89 ≥ 0.82  →  assign to cpt_ADH_humidity-cure-window  (claim 47)
```

The second claim (the Florida anecdote) resolves to `cpt_RET_climate-retention-impact`
at 0.83 — a *different* concept, correctly separated.

---

## S5 · Deduplication & conflict

Claim 47 is checked against the concept's existing claim set. A prior claim from another
creator asserts optimal RH of *60–70%* for fast-set adhesives.

```
polarity_conflict detected → composite score penalised −0.20 → 0.81
0.80 ≤ 0.81 < 0.93 → LLM adjudication
```

Adjudication verdict:

```json
{
  "verdict": "variant",
  "certainty": 0.84,
  "contradiction_axis": "optimal humidity value",
  "context_distinction": "The 60-70% figure is stated for fast-set/low-viscosity adhesives; the 45-55% figure for standard viscosity. This is product-dependent scope, not a factual conflict.",
  "variant_relation": "applies_to"
}
```

Result: **no merge, no contradiction.** A conditional scope is added to the parameter
(`viscosity=standard`) and a sibling parameter is recorded for fast-set adhesives. This is
the resolution path that most apparent disagreements in this corpus take.

---

## S6 · Card synthesis

47 claims → ~40 selected for context (highest tier, highest reliability, viewpoint diversity)
→ card generated → **attribution validator** run.

One generated sentence — *"Most professionals recommend a dehumidifier below 55%"* — has no
supporting claim. It is **removed, not rewritten**. The card ships shorter and fully grounded.

Confidence computed at **0.812 (high)** — the worked calculation is in
[docs/06 §5](../docs/06-confidence-and-evidence.md#5-worked-example).

---

## S7 · Graph linking

```
relative_humidity  --causes[s=0.85, cond: RH>60]-->  premature_cure     (claim_derived, conf 0.88)
premature_cure     --causes[s=0.80]-->               bond_brittleness   (claim_derived, conf 0.81)
bond_brittleness   --causes[s=0.88]-->               premature_shedding (claim_derived, conf 0.86)
humidity_card      --measured_by-->                  ent_tool_hygrometer (structural, conf 1.0)
humidity_card      --applies_to-->                   ent_chem_cyanoacrylate (structural, conf 1.0)
```

Four of five edges come free from `claim_type: causal` — no separate extraction call.
Hygiene checks: no cycles, no contradictory pairs, no orphans.

---

## S8 · Embedding

| Collection | Vectors added |
| --- | --- |
| `card_summary` | 1 |
| `card_section` | 7 (definition, summary, mechanism, application, steps, mistakes, exceptions) |
| `claim` | 2 |
| `quote` | 2 |

---

## S9 · Vault export

Written to `vault/10-Knowledge/07-Adhesive-Science/Adhesive Humidity Cure Window.md`.
Rendered card: [`examples/example-card.md`](example-card.md).

---

## Downstream: the payoff

An artist asks the Troubleshooting Assistant:

> *"Outer corners shedding at day 5, client is oily, my studio reads 68%."*

The system does **not** search text. It:

1. Parses context → `{studio_rh: 68, skin_type: oily, zone: outer_corner, onset_days: 5}`
2. Reverse-traverses `premature_shedding` → 4 candidate root causes
3. Scores each by `path_confidence × context_match × card_confidence`
4. Finds `studio_rh 68` violates `optimal_relative_humidity 45–55 %RH` → **context conflict, high severity**
5. Returns ranked causes with the causal path, plus the discriminating question
   *"does the shed extension still have adhesive attached?"*
6. Cites Jane Doe at 21:31 with a playable deep link

```json
{
  "answer": "Your studio humidity is the most likely primary cause...",
  "confidence": "high",
  "citations": [{"marker": "[K1]", "card_id": "kc_ADH_humidity-cure-window",
                 "confidence": 0.812, "deep_link": "https://youtube.com/watch?v=EXAMPLE&t=1291"}],
  "caveats": [{"type": "context_conflict",
               "message": "Your studio humidity (68%) is above the 45-55% range this guidance assumes."}],
  "safety": {"risk_tier": 1, "referral_recommended": false}
}
```

None of that is possible from embedded transcript chunks. It requires the parameters to be
typed, the relations to be directional and conditional, and the confidences to be computed —
which is precisely what the preceding nine stages exist to produce.
