import { useEffect, useRef } from "react";
import type { FeatureCollection } from "geojson";
import maplibregl, { type LngLatBoundsLike, type MapLayerMouseEvent } from "maplibre-gl";
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
const selectedLayerId = "selected-electorate";

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
              "#6b8fcf",
              "NSW",
              "#5e9fc0",
              "NT",
              "#d48952",
              "QLD",
              "#b96969",
              "SA",
              "#7d79bf",
              "TAS",
              "#4c9b82",
              "VIC",
              "#687ec3",
              "WA",
              "#c49a4c",
              "#78828c"
            ],
            [
              "match",
              ["get", "party_short_name"],
              "ALP",
              "#d85a54",
              "LP",
              "#2f72b7",
              "LNP",
              "#2f72b7",
              "Nats",
              "#4f9659",
              "AG",
              "#2d9b75",
              "IND",
              "#c7953d",
              "#78828c"
            ]
          ],
          "fill-opacity": [
            "case",
            ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
            0.72,
            0.48
          ]
        }
      });
      map.addLayer({
        id: lineLayerId,
        type: "line",
        source: sourceId,
        paint: {
          "line-color": "#26343b",
          "line-opacity": 0.42,
          "line-width": 0.8
        }
      });
      map.addLayer({
        id: selectedLayerId,
        type: "line",
        source: sourceId,
        filter: ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
        paint: {
          "line-color": "#ffd166",
          "line-width": 3.4,
          "line-opacity": 0.95
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
    if (map.getLayer(selectedLayerId)) {
      map.setFilter(selectedLayerId, ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1]);
    }
    if (map.getLayer(fillLayerId)) {
      map.setPaintProperty(fillLayerId, "fill-opacity", [
        "case",
        ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
        0.72,
        0.48
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
