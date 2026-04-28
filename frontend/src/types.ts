export type MapGeometry = {
  type: string;
  coordinates: unknown;
};

export type MapProperties = {
  electorate_id: number;
  electorate_name: string;
  chamber: string;
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
  attribution: string;
  counts: Record<string, number | string | null>;
};

export type CoverageResponse = {
  status: string;
  active_country: string;
  active_levels: string[];
  planned_levels: string[];
  coverage_layers: CoverageLayer[];
  influence_events_by_family: Array<Record<string, number | string | null>>;
  influence_event_totals: Record<string, number | string | null>;
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
};

export type RepresentativeProfile = {
  person: {
    id: number;
    display_name: string;
    canonical_name: string;
  };
  contact: RepresentativeContact;
  event_summary: RepresentativeEventSummary[];
  recent_events: RepresentativeEvent[];
  campaign_support_summary: RepresentativeCampaignSupportSummary[];
  campaign_support_recent_events: RepresentativeEvent[];
  campaign_support_caveat: string;
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
  evidence_note?: string | null;
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
