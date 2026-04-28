import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Banknote,
  Building2,
  CircleDot,
  Landmark,
  Layers,
  Loader2,
  MapPin,
  Search,
  Users
} from "lucide-react";
import {
  fetchCoverage,
  fetchElectorateMap,
  fetchEntityProfile,
  fetchInfluenceGraph,
  fetchPartyProfile,
  fetchRepresentativeProfile,
  searchDatabase
} from "./api";
import { MapCanvas } from "./components/MapCanvas";
import { DetailsPanel } from "./components/DetailsPanel";
import { EntityProfilePanel } from "./components/EntityProfilePanel";
import { InfluenceGraphPanel } from "./components/InfluenceGraphPanel";
import { PartyProfilePanel } from "./components/PartyProfilePanel";
import {
  AUSTRALIA_BOUNDS,
  electorateColor,
  findFeatureByResult,
  formatMoney,
  senateRegionColor
} from "./map";
import type {
  CoverageResponse,
  ElectorateFeature,
  EntityProfile,
  InfluenceGraph,
  LoadState,
  PartyProfile,
  RepresentativeProfile,
  SearchResult
} from "./types";

const states = ["All", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"];
type DataLevel = "federal" | "state" | "council";
type GraphRoot = {
  kind: "person" | "party" | "entity";
  id: number | string;
  label: string;
  includeCandidates: boolean;
};

const levelLabels: Record<DataLevel, string> = {
  federal: "Federal",
  state: "State",
  council: "Council"
};

function App() {
  const [features, setFeatures] = useState<ElectorateFeature[]>([]);
  const [selectedFeature, setSelectedFeature] = useState<ElectorateFeature | null>(null);
  const [mapCaveat, setMapCaveat] = useState("");
  const [dataLevel, setDataLevel] = useState<DataLevel>("federal");
  const [stateFilter, setStateFilter] = useState("All");
  const [chamber, setChamber] = useState<"house" | "senate">("house");
  const [mapStatus, setMapStatus] = useState<LoadState>("idle");
  const [mapError, setMapError] = useState("");
  const [query, setQuery] = useState("");
  const [searchStatus, setSearchStatus] = useState<LoadState>("idle");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchCaveat, setSearchCaveat] = useState("");
  const [selectedSearchResult, setSelectedSearchResult] = useState<SearchResult | null>(null);
  const [pendingSearchResult, setPendingSearchResult] = useState<SearchResult | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [coverageStatus, setCoverageStatus] = useState<LoadState>("idle");
  const [selectedPersonId, setSelectedPersonId] = useState<number | null>(null);
  const [contactPersonId, setContactPersonId] = useState<number | null>(null);
  const [representativeProfileRefreshKey, setRepresentativeProfileRefreshKey] = useState(0);
  const [representativeProfile, setRepresentativeProfile] =
    useState<RepresentativeProfile | null>(null);
  const [representativeProfileStatus, setRepresentativeProfileStatus] =
    useState<LoadState>("idle");
  const [entityProfile, setEntityProfile] = useState<EntityProfile | null>(null);
  const [entityProfileStatus, setEntityProfileStatus] = useState<LoadState>("idle");
  const [entityProfileError, setEntityProfileError] = useState("");
  const [partyProfile, setPartyProfile] = useState<PartyProfile | null>(null);
  const [partyProfileStatus, setPartyProfileStatus] = useState<LoadState>("idle");
  const [partyProfileError, setPartyProfileError] = useState("");
  const [graphRoot, setGraphRoot] = useState<GraphRoot | null>(null);
  const [influenceGraph, setInfluenceGraph] = useState<InfluenceGraph | null>(null);
  const [influenceGraphStatus, setInfluenceGraphStatus] = useState<LoadState>("idle");
  const [influenceGraphError, setInfluenceGraphError] = useState("");

  useEffect(() => {
    if (dataLevel !== "federal") {
      setFeatures([]);
      setSelectedFeature(null);
      setMapStatus("ready");
      setMapError("");
      setMapCaveat(
        `${levelLabels[dataLevel]} data is part of the planned expansion. The current loaded dataset is Commonwealth/federal.`
      );
      return;
    }
    const controller = new AbortController();
    setMapStatus("loading");
    setMapError("");
    fetchElectorateMap({
      chamber,
      state: stateFilter === "All" ? undefined : stateFilter,
      includeGeometry: true,
      signal: controller.signal
    })
      .then((payload) => {
        setFeatures(payload.features);
        setMapCaveat(payload.caveat);
        setMapStatus("ready");
        setSelectedFeature((current) => {
          if (!current) return payload.features[0] ?? null;
          return payload.features.find((feature) => feature.id === current.id) ?? payload.features[0] ?? null;
        });
      })
      .catch((error: Error) => {
        if (controller.signal.aborted) return;
        setMapStatus("error");
        setMapError(error.message);
      });
    return () => controller.abort();
  }, [chamber, dataLevel, stateFilter]);

  useEffect(() => {
    const controller = new AbortController();
    setCoverageStatus("loading");
    fetchCoverage(controller.signal)
      .then((payload) => {
        setCoverage(payload);
        setCoverageStatus("ready");
      })
      .catch(() => {
        if (!controller.signal.aborted) setCoverageStatus("error");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!pendingSearchResult || dataLevel !== "federal") return;
    const feature = findFeatureByResult(pendingSearchResult.id, pendingSearchResult.type, features);
    if (!feature) return;
    setSelectedFeature(feature);
    setPendingSearchResult(null);
  }, [dataLevel, features, pendingSearchResult]);

  useEffect(() => {
    const firstRepresentative = selectedFeature?.properties.current_representatives[0];
    setSelectedPersonId(firstRepresentative?.person_id ?? null);
    setContactPersonId(null);
  }, [selectedFeature]);

  useEffect(() => {
    if (!selectedPersonId) {
      setRepresentativeProfile(null);
      setRepresentativeProfileStatus("idle");
      return;
    }
    const controller = new AbortController();
    setRepresentativeProfileStatus("loading");
    fetchRepresentativeProfile(selectedPersonId, controller.signal)
      .then((payload) => {
        setRepresentativeProfile(payload);
        setRepresentativeProfileStatus("ready");
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setRepresentativeProfile(null);
        setRepresentativeProfileStatus("error");
      });
    return () => controller.abort();
  }, [representativeProfileRefreshKey, selectedPersonId]);

  useEffect(() => {
    const cleaned = query.trim();
    if (dataLevel !== "federal" || cleaned.length < 3) {
      setSearchResults([]);
      setSearchStatus("idle");
      setSelectedSearchResult(null);
      return;
    }
    const controller = new AbortController();
    const handle = window.setTimeout(() => {
      setSearchStatus("loading");
      searchDatabase(cleaned, controller.signal)
        .then((payload) => {
          setSearchResults(payload.results);
          setSearchCaveat(payload.caveat);
          setSearchStatus("ready");
        })
        .catch((error: Error) => {
          if (controller.signal.aborted) return;
          setSearchStatus("error");
          setSearchCaveat(error.message);
        });
    }, 180);
    return () => {
      controller.abort();
      window.clearTimeout(handle);
    };
  }, [dataLevel, query]);

  useEffect(() => {
    if (selectedSearchResult?.type !== "entity") {
      setEntityProfile(null);
      setEntityProfileStatus("idle");
      setEntityProfileError("");
      return;
    }
    const controller = new AbortController();
    setEntityProfile(null);
    setEntityProfileStatus("loading");
    setEntityProfileError("");
    fetchEntityProfile(selectedSearchResult.id, controller.signal)
      .then((payload) => {
        setEntityProfile(payload);
        setEntityProfileStatus("ready");
      })
      .catch((error: Error) => {
        if (controller.signal.aborted) return;
        setEntityProfile(null);
        setEntityProfileError(error.message);
        setEntityProfileStatus("error");
      });
    return () => controller.abort();
  }, [selectedSearchResult]);

  useEffect(() => {
    if (selectedSearchResult?.type !== "party") {
      setPartyProfile(null);
      setPartyProfileStatus("idle");
      setPartyProfileError("");
      return;
    }
    const controller = new AbortController();
    setPartyProfile(null);
    setPartyProfileStatus("loading");
    setPartyProfileError("");
    fetchPartyProfile(selectedSearchResult.id, controller.signal)
      .then((payload) => {
        setPartyProfile(payload);
        setPartyProfileStatus("ready");
      })
      .catch((error: Error) => {
        if (controller.signal.aborted) return;
        setPartyProfile(null);
        setPartyProfileError(error.message);
        setPartyProfileStatus("error");
      });
    return () => controller.abort();
  }, [selectedSearchResult]);

  useEffect(() => {
    if (!graphRoot) {
      setInfluenceGraph(null);
      setInfluenceGraphStatus("idle");
      setInfluenceGraphError("");
      return;
    }
    const controller = new AbortController();
    setInfluenceGraph(null);
    setInfluenceGraphStatus("loading");
    setInfluenceGraphError("");
    fetchInfluenceGraph({
      personId: graphRoot.kind === "person" ? graphRoot.id : undefined,
      partyId: graphRoot.kind === "party" ? graphRoot.id : undefined,
      entityId: graphRoot.kind === "entity" ? graphRoot.id : undefined,
      includeCandidates: graphRoot.includeCandidates,
      limit: 80,
      signal: controller.signal
    })
      .then((payload) => {
        setInfluenceGraph(payload);
        setInfluenceGraphStatus("ready");
      })
      .catch((error: Error) => {
        if (controller.signal.aborted) return;
        setInfluenceGraph(null);
        setInfluenceGraphError(error.message);
        setInfluenceGraphStatus("error");
      });
    return () => controller.abort();
  }, [graphRoot]);

  const totals = useMemo(() => {
    return features.reduce(
      (acc, feature) => {
        acc.electorates += 1;
        acc.representatives += feature.properties.current_representative_count || 0;
        acc.events +=
          feature.properties.current_representative_lifetime_influence_event_count || 0;
        acc.reported +=
          feature.properties.current_representative_lifetime_reported_amount_total || 0;
        return acc;
      },
      { electorates: 0, representatives: 0, events: 0, reported: 0 }
    );
  }, [features]);

  function selectSearchResult(result: SearchResult) {
    const feature = findFeatureByResult(result.id, result.type, features);
    if (feature) {
      setSelectedFeature(feature);
      setPendingSearchResult(null);
      setSelectedSearchResult(null);
      setEntityProfile(null);
      setEntityProfileStatus("idle");
      setPartyProfile(null);
      setPartyProfileStatus("idle");
      return;
    }

    setSelectedSearchResult(result);
    const resultChamber = stringMetadata(result, "chamber")?.toLowerCase();
    const resultState = stringMetadata(result, "state_or_territory")?.toUpperCase();
    if (resultChamber === "house" || resultChamber === "senate") {
      setDataLevel("federal");
      setChamber(resultChamber);
      if (resultState && states.includes(resultState)) {
        setStateFilter(resultState);
      }
      setPendingSearchResult(result);
    }
  }

  function selectRepresentativeForContact(personId: number) {
    setSelectedPersonId(personId);
    setContactPersonId(personId);
    setRepresentativeProfileRefreshKey((current) => current + 1);
  }

  function openRepresentativeGraph(personId: number, label: string) {
    setGraphRoot({ kind: "person", id: personId, label, includeCandidates: false });
  }

  function toggleGraphCandidates(includeCandidates: boolean) {
    setGraphRoot((current) => (
      current?.kind === "party" ? { ...current, includeCandidates } : current
    ));
  }

  return (
    <main className="app-shell">
      <section className="map-stage" aria-label="Australian political influence map">
        <MapCanvas
          features={features}
          selectedFeature={selectedFeature}
          initialBounds={AUSTRALIA_BOUNDS}
          onSelectFeature={setSelectedFeature}
        />
        <div className="map-topbar">
          <div className="brand-block">
            <Landmark size={24} aria-hidden="true" />
            <div>
              <p className="eyebrow">
                {dataLevel === "federal"
                  ? `${chamber === "senate" ? "Federal Senate" : "Federal House"} beta`
                  : `${levelLabels[dataLevel]} pipeline planned`}
              </p>
              <h1>Political Influence Explorer</h1>
            </div>
          </div>
          <div className="status-pill" data-state={mapStatus}>
            {mapStatus === "loading" ? <Loader2 size={16} className="spin" /> : <CircleDot size={16} />}
            <span>
              {mapStatus === "loading"
                ? "Loading records"
                : dataLevel === "federal"
                  ? `${features.length} map features`
                  : "Expansion scope"}
            </span>
          </div>
        </div>

        <aside className="control-panel" aria-label="Map controls and search">
          <div className="level-control" role="group" aria-label="Government level">
            {(["federal", "state", "council"] as DataLevel[]).map((level) => (
              <button
                key={level}
                type="button"
                className={dataLevel === level ? "active" : ""}
                aria-pressed={dataLevel === level}
                onClick={() => setDataLevel(level)}
              >
                {levelLabels[level]}
              </button>
            ))}
          </div>

          <div className="search-box">
            <Search size={18} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              disabled={dataLevel !== "federal"}
              placeholder={
                dataLevel === "federal"
                  ? "Search representatives, electorates, parties, entities, sectors"
                  : `${levelLabels[dataLevel]} search will activate after ingestion`
              }
              aria-label="Search the political influence database"
            />
            {searchStatus === "loading" && <Loader2 size={16} className="spin" aria-hidden="true" />}
          </div>

          <div className="toolbar-row" aria-label="Map filters">
            <div className="segmented" role="group" aria-label="Chamber">
              <button
                type="button"
                className={chamber === "house" ? "active" : ""}
                aria-pressed={chamber === "house"}
                disabled={dataLevel !== "federal"}
                onClick={() => setChamber("house")}
              >
                House
              </button>
              <button
                type="button"
                className={chamber === "senate" ? "active" : ""}
                aria-pressed={chamber === "senate"}
                disabled={dataLevel !== "federal"}
                onClick={() => setChamber("senate")}
              >
                Senate
              </button>
            </div>
            <label className="select-label">
              <Layers size={16} aria-hidden="true" />
              <select
                value={stateFilter}
                disabled={dataLevel !== "federal"}
                onChange={(event) => setStateFilter(event.target.value)}
              >
                {states.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {dataLevel !== "federal" && (
            <div className="scope-notice">
              <strong>{levelLabels[dataLevel]} scope is reserved.</strong>
              <span>
                The interface is ready for this level, but the source pipelines and
                database layers are not loaded yet.
              </span>
            </div>
          )}

          <div className="metric-grid" aria-label="Current map totals">
            <Metric
              icon={<MapPin size={17} />}
              label={chamber === "senate" ? "Regions" : "Electorates"}
              value={totals.electorates.toLocaleString("en-AU")}
            />
            <Metric icon={<Users size={17} />} label="Reps" value={totals.representatives.toLocaleString("en-AU")} />
            <Metric icon={<Building2 size={17} />} label="Rep records" value={totals.events.toLocaleString("en-AU")} />
            <Metric icon={<Banknote size={17} />} label="Rep reported" value={formatMoney(totals.reported)} />
          </div>

          <CoveragePanel coverage={coverage} status={coverageStatus} />

          {mapError && (
            <div className="inline-alert" role="alert">
              <AlertCircle size={16} />
              <span>{mapError}</span>
            </div>
          )}

          {dataLevel === "federal" && query.trim().length >= 3 && (
            <div className="search-results" aria-label="Search results" aria-live="polite">
              {searchStatus === "loading" && (
                <p className="muted inline-loading">
                  <Loader2 size={14} className="spin" aria-hidden="true" />
                  Searching
                </p>
              )}
              {searchStatus === "error" && (
                <p className="muted">Search failed: {searchCaveat}</p>
              )}
              {searchStatus === "ready" && searchResults.length === 0 && (
                <p className="muted">No source-backed results matched this search.</p>
              )}
              {selectedSearchResult?.type === "entity" && (
                <EntityProfilePanel
                  profile={entityProfile}
                  status={entityProfileStatus}
                  error={entityProfileError}
                  onOpenGraph={(entityId, label) =>
                    setGraphRoot({ kind: "entity", id: entityId, label, includeCandidates: false })
                  }
                  onClose={() => setSelectedSearchResult(null)}
                />
              )}
              {selectedSearchResult?.type === "party" && (
                <PartyProfilePanel
                  profile={partyProfile}
                  status={partyProfileStatus}
                  error={partyProfileError}
                  onOpenGraph={(partyId, label) =>
                    setGraphRoot({ kind: "party", id: partyId, label, includeCandidates: false })
                  }
                  onClose={() => setSelectedSearchResult(null)}
                />
              )}
              {searchResults.map((result) => (
                <button
                  type="button"
                  key={`${result.type}:${result.id}`}
                  className="search-result"
                  data-selected={
                    selectedSearchResult?.type === result.type &&
                    String(selectedSearchResult.id) === String(result.id)
                  }
                  onClick={() => selectSearchResult(result)}
                >
                  <span className="result-type">{result.type.replace("_", " ")}</span>
                  <strong>{result.label}</strong>
                  <small>{result.subtitle || "Source-backed record"}</small>
                </button>
              ))}
              {selectedSearchResult &&
                selectedSearchResult.type !== "entity" &&
                selectedSearchResult.type !== "party" && (
                <div className="search-selection-note">
                  <strong>{selectedSearchResult.label}</strong>
                  <span>
                    This {selectedSearchResult.type.replace("_", " ")} result is in the database,
                    but it is not yet a map drilldown target. Use it as a discovery lead while
                    party, sector, and topic detail panels are built.
                  </span>
                </div>
              )}
              {searchCaveat && <p className="caveat compact">{searchCaveat}</p>}
            </div>
          )}
        </aside>

        <DetailsPanel
          feature={selectedFeature}
          caveat={mapCaveat}
          partyColor={
            selectedFeature?.properties.chamber === "senate"
              ? senateRegionColor(selectedFeature.properties.state_or_territory)
              : electorateColor(selectedFeature?.properties.party_name)
          }
          selectedPersonId={selectedPersonId}
          contactPersonId={contactPersonId}
          representativeProfile={representativeProfile}
          representativeProfileStatus={representativeProfileStatus}
          onSelectRepresentative={selectRepresentativeForContact}
          onOpenRepresentativeGraph={openRepresentativeGraph}
          onCloseContact={() => setContactPersonId(null)}
        />
        <InfluenceGraphPanel
          graph={influenceGraph}
          root={graphRoot}
          status={influenceGraphStatus}
          error={influenceGraphError}
          onToggleCandidates={toggleGraphCandidates}
          onClose={() => setGraphRoot(null)}
        />
      </section>
    </main>
  );
}

function Metric({
  icon,
  label,
  value
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="metric">
      <span className="metric-icon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CoveragePanel({
  coverage,
  status
}: {
  coverage: CoverageResponse | null;
  status: LoadState;
}) {
  if (status === "loading") {
    return (
      <div className="coverage-panel" aria-label="Database coverage">
        <div className="coverage-header">
          <strong>Database coverage</strong>
          <span>Loading</span>
        </div>
      </div>
    );
  }
  if (!coverage) return null;

  const totalEvents = numberValue(coverage.influence_event_totals.event_count);
  const personLinkedEvents = numberValue(
    coverage.influence_event_totals.person_linked_event_count
  );
  const moneyEvents = numberValue(
    coverage.influence_events_by_family.find((row) => row.event_family === "money")
      ?.event_count
  );
  const reportedTotal = numberValue(coverage.influence_event_totals.reported_amount_total);
  const stateLayer = coverage.coverage_layers.find((layer) => layer.level === "state");
  const councilLayer = coverage.coverage_layers.find((layer) => layer.level === "council");

  return (
    <div className="coverage-panel" aria-label="Database coverage">
      <div className="coverage-header">
        <strong>Database coverage</strong>
        <span>{coverage.active_country} · {coverage.active_levels.join(", ")}</span>
      </div>
      <div className="coverage-grid">
        <span>
          <small>All influence rows</small>
          <strong>{totalEvents.toLocaleString("en-AU")}</strong>
        </span>
        <span>
          <small>Money rows</small>
          <strong>{moneyEvents.toLocaleString("en-AU")}</strong>
        </span>
        <span>
          <small>Person-linked</small>
          <strong>{personLinkedEvents.toLocaleString("en-AU")}</strong>
        </span>
        <span>
          <small>DB reported total</small>
          <strong>{formatMoney(reportedTotal)}</strong>
        </span>
      </div>
      <div className="coverage-status-row">
        <span>State: {stateLayer?.status || "planned"}</span>
        <span>Council: {councilLayer?.status || "planned"}</span>
      </div>
      <details className="coverage-caveat">
        <summary>Coverage caveat</summary>
        <p>{coverage.caveat}</p>
      </details>
    </div>
  );
}

function numberValue(value: number | string | null | undefined): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export default App;

function stringMetadata(result: SearchResult, key: string): string | null {
  const value = result.metadata[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
