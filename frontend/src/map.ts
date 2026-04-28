import type { ElectorateFeature, ElectorateFeatureCollection } from "./types";

export const AUSTRALIA_BOUNDS: [[number, number], [number, number]] = [
  [111.5, -44.5],
  [154.5, -9.0]
];

export function mapStyleUrl(): { url: string; missingKey: boolean } {
  const key = import.meta.env.VITE_MAPTILER_API_KEY;
  const styleId = import.meta.env.VITE_MAPTILER_STYLE_ID || "basic-v2";
  if (!key) {
    return { url: "https://demotiles.maplibre.org/style.json", missingKey: true };
  }
  return {
    url: `https://api.maptiler.com/maps/${styleId}/style.json?key=${key}`,
    missingKey: false
  };
}

export function featureCollection(features: ElectorateFeature[]): ElectorateFeatureCollection {
  return {
    type: "FeatureCollection",
    features,
    feature_count: features.length,
    filters: {},
    caveat: ""
  };
}

export function electorateColor(partyName?: string | null): string {
  const name = (partyName || "").toLowerCase();
  if (name.includes("labor")) return "#d94a46";
  if (name.includes("liberal")) return "#2e65b8";
  if (name.includes("national")) return "#2f8c56";
  if (name.includes("greens")) return "#2f9a6a";
  if (name.includes("independent")) return "#8b6f36";
  return "#68717d";
}

export function formatMoney(value?: number | null): string {
  if (value === null || value === undefined) return "Not disclosed";
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0
  }).format(value);
}

export function findFeatureByResult(
  resultId: string | number,
  resultType: string,
  features: ElectorateFeature[]
): ElectorateFeature | undefined {
  if (resultType === "electorate") {
    return features.find((feature) => String(feature.id) === String(resultId));
  }
  if (resultType === "representative") {
    return features.find((feature) =>
      feature.properties.current_representatives.some(
        (representative) => String(representative.person_id) === String(resultId)
      )
    );
  }
  return undefined;
}
