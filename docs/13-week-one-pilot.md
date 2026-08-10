# 13 — Week One Pilot: Does Claim Extraction Actually Work?

## The question

> Can claims be pulled from real lash transcripts with **verbatim fidelity** and **correct
> epistemic annotation**?

Everything in `docs/00`–`12` assumes the answer is yes. If it is no, the architecture doesn't
need adjusting — it needs rethinking. That is why this runs before anything else gets built.

**The deliverable of this week is not code. It is a number and a decision.**

---

## What you do vs what the code does

| Step | Who | Why |
| --- | --- | --- |
| Select 10 transcripts | **You** | Requires knowing which content contains contested claims |
| Score creators | **You** | Requires knowing who is actually credible |
| Run S0→S2 | Code | `lke pilot run` |
| Read every claim | **You** | The whole point — nobody else can judge fidelity |
| Compute the verdict | Code | `lke pilot score` |

The parts that need you are the parts that need lash expertise. Budget **6–8 hours of your
own reading time.** That is the real cost of this week, and it is unavoidable — an automated
proxy for this judgement is exactly the thing you don't yet have.

---

## Step 1 — Choose the 10 transcripts (do not skip this)

Ten random transcripts will give you a misleading answer. The sample must be **stratified and
adversarial**, and it must be content **you already know the truth about** — you cannot audit
extraction quality on material where you can't tell right from wrong.

| # | Pick a transcript that is… | What it stress-tests |
| --- | --- | --- |
| 1–2 | Clean, structured (course module, lecture) | Best case. If it fails here, stop. |
| 3–4 | Instagram/TikTok short-form | Worst case: no context, fast speech, jargon, poor ASR |
| 5–6 | Multi-speaker podcast or panel | Speaker attribution and cross-talk |
| 7–8 | **Numbers-heavy** (humidity, diameters, curls, timings) | Parametric extraction — the feature the whole product rests on |
| 9 | Contains a claim you **know is contested** (adhesive refrigeration, patch testing, the 24–48h water rule) | Does it capture hedging and the disputed position? |
| 10 | Contains a claim you **know is wrong** but is confidently stated | Does it record it as a claim without laundering it into fact? |

Transcripts 9 and 10 matter most. Anyone can extract sentences from a clean lecture. The
system's actual promise is telling confident-and-wrong apart from confident-and-right, and
these two transcripts are where that gets tested.

Put them in `data/raw/`. VTT, SRT, JSON, or plain text all work.

---

## Step 2 — Register the creators

For each creator in your 10, fill in `data/pilot/creators.yaml`:

```yaml
- id: crt_jane-doe-lashes
  display_name: Jane Doe
  years_experience: 11
  domain_expertise:      # 0-1, PER DOMAIN — this is the point
    ADH: 0.85
    RET: 0.90
    BIZ: 0.40
  commercial_interests:
    - { entity: ent_brand_xyz, nature: owner }
  independence_group: ig_russian-volume-lineage   # who trained whom
```

`independence_group` is the field to think hardest about. If two of your ten creators trained
under the same person, they are **one** independent voice, and the pilot should show that.

---

## Step 3 — Run the pipeline

```bash
uv sync
export LKE_MODEL_API_KEY=...          # frontier model for S2
lke pilot run --input data/raw --limit 10
```

Writes `data/pilot/claims.jsonl` plus a human-readable audit sheet at
`data/pilot/audit.md`.

Expect roughly 60 claims per hour of content — 10 transcripts of ~45 minutes each should
yield **400–500 claims**.

---

## Step 4 — Read every claim (the actual work)

Open `data/pilot/audit.md`. Every claim shows the verbatim quote, its timestamp, the
normalised statement, and the annotations. For each one, mark a verdict:

| Verdict | Meaning |
| --- | --- |
| `correct` | Faithfully captures a real assertion |
| `type_wrong` | Real claim, wrong `claim_type` |
| `tier_wrong` | Real claim, wrong `evidence_tier` (anecdote scored as expert assertion, etc.) |
| `scope_wrong` | Conditional claim recorded as universal, or vice versa — **the dangerous one** |
| `not_a_claim` | Conversational filler promoted to knowledge |
| `fabricated` | Quote does not appear in the transcript — **a hard stop** |

Then, per transcript, note **how many real claims were missed**. Recall matters as much as
precision, and only a human reading the source can measure it.

`scope_wrong` deserves attention while you read. "In summer I use a faster glue" recorded as
"use a faster glue" is how a knowledge base starts giving confidently wrong advice — it is
the failure most likely to survive into production unnoticed.

---

## Step 5 — Get the verdict

```bash
lke pilot score data/pilot/audit.md
```

### Gates

| Metric | Gate | If it fails |
| --- | --- | --- |
| Fabricated quotes | **0** | **Hard stop.** Provenance is the foundation; investigate before anything else |
| Verbatim validation failures | ≤ 2% | Tighten the prompt's quoting instruction |
| Extraction precision (`correct` + `type_wrong`) | ≥ 90% | Prompt work |
| Claim-type accuracy | ≥ 85% | Prompt work; may need few-shot examples |
| Evidence-tier accuracy | ≥ 80% | Tier rubric needs sharpening |
| Scope accuracy | ≥ 90% | Prompt work — prioritise this one |
| Recall (missed claims) | ≥ 85% | Segmentation or salience gating too aggressive |
| Cost per transcript | ≤ 1.3× budget | Tune salience gating |

### Reading the result

- **All gates pass** → the architecture holds. Proceed to Phase 1 in `docs/12` and scale to 50.
- **Precision/type/tier fail, no fabrication** → normal. This is prompt engineering, 2–3
  iterations. The architecture is fine.
- **Fabrication > 0** → stop and diagnose. Either the model is inventing quotes (change the
  approach) or the transcript text is being mutated between S1 and S2 (a bug — more likely).
- **Recall < 70%** → the problem is upstream in segmentation, not extraction.
- **Scope accuracy < 80%** → the most serious non-fabrication failure. Lash knowledge is
  overwhelmingly conditional; a system that flattens conditions produces dangerous advice.

---

## Step 6 — Write down what you learned

Whatever the outcome, record it in `data/pilot/findings.md`:

- Which claim types were hardest to extract
- Which creators produced the noisiest transcripts
- Concepts you saw repeated across transcripts (early signal on the concept registry)
- Any claim that made you think "the taxonomy has no home for this"

That last one is the most valuable output of the week after the verdict itself. The taxonomy
will be wrong on first contact with real content, and this is your cheapest chance to find out
where.

---

## What this week does NOT include

Deliberately out of scope, so the week stays focused on the one question:

- No concept resolution, deduplication, or cards (S4–S6)
- No graph, no embeddings, no vault
- No API, no AI features

If claim extraction works, all of that follows mechanically. If it doesn't, none of it matters.

---

## Time budget

| Activity | Hours |
| --- | --- |
| Selecting transcripts + scoring creators | 1–2 |
| Running the pipeline | 0.5 |
| **Reading 400–500 claims** | **6–8** |
| Scoring and writing findings | 1 |
| Prompt iteration if gates fail | 2–4 per round |

Roughly **two focused days.** Against the alternative — discovering the foundation is unsound
after building nine features on it — that is the cheapest insurance available.
