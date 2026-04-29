import { AlertCircle, CheckCircle2, CircleDashed, Loader2, Network, X } from "lucide-react";
import { useMemo, useState } from "react";
import { formatMoney } from "../map";
import type { InfluenceGraph, InfluenceGraphEdge, InfluenceGraphNode, LoadState } from "../types";

type GraphRoot = {
  kind: "person" | "party" | "entity";
  id: number | string;
  label: string;
  includeCandidates: boolean;
};

type InfluenceGraphPanelProps = {
  graph: InfluenceGraph | null;
  root: GraphRoot | null;
  status: LoadState;
  error: string;
  onClose: () => void;
  onToggleCandidates: (includeCandidates: boolean) => void;
};

type PositionedNode = InfluenceGraphNode & {
  x: number;
  y: number;
  radius: number;
  degree: number;
};

const width = 760;
const height = 420;
const center = { x: width / 2, y: height / 2 };

export function InfluenceGraphPanel({
  graph,
  root,
  status,
  error,
  onClose,
  onToggleCandidates
}: InfluenceGraphPanelProps) {
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const layout = useMemo(() => (graph ? buildLayout(graph) : null), [graph]);
  const selectedEdge =
    graph?.edges.find((edge) => edge.id === selectedEdgeId) ?? graph?.edges[0] ?? null;
  const selectedNode =
    graph?.nodes.find((node) => node.id === selectedNodeId) ??
    graph?.nodes.find((node) => node.id === graph.root_id) ??
    null;
  const canToggleCandidates = root?.kind === "party";

  if (!root || status === "idle") return null;

  return (
    <section className="influence-graph-panel" aria-label="Evidence network">
      <div className="influence-graph-header">
        <div>
          <span className="result-type">Evidence network</span>
          <h2>{root.label}</h2>
          <p>{graphSubtitle(root, graph)}</p>
          <p className="graph-interpretation-note">
            Connections show disclosed records, reviewed links, or labelled estimates. They do not
            prove causation or improper conduct.
          </p>
        </div>
        <div className="graph-header-actions">
          {canToggleCandidates && (
            <label className="candidate-toggle">
              <input
                type="checkbox"
                checked={root.includeCandidates}
                onChange={(event) => onToggleCandidates(event.target.checked)}
              />
              <span>Review candidates</span>
            </label>
          )}
          <button className="icon-button" type="button" aria-label="Close evidence network" onClick={onClose}>
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

      {status === "loading" && (
        <p className="muted inline-loading">
          <Loader2 size={14} className="spin" aria-hidden="true" />
          Loading source-backed network
        </p>
      )}

      {status === "error" && (
        <div className="graph-error" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          <span>{error || "Could not load evidence network."}</span>
        </div>
      )}

      {status === "ready" && graph && layout && (
        <>
          <div className="graph-summary-row" aria-label="Graph summary">
            <span>
              <Network size={15} aria-hidden="true" />
              {graph.node_count.toLocaleString("en-AU")} actors
            </span>
            <span>
              <CheckCircle2 size={15} aria-hidden="true" />
              {reviewedEdgeCount(graph).toLocaleString("en-AU")} reviewed/context connections
            </span>
            <span>
              <CircleDashed size={15} aria-hidden="true" />
              {candidateEdgeCount(graph).toLocaleString("en-AU")} candidates
            </span>
          </div>

          <div className="graph-body">
            <div className="graph-visual-wrap">
              <svg
                className="influence-graph-svg"
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label="Network diagram of disclosed records, reviewed links, and context estimates"
              >
                <defs>
                  <marker
                    id="graph-arrow"
                    markerHeight="7"
                    markerWidth="7"
                    orient="auto"
                    refX="6"
                    refY="3.5"
                  >
                    <path d="M0,0 L7,3.5 L0,7 Z" fill="#52636c" />
                  </marker>
                </defs>
                {layout.edges.map((edge) => {
                  const source = layout.nodesById.get(edge.source);
                  const target = layout.nodesById.get(edge.target);
                  if (!source || !target) return null;
                  const selected = selectedEdge?.id === edge.id;
                  return (
                    <g key={edge.id}>
                      <line
                        x1={source.x}
                        y1={source.y}
                        x2={target.x}
                        y2={target.y}
                        className="graph-edge-hit"
                        role="button"
                        tabIndex={0}
                        aria-label={`Inspect connection: ${edgeLabel(edge, graph.nodes)}`}
                        onMouseEnter={() => setSelectedEdgeId(edge.id)}
                        onFocus={() => setSelectedEdgeId(edge.id)}
                        onClick={() => setSelectedEdgeId(edge.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedEdgeId(edge.id);
                          }
                        }}
                      />
                      <line
                        x1={edgePoint(source, target, source.radius + 4).x}
                        y1={edgePoint(source, target, source.radius + 4).y}
                        x2={edgePoint(target, source, target.radius + 9).x}
                        y2={edgePoint(target, source, target.radius + 9).y}
                        className="graph-edge"
                        data-edge-kind={edgeKind(edge)}
                        data-selected={selected}
                        markerEnd={isCandidateEdge(edge) ? undefined : "url(#graph-arrow)"}
                        style={{ strokeWidth: edgeWidth(edge) }}
                      >
                        <title>{edgeTooltip(edge)}</title>
                      </line>
                    </g>
                  );
                })}
                {layout.nodes.map((node) => (
                  <g
                    key={node.id}
                    className="graph-node"
                    data-node-type={node.type}
                    data-root={node.id === graph.root_id}
                    data-selected={selectedNode?.id === node.id}
                    transform={`translate(${node.x} ${node.y})`}
                    onMouseEnter={() => setSelectedNodeId(node.id)}
                    onClick={() => setSelectedNodeId(node.id)}
                  >
                    <circle r={node.radius}>
                      <title>{nodeTooltip(node)}</title>
                    </circle>
                    <text y={node.radius + 15}>{truncateLabel(node.label, node.id === graph.root_id ? 34 : 24)}</text>
                  </g>
                ))}
              </svg>
              <div className="graph-legend" aria-label="Graph legend">
                <span><i data-kind="money" /> Public disclosure flow</span>
                <span><i data-kind="campaign-support" /> Campaign support, not personal receipt</span>
                <span><i data-kind="access" /> Registered access context</span>
                <span><i data-kind="reviewed" /> Reviewed party connection</span>
                <span><i data-kind="context" /> Modelled/context pathway</span>
                <span><i data-kind="candidate" /> Candidate, needs review</span>
              </div>
            </div>

            <div className="graph-inspector">
              <h3>Selected connection</h3>
              {selectedEdge ? (
                <GraphEdgeCard edge={selectedEdge} />
              ) : (
                <p className="muted">Hover or select a line to inspect its backend evidence.</p>
              )}
              {selectedNode && (
                <div className="graph-node-card">
                  <small>Selected actor</small>
                  <strong>{selectedNode.label}</strong>
                  <span>{selectedNode.type.replaceAll("_", " ")}</span>
                </div>
              )}
            </div>
          </div>

          <div className="graph-edge-list" aria-label="Top network connections">
            {graph.edges.slice(0, 8).map((edge) => (
              <button
                key={edge.id}
                type="button"
                data-selected={selectedEdge?.id === edge.id}
                onClick={() => setSelectedEdgeId(edge.id)}
              >
                <span>{edgeLabel(edge, graph.nodes)}</span>
                <strong>{edge.type.replaceAll("_", " ")}</strong>
                <small>
                  {[eventCountLabel(edge), edgeAmountLabel(edge)]
                    .filter(Boolean)
                    .join(" · ")}
                </small>
              </button>
            ))}
          </div>

          <p className="caveat compact">{graph.caveat}</p>
        </>
      )}
    </section>
  );
}

function buildLayout(graph: InfluenceGraph) {
  const degrees = new Map<string, number>();
  for (const edge of graph.edges) {
    degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + 1);
    degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + 1);
  }
  const rootNode = graph.nodes.find((node) => node.id === graph.root_id);
  const otherNodes = graph.nodes
    .filter((node) => node.id !== graph.root_id)
    .sort((left, right) => {
      const weightDelta = nodeWeight(graph.edges, right.id) - nodeWeight(graph.edges, left.id);
      if (weightDelta !== 0) return weightDelta;
      return left.label.localeCompare(right.label);
    });
  const positioned: PositionedNode[] = [];
  if (rootNode) {
    positioned.push({
      ...rootNode,
      x: center.x,
      y: center.y,
      radius: 31,
      degree: degrees.get(rootNode.id) ?? 0
    });
  }
  const radiusX = otherNodes.length > 16 ? 292 : 246;
  const radiusY = otherNodes.length > 16 ? 154 : 132;
  otherNodes.forEach((node, index) => {
    const ring = index < 18 ? 0 : 1;
    const ringIndex = ring === 0 ? index : index - 18;
    const ringCount = ring === 0 ? Math.min(otherNodes.length, 18) : Math.max(otherNodes.length - 18, 1);
    const angle = -Math.PI / 2 + (Math.PI * 2 * ringIndex) / ringCount;
    const scale = ring === 0 ? 1 : 0.68;
    const degree = degrees.get(node.id) ?? 0;
    positioned.push({
      ...node,
      x: center.x + Math.cos(angle) * radiusX * scale,
      y: center.y + Math.sin(angle) * radiusY * scale,
      radius: nodeRadius(node, degree),
      degree
    });
  });
  return {
    nodes: positioned,
    edges: graph.edges,
    nodesById: new Map(positioned.map((node) => [node.id, node]))
  };
}

function nodeWeight(edges: InfluenceGraphEdge[], nodeId: string) {
  return edges
    .filter((edge) => edge.source === nodeId || edge.target === nodeId)
    .reduce((total, edge) => total + edgeNumericWeight(edge), 0);
}

function edgeNumericWeight(edge: InfluenceGraphEdge) {
  if (isContextEdge(edge)) return Math.min(edge.event_count ?? 1, 3);
  const amount = edge.reported_amount_total ?? 0;
  if (amount > 0) return Math.log10(amount + 1) * 10;
  return edge.event_count ?? 1;
}

function nodeRadius(node: InfluenceGraphNode, degree: number) {
  if (node.type === "party") return 28;
  if (node.type === "person") return 24;
  if (node.type === "entity") return Math.min(27, 18 + degree * 2.2);
  return 16;
}

function edgePoint(from: PositionedNode, to: PositionedNode, inset: number) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
  return {
    x: from.x + (dx / length) * inset,
    y: from.y + (dy / length) * inset
  };
}

function edgeWidth(edge: InfluenceGraphEdge) {
  if (isContextEdge(edge)) return Math.min(2.6, 1.2 + edgeNumericWeight(edge) / 5);
  return Math.min(6, 1.4 + edgeNumericWeight(edge) / 9);
}

function edgeKind(edge: InfluenceGraphEdge) {
  if (isCandidateEdge(edge)) return "candidate";
  if (isCampaignSupportEdge(edge)) return "campaign-support";
  if (isContextEdge(edge)) return "context";
  if (edge.event_family === "access") return "access";
  if (edge.type.includes("party_entity_link")) return "reviewed";
  if (edge.event_family === "benefit") return "benefit";
  return "money";
}

function isContextEdge(edge: InfluenceGraphEdge) {
  return (
    edge.type.includes("modelled") ||
    edge.type.includes("representation_context") ||
    edge.evidence_tier === "modelled_allocation" ||
    edge.evidence_tier === "party_membership_context"
  );
}

function isCandidateEdge(edge: InfluenceGraphEdge) {
  return edge.type.includes("candidate") || edge.evidence_status === "candidate_requires_review";
}

function isCampaignSupportEdge(edge: InfluenceGraphEdge) {
  return edge.event_family === "campaign_support";
}

function isNonAmountEdge(edge: InfluenceGraphEdge) {
  return isContextEdge(edge) || edge.event_family === "access";
}

function reviewedEdgeCount(graph: InfluenceGraph) {
  return graph.edges.filter((edge) => !isCandidateEdge(edge)).length;
}

function candidateEdgeCount(graph: InfluenceGraph) {
  return graph.edges.filter(isCandidateEdge).length;
}

function graphSubtitle(root: GraphRoot, graph: InfluenceGraph | null) {
  const scope = root.kind === "person" ? "representative" : root.kind;
  if (!graph) return `Loading ${scope} connections`;
  return `${graph.edge_count.toLocaleString("en-AU")} source-backed, reviewed, and modelled context connections around this ${scope}`;
}

function truncateLabel(label: string, maxLength: number) {
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength - 1)}...`;
}

function nodeTooltip(node: InfluenceGraphNode) {
  return [
    node.label,
    `Actor type: ${node.type.replaceAll("_", " ")}`,
    node.entity_type ? `Entity type: ${node.entity_type}` : null
  ]
    .filter(Boolean)
    .join("\n");
}

function edgeTooltip(edge: InfluenceGraphEdge) {
  return [
    edge.type.replaceAll("_", " "),
    edge.event_family ? `Family: ${edge.event_family}` : null,
    edge.event_type ? `Type: ${edge.event_type}` : null,
    edge.link_type ? `Link: ${edge.link_type}` : null,
    edge.review_status ? `Review: ${edge.review_status}` : null,
    edge.evidence_tier ? `Evidence tier: ${edge.evidence_tier.replaceAll("_", " ")}` : null,
    edge.allocation_method
      ? `Allocation: ${allocationLabel(edge)}`
      : null,
    eventCountLabel(edge),
    isNonAmountEdge(edge)
      ? "Direct personal reported total: not applicable to this edge"
      : `${edgeAmountTitle(edge)}: ${formatMoney(edge.reported_amount_total)}`,
    isCampaignSupportEdge(edge)
      ? "Campaign-support records are context, not evidence of personal receipt."
      : null,
    edge.modelled_amount_total !== null && edge.modelled_amount_total !== undefined
      ? `Estimated indirect exposure: ${formatMoney(edge.modelled_amount_total)} (not received)`
      : null,
    edge.claim_scope ?? null
  ]
    .filter(Boolean)
    .join("\n");
}

function eventCountLabel(edge: InfluenceGraphEdge) {
  if (edge.event_count === null || edge.event_count === undefined) return null;
  return `${edge.event_count.toLocaleString("en-AU")} records`;
}

function edgeAmountLabel(edge: InfluenceGraphEdge) {
  if (edge.event_family === "access") return "not a money record";
  if (edge.modelled_amount_total !== null && edge.modelled_amount_total !== undefined) {
    return `estimated indirect exposure ${formatMoney(edge.modelled_amount_total)} (not received)`;
  }
  if (isCampaignSupportEdge(edge)) {
    return `campaign support ${formatMoney(edge.reported_amount_total)} (not personal receipt)`;
  }
  return formatMoney(edge.reported_amount_total);
}

function edgeAmountTitle(edge: InfluenceGraphEdge) {
  if (isCampaignSupportEdge(edge)) {
    return "Campaign-support reported total, not personal receipt";
  }
  return "Reported total";
}

function allocationLabel(edge: InfluenceGraphEdge) {
  if (
    edge.allocation_method === "equal_current_representative_share" &&
    edge.allocation_denominator
  ) {
    return `equal share across ${edge.allocation_denominator.toLocaleString("en-AU")} current representatives`;
  }
  return edge.allocation_method?.replaceAll("_", " ") ?? "not applicable";
}

function edgeLabel(edge: InfluenceGraphEdge, nodes: InfluenceGraphNode[]) {
  const source = nodes.find((node) => node.id === edge.source)?.label ?? edge.source;
  const target = nodes.find((node) => node.id === edge.target)?.label ?? edge.target;
  return `${source} -> ${target}`;
}

function GraphEdgeCard({ edge }: { edge: InfluenceGraphEdge }) {
  return (
    <div className="graph-edge-card">
      <strong>{isCampaignSupportEdge(edge) ? "Campaign support context" : edge.type.replaceAll("_", " ")}</strong>
      <span>{[edge.event_family, edge.event_type, edge.link_type].filter(Boolean).join(" · ")}</span>
      {isCampaignSupportEdge(edge) && (
        <p>These records describe campaign support or expenditure context, not money personally received by the representative.</p>
      )}
      <dl>
        <div>
          <dt>Records</dt>
          <dd>{edge.event_count?.toLocaleString("en-AU") ?? "Not applicable"}</dd>
        </div>
        <div>
          <dt>{isNonAmountEdge(edge) ? "Direct personal reported total" : edgeAmountTitle(edge)}</dt>
          <dd>
            {isNonAmountEdge(edge)
              ? "Not applicable to this edge"
              : formatMoney(edge.reported_amount_total)}
          </dd>
        </div>
        {edge.modelled_amount_total !== null && edge.modelled_amount_total !== undefined && (
          <div>
            <dt>Modelled exposure</dt>
            <dd>{formatMoney(edge.modelled_amount_total)}</dd>
          </div>
        )}
        {edge.party_context_reported_amount_total !== null &&
          edge.party_context_reported_amount_total !== undefined && (
            <div>
              <dt>Party context total</dt>
              <dd>{formatMoney(edge.party_context_reported_amount_total)}</dd>
            </div>
          )}
        <div>
          <dt>Evidence</dt>
          <dd>
            {(
              edge.evidence_tier ||
              edge.evidence_status ||
              edge.review_status ||
              "not recorded"
            ).replaceAll("_", " ")}
          </dd>
        </div>
        {edge.allocation_method && (
          <div>
            <dt>Allocation</dt>
            <dd>{allocationLabel(edge)}</dd>
          </div>
        )}
        <div>
          <dt>Date span</dt>
          <dd>
            {edge.first_event_date || edge.last_event_date
              ? `${edge.first_event_date || "unknown"} to ${edge.last_event_date || "unknown"}`
              : "Not disclosed"}
          </dd>
        </div>
      </dl>
      {edge.claim_scope && <p>{edge.claim_scope}</p>}
      {edge.display_caveat && <p>{edge.display_caveat}</p>}
      {edge.evidence_note && <p>{edge.evidence_note}</p>}
      {edge.source_urls?.[0] && (
        <a href={edge.source_urls[0]} target="_blank" rel="noreferrer">
          Source document
        </a>
      )}
    </div>
  );
}
