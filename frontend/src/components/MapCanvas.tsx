import { useEffect, useRef } from "react";
import type { FeatureCollection } from "geojson";
import maplibregl, {
  type LayerSpecification,
  type LngLatBoundsLike,
  type MapLayerMouseEvent
} from "maplibre-gl";
import { featureCollection, mapStyleUrl } from "../map";
import type { ElectorateFeature } from "../types";

type MapCanvasProps = {
  features: ElectorateFeature[];
  selectedFeature: ElectorateFeature | null;
  initialBounds: LngLatBoundsLike;
  onSelectFeature: (feature: ElectorateFeature) => void;
};

const sourceId = "electorates";
const fillLayerId = "electorate-fills";
const lineLayerId = "electorate-lines";
const selectedHaloLayerId = "selected-electorate-halo";
const selectedLayerId = "selected-electorate";
type LinePaint = NonNullable<Extract<LayerSpecification, { type: "line" }>["paint"]>;
const selectedHaloWidth: LinePaint["line-width"] = [
  "interpolate",
  ["exponential", 1.2],
  ["zoom"],
  1.5,
  1,
  2.5,
  1.5,
  3,
  2.2,
  4.5,
  3,
  6,
  4.2,
  8,
  5.8,
  10,
  7.2,
  12,
  8.4
];
const selectedStrokeWidth: LinePaint["line-width"] = [
  "interpolate",
  ["exponential", 1.2],
  ["zoom"],
  1.5,
  0.45,
  2.5,
  0.75,
  3,
  1.1,
  4.5,
  1.6,
  6,
  2.4,
  8,
  3.4,
  10,
  4.4,
  12,
  5.2
];
const selectedHaloBlur: LinePaint["line-blur"] = [
  "interpolate",
  ["linear"],
  ["zoom"],
  1.5,
  0,
  3,
  0.1,
  6,
  0.35,
  10,
  0.8
];

export function MapCanvas({
  features,
  selectedFeature,
  initialBounds,
  onSelectFeature
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const featuresRef = useRef<ElectorateFeature[]>([]);
  const missingKeyRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const style = mapStyleUrl();
    missingKeyRef.current = style.missingKey;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: style.url,
      bounds: initialBounds,
      fitBoundsOptions: { padding: 34 },
      attributionControl: { compact: true }
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("load", () => {
      map.addSource(sourceId, {
        type: "geojson",
        data: featureCollection([]) as FeatureCollection
      });
      map.addLayer({
        id: fillLayerId,
        type: "fill",
        source: sourceId,
        paint: {
          "fill-color": [
            "case",
            ["==", ["get", "chamber"], "senate"],
            [
              "match",
              ["get", "state_or_territory"],
              "ACT",
              "#7c3aed",
              "NSW",
              "#00a3e0",
              "NT",
              "#f97316",
              "QLD",
              "#ef4444",
              "SA",
              "#8b5cf6",
              "TAS",
              "#10b981",
              "VIC",
              "#2563eb",
              "WA",
              "#f59e0b",
              "#64748b"
            ],
            [
              "match",
              ["get", "party_short_name"],
              "ALP",
              "#f04438",
              "LP",
              "#1769e0",
              "LNP",
              "#0b5fd3",
              "NATS",
              "#21a857",
              "Nats",
              "#21a857",
              "AG",
              "#00a651",
              "IND",
              "#00a6a6",
              "ON",
              "#ff6b00",
              "UAP",
              "#ffd400",
              "JLN",
              "#8b5cf6",
              "KAP",
              "#c2410c",
              "CLP",
              "#0064b7",
              "CA",
              "#14b8d4",
              "AV",
              "#2dd4bf",
              "#64748b"
            ]
          ],
          "fill-opacity": [
            "case",
            ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
            0.76,
            0.57
          ],
          "fill-antialias": false
        }
      });
      map.addLayer({
        id: lineLayerId,
        type: "line",
        source: sourceId,
        paint: {
          "line-color": "#26343b",
          "line-opacity": 0.5,
          "line-width": 0.8
        }
      });
      map.addLayer({
        id: selectedHaloLayerId,
        type: "line",
        source: sourceId,
        filter: ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
        paint: {
          "line-color": "#ffffff",
          "line-width": selectedHaloWidth,
          "line-opacity": 0.92,
          "line-blur": selectedHaloBlur
        }
      });
      map.addLayer({
        id: selectedLayerId,
        type: "line",
        source: sourceId,
        filter: ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
        paint: {
          "line-color": "#ffe600",
          "line-width": selectedStrokeWidth,
          "line-opacity": 1
        }
      });
      syncData(map, features);
    });
    map.on("click", fillLayerId, (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.electorate_id;
      const feature = featuresRef.current.find((item) => item.properties.electorate_id === Number(id));
      if (feature) onSelectFeature(feature);
    });
    map.on("mouseenter", fillLayerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", fillLayerId, () => {
      map.getCanvas().style.cursor = "";
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [initialBounds, onSelectFeature]);

  useEffect(() => {
    featuresRef.current = features;
    if (!mapRef.current?.isStyleLoaded()) return;
    syncData(mapRef.current, features);
  }, [features]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    if (map.getLayer(selectedHaloLayerId)) {
      map.setFilter(selectedHaloLayerId, ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1]);
    }
    if (map.getLayer(selectedLayerId)) {
      map.setFilter(selectedLayerId, ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1]);
    }
    if (map.getLayer(fillLayerId)) {
      map.setPaintProperty(fillLayerId, "fill-opacity", [
        "case",
        ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
        0.76,
        0.57
      ]);
    }
  }, [selectedFeature]);

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map-canvas" />
      {missingKeyRef.current && (
        <div className="map-warning">
          MapTiler key missing. Using fallback basemap.
        </div>
      )}
    </div>
  );
}

function syncData(map: maplibregl.Map, features: ElectorateFeature[]) {
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;
  source.setData(
    featureCollection(features.filter((feature) => feature.geometry)) as FeatureCollection
  );
}
