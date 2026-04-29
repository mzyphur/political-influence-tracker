import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  BadgeCheck,
  Banknote,
  BookOpen,
  Building2,
  CircleDot,
  Gift,
  Landmark,
  Layers,
  Loader2,
  MapPin,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightOpen,
  ReceiptText,
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
  fetchStateLocalRecords,
  fetchStateLocalSummary,
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
  SearchResponse,
  SearchResult,
  StateLocalSummaryContextRow,
  StateLocalSummaryEntityRow,
  StateLocalSummaryRecord,
  StateLocalSummaryResponse
} from "./types";

const states = ["All", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"];
type DataLevel = "federal" | "state" | "council";
type GraphRoot = {
  kind: "person" | "party" | "entity";
  id: number | string;
  label: string;
  includeCandidates: boolean;
};
type StateLocalRecordPage = {
  records: StateLocalSummaryRecord[];
  status: LoadState;
  error: string;
  hasMore: boolean | null;
  nextCursor: string | null;
  totalCount: number | null;
};
type DisplayLandMask = NonNullable<CoverageResponse["display_land_masks"]>[number];

const emptyStateLocalRecordPage = (): StateLocalRecordPage => ({
  records: [],
  status: "idle",
  error: "",
  hasMore: null,
  nextCursor: null,
  totalCount: null
});

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
  const [searchLimitations, setSearchLimitations] = useState<SearchResponse["limitations"]>([]);
  const [searchCaveat, setSearchCaveat] = useState("");
  const [selectedSearchResult, setSelectedSearchResult] = useState<SearchResult | null>(null);
  const [pendingSearchResult, setPendingSearchResult] = useState<SearchResult | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [coverageStatus, setCoverageStatus] = useState<LoadState>("idle");
  const [stateLocalSummary, setStateLocalSummary] =
    useState<StateLocalSummaryResponse | null>(null);
  const [stateLocalSummaryStatus, setStateLocalSummaryStatus] =
    useState<LoadState>("idle");
  const [stateLocalSummaryError, setStateLocalSummaryError] = useState("");
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
  const [controlsCollapsed, setControlsCollapsed] = useState(false);
  const [detailsCollapsed, setDetailsCollapsed] = useState(false);
  const controlsPeekButtonRef = useRef<HTMLButtonElement | null>(null);
  const controlsCollapseButtonRef = useRef<HTMLButtonElement | null>(null);
  const detailsPeekButtonRef = useRef<HTMLButtonElement | null>(null);
  const detailsCollapseButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousControlsCollapsedRef = useRef(controlsCollapsed);
  const previousDetailsCollapsedRef = useRef(detailsCollapsed);
  const selectedCoverageLayer = coverage?.coverage_layers.find(
    (item) => item.level === dataLevel
  );
  const selectedCoverageRows = numberValue(selectedCoverageLayer?.counts.money_flow_rows);
  const selectedLevelHasPartialData = dataLevel !== "federal" && selectedCoverageRows > 0;
  const hasPostcodeLimitations = searchLimitations.some(
    (limitation) => limitation.feature === "postcode_search"
  );

  useEffect(() => {
    if (dataLevel !== "federal") {
      const layer = coverage?.coverage_layers.find((item) => item.level === dataLevel);
      const rowCount = numberValue(layer?.counts.money_flow_rows);
      const activeText = rowCount
        ? `${levelLabels[dataLevel]} source data is partially active (${rowCount.toLocaleString("en-AU")} QLD disclosure rows loaded). Map drilldown for this level is still being built.`
        : `${levelLabels[dataLevel]} data is part of the planned expansion. The current map is Commonwealth/federal.`;
      setFeatures([]);
      setSelectedFeature(null);
      setMapStatus("ready");
      setMapError("");
      setMapCaveat(activeText);
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
          if (pendingSearchResult) return null;
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
  }, [chamber, coverage, dataLevel, stateFilter]);

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
    if (dataLevel === "federal") {
      setStateLocalSummary(null);
      setStateLocalSummaryStatus("idle");
      setStateLocalSummaryError("");
      return;
    }
    const controller = new AbortController();
    setStateLocalSummary(null);
    setStateLocalSummaryStatus("loading");
    setStateLocalSummaryError("");
    fetchStateLocalSummary({
      level: dataLevel,
      limit: 5,
      signal: controller.signal
    })
      .then((payload) => {
        setStateLocalSummary(payload);
        setStateLocalSummaryStatus("ready");
      })
      .catch((error: Error) => {
        if (controller.signal.aborted) return;
        setStateLocalSummary(null);
        setStateLocalSummaryError(error.message);
        setStateLocalSummaryStatus("error");
      });
    return () => controller.abort();
  }, [dataLevel]);

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
      setSearchLimitations([]);
      setSearchStatus("idle");
      return;
    }
    const controller = new AbortController();
    const handle = window.setTimeout(() => {
      setSearchStatus("loading");
      searchDatabase(cleaned, controller.signal)
        .then((payload) => {
          setSearchResults(payload.results);
          setSearchLimitations(payload.limitations);
          setSearchCaveat(payload.caveat);
          setSearchStatus("ready");
        })
        .catch((error: Error) => {
          if (controller.signal.aborted) return;
          setSearchStatus("error");
          setSearchLimitations([]);
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

  useEffect(() => {
    if (previousControlsCollapsedRef.current !== controlsCollapsed) {
      window.requestAnimationFrame(() => {
        if (controlsCollapsed) {
          controlsPeekButtonRef.current?.focus();
        } else {
          controlsCollapseButtonRef.current?.focus();
        }
      });
    }
    previousControlsCollapsedRef.current = controlsCollapsed;
  }, [controlsCollapsed]);

  useEffect(() => {
    if (previousDetailsCollapsedRef.current !== detailsCollapsed) {
      window.requestAnimationFrame(() => {
        if (detailsCollapsed) {
          detailsPeekButtonRef.current?.focus();
        } else {
          detailsCollapseButtonRef.current?.focus();
        }
      });
    }
    previousDetailsCollapsedRef.current = detailsCollapsed;
  }, [detailsCollapsed]);

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
      setSelectedSearchResult(result.type === "postcode" ? result : null);
      setEntityProfile(null);
      setEntityProfileStatus("idle");
      setPartyProfile(null);
      setPartyProfileStatus("idle");
      return;
    }

    setSelectedSearchResult(result);
    const resultChamber = stringMetadata(result, "chamber")?.toLowerCase();
    const resultState = stringMetadata(result, "state_or_territory")?.toUpperCase();
    if (result.type === "postcode") {
      setDataLevel("federal");
      setChamber("house");
      setSelectedFeature(null);
      if (resultState && states.includes(resultState)) {
        setStateFilter(resultState);
      }
      setPendingSearchResult(result);
      return;
    }
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

  function openPartyProfile(partyId: number, label: string) {
    setSelectedSearchResult({
      type: "party",
      id: partyId,
      label,
      subtitle: "Selected from current representation",
      rank: 30,
      metadata: { id: partyId }
    });
  }

  function openEntityProfile(entityId: number, label: string) {
    setSelectedSearchResult({
      type: "entity",
      id: entityId,
      label,
      subtitle: "Selected from QLD ECQ disclosure summary",
      rank: 25,
      metadata: { id: entityId }
    });
  }

  function toggleGraphCandidates(includeCandidates: boolean) {
    setGraphRoot((current) => (
      current?.kind === "party" ? { ...current, includeCandidates } : current
    ));
  }

  return (
    <main className="app-shell">
      <section
        className="map-stage"
        data-details-collapsed={detailsCollapsed}
        aria-label="Australian political influence map"
      >
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
                  : selectedLevelHasPartialData
                    ? `${levelLabels[dataLevel]} QLD summary beta`
                    : `${levelLabels[dataLevel]} pipeline planned`}
              </p>
              <h1>Political Influence Explorer</h1>
            </div>
            <a
              className="methodology-link"
              href="/methodology.html"
              target="_blank"
              rel="noreferrer"
              aria-label="Open methodology companion page"
              title="Methodology"
            >
              <BookOpen size={16} aria-hidden="true" />
              <span>Method</span>
            </a>
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

        {controlsCollapsed ? (
          <button
            ref={controlsPeekButtonRef}
            type="button"
            className="panel-peek-button panel-peek-left"
            aria-label="Open map controls"
            aria-expanded={false}
            title="Open map controls"
            onClick={() => setControlsCollapsed(false)}
          >
            <PanelLeftOpen size={18} aria-hidden="true" />
            <span>Controls</span>
          </button>
        ) : (
          <aside className="control-panel" id="map-controls-panel" aria-label="Map controls and search">
            <div className="control-panel-heading">
              <span>Explore</span>
              <button
                ref={controlsCollapseButtonRef}
                type="button"
                className="panel-collapse-button control-collapse-button"
                aria-label="Collapse map controls"
                aria-controls="map-controls-panel"
                aria-expanded={true}
                title="Collapse map controls"
                onClick={() => setControlsCollapsed(true)}
              >
                <PanelLeftClose size={16} aria-hidden="true" />
              </button>
            </div>
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
                  : selectedLevelHasPartialData
                    ? `${levelLabels[dataLevel]} map/search drilldown is pending`
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

          {dataLevel === "federal" ? (
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
          ) : (
            <StateLocalSummaryPanel
              level={dataLevel}
              summary={stateLocalSummary}
              status={stateLocalSummaryStatus}
              error={stateLocalSummaryError}
              onOpenEntityProfile={openEntityProfile}
            />
          )}

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
              {searchStatus === "ready" && searchResults.length === 0 && !hasPostcodeLimitations && (
                <p className="muted">No source-backed results matched this search.</p>
              )}
              {searchStatus === "ready" && searchResults.length === 0 && hasPostcodeLimitations && (
                <p className="muted">No map-linked postcode result is loaded for this search.</p>
              )}
              {searchLimitations.length > 0 && (
                <div className="search-limitations" aria-label="Search limitations">
                  {searchLimitations.map((limitation) => (
                    <p
                      className="caveat compact"
                      key={`${limitation.feature}:${limitation.status}:${limitation.message}`}
                    >
                      {limitation.message}
                    </p>
                  ))}
                </div>
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
                    {searchSelectionNote(
                      selectedSearchResult,
                      pendingSearchResult?.type === selectedSearchResult.type &&
                        String(pendingSearchResult.id) === String(selectedSearchResult.id)
                    )}
                  </span>
                </div>
              )}
              {searchCaveat && <p className="caveat compact">{searchCaveat}</p>}
            </div>
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
        </aside>
        )}

        {detailsCollapsed ? (
          <button
            ref={detailsPeekButtonRef}
            type="button"
            className="panel-peek-button panel-peek-right"
            aria-label="Open selection details"
            aria-expanded={false}
            title="Open selection details"
            onClick={() => setDetailsCollapsed(false)}
          >
            <PanelRightOpen size={18} aria-hidden="true" />
            <span>Details</span>
          </button>
        ) : (
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
            onOpenPartyProfile={openPartyProfile}
            onCloseContact={() => setContactPersonId(null)}
            onCollapse={() => setDetailsCollapsed(true)}
            collapseButtonRef={detailsCollapseButtonRef}
          />
        )}
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

function StateLocalSummaryPanel({
  level,
  summary,
  status,
  error,
  onOpenEntityProfile
}: {
  level: DataLevel;
  summary: StateLocalSummaryResponse | null;
  status: LoadState;
  error: string;
  onOpenEntityProfile: (entityId: number, label: string) => void;
}) {
  const levelName = level === "council" ? "local/council" : level;
  const [recordPage, setRecordPage] = useState<StateLocalRecordPage>(
    emptyStateLocalRecordPage
  );
  const recordFetchRef = useRef<AbortController | null>(null);
  const summaryRecentRows = summary?.recent_records ?? [];
  const mergedRecentRows = useMemo(
    () => mergeStateLocalRecords(summaryRecentRows, recordPage.records),
    [recordPage.records, summaryRecentRows]
  );
  const nextRecordCursor =
    recordPage.nextCursor ?? mergedRecentRows[mergedRecentRows.length - 1]?.pagination_cursor ?? null;
  const canLoadMoreRecords =
    status === "ready" &&
    Boolean(summary) &&
    mergedRecentRows.length > 0 &&
    recordPage.hasMore !== false &&
    Boolean(nextRecordCursor);

  useEffect(() => {
    recordFetchRef.current?.abort();
    setRecordPage(emptyStateLocalRecordPage());
    return () => recordFetchRef.current?.abort();
  }, [level, summary?.db_level, summary?.requested_level]);

  const loadMoreRecords = () => {
    if (!summary || !nextRecordCursor || recordPage.status === "loading") return;
    recordFetchRef.current?.abort();
    const controller = new AbortController();
    recordFetchRef.current = controller;
    setRecordPage((current) => ({
      ...current,
      status: "loading",
      error: ""
    }));
    fetchStateLocalRecords({
      level: level === "council" ? "council" : "state",
      cursor: nextRecordCursor,
      limit: 25,
      signal: controller.signal
    })
      .then((payload) => {
        setRecordPage((current) => ({
          records: mergeStateLocalRecords(current.records, payload.records),
          status: "ready",
          error: "",
          hasMore: payload.has_more,
          nextCursor: payload.next_cursor,
          totalCount: payload.total_count
        }));
      })
      .catch((loadError: Error) => {
        if (controller.signal.aborted) return;
        setRecordPage((current) => ({
          ...current,
          status: "error",
          error: loadError.message
        }));
      });
  };

  if (status === "idle" || status === "loading") {
    return (
      <div className="state-local-summary" aria-label="State and local disclosure summary">
        <div className="state-summary-header">
          <strong>QLD ECQ disclosures</strong>
          <span>
            <Loader2 size={13} className="spin" aria-hidden="true" />
            Loading
          </span>
        </div>
      </div>
    );
  }
  if (status === "error") {
    return (
      <div className="inline-alert" role="alert">
        <AlertCircle size={16} />
        <span>QLD disclosure summary failed: {error}</span>
      </div>
    );
  }
  if (!summary || summary.totals_by_level.length === 0) {
    return (
      <div className="scope-notice">
        <strong>{levelLabels[level]} map drilldown is being built.</strong>
        <span>
          QLD ECQ disclosure ingestion is wired, but no rows were returned for this level.
        </span>
      </div>
    );
  }

  const totals = rollupStateLocalTotals(summary);
  const identifierBackedRowSides =
    totals.sourceIdentifierBacked + totals.recipientIdentifierBacked;

  return (
    <div className="state-local-summary" aria-label="State and local disclosure summary">
      <div className="state-summary-header">
        <strong>QLD ECQ disclosures</strong>
        <span>{levelName} partial data</span>
      </div>
      <div className="state-summary-grid">
        <Metric
          icon={<ReceiptText size={16} />}
          label="Rows"
          value={totals.moneyFlowCount.toLocaleString("en-AU")}
        />
        <Metric
          icon={<Gift size={16} />}
          label="Gifts"
          value={totals.giftOrDonationCount.toLocaleString("en-AU")}
        />
        <Metric
          icon={<Banknote size={16} />}
          label="Spend"
          value={totals.electoralExpenditureCount.toLocaleString("en-AU")}
        />
        <Metric
          icon={<BadgeCheck size={16} />}
          label="ID-backed sides"
          value={identifierBackedRowSides.toLocaleString("en-AU")}
        />
      </div>
      <div className="state-summary-id-row">
        <span>Source ID-backed rows</span>
        <strong>{totals.sourceIdentifierBacked.toLocaleString("en-AU")}</strong>
        <span>Recipient ID-backed rows</span>
        <strong>{totals.recipientIdentifierBacked.toLocaleString("en-AU")}</strong>
        <span>Event-backed rows</span>
        <strong>{totals.eventContextBacked.toLocaleString("en-AU")}</strong>
        <span>Local electorate-backed rows</span>
        <strong>{totals.localElectorateContextBacked.toLocaleString("en-AU")}</strong>
      </div>
      <div className="state-summary-money-row">
        <span>Gift/donation total</span>
        <strong>{formatMoney(totals.giftOrDonationReportedAmountTotal)}</strong>
        <span>Campaign spend total</span>
        <strong>{formatMoney(totals.electoralExpenditureReportedAmountTotal)}</strong>
      </div>
      <StateLocalRecentRecords
        rows={mergedRecentRows}
        totalCount={recordPage.totalCount}
        status={recordPage.status}
        error={recordPage.error}
        canLoadMore={canLoadMoreRecords}
        onLoadMore={loadMoreRecords}
      />
      <StateLocalRankList
        title="Top gift donors"
        rows={summary.top_gift_donors}
        onOpenEntityProfile={onOpenEntityProfile}
      />
      <StateLocalRankList
        title="Top gift recipients"
        rows={summary.top_gift_recipients}
        onOpenEntityProfile={onOpenEntityProfile}
      />
      <StateLocalRankList
        title="Top campaign spend actors"
        rows={summary.top_expenditure_actors}
        onOpenEntityProfile={onOpenEntityProfile}
      />
      <StateLocalContextList title="Top ECQ election events" rows={summary.top_events} />
      <StateLocalContextList
        title="Top local electorates named"
        rows={summary.top_local_electorates}
      />
      <details className="coverage-caveat">
        <summary>State/local caveat</summary>
        <p>{summary.caveat}</p>
        <p>
          Map drilldown is pending. These rows are source-family disclosure coverage,
          not claims that a current MP personally received the money.
        </p>
        <p>
          Local electorate labels are ECQ disclosure context only. They do not attribute
          a gift, donation, or campaign expenditure row to a candidate, councillor, or MP.
        </p>
      </details>
    </div>
  );
}

function StateLocalRecentRecords({
  rows,
  totalCount,
  status,
  error,
  canLoadMore,
  onLoadMore
}: {
  rows: StateLocalSummaryRecord[];
  totalCount: number | null;
  status: LoadState;
  error: string;
  canLoadMore: boolean;
  onLoadMore: () => void;
}) {
  return (
    <div className="state-summary-list state-summary-recent-list">
      <h3>Recent source rows</h3>
      {rows.length === 0 ? (
        <p className="muted">No current QLD ECQ rows returned for this slice.</p>
      ) : (
        rows.map((row) => {
          const sourceHref = safeSourceHref(row.source_final_url || row.source_url);
          const context = stateLocalRecordContext(row);
          const idSignals = [
            row.source_identifier_backed ? "source ECQ ID" : "",
            row.recipient_identifier_backed ? "recipient ECQ ID" : ""
          ].filter(Boolean);
          return (
            <div
              className="state-summary-row state-summary-record-row"
              key={row.id}
              title={stateLocalRecordTooltip(row)}
            >
              <strong>{stateLocalRecordHeadline(row)}</strong>
              <span>
                {stateLocalRecordKind(row)} · {formatMoney(row.amount)} ·{" "}
                {row.jurisdiction_level}
              </span>
              {context.length > 0 && <span>{context.join(" · ")}</span>}
              <span>
                {[row.source_row_ref, ...idSignals].filter(Boolean).join(" · ") ||
                  "Source row ref not recorded"}
                {sourceHref ? (
                  <>
                    {" · "}
                    <a href={sourceHref} target="_blank" rel="noreferrer">
                      source
                    </a>
                  </>
                ) : null}
              </span>
            </div>
          );
        })
      )}
      {rows.length > 0 && (
        <div className="state-summary-feed-footer">
          <span>
            Showing {rows.length.toLocaleString("en-AU")}
            {totalCount !== null ? ` of ${totalCount.toLocaleString("en-AU")}` : ""} loaded
            QLD rows.
          </span>
          {error && <span className="state-summary-error">Load failed: {error}</span>}
          {canLoadMore && (
            <button
              type="button"
              className="secondary-action-button"
              onClick={onLoadMore}
              disabled={status === "loading"}
            >
              {status === "loading" ? (
                <>
                  <Loader2 size={13} className="spin" aria-hidden="true" />
                  Loading
                </>
              ) : (
                "Load more rows"
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function mergeStateLocalRecords(
  baseRows: StateLocalSummaryRecord[],
  extraRows: StateLocalSummaryRecord[]
): StateLocalSummaryRecord[] {
  const seen = new Set<number>();
  const merged: StateLocalSummaryRecord[] = [];
  for (const row of [...baseRows, ...extraRows]) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    merged.push(row);
  }
  return merged;
}

function stateLocalRecordKind(row: StateLocalSummaryRecord): string {
  if (row.flow_kind === "qld_electoral_expenditure") return "Campaign spend incurred";
  return row.receipt_type || "Gift/donation row";
}

function stateLocalRecordHeadline(row: StateLocalSummaryRecord): string {
  const source = row.source_name || "Source not identified";
  if (row.flow_kind === "qld_electoral_expenditure") {
    return `${source} incurred electoral expenditure`;
  }
  return `${source} to ${row.recipient_name || "recipient not identified"}`;
}

function stateLocalRecordContext(row: StateLocalSummaryRecord): string[] {
  return [
    row.event_name,
    row.local_electorate_name,
    row.purpose_of_expenditure,
    row.description_of_goods_or_services,
    row.date_received || row.date_reported || row.financial_year
  ].filter((value): value is string => Boolean(value));
}

function stateLocalRecordTooltip(row: StateLocalSummaryRecord): string {
  return [
    `Source document ID: ${row.source_document_id}`,
    `Source: ${row.source_document_name}`,
    `Fetched: ${row.source_document_fetched_at}`,
    `SHA-256: ${row.source_document_sha256}`,
    row.source_row_ref ? `Source row: ${row.source_row_ref}` : null,
    row.transaction_kind ? `Transaction kind: ${row.transaction_kind}` : null,
    row.public_amount_counting_role
      ? `Amount counting role: ${row.public_amount_counting_role}`
      : null,
    row.flow_kind === "qld_electoral_expenditure"
      ? "Interpretation: expenditure incurred, not money received by the named actor."
      : null
  ]
    .filter(Boolean)
    .join("\n");
}

function StateLocalRankList({
  title,
  rows,
  onOpenEntityProfile
}: {
  title: string;
  rows: StateLocalSummaryEntityRow[];
  onOpenEntityProfile: (entityId: number, label: string) => void;
}) {
  return (
    <div className="state-summary-list">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="muted">No rows returned for this slice.</p>
      ) : (
        rows.map((row) => {
          const label = row.name || "Source not identified";
          const body = (
            <>
              <strong>{label}</strong>
              <span>
                {row.event_count.toLocaleString("en-AU")} records ·{" "}
                {formatMoney(row.reported_amount_total)} ·{" "}
                {row.identifier_backed ? "ECQ-backed ID" : "source free-text name"}
              </span>
            </>
          );
          if (row.entity_id) {
            return (
              <button
                type="button"
                className="state-summary-row state-summary-row-button"
                key={`${title}:${row.entity_id}`}
                onClick={() => onOpenEntityProfile(row.entity_id as number, label)}
                title={`Open entity profile for ${label}`}
              >
                {body}
              </button>
            );
          }
          return (
            <div className="state-summary-row" key={`${title}:${label}`}>
              {body}
            </div>
          );
        })
      )}
    </div>
  );
}

function StateLocalContextList({
  title,
  rows
}: {
  title: string;
  rows: StateLocalSummaryContextRow[];
}) {
  return (
    <div className="state-summary-list state-summary-context-list">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="muted">No ECQ lookup-backed context rows returned for this slice.</p>
      ) : (
        rows.slice(0, 5).map((row) => {
          const dateLabel = row.polling_date || row.start_date;
          const moneyParts = [
            `${row.money_flow_count.toLocaleString("en-AU")} records`,
            `${row.gift_or_donation_count.toLocaleString("en-AU")} gifts`,
            `${row.electoral_expenditure_count.toLocaleString("en-AU")} spend rows`
          ];
          return (
            <div className="state-summary-row" key={`${title}:${row.external_id ?? row.name}`}>
              <strong>{row.name || "ECQ context not named"}</strong>
              <span>{moneyParts.join(" · ")}</span>
              <span>
                {formatMoney(row.gift_or_donation_reported_amount_total)} gifts ·{" "}
                {formatMoney(row.electoral_expenditure_reported_amount_total)} spend
                {dateLabel ? ` · event date ${dateLabel}` : ""}
              </span>
            </div>
          );
        })
      )}
    </div>
  );
}

function rollupStateLocalTotals(summary: StateLocalSummaryResponse): {
  moneyFlowCount: number;
  giftOrDonationCount: number;
  electoralExpenditureCount: number;
  sourceIdentifierBacked: number;
  recipientIdentifierBacked: number;
  eventContextBacked: number;
  localElectorateContextBacked: number;
  giftOrDonationReportedAmountTotal: number | null;
  electoralExpenditureReportedAmountTotal: number | null;
} {
  return summary.totals_by_level.reduce(
    (acc, row) => {
      acc.moneyFlowCount += numberValue(row.money_flow_count);
      acc.giftOrDonationCount += numberValue(row.gift_or_donation_count);
      acc.electoralExpenditureCount += numberValue(row.electoral_expenditure_count);
      acc.sourceIdentifierBacked += numberValue(row.source_identifier_backed_count);
      acc.recipientIdentifierBacked += numberValue(row.recipient_identifier_backed_count);
      acc.eventContextBacked += numberValue(row.event_context_backed_count);
      acc.localElectorateContextBacked += numberValue(row.local_electorate_context_backed_count);
      if (
        row.gift_or_donation_reported_amount_total !== null &&
        row.gift_or_donation_reported_amount_total !== undefined
      ) {
        acc.giftOrDonationReportedAmountTotal = (
          acc.giftOrDonationReportedAmountTotal === null
            ? row.gift_or_donation_reported_amount_total
            : acc.giftOrDonationReportedAmountTotal + row.gift_or_donation_reported_amount_total
        );
      }
      if (
        row.electoral_expenditure_reported_amount_total !== null &&
        row.electoral_expenditure_reported_amount_total !== undefined
      ) {
        acc.electoralExpenditureReportedAmountTotal = (
          acc.electoralExpenditureReportedAmountTotal === null
            ? row.electoral_expenditure_reported_amount_total
            : acc.electoralExpenditureReportedAmountTotal +
              row.electoral_expenditure_reported_amount_total
        );
      }
      return acc;
    },
    {
      moneyFlowCount: 0,
      giftOrDonationCount: 0,
      electoralExpenditureCount: 0,
      sourceIdentifierBacked: 0,
      recipientIdentifierBacked: 0,
      eventContextBacked: 0,
      localElectorateContextBacked: 0,
      giftOrDonationReportedAmountTotal: null as number | null,
      electoralExpenditureReportedAmountTotal: null as number | null
    }
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
  const displayLandMask = coverage.display_land_masks?.[0];
  const displayLandMaskLabel = displayLandMask
    ? displayLandMask.source_name || displayLandMask.source_key
    : "not loaded";
  const partialLevels = coverage.partial_levels?.length
    ? ` · partial: ${coverage.partial_levels.join(", ")}`
    : "";

  return (
    <div className="coverage-panel" aria-label="Database coverage">
      <div className="coverage-header">
        <strong>Database coverage</strong>
        <span>
          {coverage.active_country} · active: {coverage.active_levels.join(", ")}
          {partialLevels}
        </span>
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
        <span>State: {coverageLayerSummary(stateLayer)}</span>
        <span>Council: {coverageLayerSummary(councilLayer)}</span>
      </div>
      <div className="coverage-status-row">
        <span title={displayLandMaskTooltip(displayLandMask)}>
          Map land mask: {displayLandMaskLabel}
        </span>
      </div>
      <details className="coverage-caveat">
        <summary>Coverage caveat</summary>
        <p>{coverage.caveat}</p>
      </details>
    </div>
  );
}

function coverageLayerSummary(layer: CoverageResponse["coverage_layers"][number] | undefined): string {
  if (!layer) return "planned";
  const rows = numberValue(layer.counts.money_flow_rows);
  const base = layer.status || "planned";
  return rows ? `${base} · ${rows.toLocaleString("en-AU")} rows` : base;
}

function numberValue(value: number | string | null | undefined): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function displayLandMaskTooltip(mask: DisplayLandMask | undefined): string {
  if (!mask) {
    return "No display land mask is loaded. Source electorate boundaries remain available.";
  }
  return [
    `Source key: ${mask.source_key}`,
    `Geometry role: ${mask.geometry_role}`,
    `Method: ${mask.mask_method || "not recorded"}`,
    `Licence status: ${mask.licence_status || "source document terms"}`,
    mask.source_limitations ? `Limitations: ${mask.source_limitations}` : null,
    `Display geometry only; official source electorate geometry remains preserved.`
  ]
    .filter(Boolean)
    .join("\n");
}

function safeSourceHref(value: string | null | undefined) {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

export default App;

function stringMetadata(result: SearchResult, key: string): string | null {
  const value = result.metadata[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function searchSelectionNote(result: SearchResult, isPending = false): string {
  if (result.type === "postcode") {
    if (isPending) {
      return (
        "Looking for this source-backed AEC electorate candidate in the current House map. " +
        "If it does not appear, the candidate may be a next-election boundary result that " +
        "has not yet been linked to the loaded map boundary table."
      );
    }
    return (
      "Opened this source-backed AEC electorate candidate on the map. Postcodes can split " +
      "across electorates and the AEC finder can reflect next-election boundaries, so this " +
      "is not address-level proof of the current local member."
    );
  }
  return (
    `This ${result.type.replace("_", " ")} result is in the database, but it is not yet ` +
    "a map drilldown target. Use it as a discovery lead while party, sector, and topic " +
    "detail panels are built."
  );
}
