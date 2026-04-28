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
  formatMoney
} from "./map";
import type { ElectorateFeature, LoadState, SearchResult } from "./types";

const states = ["All", "ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"];

function App() {
  const [features, setFeatures] = useState<ElectorateFeature[]>([]);
  const [selectedFeature, setSelectedFeature] = useState<ElectorateFeature | null>(null);
  const [mapCaveat, setMapCaveat] = useState("");
  const [stateFilter, setStateFilter] = useState("All");
  const [chamber, setChamber] = useState<"house" | "senate">("house");
  const [mapStatus, setMapStatus] = useState<LoadState>("idle");
  const [mapError, setMapError] = useState("");
  const [query, setQuery] = useState("");
  const [searchStatus, setSearchStatus] = useState<LoadState>("idle");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchCaveat, setSearchCaveat] = useState("");

  useEffect(() => {
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
  }, [chamber, stateFilter]);

  useEffect(() => {
    const cleaned = query.trim();
    if (cleaned.length < 3) {
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
  }, [query]);

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
    if (feature) setSelectedFeature(feature);
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
              <p className="eyebrow">Commonwealth beta</p>
              <h1>Political Influence Explorer</h1>
            </div>
          </div>
          <div className="status-pill" data-state={mapStatus}>
            {mapStatus === "loading" ? <Loader2 size={16} className="spin" /> : <CircleDot size={16} />}
            <span>{mapStatus === "loading" ? "Loading records" : `${features.length} map features`}</span>
          </div>
        </div>

        <aside className="control-panel" aria-label="Map controls and search">
          <div className="search-box">
            <Search size={18} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search representatives, electorates, parties, entities, sectors"
              aria-label="Search the political influence database"
            />
            {searchStatus === "loading" && <Loader2 size={16} className="spin" aria-hidden="true" />}
          </div>

          <div className="toolbar-row" aria-label="Map filters">
            <div className="segmented" role="group" aria-label="Chamber">
              <button
                type="button"
                className={chamber === "house" ? "active" : ""}
                onClick={() => setChamber("house")}
              >
                House
              </button>
              <button
                type="button"
                className={chamber === "senate" ? "active" : ""}
                onClick={() => setChamber("senate")}
              >
                Senate
              </button>
            </div>
            <label className="select-label">
              <Layers size={16} aria-hidden="true" />
              <select value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}>
                {states.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="metric-grid" aria-label="Current map totals">
            <Metric icon={<MapPin size={17} />} label="Electorates" value={totals.electorates.toLocaleString("en-AU")} />
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
          partyColor={electorateColor(selectedFeature?.properties.party_name)}
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
