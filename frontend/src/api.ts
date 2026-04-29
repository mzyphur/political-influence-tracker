import type {
  CoverageResponse,
  ElectorateFeatureCollection,
  EntityProfile,
  InfluenceGraph,
  PartyProfile,
  RepresentativeEvidenceResponse,
  RepresentativeProfile,
  SearchResponse,
  StateLocalRecordsResponse,
  StateLocalSummaryResponse
} from "./types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "";

function apiUrl(path: string, params?: URLSearchParams): string {
  const url = `${apiBaseUrl}${path}`;
  const query = params?.toString();
  return query ? `${url}?${query}` : url;
}

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: unknown };
      detail = typeof payload.detail === "string" ? payload.detail : "";
    } catch {
      detail = "";
    }
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function fetchElectorateMap(options: {
  chamber: "house" | "senate";
  state?: string;
  boundarySet?: string;
  includeGeometry?: boolean;
  signal?: AbortSignal;
}): Promise<ElectorateFeatureCollection> {
  const params = new URLSearchParams({
    chamber: options.chamber,
    simplify_tolerance: "0.0005",
    geometry_role: "display"
  });
  if (options.state) params.set("state", options.state);
  if (options.boundarySet) params.set("boundary_set", options.boundarySet);
  if (options.includeGeometry === false) params.set("include_geometry", "false");
  return fetchJson<ElectorateFeatureCollection>(
    apiUrl("/api/map/electorates", params),
    options.signal
  );
}

export async function fetchCoverage(signal?: AbortSignal): Promise<CoverageResponse> {
  return fetchJson<CoverageResponse>(apiUrl("/api/coverage"), signal);
}

export async function fetchStateLocalSummary(options: {
  level?: "state" | "council" | "local";
  limit?: number;
  signal?: AbortSignal;
}): Promise<StateLocalSummaryResponse> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 8)
  });
  if (options.level) params.set("level", options.level);
  return fetchJson<StateLocalSummaryResponse>(
    apiUrl("/api/state-local/summary", params),
    options.signal
  );
}

export async function fetchStateLocalRecords(options: {
  level?: "state" | "council" | "local";
  flowKind?:
    | "act_annual_free_facilities_use"
    | "act_annual_gift_in_kind"
    | "act_annual_gift_of_money"
    | "act_annual_receipt"
    | "act_gift_in_kind"
    | "act_gift_of_money"
    | "nt_annual_debt"
    | "nt_annual_gift"
    | "nt_annual_receipt"
    | "nt_donor_return_donation"
    | "qld_gift"
    | "qld_electoral_expenditure"
    | "sa_annual_political_expenditure_return_summary"
    | "sa_associated_entity_return_summary"
    | "sa_candidate_campaign_donations_return_summary"
    | "sa_capped_expenditure_return_summary"
    | "sa_donor_return_summary"
    | "sa_political_party_return_summary"
    | "sa_prescribed_expenditure_return_summary"
    | "sa_special_large_gift_return_summary"
    | "sa_third_party_capped_expenditure_return_summary"
    | "sa_third_party_return_summary"
    | "tas_reportable_donation"
    | "tas_reportable_loan"
    | "vic_administrative_funding_entitlement"
    | "vic_policy_development_funding_payment"
    | "vic_public_funding_payment"
    | "wa_political_contribution";
  cursor?: string;
  limit?: number;
  signal?: AbortSignal;
}): Promise<StateLocalRecordsResponse> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 25)
  });
  if (options.level) params.set("level", options.level);
  if (options.flowKind) params.set("flow_kind", options.flowKind);
  if (options.cursor) params.set("cursor", options.cursor);
  return fetchJson<StateLocalRecordsResponse>(
    apiUrl("/api/state-local/records", params),
    options.signal
  );
}

export async function fetchRepresentativeProfile(
  personId: number,
  signal?: AbortSignal
): Promise<RepresentativeProfile> {
  return fetchJson<RepresentativeProfile>(apiUrl(`/api/representatives/${personId}`), signal);
}

export async function fetchRepresentativeEvidence(options: {
  personId: number;
  group?: "direct" | "campaign_support";
  eventFamily?: string;
  cursor?: string;
  limit?: number;
  signal?: AbortSignal;
}): Promise<RepresentativeEvidenceResponse> {
  const params = new URLSearchParams({
    group: options.group ?? "direct",
    limit: String(options.limit ?? 25)
  });
  if (options.eventFamily) params.set("event_family", options.eventFamily);
  if (options.cursor) params.set("cursor", options.cursor);
  return fetchJson<RepresentativeEvidenceResponse>(
    apiUrl(`/api/representatives/${options.personId}/evidence`, params),
    options.signal
  );
}

export async function fetchEntityProfile(
  entityId: number | string,
  signal?: AbortSignal
): Promise<EntityProfile> {
  return fetchJson<EntityProfile>(apiUrl(`/api/entities/${entityId}`), signal);
}

export async function fetchPartyProfile(
  partyId: number | string,
  signal?: AbortSignal
): Promise<PartyProfile> {
  return fetchJson<PartyProfile>(apiUrl(`/api/parties/${partyId}`), signal);
}

export async function fetchInfluenceGraph(
  options: {
    personId?: number | string;
    partyId?: number | string;
    entityId?: number | string;
    includeCandidates?: boolean;
    limit?: number;
    signal?: AbortSignal;
  }
): Promise<InfluenceGraph> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 80)
  });
  if (options.personId !== undefined) params.set("person_id", String(options.personId));
  if (options.partyId !== undefined) params.set("party_id", String(options.partyId));
  if (options.entityId !== undefined) params.set("entity_id", String(options.entityId));
  if (options.includeCandidates) params.set("include_candidates", "true");
  return fetchJson<InfluenceGraph>(
    apiUrl("/api/graph/influence", params),
    options.signal
  );
}

export async function searchDatabase(
  query: string,
  signal?: AbortSignal
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: "8" });
  for (const type of [
    "representative",
    "electorate",
    "party",
    "entity",
    "sector",
    "policy_topic",
    "postcode"
  ]) {
    params.append("types", type);
  }
  return fetchJson<SearchResponse>(apiUrl("/api/search", params), signal);
}
