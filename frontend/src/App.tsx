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
import { fetchElectorateMap, searchDatabase } from "./api";
import { MapCanvas } from "./components/MapCanvas";
import { DetailsPanel } from "./components/DetailsPanel";
import {
  AUSTRALIA_BOUNDS,
  electorateColor,
  findFeatureByResult,
  formatMoney,
  senateRegionColor
} from "./map";
import type { ElectorateFeature, LoadState, SearchResult } from "./types";

const states = ["All", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"];
type DataLevel = "federal" | "state" | "council";

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
  const [pendingSearchResult, setPendingSearchResult] = useState<SearchResult | null>(null);

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
    if (!pendingSearchResult || dataLevel !== "federal") return;
    const feature = findFeatureByResult(pendingSearchResult.id, pendingSearchResult.type, features);
    if (!feature) return;
    setSelectedFeature(feature);
    setPendingSearchResult(null);
  }, [dataLevel, features, pendingSearchResult]);

  useEffect(() => {
    const cleaned = query.trim();
    if (dataLevel !== "federal" || cleaned.length < 3) {
      setSearchResults([]);
      setSearchStatus("idle");
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
      return;
    }

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
                disabled={dataLevel !== "federal"}
                onClick={() => setChamber("house")}
              >
                House
              </button>
              <button
                type="button"
                className={chamber === "senate" ? "active" : ""}
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
            <Metric icon={<Building2 size={17} />} label="Events" value={totals.events.toLocaleString("en-AU")} />
            <Metric icon={<Banknote size={17} />} label="Reported" value={formatMoney(totals.reported)} />
          </div>

          {mapError && (
            <div className="inline-alert" role="alert">
              <AlertCircle size={16} />
              <span>{mapError}</span>
            </div>
          )}

          {searchResults.length > 0 && (
            <div className="search-results" aria-label="Search results">
              {searchResults.map((result) => (
                <button
                  type="button"
                  key={`${result.type}:${result.id}`}
                  className="search-result"
                  onClick={() => selectSearchResult(result)}
                >
                  <span className="result-type">{result.type.replace("_", " ")}</span>
                  <strong>{result.label}</strong>
                  <small>{result.subtitle || "Source-backed record"}</small>
                </button>
              ))}
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

export default App;

function stringMetadata(result: SearchResult, key: string): string | null {
  const value = result.metadata[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
