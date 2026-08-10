# LashOS Knowledge Engine

> The foundational intelligence layer for LashOS — a system that converts raw lash-industry
> transcripts into structured, deduplicated, source-attributed, AI-queryable knowledge.

---

## What this is

This repository contains the architecture and implementation of the **LashOS Knowledge Engine (LKE)**:
a production-grade knowledge extraction and knowledge graph platform for the professional
eyelash extension industry.

It ingests thousands of transcripts (podcasts, YouTube, Instagram, courses, interviews, panels,
masterclasses) and outputs a **living knowledge base** that powers:

- AI Lash Educator
- AI Consultation Assistant
- AI Retention Expert
- AI Styling Assistant
- AI Product Recommendation Engine
- AI Troubleshooting Assistant
- AI Business Coach
- AI Course Generator
- AI Certification Platform

## What this is explicitly NOT

| Not this | Because |
| --- | --- |
| A note-taking system | Notes are for humans reading linearly. This is a queryable knowledge substrate for machines. |
| A transcript archive | Transcripts are raw material, not product. They live in cold storage outside the vault. |
| A basic Obsidian vault | The vault is a **rendered view**, not the source of truth. It is regenerated from the database. |
| A RAG-over-transcripts chatbot | Chunk-and-embed over raw transcripts reproduces the industry's misinformation verbatim, with no confidence, no attribution, and no contradiction handling. |

---

## The core thesis

```
Transcript  →  Chunk  →  Claim  →  Concept  →  Knowledge Card  →  Graph  →  Intelligence
             (verbatim) (atomic)  (canonical) (synthesized)     (linked)   (decisions)
```

Three decisions define this system:

**1. Claims and Cards are different objects.**
A *Claim* is one assertion by one speaker at one timestamp. Claims are immutable, never merged,
never deduplicated — the number of independent claims supporting a concept **is** its confidence
signal. A *Knowledge Card* is a canonical concept, synthesized from a set of claims. Deduplication
happens at the concept layer, never at the evidence layer.

**2. Contradiction is data, not noise.**
The lash industry runs on confidently-asserted folklore. Two educators with 100k followers each
will state opposite things about cold-storing adhesive. A system that averages them produces
garbage. LKE stores contradictions as first-class objects, tracks who is on which side, and
teaches downstream AI to *express disagreement* rather than fabricate consensus.

**3. Knowledge must be parametric, not just prose.**
"Adhesive likes humidity around 50%" is a sentence. `{parameter: relative_humidity, optimal:
[45,55], unit: "%RH", applies_to: ent_chem_cyanoacrylate}` is something a retention model can
compute with. Every card carries a typed parameter block where one exists. This is the difference
between retrieving text and making decisions.

---

## Repository map

```
docs/        Architecture — read these first, in order 00 → 12
schemas/     JSON Schema + YAML contracts for every object in the system
taxonomy/    Machine-readable master taxonomy, entity types, relation types
templates/   Obsidian markdown templates (rendered output format)
db/          PostgreSQL migrations — the system of record
src/         Python implementation (lashos_ke package)
examples/    A fully worked example: transcript → claims → card → vault note
vault/       Generated Obsidian vault (build artifact — do not hand-edit outside override blocks)
data/        Raw / interim / processed transcript storage (gitignored)
```

## Reading order

| # | Document | What it answers |
| --- | --- | --- |
| [00](docs/00-system-architecture.md) | System Architecture | How the whole thing fits together |
| [01](docs/01-master-taxonomy.md) | Master Taxonomy | How lash knowledge is organized |
| [02](docs/02-data-model.md) | Data Model | What every object is and what fields it has |
| [03](docs/03-extraction-pipeline.md) | Extraction Pipeline | Stages 0–8, transcript to vault |
| [04](docs/04-knowledge-graph.md) | Knowledge Graph | Nodes, edges, traversal, reasoning |
| [05](docs/05-deduplication.md) | Deduplication & Conflict | Merge, variant, contradict, evolve |
| [06](docs/06-confidence-and-evidence.md) | Confidence & Evidence | Scoring formulas and AI gating |
| [07](docs/07-rag-architecture.md) | RAG Architecture | Retrieval, embeddings, answer synthesis |
| [08](docs/08-obsidian-vault.md) | Obsidian Vault | Vault layout, frontmatter, Dataview |
| [09](docs/09-database-schema.md) | Database Schema | PostgreSQL tables and indexes |
| [10](docs/10-api-architecture.md) | API Architecture | Service boundaries and endpoints |
| [11](docs/11-technology-stack.md) | Technology Stack | Every choice, with rationale |
| [12](docs/12-implementation-plan.md) | Implementation Plan | Phased build, 0 → production |
| [13](docs/13-week-one-pilot.md) | **Week One Pilot** | **Start here to build. Does claim extraction actually work?** |

---

## Status

Architecture complete. Implementation scaffold in place. See
[docs/12-implementation-plan.md](docs/12-implementation-plan.md) for the build sequence.
