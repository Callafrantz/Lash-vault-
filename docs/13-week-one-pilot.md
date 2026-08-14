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
| Run S0→S2 | Code | `pilot run` |
| Read every claim | **You** | The whole point — nobody else can judge fidelity |
| Compute the verdict | Code | `pilot score` |

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

python3 --version                        # must be 3.11 or higher
python3 -m pip install -e .          # ~20 packages, all the pilot needs
```

**Use `python3 -m pip`, not bare `pip`.** On macOS `pip` is usually not on PATH, and
neither is the `lke` command an editable install creates. Every command below therefore
uses the module form, which always works:

```bash
python3 -m lashos_ke.cli.main pilot --help
```

If `lke` happens to work on your machine, it is the same thing and shorter.

**Scaffold the manifest** from whatever is in `data/raw/`:

```bash
python3 -m lashos_ke.cli.main pilot init
```

Fill in `data/pilot/sources.yaml` (Step 2), then **check segmentation before spending
anything** — a dry run makes no model calls and needs no key:

```bash
python3 -m lashos_ke.cli.main pilot run --dry-run
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
python3 -m lashos_ke.cli.main pilot run --limit 10
```

Writes `data/pilot/claims.jsonl` (machine-readable) and `data/pilot/audit.md` (your
reading sheet), and prints a summary including token spend and approximate cost.

**Extraction is slow, and that is normal.** Each chunk is one model call with thinking
on — 30 to 90 seconds. A 45-minute transcript is ~18 chunks, so **budget 10–25 minutes
per transcript**. You will see a line per chunk as it completes:

```
Using API key from ANTHROPIC_API_KEY.

[episode-04.vtt]
  312 cues → 47 chunks (8214 words) · 29 salient (18 gated out)
    #1    288w  ·   6 claims     41s  $0.019   (1/29 · $0.02 · ~19 min left)
    #3    264w  ·   4 claims     37s  $0.017   (2/29 · $0.04 · ~17 min left)
```

If those lines are appearing, it is working — do not kill it. **Ctrl-C is safe if you
do need to stop**: everything extracted up to that point is still written to
`claims.jsonl` and `audit.md`, and only the in-flight chunk is lost.

**Useful flags:** `--effort medium` (cheaper, still strong), `--min-salience 0.2`
(send more chunks if recall looks low), `--limit N`, `--max-spend N`.

Expect roughly 60 claims per hour of content — 10 transcripts of ~45 minutes should
yield **400–500 claims**.

> **What a model key is.** It's a password that lets this code talk to the model —
> a long string starting `sk-ant-api03-`. Create one at
> [console.anthropic.com](https://console.anthropic.com) → API keys, and put it in
> your shell as `ANTHROPIC_API_KEY`. It is billed per use, it is not a subscription,
> and it is separate from any Claude app subscription. Treat it like a password:
> never commit it, never paste it into a document or a saved terminal log. The
> pilot's 10 transcripts cost a few dollars, and the run prints its own spend at the
> end.

### The key does not survive a new Terminal window

`export` sets a variable **for one shell only**. Open a new tab, reboot, or rotate the
key, and that shell has no credential again — the single most common way this pilot
fails. Make it stick once:

```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-api03-<your-key>' >> ~/.zshrc
source ~/.zshrc
```

To check the current shell without printing the key to screen:

```bash
[ -n "$ANTHROPIC_API_KEY" ] && echo set || echo unset
```

`pilot run` checks for a credential before it parses anything, so a missing key costs
you a message rather than a run. If you use `ant auth login` instead, the stored
profile is detected and no environment variable is needed.

### What it costs

Estimated against the real prompt and 45-minute transcripts, with the salience gate
removing roughly 45% of chunks and the system prompt cached after the first call:

| Model | 1 transcript | 10 transcripts |
| --- | --- | --- |
| Opus 5 | ~$0.38 | ~$3.75 |
| Sonnet 5 | ~$0.15 | ~$1.50 |
| Haiku 4.5 | ~$0.08 | ~$0.75 |

The run reports its own spend, priced per model — including which model actually served
the request, since that is what determines the rate. An unrecognised model ID is priced
at the most expensive entry, so an unfamiliar name over-estimates rather than surprising
you.

**`--max-spend` is a hard ceiling**, defaulting to `$5.00`. It is checked *before* each
call, so a run can exceed it by at most one call's cost. When it trips, the run stops
and **still writes `claims.jsonl` and `audit.md`** for everything extracted up to that
point, naming the transcript it stopped on. A partial pilot is useful; a surprise bill
is not.

```bash
python3 -m lashos_ke.cli.main pilot run --limit 10 --max-spend 2.00
```

> **On privacy.** The Anthropic API does not train on API inputs or outputs by default.
> Your education manual and licensed course transcripts stay yours on this path — which
> matters here, because the highest-value sources in your corpus are also the ones you
> are least free to leak.

`src/lashos_ke/core/llm.py` is the only file in the codebase that talks to a model
provider. Moving to a local or free-tier model later is a contained change to that one
file — worth knowing, not worth building now.

### Start with ONE transcript

Do not run all ten first. Point it at a single transcript, read those ~40 claims, and
you will know within half an hour whether extraction is fundamentally sound. If it is
broken, you have saved yourself the other nine and the six hours of reading.

```bash
python3 -m lashos_ke.cli.main pilot run --limit 1
```

That is roughly forty cents on Opus 5 and is the run whose output is worth reading
properly. Scale to ten only once the first one looks right.

A cheaper smoke test is available if you only want to check the plumbing:

```bash
python3 -m lashos_ke.cli.main pilot run --limit 1 --model claude-haiku-4-5   # ~$0.08
```

**`--effort` does not apply to Haiku 4.5 or Sonnet 4.5** — those models reject the
parameter outright, so the run omits it and prints a note. Reasoning depth is then the
model's own default. Do not judge extraction quality on that pass; it tells you the
pipeline works, not that the architecture does.

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
python3 -m lashos_ke.cli.main pilot score
```

### Gates

| Metric | Gate | If it fails |
| --- | --- | --- |
| Fabricated quotes | **0** | **Hard stop.** Provenance is the foundation; investigate before anything else |
| Verbatim validation failures | ≤ 2% | Tighten the prompt's quoting instruction — but read the paraphrase split first |
| Extraction precision (`correct` + `type_wrong`) | ≥ 90% | Prompt work |
| Claim-type accuracy | ≥ 85% | Prompt work; may need few-shot examples |
| Evidence-tier accuracy | ≥ 80% | Tier rubric needs sharpening |
| Scope accuracy | ≥ 90% | Prompt work — prioritise this one |
| Recall (missed claims) | ≥ 85% | Segmentation or salience gating too aggressive |
| Cost per transcript | ≤ 1.3× budget | Tune salience gating |

### Paraphrase is not fabrication

A quote that cannot be found verbatim has two possible causes, and they call for opposite
responses. The validator separates them and the report shows the split:

```
  Verbatim failure rate            8.3%
  Fabricated quotes                   0
    of which paraphrase             9/10
```

- **`quote_paraphrased`** — the model reworded a span that genuinely is in the transcript
  ("if you're above sixty percent humidity" → "if you're above 60% humidity"). Provenance
  held: the claim was discarded exactly as designed. Raise `--effort`, or use a stronger
  model, and re-run. **This is not an architecture failure.**
- **`quote_not_found`** — no similar span exists. The content was invented. This is the
  failure the pilot exists to catch.

**Both are still discarded.** The verbatim guarantee does not bend for a near miss — a
"close enough" quote is a quote the speaker did not say, and attaching their name and a
timestamp to it is precisely what this system exists to prevent. The split changes the
diagnosis, never the outcome.

The classifier is deliberately conservative: it scores surface overlap, not meaning, so a
heavy reword ("when humidity exceeds 60%") scores too low and is reported as
`quote_not_found`. That bias is intentional — a false fabrication alarm costs you an
investigation, while a fabrication excused as a harmless paraphrase hides the one failure
that should stop the build. Each finding carries its similarity score, so you can open a
borderline case and judge it yourself.

### Reading the result

- **All gates pass** → the architecture holds. Proceed to Phase 1 in `docs/12` and scale to 50.
- **Precision/type/tier fail, no fabrication** → normal. This is prompt engineering, 2–3
  iterations. The architecture is fine.
- **Verbatim gate fails, mostly paraphrase** → prompt or model strength, not architecture.
  See the split above before concluding anything.
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
