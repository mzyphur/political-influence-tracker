# Sector Taxonomy Evolution — Why and How We Refine

**Last updated:** 2026-05-01

## Current state (v1)

The 33-value sector taxonomy used by Stage 1 (entity industry
classification) v1 and Stage 3 (AusTender topic tagging) v1 + v2
collapses several Australian-specific industries into single
buckets:

* `fossil_fuels` — combines coal (thermal + metallurgical), gas
  (LNG + domestic), oil/petroleum, and uranium into ONE bucket.
* `mining` — combines iron ore, lithium / critical minerals,
  copper, gold, zinc, and others into ONE bucket.
* `consulting` — combines Big-4 audit/assurance (Deloitte / PwC /
  KPMG / EY), strategy (McKinsey / BCG / Bain), IT services
  (Accenture / Infosys / TCS), and boutique advisory into ONE bucket.

For US/UK readings these collapses might be tolerable. For
**Australia specifically**, this loses critical resolution:

* Australia is a global coal exporter (≈$60B / year) AND a major LNG exporter (~$80B / year, Asia-bound). Coal and gas
  donors / lobbyists pursue different policy agendas.
* The lithium / critical-minerals industry is structurally
  newer than the iron-ore industry; political relationships
  + electoral concentration are very different.
* The Big-4 consulting firms have specific exposure (PwC tax
  advisory leak; KPMG defence consulting; etc.) that calls for
  separate treatment from generic consulting.

The project's claim-discipline rule means we do NOT just
re-tag entities post-hoc with finer sub-buckets. The right
approach is a versioned taxonomy bump.

## v2 taxonomy proposal

### What changes

`fossil_fuels` → split into 4 sub-codes plus a residual:

| Old | New | Australia examples |
|---|---|---|
| `fossil_fuels` | `coal` | Whitehaven, Glencore Coal, Yancoal, Peabody, Bowen Coking Coal |
| `fossil_fuels` | `gas` | Santos, Woodside, Origin Energy, AGL, Beach Energy |
| `fossil_fuels` | `petroleum` | ExxonMobil Australia, BP, Shell, Caltex/Ampol |
| `fossil_fuels` | `uranium` | BHP (Olympic Dam), Cameco, Heathgate Resources |
| `fossil_fuels` | `fossil_fuels_other` | Mixed-portfolio fossil-fuel entities; coal-seam-gas pioneers; oil-shale |

`mining` → kept as the broad bucket BUT add:

| Old | New | Australia examples |
|---|---|---|
| `mining` | `iron_ore` | Rio Tinto, BHP iron ore, Fortescue Metals, Hancock Prospecting |
| `mining` | `critical_minerals` | Pilbara Minerals, IGO, Lynas (rare earths), MinRes lithium |
| `mining` | `mining_other` | Gold (Newcrest), copper (OZ Minerals), zinc (Glencore non-coal) |

`consulting` → kept as the broad bucket BUT (optional v2.1)
add:

| Old | New | Australia examples |
|---|---|---|
| `consulting` | `big_four_consulting` | Deloitte, PwC, KPMG, EY |
| `consulting` | `strategy_consulting` | McKinsey, BCG, Bain, Accenture Strategy |
| `consulting` | `it_consulting` | Accenture, Infosys, TCS, Wipro, IBM Services |
| `consulting` | `consulting_other` | Boutique / specialist firms |

### What stays the same

The other 30 sectors (`renewable_energy`, `gambling`, `alcohol`,
`tobacco`, `finance`, `superannuation`, `insurance`, `banking`,
`technology`, `telecoms`, `defence`, `law`, `accounting`,
`healthcare`, `pharmaceuticals`, `education`, `media`,
`sport_entertainment`, `transport`, `aviation`, `agriculture`,
`unions`, `business_associations`, `charities_nonprofits`,
`foreign_government`, `government_owned`, `political_entity`,
`individual_uncoded`, `unknown`, `property_development`,
`construction`) remain unchanged.

Total v2 sector count: **33 - 2 (collapsed) + 9 (new sub-codes) =
40 codes** (not 38; counting `*_other` as new).

### Schema migration

Migration `043_extend_sector_taxonomy_v2.sql`:
* Adds the 9 new sector codes to the `entity_industry_classification.public_sector`
  CHECK constraint.
* Adds the same 9 new codes to `austender_contract_topic_tag.sector`
  CHECK constraint.
* Existing rows with `fossil_fuels` or `mining` remain valid;
  v2 outputs use the more specific sub-codes when applicable.

### Prompt versions

* Stage 1 prompt → v2 at `prompts/entity_industry_classification/v2.md`.
* Stage 3 prompt → v3 at `prompts/austender_contract_topic_tag/v3.md`.

Both updated with:
* The new 40-value sector list.
* Explicit guidance on choosing sub-codes (e.g. "thermal coal
  miners → `coal`; metallurgical coal-only producers → `coal`;
  diversified mining majors with coal as one segment → judgement
  call, prefer the dominant segment").
* New worked examples covering BHP (mining_other vs coal vs uranium —
  conglomerate handling), Whitehaven (clear `coal`),
  Santos (clear `gas`).

### Re-classification plan

Two paths:

**Path A — full re-run** (preferred). Re-classify all 28,218
entities and all 73,458+ contracts under v2 / v3. Cost:
* Stage 1 v2: ~$100 USD (Sonnet 4.6, cache invalidated by
  prompt version bump).
* Stage 3 v3 5-year corpus: ~$200-400 USD.
* Total: ~$400 USD.

The benefit: full uniformity, no mixed-taxonomy confusion in
the cross-correlation views.

**Path B — surgical re-run** (cheaper). Only re-classify
entities whose v1 sector was `fossil_fuels` or `mining`,
plus contracts tagged with those sectors. Cost: ~$10 USD.

The downside: cross-correlation views must handle a mix of
v1 + v2 sector codes; researchers see "fossil_fuels" + "coal"
+ "gas" as distinct dimensions, which is messy.

**Decision:** Path A. The cost is small relative to the
analytical clarity gain. The project budget supports it.

### Timeline

1. Stage 1 v1 completes (in flight, ~70% done at 2026-05-01).
2. Stage 1 v1 results loaded to DB; cross-correlation refreshed
   at v1 taxonomy.
3. v2 prompts drafted + reviewed.
4. Schema migration 043 applied.
5. Stage 1 v2 full re-run.
6. Stage 3 v3 full pilot (200 contracts) + IRR check vs Stage 3 v2.
7. If Stage 3 v3 IRR shows substantial agreement with v2 on the
   un-changed sectors AND meaningful sub-classification on
   `fossil_fuels` / `mining` entries, proceed to full Stage 3 v3
   run.
8. Update all docs + cross-correlation views to reflect the v2
   taxonomy.

## Other taxonomy ideas (deferred — v3+)

These are noted for future versions but NOT in the immediate
v2 plan:

* **Pharmaceutical sub-codes** (`pharma_manufacturer`,
  `pharma_distributor`, `medical_devices`, `pbs_supplier`).
* **Defence prime vs subcontractor** split.
* **Banking → big-four bank vs second-tier vs neobank**.
* **Agricultural sub-codes** (broadacre / livestock / dairy /
  horticulture / fisheries).
* **Media → public broadcaster vs commercial vs digital**.

These are valuable but the marginal analytical gain is smaller
than the energy / mining split. v3 conversation, not v2.

## Why we do this carefully

The project's commitment to reproducible research means a
taxonomy revision is non-trivial. Existing v1-tagged rows
remain in the database with `extraction_method =
'llm_<task>_v1'` — they're auditable history, not silently
overwritten. v2 / v3 rows live alongside; researchers can
compare across versions; IRR statistics quantify the
agreement.

We measure twice, cut once. Even a $400 USD re-run is small
versus the cost of getting the taxonomy wrong at public
launch.
