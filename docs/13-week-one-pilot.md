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

Ten random transcripts will give you a misleading answer. The sample must be **stratified**,
and it must be content **you already know cold** — not because you need to check whether the
educators are right, but because you need to spot a mangled extraction in seconds rather than
re-deriving the truth for every claim.

> **What this measures.** The pilot tests **extraction fidelity, not content accuracy.** A
> curated corpus of industry-leading educators does not reduce the need for this audit — it
> changes what you are checking. If the manual says *"for oily clients, drop to 0.05"* and
> the pipeline records *"drop to 0.05"*, the content was perfect and the extraction still
> produced dangerous advice. The claim is true; the machine broke it.

| # | Pick a transcript that is… | What it stress-tests |
| --- | --- | --- |
| 1–2 | The **education manual** (or a chapter of it) | Best case: written, edited, structured. If extraction fails here, stop immediately |
| 3–4 | Instagram/TikTok short-form | Worst case: no context, fast speech, jargon, poor ASR |
| 5–7 | **Multi-speaker podcast that reaches a conclusion** | Deliberation handling — speaker attribution, initial vs revised positions, consensus vs dissent |
| 8–9 | **Numbers-heavy** (humidity, diameters, curls, timings) | Parametric extraction — the feature the whole product rests on |
| 10 | A discussion the panel **could not settle** | Does it preserve the open question instead of manufacturing a conclusion? |

**Transcripts 5–7 matter most for your corpus.** A panel that debates and converges carries
more structure than any monologue, and it is where the pipeline has the most to get wrong:
attributing a position to the wrong speaker, missing that someone changed their mind, or —
worst — recording a five-person consensus as five independent confirmations. See
[`extract/deliberation.py`](../src/lashos_ke/extract/deliberation.py) for how that is counted.

Transcript 10 is the sleeper. An open question that leading practitioners could not resolve on
air is, by definition, a real research gap — and those are among the most commercially
valuable items the corpus can produce.

### A note on an elite-only corpus

Curating for industry leaders is the right call for content quality. It has one specific
side effect worth planning for: **leaders are the roots of lineages.** When 200 techs repeat
something, the leading educator is usually where it originated. Being the best source does not
make you an independent one.

This is not a reason to doubt your selections. It is a reason to fill in `independence_group`
carefully in Step 2 — otherwise the corroboration maths will read a single influential voice
as broad consensus.

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

**Install** — needs Python 3.11+ and nothing else:

```bash
git clone https://github.com/Callafrantz/Lash-vault-.git
cd Lash-vault-
pip install -e .          # gives you the `lke` command
pip install anthropic     # the model SDK
```

**Scaffold the manifest** from whatever is in `data/raw/`:

```bash
lke pilot init
```

Fill in `data/pilot/sources.yaml` (Step 2), then **check segmentation before spending
anything** — a dry run makes no model calls and needs no key:

```bash
lke pilot run --dry-run
```

```
[episode-04.vtt]
  312 cues → 47 chunks (8214 words) · 29 salient (18 gated out)
    [GATED] #0  sal=0.05   promo         210w  Welcome back, and a huge thank you to our sponsor...
    [send ] #1  sal=0.64   explanation   288w  So the biggest thing nobody talks about is your room...
```

Read that output. If technical content is showing as `GATED`, or a sponsor read is
merged into a real chunk, fix segmentation *before* paying for extraction — a recall
problem created in S1 looks exactly like an extraction problem in the final score.

**Then extract:**

```bash
export ANTHROPIC_API_KEY=sk-ant-...       # or: ant auth login
lke pilot run --limit 10
```

Writes `data/pilot/claims.jsonl` (machine-readable) and `data/pilot/audit.md` (your
reading sheet), and prints a summary including token spend and approximate cost.

**Useful flags:** `--effort medium` (cheaper, still strong), `--min-salience 0.2`
(send more chunks if recall looks low), `--limit N`.

Expect roughly 60 claims per hour of content — 10 transcripts of ~45 minutes should
yield **400–500 claims**.

> **What a model key is.** It's a password that lets this code talk to the model —
> a long string starting `sk-ant-`. Create one at
> [console.anthropic.com](https://console.anthropic.com) → API keys, and put it in
> your shell as `ANTHROPIC_API_KEY`. It is billed per use, it is not a subscription,
> and it is separate from any Claude app subscription. Treat it like a password:
> never commit it, never paste it into a document. The pilot's 10 transcripts cost
> a few dollars, and the run prints its own spend at the end.

### Start with ONE transcript

Do not run all ten first. Point it at a single transcript, read those ~40 claims, and
you will know within half an hour whether extraction is fundamentally sound. If it is
broken, you have saved yourself the other nine and the six hours of reading.

```bash
lke pilot run --limit 1
```

Scale to ten only once the first one looks right.

## Step 4 — Read every claim (the actual work)

Open `data/pilot/audit.md` in any editor. Every claim shows the verbatim quote, its timestamp, the
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
lke pilot score
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
