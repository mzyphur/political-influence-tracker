export type MapGeometry = {
  type: string;
  coordinates: unknown;
};

export type Chamber = "house" | "senate" | "state" | "council";

export type MapProperties = {
  electorate_id: number;
  electorate_name: string;
  chamber: Chamber;
  state_or_territory: string | null;
  boundary_set: string | null;
  has_boundary: boolean;
  representative_id: number | null;
  representative_name: string | null;
  party_id: number | null;
  party_name: string | null;
  party_short_name: string | null;
  current_representative_count: number;
  current_representatives: RepresentativeSummary[];
  party_breakdown: PartyBreakdown[];
  map_geometry_role?: "display" | "source";
  map_geometry_scope?: string;
  current_representative_lifetime_influence_event_count: number;
  current_representative_lifetime_money_event_count: number;
  current_representative_lifetime_benefit_event_count: number;
  current_representative_lifetime_campaign_support_event_count: number;
  current_representative_campaign_support_reported_total: number | null;
  current_representative_needs_review_event_count: number;
  current_representative_official_record_event_count: number;
  current_representative_lifetime_reported_amount_total: number | null;
};

export type RepresentativeSummary = {
  person_id: number;
  display_name: string;
  party_id: number | null;
  party_name: string | null;
  party_short_name: string | null;
  chamber: string;
  state_or_territory?: string | null;
  term_start: string | null;
  portfolio?: string | null;
  public_email?: string | null;
  electorate_offices?: Array<{
    address_lines?: string[];
    email?: string;
    source_row_number?: number;
  }>;
};

export type PartyBreakdown = {
  party_id: number | null;
  party_name: string | null;
  party_short_name: string | null;
  representative_count: number;
};

export type ElectorateFeature = {
  type: "Feature";
  id: number;
  geometry: MapGeometry | null;
  properties: MapProperties;
};

export type ElectorateFeatureCollection = {
  type: "FeatureCollection";
  features: ElectorateFeature[];
  feature_count: number;
  filters: Record<string, unknown>;
  caveat: string;
};

export type QldCouncilDisclosureContext = {
  available: boolean;
  match_basis: string;
  not_council_or_councillor_receipt: boolean;
  money_flow_count: number;
  gift_or_donation_count?: number;
  electoral_expenditure_count?: number;
  exact_area_count?: number;
  alias_area_count?: number;
  child_area_count?: number;
  matched_local_electorate_count?: number;
  gift_or_donation_reported_amount_total?: number | null;
  electoral_expenditure_reported_amount_total?: number | null;
  first_record_date?: string | null;
  last_record_date?: string | null;
  matched_local_electorates?: Array<{
    local_electorate_external_id: string | null;
    local_electorate_name: string | null;
    match_scope: string;
    money_flow_count: number;
    gift_or_donation_count: number;
    electoral_expenditure_count: number;
    gift_or_donation_reported_amount_total: number | null;
    electoral_expenditure_reported_amount_total: number | null;
  }>;
  top_events?: Array<{
    event_external_id: string | null;
    event_name: string | null;
    money_flow_count: number;
    gift_or_donation_reported_amount_total: number | null;
    electoral_expenditure_reported_amount_total: number | null;
  }>;
  top_gift_donors?: Array<{
    source_name: string | null;
    money_flow_count: number;
    reported_amount_total: number | null;
  }>;
  top_expenditure_actors?: Array<{
    source_name: string | null;
    money_flow_count: number;
    reported_amount_total: number | null;
  }>;
  caveat: string;
};

export type ElectorateProfile = {
  electorate: {
    id: number;
    name: string;
    chamber: Chamber;
    state_or_territory: string | null;
    has_boundary: boolean;
  };
  representatives: Array<Record<string, unknown>>;
  current_representative_influence_summary: Array<Record<string, unknown>>;
  qld_ecq_local_disclosure_context: QldCouncilDisclosureContext | null;
  caveat: string;
};

export type SearchResult = {
  type: string;
  id: number | string;
  label: string;
  subtitle: string;
  rank: number;
  metadata: Record<string, unknown>;
};

export type SearchResponse = {
  query: string;
  normalized_query: string;
  results: SearchResult[];
  result_count: number;
  limitations: Array<{ feature: string; status: string; message: string }>;
  caveat: string;
};

export type CoverageLayer = {
  id: string;
  label: string;
  level: string;
  status: string;
  jurisdiction?: string | null;
  attribution: string;
  counts: Record<string, number | string | null>;
};

export type CoverageResponse = {
  status: string;
  active_country: string;
  active_levels: string[];
  partial_levels?: string[];
  planned_levels: string[];
  coverage_layers: CoverageLayer[];
  display_land_masks?: Array<{
    source_key: string;
    country_name: string;
    geometry_role: string;
    source_document_id: number | null;
    source_name: string | null;
    source_type: string | null;
    jurisdiction: string | null;
    source_url: string | null;
    source_final_url: string | null;
    source_fetched_at: string | null;
    licence_status: string | null;
    mask_method: string | null;
    source_limitations: string | null;
    geometry_is_valid: boolean | null;
    geometry_part_count: number | null;
  }>;
  influence_events_by_family: Array<Record<string, number | string | null>>;
  influence_event_totals: Record<string, number | string | null>;
  caveat: string;
};

export type StateLocalSummaryEntityRow = {
  entity_id: number | null;
  name: string | null;
  event_count: number;
  reported_amount_total: number | null;
  identifier_count: number;
  identifier_backed: boolean | null;
};

export type StateLocalSummaryContextRow = {
  external_id: string | null;
  name: string | null;
  level: string | null;
  code: string | null;
  event_type: string | null;
  polling_date: string | null;
  start_date: string | null;
  date_caveat: string | null;
  money_flow_count: number;
  gift_or_donation_count: number;
  electoral_expenditure_count: number;
  gift_or_donation_reported_amount_total: number | null;
  electoral_expenditure_reported_amount_total: number | null;
};

export type StateLocalSummaryTotalRow = {
  jurisdiction_name: string;
  jurisdiction_level: string;
  jurisdiction_code: string;
  money_flow_count: number;
  gift_or_donation_count: number;
  gift_in_kind_count: number;
  electoral_expenditure_count: number;
  public_funding_count: number;
  return_summary_count: number;
  gift_or_donation_reported_amount_total: number | null;
  electoral_expenditure_reported_amount_total: number | null;
  public_funding_reported_amount_total: number | null;
  return_summary_reported_amount_total: number | null;
  source_identifier_backed_count: number;
  recipient_identifier_backed_count: number;
  event_context_backed_count: number;
  local_electorate_context_backed_count: number;
};

export type StateLocalAggregateTotalRow = {
  jurisdiction_name: string;
  jurisdiction_level: string;
  jurisdiction_code: string;
  source_dataset: string;
  context_type: string;
  aggregate_context_count: number;
  source_record_count: number | null;
  reported_amount_total: number | null;
  reporting_period_start: string | null;
  reporting_period_end: string | null;
  source_document_count: number;
  latest_source_fetched_at: string | null;
};

export type StateLocalAggregateLocationRow = {
  id: number;
  jurisdiction_name: string;
  jurisdiction_level: string;
  jurisdiction_code: string;
  source_dataset: string;
  context_type: string;
  geography_type: string | null;
  geography_name: string | null;
  reported_amount_total: number | null;
  source_record_count: number | null;
  reporting_period_start: string | null;
  reporting_period_end: string | null;
  attribution_scope: string | null;
  caveat: string | null;
  source_document_id: number | null;
  source_document_name: string | null;
  source_url: string | null;
  source_final_url: string | null;
  source_document_sha256: string | null;
  source_document_fetched_at: string | null;
};

export type StateLocalSummaryRecord = {
  id: number;
  jurisdiction_name: string;
  jurisdiction_level: string;
  jurisdiction_code: string;
  source_dataset: string | null;
  flow_kind: string | null;
  receipt_type: string | null;
  disclosure_category: string | null;
  source_entity_id: number | null;
  source_name: string | null;
  recipient_entity_id: number | null;
  recipient_name: string | null;
  amount: number | null;
  currency: string;
  financial_year: string | null;
  date_received: string | null;
  date_reported: string | null;
  source_row_ref: string | null;
  report_url: string | null;
  original_text: string | null;
  confidence: string | null;
  transaction_kind: string | null;
  description_of_goods_or_services: string | null;
  purpose_of_expenditure: string | null;
  public_amount_counting_role: string | null;
  date_caveat: string | null;
  record_caveat: string | null;
  campaign_support_attribution: Record<string, unknown> | null;
  public_funding_context: Record<string, unknown> | null;
  supporting_documents: Array<Record<string, unknown>> | null;
  source_identifier_backed: boolean | null;
  recipient_identifier_backed: boolean | null;
  event_external_id: string | null;
  event_name: string | null;
  event_polling_date: string | null;
  local_electorate_external_id: string | null;
  local_electorate_name: string | null;
  source_document_id: number;
  source_id: string;
  source_document_name: string;
  source_url: string | null;
  source_final_url: string | null;
  source_document_sha256: string;
  source_document_fetched_at: string;
  pagination_cursor?: string;
};

export type StateLocalRecordsResponse = {
  status: string;
  source_family: string;
  jurisdiction: string;
  requested_level: string;
  db_level: string;
  requested_jurisdiction_code: string | null;
  db_jurisdiction_codes: string[];
  flow_kind: string | null;
  records: StateLocalSummaryRecord[];
  record_count: number;
  total_count: number;
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
  caveat: string;
};

export type StateLocalSummaryResponse = {
  status: string;
  source_family: string;
  jurisdiction: string;
  requested_level: string;
  db_level: string;
  requested_jurisdiction_code: string | null;
  db_jurisdiction_codes: string[];
  totals_by_level: StateLocalSummaryTotalRow[];
  source_document_count: number;
  latest_source_fetched_at: string | null;
  top_gift_donors: StateLocalSummaryEntityRow[];
  top_gift_recipients: StateLocalSummaryEntityRow[];
  top_expenditure_actors: StateLocalSummaryEntityRow[];
  top_public_funding_recipients: StateLocalSummaryEntityRow[];
  top_return_summary_sources: StateLocalSummaryEntityRow[];
  top_return_summary_recipients: StateLocalSummaryEntityRow[];
  top_events: StateLocalSummaryContextRow[];
  top_local_electorates: StateLocalSummaryContextRow[];
  recent_records: StateLocalSummaryRecord[];
  aggregate_context_totals: StateLocalAggregateTotalRow[];
  top_aggregate_donor_locations: StateLocalAggregateLocationRow[];
  aggregate_context_caveat: string;
  caveat: string;
};

export type RepresentativeEventSummary = {
  event_family: string;
  event_count: number;
  reported_amount_event_count: number;
  reported_amount_total: number | null;
  first_event_date: string | null;
  last_event_date: string | null;
};

export type RepresentativeCampaignSupportSummary = {
  event_type: string;
  attribution_tier: string | null;
  event_count: number;
  reported_amount_event_count: number;
  reported_amount_total: number | null;
  first_event_date: string | null;
  last_event_date: string | null;
};

export type RepresentativePartyExposureSummary = {
  party_id: number;
  party_name: string;
  party_short_name: string | null;
  chamber: string | null;
  state_or_territory: string | null;
  electorate_name: string | null;
  term_start: string | null;
  event_count: number;
  reported_amount_event_count: number;
  party_context_reported_amount_total: number | null;
  modelled_amount_total: number | null;
  allocation_method: string;
  allocation_denominator: number | null;
  allocation_weight: number | null;
  allocation_basis: string | null;
  model_name: string | null;
  model_version: string | null;
  uncertainty_label: string | null;
  first_event_date: string | null;
  last_event_date: string | null;
  input_event_count: number;
  input_source_document_count: number;
  event_period_scope: string;
  representative_scope: string;
  party_context_label: string;
  /** True when the underlying party row is an AEC-registered electoral
   * vehicle for a specific candidate (e.g. "Kim for Canberra") rather
   * than an ideological federal party. The frontend should render
   * these with a distinct chip so a public reader is not led to
   * treat the registered name as a conventional party. */
  is_personality_vehicle: boolean;
  /** Optional hint at the affiliated person's name(s), populated by
   * `schema/037_seed_candidate_vehicle_party_rows.sql` for personality-
   * vehicle parties. Display alongside the chip when present. */
  affiliated_person_hint: string | null;
  /** Sub-national rollout (Batch R). The party row's jurisdiction so
   * the frontend can render federal vs state-jurisdiction party-
   * mediated exposure in distinct sections. For the federal launch,
   * every row returned by `_representative_party_exposure_summary`
   * is federal (the office_term-anchored query only finds the MP's
   * currently-seated party, which is federal). State-jurisdiction
   * rows will reach the response only via a future bridge layer.
   * `party_jurisdiction_code` matches `jurisdiction.code` in the DB
   * (e.g. `"CWLTH"` for federal, `"QLD"` / `"NSW"` / etc. for state). */
  party_jurisdiction_id: number | null;
  party_jurisdiction_code: string | null;
  party_jurisdiction_level: string | null;
  party_jurisdiction_name: string | null;
  claim_scope: string;
};

/**
 * Sub-national rollout (Batch R Option C) — bridge layer that
 * surfaces the state-branch context of a federal MP's party as a
 * SEPARATE evidence tier. For a federal ALP MP, this is the per-
 * state breakdown of state-branch ALP rows (QLD ALP, NSW ALP,
 * etc.) — each with its own reviewed `party_entity_link` count
 * and party-mediated money rollup. NOT to be summed with the
 * federal `party_exposure_summary`; the project's claim-discipline
 * rule keeps these as separate tiers.
 */
export type RepresentativeStateBranchPartyExposureSummary = {
  state_party_id: number;
  state_party_name: string;
  state_party_short_name: string | null;
  state_jurisdiction_id: number;
  state_jurisdiction_code: string;
  state_jurisdiction_level: string;
  state_jurisdiction_name: string;
  federal_party_id: number;
  federal_party_name: string;
  reviewed_link_count: number;
  event_count: number;
  reported_amount_event_count: number;
  party_context_reported_amount_total: number | null;
  first_event_date: string | null;
  last_event_date: string | null;
  input_source_document_count: number;
  claim_scope: string;
};

export type RepresentativeBenefitSummary = {
  event_type: string;
  event_subtype: string;
  event_count: number;
  provider_linked_event_count: number;
  named_provider_event_count: number;
  reported_amount_event_count: number;
  reported_amount_total: number | null;
  dated_event_count: number;
  needs_review_event_count: number;
  missing_data_event_count: number;
  first_event_date: string | null;
  last_event_date: string | null;
};

export type RepresentativeBenefitProviderSummary = {
  provider_name: string;
  provider_entity_id: number | null;
  event_count: number;
  event_types: string[];
  event_subtypes: string[];
  reported_amount_event_count: number;
  reported_amount_total: number | null;
  needs_review_event_count: number;
  missing_data_event_count: number;
  first_event_date: string | null;
  last_event_date: string | null;
};

export type RepresentativeInfluenceSectorSummary = {
  public_sector: string;
  influence_event_count: number;
  money_event_count: number;
  benefit_event_count: number;
  reported_amount_event_count: number;
  reported_amount_total: number | null;
  needs_review_event_count: number;
  source_document_count: number;
  official_sector_event_count: number;
  manual_sector_event_count: number;
  inferred_or_unknown_sector_event_count: number;
  first_event_date: string | null;
  last_event_date: string | null;
};

export type RepresentativeVoteTopicSummary = {
  topic_label: string;
  topic_slug: string;
  chamber: string;
  division_vote_count: number;
  aye_count: number;
  no_count: number;
  absent_count: number;
  other_vote_count: number;
  rebel_count: number;
  first_division_date: string | null;
  last_division_date: string | null;
};

export type RepresentativeSourceEffectContext = {
  topic_label: string;
  public_sector: string;
  relationship: string;
  division_vote_count: number;
  lifetime_influence_event_count: number;
  lifetime_reported_amount_total: number | null;
  influence_events_before_first_vote: number;
  influence_events_during_vote_span: number;
  influence_events_after_last_vote: number;
  influence_events_unknown_timing: number;
  sector_topic_link_confidence: string;
};

export type RepresentativeEvent = {
  id: number;
  event_family: string;
  event_type: string;
  event_subtype: string | null;
  source_raw_name: string | null;
  source_entity_name: string | null;
  amount: number | null;
  currency: string;
  amount_status: string;
  event_date: string | null;
  reporting_period: string | null;
  date_reported: string | null;
  description: string;
  disclosure_system: string;
  disclosure_threshold: string | null;
  evidence_status: string;
  extraction_method: string;
  review_status: string;
  missing_data_flags: unknown[];
  source_ref: string | null;
  source_id: string;
  source_name: string;
  source_type: string;
  source_url: string | null;
  source_final_url: string | null;
  pagination_cursor?: string;
};

export type RepresentativeEvidenceResponse = {
  person_id: number;
  group: "direct" | "campaign_support";
  event_family: string | null;
  events: RepresentativeEvent[];
  event_count: number;
  total_count: number;
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
  caveat: string;
};

export type RepresentativeProfile = {
  person: {
    id: number;
    display_name: string;
    canonical_name: string;
  };
  contact: RepresentativeContact;
  event_summary: RepresentativeEventSummary[];
  benefit_summary: RepresentativeBenefitSummary[];
  benefit_provider_summary: RepresentativeBenefitProviderSummary[];
  recent_events: RepresentativeEvent[];
  campaign_support_summary: RepresentativeCampaignSupportSummary[];
  campaign_support_recent_events: RepresentativeEvent[];
  campaign_support_caveat: string;
  party_exposure_summary: RepresentativePartyExposureSummary[];
  party_exposure_caveat: string;
  /** Sub-national rollout bridge layer (Batch R Option C). State-
   * jurisdiction party rows that share the federal canonical name
   * with the MP's federal party, surfaced as a SEPARATE evidence
   * tier with their own claim-discipline caveat. Empty when the
   * MP's party has no state-branch peers with reviewed links. */
  state_branch_party_exposure_summary: RepresentativeStateBranchPartyExposureSummary[];
  state_branch_party_exposure_caveat: string;
  influence_by_sector: RepresentativeInfluenceSectorSummary[];
  vote_topics: RepresentativeVoteTopicSummary[];
  source_effect_context: RepresentativeSourceEffectContext[];
  caveat: string;
};

export type EntityProfile = {
  entity: {
    id: number;
    canonical_name: string;
    normalized_name: string;
    entity_type: string;
    country: string | null;
    state_or_territory: string | null;
    website: string | null;
  };
  classifications: Array<{
    public_sector: string;
    method: string;
    confidence: string;
    evidence_note: string | null;
    reviewed_at: string | null;
  }>;
  identifiers: Array<{
    identifier_type: string;
    identifier_value: string;
    source_id: string | null;
    source_name: string | null;
    source_url: string | null;
    source_final_url: string | null;
  }>;
  as_source_summary: EntityEventSummary[];
  as_recipient_summary: EntityEventSummary[];
  top_recipients: Array<{
    recipient_id: number | null;
    recipient_type: string;
    recipient_label: string;
    event_count: number;
    reported_amount_event_count: number;
    reported_amount_total: number | null;
  }>;
  top_sources: Array<{
    source_id: string | null;
    source_type: string;
    source_label: string;
    event_count: number;
    reported_amount_event_count: number;
    reported_amount_total: number | null;
  }>;
  recent_events: EntityEvent[];
  caveat: string;
};

export type EntityEventSummary = {
  event_family: string;
  event_type: string;
  event_count: number;
  person_linked_event_count?: number;
  reported_amount_event_count: number;
  reported_amount_total: number | null;
  campaign_support_reported_amount_event_count?: number;
  campaign_support_reported_amount_total?: number | null;
  first_event_date: string | null;
  last_event_date: string | null;
};

export type EntityEvent = {
  id: number;
  entity_role: "as_source" | "as_recipient";
  event_family: string;
  event_type: string;
  event_subtype: string | null;
  source_raw_name: string | null;
  source_entity_name: string | null;
  recipient_raw_name: string | null;
  recipient_person_name: string | null;
  recipient_entity_name: string | null;
  amount: number | null;
  currency: string;
  amount_status: string;
  event_date: string | null;
  reporting_period: string | null;
  date_reported: string | null;
  description: string;
  evidence_status: string;
  review_status: string;
  missing_data_flags: unknown[];
  source_ref: string | null;
  source_id: string;
  source_name: string;
  source_type: string;
  source_url: string | null;
  source_final_url: string | null;
};

export type PartyProfile = {
  party: {
    id: number;
    name: string;
    display_name?: string;
    short_name: string | null;
    party_group: string | null;
    jurisdiction_name: string | null;
    jurisdiction_level: string | null;
  };
  office_summary: Array<{
    chamber: string;
    current_representative_count: number;
  }>;
  linked_entities: Array<{
    entity_id: number;
    canonical_name: string;
    entity_type: string | null;
    link_type: string;
    method: string;
    confidence: string;
    review_status: string;
    evidence_note: string | null;
    influence_event_count?: number;
    reported_amount_total?: number | null;
  }>;
  candidate_entities: Array<{
    entity_id: number;
    canonical_name: string;
    entity_type: string | null;
    link_type: string;
    method: string;
    confidence: string;
    review_status: string;
    evidence_note: string | null;
    influence_event_count?: number;
    reported_amount_total?: number | null;
  }>;
  money_summary: Array<{
    entity_role: string;
    event_type: string;
    event_count: number;
    reported_amount_event_count: number;
    reported_amount_total: number | null;
    first_event_date: string | null;
    last_event_date: string | null;
  }>;
  by_financial_year: Array<{
    financial_year: string | null;
    event_count: number;
    reported_amount_total: number | null;
  }>;
  by_return_type: Array<{
    return_type: string | null;
    event_count: number;
    reported_amount_total: number | null;
  }>;
  top_sources: Array<{
    source_id: string | null;
    source_label: string;
    event_count: number;
    reported_amount_total: number | null;
  }>;
  top_recipients: Array<{
    recipient_id: string | null;
    recipient_label: string;
    event_count: number;
    reported_amount_total: number | null;
  }>;
  associated_entity_returns: Array<{
    entity_id: number;
    canonical_name: string;
    event_count: number;
    reported_amount_total: number | null;
  }>;
  recent_events: PartyEvent[];
  caveat: string;
};

export type PartyEvent = {
  id: number;
  entity_role: string;
  event_type: string;
  source_raw_name: string | null;
  source_entity_name: string | null;
  recipient_raw_name: string | null;
  recipient_entity_name: string | null;
  amount: number | null;
  currency: string;
  amount_status: string;
  event_date: string | null;
  reporting_period: string | null;
  description: string;
  review_status: string;
  source_id: string;
  source_name: string;
  source_url: string | null;
  source_final_url: string | null;
};

export type InfluenceGraphNode = {
  id: string;
  type: "person" | "party" | "entity" | "raw_source" | "raw_counterparty" | string;
  label: string;
  short_name?: string | null;
  entity_type?: string | null;
};

export type InfluenceGraphEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  event_family?: string | null;
  event_type?: string | null;
  link_type?: string | null;
  method?: string | null;
  confidence?: string | number | null;
  review_status?: string | null;
  evidence_status?: string | null;
  evidence_tier?: string | null;
  evidence_note?: string | null;
  allocation_method?: string | null;
  allocation_basis?: string | null;
  allocation_denominator?: number | null;
  allocation_weight?: number | null;
  party_context_reported_amount_total?: number | null;
  modelled_amount_total?: number | null;
  model_name?: string | null;
  model_version?: string | null;
  event_period_scope?: string | null;
  representative_scope?: string | null;
  party_context_label?: string | null;
  input_event_ids?: number[];
  input_source_document_ids?: number[];
  amount_estimate?: number | null;
  amount_lower_bound?: number | null;
  amount_upper_bound?: number | null;
  currency?: string | null;
  uncertainty_label?: string | null;
  display_caveat?: string | null;
  generated_at?: string | null;
  claim_scope?: string | null;
  event_count?: number | null;
  reported_amount_event_count?: number | null;
  reviewed_event_count?: number | null;
  needs_review_event_count?: number | null;
  missing_data_event_count?: number | null;
  reported_amount_total?: number | null;
  first_event_date?: string | null;
  last_event_date?: string | null;
  source_urls?: string[];
};

export type InfluenceGraph = {
  root_id: string;
  nodes: InfluenceGraphNode[];
  edges: InfluenceGraphEdge[];
  node_count: number;
  edge_count: number;
  filters: {
    person_id?: number | null;
    party_id?: number | null;
    entity_id?: number | null;
    include_candidates?: boolean;
    limit?: number;
  };
  caveat: string;
};

export type RepresentativeContact = {
  email: string | null;
  email_source_metadata_path: string | null;
  phones: {
    electorate: string | null;
    parliament: string | null;
    tollfree: string | null;
    fax: string | null;
  };
  addresses: {
    physical_office: string | null;
    postal: string | null;
    parliament: string | null;
  };
  web: {
    official_profile: string | null;
    contact_form: string | null;
    personal_website: string | null;
  };
  source_url: string | null;
  source_note: string;
};

export type LoadState = "idle" | "loading" | "ready" | "error";


/* -------------------------------------------------------------- *
 * Industry-aggregate + cross-source correlation types (Batch BB) *
 * -------------------------------------------------------------- */

/**
 * Per-sector aggregate row with side-by-side donor totals (tier 1)
 * and contract totals (tier 2). NEVER summed across the boundary.
 */
export type IndustryAggregateRow = {
  sector: string;
  /* Donor side (deterministic). May be null for sectors with no
   * recorded donor activity. */
  distinct_donor_entities: number | null;
  donor_event_count: number | null;
  money_event_count: number | null;
  campaign_support_event_count: number | null;
  private_interest_event_count: number | null;
  benefit_event_count: number | null;
  access_event_count: number | null;
  organisational_role_event_count: number | null;
  total_money_aud: number | null;
  total_campaign_support_aud: number | null;
  donor_earliest_event_date: string | null;
  donor_latest_event_date: string | null;
  donor_evidence_tier: string | null;
  donor_sector_method: string | null;
  /* Contract side (LLM-tagged). May be null for sectors with no
   * tagged contracts in the current corpus. */
  contract_prompt_version: string | null;
  contract_count: number | null;
  distinct_contract_ids: number | null;
  distinct_suppliers: number | null;
  total_contract_value_aud: number | null;
  contracting_agencies: string[] | null;
  procurement_classes: string[] | null;
  contract_evidence_tier: string | null;
};

export type IndustryAggregateResponse = {
  claim_discipline_caveat: string;
  row_count: number;
  filters: {
    min_donor_money_aud: number;
    min_contract_value_aud: number;
    limit: number;
  };
  rows: IndustryAggregateRow[];
};


/**
 * Per-supplier overlap row: a contract supplier that ALSO appears
 * as a donor / gift-giver / host in the deterministic record.
 */
export type ContractDonorOverlapRow = {
  supplier_name: string;
  supplier_normalized: string;
  contract_prompt_version: string;
  contract_count: number;
  distinct_contract_ids: number;
  total_contract_value_aud: number | null;
  contract_sectors: string[];
  contract_policy_topics: string[];
  contract_agencies: string[];
  matched_entity_id: number | null;
  matched_entity_canonical_name: string | null;
  matched_entity_type: string | null;
  donor_event_count: number;
  money_event_count: number;
  campaign_support_event_count: number;
  private_interest_event_count: number;
  benefit_event_count: number;
  access_event_count: number;
  organisational_role_event_count: number;
  donor_total_money_aud: number | null;
  donor_total_campaign_support_aud: number | null;
  donor_event_families: string[];
  donor_earliest_event_date: string | null;
  donor_latest_event_date: string | null;
  contract_evidence_tier: string;
  donor_evidence_tier: string;
  claim_discipline_note: string;
};

export type ContractDonorOverlapResponse = {
  claim_discipline_caveat: string;
  row_count: number;
  filters: {
    min_contract_value_aud: number;
    min_donor_money_aud: number;
    sector: string | null;
    limit: number;
  };
  rows: ContractDonorOverlapRow[];
};


/**
 * Per-contract minister responsibility row: a tagged contract
 * joined to the minister + portfolio overseeing the awarding
 * agency, via the deterministic portfolio_agency table.
 */
export type ContractMinisterResponsibilityRow = {
  contract_id: string;
  agency_name: string;
  supplier_name: string;
  sector: string;
  policy_topics: string[];
  procurement_class: string;
  summary: string;
  portfolio_label: string | null;
  cabinet_ministry_id: number | null;
  cabinet_ministry_label: string | null;
  parliamentary_term: string | null;
  governing_party_short_name: string | null;
  minister_role_id: number | null;
  minister_person_id: number | null;
  minister_name: string | null;
  minister_role_title: string | null;
  minister_role_type: string | null;
  minister_effective_from: string | null;
  minister_effective_to: string | null;
  contract_evidence_tier: string;
  portfolio_evidence_tier: string;
  minister_evidence_tier: string;
  claim_discipline_note: string;
};

export type ContractMinisterResponsibilityResponse = {
  claim_discipline_caveat: string;
  row_count: number;
  filters: {
    agency: string | null;
    minister_name: string | null;
    portfolio: string | null;
    sector: string | null;
    limit: number;
  };
  rows: ContractMinisterResponsibilityRow[];
};


/**
 * Per-(minister, policy_topic) voting summary. Aye + no + rebellion
 * counts over divisions tagged to the topic by They Vote For You
 * (CC-BY). Does NOT pre-judge alignment.
 */
export type MinisterVotingPatternRow = {
  minister_role_id: number;
  minister_person_id: number;
  minister_name: string;
  minister_role_title: string;
  portfolio_label: string;
  cabinet_ministry_label: string;
  topic_id: number;
  policy_topic_label: string;
  policy_topic_slug: string;
  division_count: number;
  aye_count: number;
  no_count: number;
  rebellion_count: number;
  earliest_vote_date: string | null;
  latest_vote_date: string | null;
  voting_evidence_tier: string;
  portfolio_evidence_tier: string;
  claim_discipline_note: string;
};

export type MinisterVotingPatternResponse = {
  claim_discipline_caveat: string;
  row_count: number;
  filters: {
    minister_name: string | null;
    portfolio: string | null;
    topic_slug: string | null;
    limit: number;
  };
  rows: MinisterVotingPatternRow[];
};
