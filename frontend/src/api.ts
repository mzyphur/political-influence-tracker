import type {
  CoverageResponse,
  ElectorateFeatureCollection,
  EntityProfile,
  RepresentativeProfile,
  SearchResponse
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
    throw new Error(`${response.status} ${response.statusText}`);
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
    simplify_tolerance: "0.0005"
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

export async function fetchRepresentativeProfile(
  personId: number,
  signal?: AbortSignal
): Promise<RepresentativeProfile> {
  return fetchJson<RepresentativeProfile>(apiUrl(`/api/representatives/${personId}`), signal);
}

export async function fetchEntityProfile(
  entityId: number | string,
  signal?: AbortSignal
): Promise<EntityProfile> {
  return fetchJson<EntityProfile>(apiUrl(`/api/entities/${entityId}`), signal);
}

export async function searchDatabase(
  query: string,
  signal?: AbortSignal
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: "8" });
  for (const type of ["representative", "electorate", "party", "entity", "sector", "policy_topic"]) {
    params.append("types", type);
  }
  return fetchJson<SearchResponse>(apiUrl("/api/search", params), signal);
}
