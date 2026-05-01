# Influence Streams Reference

**Last updated:** 2026-05-02

**Purpose:** comprehensive reference of EVERY type of political-
influence stream the project tracks (or plans to track), grouped
by **input** (what flows TO political actors) and **outcome**
(what flows BACK to influencers). Each stream lists status, data
source, evidence tier, surface, and the user-facing question it
answers.

This is the project's pro-democracy "leave no stone unturned"
audit document. A reader who wants to know whether a particular
form of influence is captured — or what's still missing — can
read this in one sitting.

## Inputs (what flows TO political actors)

| Stream | Status | Source | Tier | Surface (live) | User-facing question |
|---|---|---|---|---|---|
| Cash donations to MPs / parties | LIVE | AEC + state ECs | 1 | `/api/representatives/{id}` party_exposure_summary | "Who donated to MP X / party Y?" |
| Public election funding | LIVE | AEC | 1 | campaign_support_summary | "How much public funding did party X receive?" |
| Cash gifts to MPs (>$300 federal) | LIVE | APH + state registers | 1 | benefit_summary + `/api/roi-items?item_type=gift` | "Which MPs received gifts from Qantas?" |
| Sponsored travel | LIVE (Stage 2) | APH ROI PDFs | 2 (LLM) | `/api/roi-items?item_type=sponsored_travel` | "Who sponsored travel for MP X?" |
| Hospitality / lounge memberships | LIVE (Stage 2) | APH ROI PDFs | 2 (LLM) | `/api/roi-items?item_type=membership` | "Which MPs use Qantas Chairman's Lounge?" |
| Directorships (paid + unpaid) | LIVE (Stage 2) | APH ROI PDFs | 2 (LLM) | `/api/roi-items?item_type=directorship` | "Which MPs sit on which company boards?" |
| Investments / shareholdings | LIVE (Stage 2) | APH ROI PDFs | 2 (LLM) | `/api/roi-items?item_type=investment` | "Which MPs hold shares in defence contractors?" |
| Real estate beneficial interest | PARTIAL (Stage 2) | APH ROI PDFs | 2 (LLM) | `/api/roi-items?item_type=real_estate` | "Which MPs own multiple investment properties?" |
| Liabilities (mortgages / loans) | LIVE (Stage 2) | APH ROI PDFs | 2 (LLM) | `/api/roi-items?item_type=liability` | "Which MPs have mortgages with banks they regulate?" |
| Lobbyist representation | SCAFFOLDED | Federal + state lobbyist registers | 1 | (loader TBD) — `lobbyist_organisation_record` table ready | "Who is lobbying who, on whose behalf?" |
| Family / spouse interests | LIVE (Stage 2 partial) | APH ROI PDFs | 2 (LLM) | `/api/roi-items?member_name_query=...` | "What are MP X's spouse's disclosed interests?" |
| Foreign-government registered influence (FITS) | NOT STARTED | AG FITS register | 1 | (Stage 9 future) | "Which entities act for foreign principals?" |
| Revolving-door / public-service movement | NOT STARTED | APS Gazette + LinkedIn-style data | 1+2 | (Stage 7 future) | "Who moved from regulator to regulated?" |
| Election advertising spend (3rd-party) | NOT YET LOADED | AEC 3rd-party returns | 1 | future | "Which 3rd-party campaigners spent $N on Election Y?" |
| Beneficial ownership obscuration | NOT STARTED | ASIC + ACNC | 1+2 | (Stage 4d future) | "Who actually controls Donor X?" |

## Outcomes (what flows BACK to influencers)

| Stream | Status | Source | Tier | Surface (live) | User-facing question |
|---|---|---|---|---|---|
| Government contracts | LIVE | AusTender + LLM topic tag (Stage 3 v2) | 1+2 | `/api/contract-donor-overlap` + `/api/contract-minister-responsibility` | "Did supplier X get $N in contracts after donating $M?" |
| Government grants | SCAFFOLDED | GrantConnect + LLM topic tag (Stage 3-grants) | 1+2 | `v_sector_money_outflow` view | "Which donors received the most grants per sector?" |
| Voting outcomes (divisions) | LIVE | APH divisions + They Vote For You | 1 | `/api/minister-voting-pattern` + `/api/donor-recipient-voting-alignment` | "How did MP-Z vote on bills affecting their donors' industry?" |
| Speaking record (Hansard) | NOT STARTED | APH Hansard | 2 (LLM) | (Stage 5 future) | "Did MP-Z advocate for industry X policy?" |
| Question Time Q&A | NOT STARTED | APH Hansard daily | 2 (LLM) | (Stage 13 future) | "What did MP-Z ask in QT about industry X?" |
| Senate Estimates exchanges | NOT STARTED | APH Estimates Hansard | 2 (LLM) | (Stage 12 future) | "Did Senator-Z question agency-A on contracts to X?" |
| Committee submissions | NOT STARTED | APH committees | 2 (LLM) | (Stage 6 future) | "Who submitted to inquiry-Y, on whose behalf?" |
| Bill sponsorship + amendments | NOT YET LOADED | APH bills register | 1 | future | "Did MP-Z introduce bills favouring industry X?" |
| Tax concessions / exemptions | NOT STARTED | ATO + Treasury data | 1 | future | "Did sector X get a $N tax concession after donating $M?" |
| Regulatory decisions | NOT STARTED | Regulator decision registers (ACCC, ASIC, APRA, etc.) | 1 | future | "Did regulator-A approve donor-X's merger?" |
| ANAO audit findings | NOT STARTED | ANAO reports | 2 (LLM) | (Stage 7 future) | "Were donor-X's contracts audited?" |
| NACC / integrity reports | NOT STARTED | NACC + state integrity commissions | 1+2 | (Stage 8 future) | "Has any MP linked to donor-X been investigated?" |
| Royal Commission archives | NOT STARTED | Per-commission archives | 2 (LLM) | (Stage 15 future) | "What did the Banking RC say about donor-X?" |
| Foreign aid + diplomatic decisions | NOT STARTED | DFAT data | 1 | future | "Did sector X benefit from a Pacific aid deal?" |
| Subsidies / industry support | PARTIAL (via grants) | GrantConnect + Treasury | 1+2 | partial | "How much support did industry X get?" |
| Ministerial meetings | PARTIAL | NSW + VIC ministerial-meeting registers | 1 | future | "How often did Minister-Z meet lobbyist-L?" |

## Cross-source correlation surfaces (existing)

| View | Surface |
|---|---|
| `v_contract_donor_overlap` | Suppliers that ALSO appear as donors |
| `v_industry_influence_aggregate` | Donor + contract aggregates per sector |
| `v_industry_anatomy` | THE comprehensive: donations + gifts + travel + memberships + contracts per sector |
| `v_contract_minister_responsibility` | Contracts → ministers via portfolio mapping |
| `v_minister_voting_pattern` | Per-minister voting record by topic |
| `v_donor_recipient_voting_alignment` | Per (donor → recipient → topic): donor money + MP voting |
| `v_sector_voting_alignment` | Per (sector → topic): sector money + recipient MPs' aggregate votes |
| `v_sector_money_outflow` | Per sector: contracts + grants (NEW Batch CC-6) |
| `v_lobbyist_client_influence_overlap` | Lobbyist firm × client × client donations (loader pending) |

## Live database state (snapshot)

| Table | Rows | Notes |
|---|---:|---|
| `influence_event` (non-rejected) | 314,040 | $13.48B reported total — federal + 8 states |
| `entity_industry_classification` (model_assisted v1) | ~5,646 | After Stage 1 v1 loader |
| `entity_industry_classification` (model_assisted v2) | growing | Stage 1 v2 in flight (~36% at this writing) |
| `austender_contract_topic_tag` | 544 | v1 + v2 pilot data |
| `llm_register_of_interests_observation` | 3,547 | Stage 2 full corpus |
| `cabinet_ministry` | 9 | 1 federal + 8 state/territory |
| `portfolio_agency` | ~73 | All portfolios across 9 ministries |
| `minister_role` | ~76 | All cabinet ministers |
| `vote_division` | 506 | 147 House + 359 Senate divisions |
| `person_vote` | 37,886 | Individual MP votes on divisions |
| `division_topic` | (CC-BY TVFY) | Policy-topic linkage on divisions |
| `lobbyist_organisation_record` | 0 | Schema only; loader pending |
| `grant_observation` | 0 | Schema only; loader pending |

## How to read this document

* **LIVE** = data is in the production DB and exposed via API.
* **SCAFFOLDED** = schema + tables exist; loader is the next-
  batch work.
* **NOT YET LOADED** = upstream data exists, parser doesn't yet.
* **NOT STARTED** = upstream data exists, no work done yet.

The pro-democracy transparency mission requires every "NOT
STARTED" / "SCAFFOLDED" stream to eventually move to "LIVE".
The strategic-plan doc at `docs/strategic_plan_post_BB.md`
captures the order. The cost projections in that plan total
~$3,500-7,000 USD in post-launch LLM spend across Stages 5-15.

## How to amend this document

Same governance as `docs/design_decisions.md`: substantive
changes require a commit to the public mirror with rationale.
The `Last updated` date at the top is bumped on every revision.
