# 01 — Master Taxonomy

## 1. Why a single tree is not enough

Every knowledge system that uses one hierarchy eventually hits the same wall: a real concept
belongs in several places at once. "Cold-storing adhesive" is simultaneously *Adhesive Science*,
*Products & Materials*, *Business Operations* (inventory), and a *contested* claim.

LKE therefore uses a **faceted taxonomy**:

- **One primary domain path** — mandatory, exactly one, hierarchical. This determines the card's
  ID prefix and its folder in the vault. It gives every card a single unambiguous home.
- **Secondary domain paths** — optional, many. Cross-cutting membership.
- **Orthogonal facets** — mandatory, independent axes that describe *what kind* of knowledge
  it is rather than *what it is about*.

This gives polyhierarchy without the ambiguity of a true graph taxonomy, and it keeps the
vault navigable by humans while remaining precisely filterable by machines.

```
Card classification = primary_path (1)
                    + secondary_paths (0..n)
                    + facets (8 required axes)
                    + free tags (0..n)
```

---

## 2. Master domain tree

17 top-level domains. Each has a stable 3-letter code used in card IDs (`kc_ADH_...`), which
means a domain can be renamed for humans without breaking a single identifier.

### 01 · ANA — Anatomy & Biology

| Subcategory | Scope |
| --- | --- |
| Eye Anatomy | Orbital structure, eyelid layers, ciliary margin, meibomian glands, tear film, conjunctiva, cornea, canthi |
| Natural Lash Anatomy | Follicle, bulb, shaft, cuticle, cortex, medulla, lash rows (1–5), density, natural curl, growth vector |
| Hair Science | Keratin structure, disulfide bonding, porosity, tensile strength, elasticity, moisture dynamics |
| Growth Cycles | Anagen / catagen / telogen / exogen, cycle duration, asynchronous shedding, natural shed rate, seasonal variation |
| Eye Shape Morphology | Almond, round, hooded, monolid, downturned, upturned, deep-set, protruding, close-set, wide-set, asymmetric |
| Lid & Crease Architecture | Crease depth, lid space, hood overhang, ptosis, lid laxity |
| Facial Proportion | Brow position, orbital bone, eye-to-brow distance, facial thirds, symmetry axes |
| Ocular Physiology | Blink rate and force, tear chemistry, ocular surface moisture, sensitivity thresholds |
| Population Variation | Ethnic and genetic lash/lid variation, age-related change, hormonal effects (pregnancy, postpartum, menopause), medication effects |

### 02 · HLT — Lash Health & Safety

| Subcategory | Scope |
| --- | --- |
| Damage Mechanisms | Mechanical stress, weight load, torque, traction alopecia, follicle trauma |
| Breakage & Weakening | Shaft fracture, thinning, stunted regrowth |
| Allergic Reactions | Type I vs Type IV hypersensitivity, sensitization thresholds, cyanoacrylate allergy, carbon black, latex, nickel |
| Irritant vs Allergic Differentiation | Symptom timing, presentation, escalation — the single most misdiagnosed topic in the industry |
| Chemical Injury | Corneal abrasion, chemical burn, remover contact injury |
| Contraindications | Blepharitis, conjunctivitis, hordeolum/chalazion, dry eye disease, trichotillomania, recent ocular surgery, LASIK windows, chemotherapy, alopecia areata, glaucoma medication (prostaglandin effects) |
| Infection & Microbiology | Bacterial load, Demodex, biofilm, staphylococcal risk, cross-contamination |
| Formaldehyde & Off-gassing | Cyanoacrylate degradation products, exposure limits |
| Artist Occupational Health | Sensitization risk, ventilation, PPE, cumulative exposure, career-ending allergy — chronically under-covered |
| Sanitation & Sterilization | Tool disinfection, autoclave, single-use policy, station hygiene, linens |
| Patch Testing | Protocols, predictive value, false negatives — *contested* |
| Medical Screening & Intake | Health history, red flags, medication review |
| Incident Response | Adverse-reaction triage, documentation, referral thresholds, insurance notification |
| Regulatory & Compliance | Licensing by jurisdiction, board rules, insurance requirements, product regulation (EU/US/UK/AU/ZA) |

### 03 · ASM — Natural Lash Assessment

| Subcategory | Scope |
| --- | --- |
| Lash Trait Analysis | Density, length, diameter, natural curl, health grade, growth direction |
| Lash Line Survey | Row identification, gaps, cowlicks, misdirected lashes |
| Weight Load Calculation | Safe extension mass per natural lash, diameter/length ratio limits, fan weight math |
| Health Grading | Objective 1–5 lash-health scale and its criteria |
| Eligibility & Risk Scoring | Composite client suitability score, deferral criteria |
| Assessment Documentation | Photo protocol, standardized measurement, baseline record |

### 04 · STY — Styling & Design

| Subcategory | Scope |
| --- | --- |
| Style Archetypes | Classic/Natural, Wispy, Wet Set, Anime/Spike, Kim K, Doll Eye, Cat Eye, Fox Eye, Open Eye, Squirrel, Round, Manga, Angel, Textured, Coloured/Accent, Bottom lash |
| Volume Systems | Classic 1:1, Hybrid, Volume 2D–6D, Mega Volume 7D–20D, Russian volume, narrow vs wide fans, handmade vs promade |
| Style Selection Logic | Eye shape × lid type × lash trait → style suitability matrix |
| Corrective Design | Compensating for droop, asymmetry, hooding, close/wide set |
| Personalisation Factors | Profession, lifestyle, maintenance capacity, wear tolerance, age, cultural preference |
| Aesthetic Principles | Balance, proportion, negative space, gradient, texture rhythm, closed-eye vs open-eye read |
| Occasion Styling | Bridal, editorial, event, photographic considerations |
| Inclusive Styling | Male and gender-neutral design, mature clients, medical hair loss |
| Trend Cycles | Regional trend origins (KR / RU / US / UK), platform-driven trends, trend half-life |

### 05 · MAP — Lash Mapping

| Subcategory | Scope |
| --- | --- |
| Mapping Fundamentals | Zone division, notation systems, map documentation and reuse |
| Length Placement | Length curves, gradient logic, maximum safe length per zone |
| Curl Placement | Curl selection, curl mixing, curl-to-lid-space matching |
| Diameter Placement | Diameter selection by zone and lash health |
| Texture Mapping | Spike ratios, wispy patterns, staggered placement rules |
| Symmetry & Correction | Measuring asymmetry, correcting mismatched eyes and lid heights |
| Layering | Upper/lower layer strategy, depth perception, base row handling |
| Map Libraries | Reusable named maps and their intended outcomes |

### 06 · RET — Retention Science

| Subcategory | Scope |
| --- | --- |
| Retention Definition & Measurement | What retention means, % retained per week, measurement protocol, benchmarks |
| Bond Mechanics | Bond footprint, base coverage, wrap, contact area, shear vs peel failure |
| Environmental Factors | Relative humidity, temperature, dew point, altitude, airflow, seasonality |
| Client Lifestyle Factors | Sleep position, exercise, sauna, swimming, sweat, skincare routine, oils, retinol, sunscreen |
| Skin Physiology | Sebum production, skin type, sweat chemistry, pH |
| Hormonal & Medical Factors | Thyroid, pregnancy, postpartum, medications, isotretinoin, chemotherapy |
| Aftercare Protocols | First 24–48 hours, cleansing frequency, brushing, sleep protection, product avoidance |
| Cleansing Science | Surfactant chemistry, oil-free formulation, foam vs liquid, over-cleansing |
| Retention Diagnostics | Root-cause decision tree, zone-pattern interpretation, timeline interpretation |
| Shedding Interpretation | Premature vs natural shed, twin/multi-lash shed, base-attached shed reading |
| Fill Cycle Economics | Optimal fill interval, fill vs full ratio, outgrown-lash policy |

### 07 · ADH — Adhesive Science

| Subcategory | Scope |
| --- | --- |
| Cyanoacrylate Chemistry | Ethyl / methyl / butyl / octyl esters, anionic polymerization, initiation by ambient moisture |
| Cure Kinetics | Set time vs surface cure vs full polymerization (24h), cure completion criteria |
| Humidity & Temperature Response | Response curves, optimal envelopes, behaviour outside range |
| Viscosity & Dry Time | Trade-off curve, matching to artist speed and technique |
| Pigments & Additives | Carbon black, clear adhesives, low-fume formulations and their performance cost |
| Storage & Shelf Life | Unopened vs opened life, temperature, desiccant, refrigeration — *contested* |
| Bottle Handling | Burping, shaking, nozzle hygiene, glue-dot refresh interval, dispensing surface |
| Adhesive Selection Logic | Matching adhesive to environment, style, technique speed and client sensitivity |
| Curing Interventions | Nano-misting, shock curing, humidifier control — *contested* |
| Ancillary Chemistry | Primers, accelerators, boosters, bonders/superbonders, sealants and their mechanisms |
| Adhesive Troubleshooting | Stickies, poor bond, shock polymerization, blooming/white residue, stringing, fumes, irritation |
| Failure Mode Analysis | Systematic classification of adhesive failures and their signatures |
| Adhesive Testing Protocol | How to evaluate a new adhesive objectively, batch variance testing |

### 08 · APP — Application Technique

| Subcategory | Scope |
| --- | --- |
| Isolation | Technique, tool choice, angle, sustained isolation, common failure patterns |
| Attachment & Placement | Base gap (0.5–1 mm), wrap, contact length, alignment to natural lash |
| Adhesive Pickup | Amount control, dip depth, dot management, timing to placement |
| Fan Making | Pinch, wiggle, lash-strip, dark spot, bloom, base uniformity, fan symmetry |
| Handmade vs Promade | Trade-offs, weight, bond quality, speed economics |
| Directional Control | Vector alignment, correcting misdirection, closed-eye vs open-eye result |
| Speed & Efficiency | Application rate, motion economy, batching, realistic benchmarks by level |
| Ergonomics & Longevity | Posture, neck/back load, RSI, eye strain, magnification, bed and stool geometry |
| Tools & Grip | Tweezer geometry, tension, grip mechanics, tool maintenance |
| Sectioning & Workflow | Working zones, order of operations, tape and pad placement |
| Bottom Lash Application | Technique differences, length limits, retention expectations |
| Fills | What to remove, outgrown policy, re-isolation, rebuild vs refresh |
| Removal | Gel/cream remover technique, banana peel, safety margins, mechanical removal risk |
| Client Positioning & Comfort | Head position, eye pad placement, taping, closed-eye integrity |
| Environment Control | Lighting, magnification, ventilation, station humidity management |
| Technique Fault Diagnosis | Reading a set to reverse-engineer the technique error |

### 09 · PRD — Products & Materials

| Subcategory | Scope |
| --- | --- |
| Adhesives | Product-level knowledge, spec sheets, comparative behaviour |
| Extensions | PBT fibre science, finish (matte/glossy), profile (round/flat/ellipse/wet-look), curl families (B/C/CC/D/DD/L/L+/M/U), diameter range (0.03–0.20), length range (5–18 mm), tray formats |
| Primers & Cleansers | Chemistry, indications, over-use effects |
| Removers | Gel, cream, solvent — chemistry, dwell time, ocular safety |
| Bonders & Sealants | Mechanism, timing, claimed vs measured benefit |
| Tools | Tweezers, tiles, fans, hygrometers, humidifiers, dehumidifiers, nano misters, beds, lighting, magnification |
| Eye Pads & Tapes | Material, adhesion, sensitivity, placement suitability |
| Lash Lift & Tint Products | Lifting/setting lotion chemistry, keratin, tint oxidation chemistry |
| Consumables & Unit Economics | Cost per service, waste rates, reorder points |
| Product Evaluation Framework | Structured test protocol for objective comparison |
| Supply Chain & Manufacturing | OEM/private-label reality, batch variance, QC, relabeling |
| Counterfeits & Quality Risk | Detection, risk exposure, sourcing hygiene |

### 10 · ADJ — Adjacent Services

| Subcategory | Scope |
| --- | --- |
| Lash Lift & Perm | Chemistry, rod selection, processing times, over-processing damage, aftercare |
| Lash Tinting | Dye chemistry, patch testing, ocular safety |
| Brow Lamination | Chemistry, timing, damage risk |
| Brow Shaping & Mapping | Geometry, mapping method, technique |
| Service Sequencing | Combining services safely, interval requirements |
| Hybrid Offerings | Lift-and-tint, lash line enhancement, service menu design |

### 11 · CON — Consultation & Client Experience

| Subcategory | Scope |
| --- | --- |
| Consultation Framework | Structured question sets, information hierarchy, time budget |
| Expectation Setting | Managing unrealistic requests, reference-photo negotiation, honest limits |
| Contraindication Screening | Intake form design, red-flag routing |
| Documentation | Photo standards, service records, map records, product records |
| Consent & Liability | Waivers, informed consent language, record retention |
| Communication Scripts | Reusable language for common scenarios |
| Experience Design | Comfort, temperature, sound, scent, pillows, session length tolerance |
| Difficult Conversations | Declining service, boundary setting, ethical upselling, price change communication |
| Complaints & Redos | Policy design, triage, goodwill economics |
| Follow-up & Aftercare Delivery | Timing, channel, content, adherence |

### 12 · PSY — Client Psychology & Behaviour

| Subcategory | Scope |
| --- | --- |
| Motivation & Identity | Why clients wear lashes; identity, ritual, confidence |
| Trust & Authority | How artists establish credibility; expertise signalling |
| Loyalty Dynamics | Retaining the client, not just the lashes |
| Price Psychology | Value perception, anchoring, sensitivity, premium positioning |
| Anxiety & Sensory Needs | Neurodivergent clients, claustrophobia, sensory load, medical anxiety |
| Body Image & Emotional Dynamics | Emotional weight of appearance services, medical hair loss |
| Segmentation & Personas | Behavioural client archetypes |
| Churn Prediction | Behavioural churn signals and lead time |
| Referral Psychology | What actually triggers referral behaviour |

### 13 · BIZ — Business & Operations

| Subcategory | Scope |
| --- | --- |
| Business Models | Solo, suite rental, salon employment, commission, mobile, studio, team, franchise |
| Pricing & Profitability | Cost per service, margin, price ladder, price increases, discount damage |
| Booking & Scheduling | Buffers, double-booking, deposits, no-show policy, waitlist |
| Cancellation & Policy Design | Enforceable, humane policy structures |
| Capacity & Utilisation | Column management, service mix, realistic weekly capacity |
| Financial Management | P&L literacy, tax, bookkeeping, break-even, owner pay |
| KPIs | Rebook rate, retention rate, average ticket, CLV, fill:full ratio, chair utilisation, no-show rate |
| Legal & Insurance | Entity structure, liability cover, contracts |
| Team & Hiring | Recruiting, training pipeline, retention, compensation models |
| Systems & SOPs | Documented procedure design, delegation readiness |
| Studio Environment | HVAC, humidity control, ventilation engineering, layout |
| Inventory Management | Par levels, reorder, shrinkage, supplier redundancy |
| Scaling | Second chair, second location, systemisation thresholds |
| Diversification & Exit | Education, product lines, licensing, sale |
| Sustainability & Burnout | Workload design, physical longevity, mental health, career arc |

### 14 · MKT — Marketing & Brand

| Subcategory | Scope |
| --- | --- |
| Positioning & Niche | Differentiation, specialisation strategy |
| Content Strategy | Platform-specific formats, cadence, hook design, education-led content |
| Lash Photography & Video | Lighting, macro technique, before/after standards, honest editing |
| Portfolio Construction | Curation, progression evidence, style-range demonstration |
| Local Discovery | Google Business, local SEO, directories, maps |
| Paid Acquisition | Channel economics, CAC vs CLV for a chair-based business |
| Offers & Promotions | Discount mechanics and their long-term damage |
| Funnels & Conversion | Enquiry → consult → booking → rebook |
| Reputation | Reviews, response strategy, recovery |
| Personal & Educator Brand | Authority building, teaching as marketing |
| Community & Collaboration | Cross-referral, artist networks, industry relationships |

### 15 · EDU — Education & Pedagogy

| Subcategory | Scope |
| --- | --- |
| Learning Pathways | Beginner → competent → advanced → specialist → educator progression |
| Curriculum Design | Module sequencing, prerequisite structure, contact-hour design |
| Skill Assessment | Rubrics, objective criteria, practical exam design |
| Practice Methodology | Deliberate practice, mannequin work, speed drills, feedback loops |
| Learner Failure Modes | Predictable plateaus and their causes |
| Certification Landscape | Accreditation bodies, credential value, jurisdictional recognition |
| Mentorship & Coaching | Structures, cadence, feedback quality |
| Teaching Technique | Demonstration, live observation, hands-on correction, remote instruction |
| Course Business | Pricing, cohorts, kits, support load, refund policy |
| Continuing Education | Skill decay, refresh cadence, advanced specialisation |

### 16 · IND — Industry Intelligence

| Subcategory | Scope |
| --- | --- |
| Market Structure | Sizing, growth, segment shares, channel structure |
| Regional Variation | US / UK / EU / AU / KR / RU / ZA / LATAM norms, pricing and technique differences |
| Regulatory Landscape | Jurisdictional rules and their trajectory |
| Supply Chain | Manufacturing concentration, distribution, private label economics |
| Competitive Landscape | Brands, educators, distributors, platforms |
| Innovation Watch | Emerging techniques, materials, equipment |
| Scientific Evidence Base | Published literature, dermatology/ophthalmology findings, evidence gaps |
| Myth & Misinformation Registry | Catalogued industry myths, origin tracing, corrective evidence |
| Thought Leader Map | Who influences what, and with what reliability |

### 17 · LOS — LashOS Intelligence *(meta-layer)*

Assets the system produces *about itself* — the bridge from knowledge to product.

| Subcategory | Scope |
| --- | --- |
| Decision Models | Formalised decision procedures (style selection, adhesive selection, fill vs full) |
| Diagnostic Trees | Executable troubleshooting trees compiled from cards |
| Prediction Features | Feature definitions for retention/churn models, with source cards |
| Recommendation Rules | Typed rules with conditions, actions, confidence, and provenance |
| Safety Gates | Rules restricting what AI may assert or recommend, by risk tier |
| Persona & Prompt Assets | System prompts for each AI feature, versioned |
| Evaluation Sets | Gold-standard Q&A with expected citations, for regression testing |
| Open Questions | Identified knowledge gaps driving future acquisition |
| Course Blueprints | Reusable module structures generated from card clusters |

---

## 3. Orthogonal facets

Eight required axes. Every card carries a value on each. These are what make the knowledge
base *filterable* for AI features rather than merely browsable.

### F1 · `knowledge_type` — what shape is this knowledge?

`definition` · `principle` · `mechanism` · `technique` · `protocol` · `heuristic` ·
`parameter` · `diagnostic` · `contraindication` · `metric` · `framework` · `script` ·
`case_study` · `opinion` · `myth`

### F2 · `epistemic_status` — how do we know it?

| Value | Meaning |
| --- | --- |
| `established_science` | Supported by peer-reviewed literature or physical/chemical law |
| `manufacturer_spec` | Stated in technical documentation by the producer |
| `industry_consensus` | Broad agreement across independent expert sources |
| `contested` | Credible experts actively disagree |
| `emerging` | New, limited evidence, insufficient corroboration |
| `anecdotal` | Individual experience, not systematically verified |
| `folklore` | Widely repeated, no traceable evidentiary origin |
| `debunked` | Actively contradicted by stronger evidence; retained to correct it |

### F3 · `risk_tier` — what happens if this is wrong?

| Tier | Name | Downstream rule |
| --- | --- | --- |
| 0 | Informational | Free use |
| 1 | Operational | Free use; low consequence |
| 2 | Client safety | AI must cite; no unqualified imperatives |
| 3 | Medical adjacent | Human-reviewed only; AI must include referral language; never diagnostic |
| 4 | Regulatory / legal | Human-reviewed; jurisdiction-scoped; disclaimer mandatory |

### F4 · `skill_level`

`foundation` · `intermediate` · `advanced` · `specialist` · `educator` · `business_owner`

### F5 · `audience`

`student` · `artist` · `educator` · `salon_owner` · `client_facing` · `supplier`

### F6 · `service_lifecycle` — where in the client journey does this apply?

`marketing` · `enquiry` · `consultation` · `assessment` · `design` · `application` ·
`aftercare` · `fill` · `removal` · `retention_followup` · `back_office`

### F7 · `context_sensitivity` — what makes this true or false?

Multi-valued. Signals which environmental or client variables gate applicability:
`climate` · `humidity` · `temperature` · `skin_type` · `lash_health` · `region` ·
`regulation` · `product_specific` · `skill_dependent` · `none`

This facet is what allows the AI to say *"this advice assumes 45–55% RH; your studio reports
68%"* instead of confidently giving wrong guidance.

### F8 · `actionability`

`informational` · `advisory` · `actionable` · `procedural` · `decisional`

---

## 4. Controlled vocabularies

Facets are closed sets. So are the industry's core parameter domains — and enforcing them is
what stops "0.07mm", ".07", "7/10 thickness" and "0.07 diameter" becoming four different values.

| Vocabulary | Values |
| --- | --- |
| `curl` | J, B, C, CC, D, DD, L, L+, LC, LD, M, U |
| `diameter_mm` | 0.03, 0.04, 0.05, 0.06, 0.07, 0.085, 0.10, 0.12, 0.15, 0.18, 0.20 |
| `length_mm` | 5–18 in 1 mm steps |
| `fan_density` | 1D … 20D |
| `finish` | matte, glossy, flat/ellipse, wet_look, cashmere |
| `eye_shape` | almond, round, hooded, monolid, downturned, upturned, deep_set, protruding, close_set, wide_set |
| `skin_type` | dry, normal, combination, oily, very_oily |
| `climate_band` | arid (<30% RH), low (30–45), optimal (45–55), high (55–70), tropical (>70) |
| `unit` | %RH, °C, °F, mm, mg, s, min, h, day, week, USD, count, ratio |

Full machine-readable definitions live in [`taxonomy/controlled_vocabularies.yaml`](../taxonomy/controlled_vocabularies.yaml).

---

## 5. Taxonomy governance

The taxonomy will be wrong on first contact with 4,000 transcripts. That is expected; what
matters is that changes are controlled.

- **Versioned.** `taxonomy.yaml` carries a semver. Cards record the taxonomy version they
  were classified under.
- **Additive by default.** New subcategories are added freely; existing nodes are never
  silently redefined.
- **Deprecation, not deletion.** A retired node is marked `deprecated: true` with a
  `superseded_by` pointer. Cards are remapped by migration, never orphaned.
- **Unclassified overflow.** Each domain has an implicit `_unsorted` bucket. When any bucket
  exceeds 25 cards, that is a signal the taxonomy is missing a real subcategory — this is the
  primary mechanism by which the taxonomy learns from the corpus.
- **Codes are permanent.** The 3-letter domain code is an immutable identifier. Display names
  are free to change.
