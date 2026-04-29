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
  const name = (partyName || "").trim().toLowerCase();
  if (name === "alp" || name.includes("labor")) return "#f04438";
  if (name === "lp" || name.includes("liberal")) return "#1769e0";
  if (name === "lnp") return "#0b5fd3";
  if (name === "nats" || name === "nat" || name.includes("national")) return "#21a857";
  if (name === "ag" || name.includes("greens")) return "#00a651";
  if (name === "ind" || name.includes("independent")) return "#00a6a6";
  if (name === "on" || name.includes("one nation")) return "#ff6b00";
  if (name === "uap" || name.includes("united australia")) return "#ffd400";
  if (name === "jln" || name.includes("jacqui lambie")) return "#8b5cf6";
  if (name === "kap" || name.includes("katter")) return "#c2410c";
  if (name === "clp" || name.includes("country liberal")) return "#0064b7";
  if (name === "ca" || name.includes("centre alliance")) return "#14b8d4";
  if (name === "av" || name.includes("australia's voice")) return "#2dd4bf";
  return "#64748b";
}

export function senateRegionColor(state?: string | null): string {
  switch ((state || "").toUpperCase()) {
    case "ACT":
      return "#7c3aed";
    case "NSW":
      return "#00a3e0";
    case "NT":
      return "#f97316";
    case "QLD":
      return "#ef4444";
    case "SA":
      return "#8b5cf6";
    case "TAS":
      return "#10b981";
    case "VIC":
      return "#2563eb";
    case "WA":
      return "#f59e0b";
    default:
      return "#64748b";
  }
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
  if (resultType === "postcode") {
    const electorateId = String(resultId).split(":")[1];
    if (!electorateId) return undefined;
    return features.find((feature) => String(feature.id) === electorateId);
  }
  return undefined;
}
