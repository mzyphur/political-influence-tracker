import { Banknote, Building2, ExternalLink, Loader2, Megaphone, Network, X } from "lucide-react";
import { formatMoney } from "../map";
import type { EntityEvent, EntityProfile, LoadState } from "../types";
import { ContractDonorOverlapPanel } from "./ContractDonorOverlapPanel";

type EntityProfilePanelProps = {
  profile: EntityProfile | null;
  status: LoadState;
  error: string;
  onOpenGraph: (entityId: number, label: string) => void;
  onClose: () => void;
};

export function EntityProfilePanel({
  profile,
  status,
  error,
  onOpenGraph,
  onClose
}: EntityProfilePanelProps) {
  if (status === "idle") return null;

  return (
    <section className="entity-profile-panel" aria-label="Entity disclosure profile">
      <div className="entity-profile-header">
        <div>
          <span className="result-type">Entity profile</span>
          <h2>{profile?.entity.canonical_name ?? "Loading entity"}</h2>
          {profile && (
            <p>
              {[profile.entity.entity_type, profile.entity.country].filter(Boolean).join(" · ") ||
                "Entity type not classified"}
            </p>
          )}
        </div>
        <div className="profile-header-actions">
          {profile && (
            <button
              className="icon-button"
              type="button"
              aria-label={`Open evidence network for ${profile.entity.canonical_name}`}
              title="Open source-backed evidence network"
              onClick={() => onOpenGraph(profile.entity.id, profile.entity.canonical_name)}
            >
              <Network size={15} aria-hidden="true" />
            </button>
          )}
          <button className="icon-button" type="button" aria-label="Close entity profile" onClick={onClose}>
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

      {status === "loading" && (
        <p className="muted inline-loading">
          <Loader2 size={14} className="spin" aria-hidden="true" />
          Loading source-backed entity records
        </p>
      )}

      {status === "error" && <p className="muted">Could not load entity profile: {error}</p>}

      {status === "ready" && profile && (
        <>
          <div className="entity-classification-row">
            {profile.classifications.slice(0, 3).map((classification) => (
              <span key={`${classification.public_sector}:${classification.method}`}>
                {classification.public_sector.replaceAll("_", " ")}
                <small>{classification.method.replaceAll("_", " ")}</small>
              </span>
            ))}
            {profile.classifications.length === 0 && <span>sector not classified</span>}
          </div>

          <div className="fact-grid compact-grid">
            <ProfileFact
              icon={<ExternalLink size={16} />}
              label="As source"
              value={summaryCount(profile.as_source_summary)}
            />
            <ProfileFact
              icon={<Banknote size={16} />}
              label="Source total"
              value={formatMoney(summaryAmount(profile.as_source_summary))}
            />
            <ProfileFact
              icon={<Building2 size={16} />}
              label="As recipient"
              value={summaryCount(profile.as_recipient_summary)}
            />
            <ProfileFact
              icon={<Banknote size={16} />}
              label="Received total"
              value={formatMoney(summaryAmount(profile.as_recipient_summary))}
            />
            <ProfileFact
              icon={<Megaphone size={16} />}
              label="Campaign support"
              value={formatMoney(
                campaignSupportAmount(profile.as_source_summary, profile.as_recipient_summary)
              )}
            />
          </div>

          <EntityRankList
            title="Top recipients"
            rows={profile.top_recipients.map((row) => ({
              key: `${row.recipient_type}:${row.recipient_id}:${row.recipient_label}`,
              label: row.recipient_label,
              count: row.event_count,
              amount: row.reported_amount_total
            }))}
          />

          <EntityRankList
            title="Top sources"
            rows={profile.top_sources.map((row) => ({
              key: `${row.source_type}:${row.source_id}:${row.source_label}`,
              label: row.source_label,
              count: row.event_count,
              amount: row.reported_amount_total
            }))}
          />

          <div className="entity-event-list">
            <h3>Recent records</h3>
            {profile.recent_events.slice(0, 6).map((event) => (
              <EntityEventRow event={event} key={event.id} />
            ))}
            {profile.recent_events.length === 0 && (
              <p className="muted">No non-rejected records are linked to this entity yet.</p>
            )}
          </div>

          <p className="caveat compact">{profile.caveat}</p>

          {/* Contract×donor overlap drill-down (Batch CC-1).
            * Shows contracts the entity received side-by-side with
            * donations they made, when both are available. Filtered
            * by the entity's likely sector via the supplier name
            * match in v_contract_donor_overlap. The panel handles
            * the empty state cleanly. */}
          {profile && (
            <ContractDonorOverlapPanel
              minContractValueAud={500_000}
              rowLimit={10}
              initiallyCollapsed
            />
          )}
        </>
      )}
    </section>
  );
}

function summaryCount(rows: Array<{ event_count: number }>) {
  return rows.reduce((total, row) => total + row.event_count, 0).toLocaleString("en-AU");
}

function summaryAmount(rows: Array<{ reported_amount_total: number | null }>) {
  return rows.reduce((total, row) => total + (row.reported_amount_total ?? 0), 0);
}

function campaignSupportAmount(
  ...groups: Array<Array<{ campaign_support_reported_amount_total?: number | null }>>
) {
  return groups
    .flat()
    .reduce((total, row) => total + (row.campaign_support_reported_amount_total ?? 0), 0);
}

function ProfileFact({
  icon,
  label,
  value
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="fact">
      <span className="fact-icon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EntityRankList({
  title,
  rows
}: {
  title: string;
  rows: Array<{ key: string; label: string; count: number; amount: number | null }>;
}) {
  if (!rows.length) return null;
  return (
    <div className="entity-rank-list">
      <h3>{title}</h3>
      {rows.slice(0, 5).map((row) => (
        <div className="entity-rank-row" key={row.key}>
          <span>{row.label}</span>
          <strong>{formatMoney(row.amount)}</strong>
          <small>{row.count.toLocaleString("en-AU")} records</small>
        </div>
      ))}
    </div>
  );
}

function eventTimeLabel(event: EntityEvent) {
  if (event.event_date) return event.event_date;
  if (event.reporting_period) return `Reporting period ${event.reporting_period}`;
  return "Date not disclosed";
}

function eventAmountLabel(event: EntityEvent) {
  if (event.event_family === "access") return "Not a money record";
  if (event.amount_status === "not_applicable") return "Not applicable";
  return formatMoney(event.amount);
}

function EntityEventRow({ event }: { event: EntityEvent }) {
  const sourceHref = event.source_final_url || event.source_url;
  const counterparty =
    event.entity_role === "as_source"
      ? event.recipient_person_name || event.recipient_entity_name || event.recipient_raw_name
      : event.source_entity_name || event.source_raw_name;
  return (
    <article className="entity-event-row">
      <div>
        <strong>{event.event_type.replaceAll("_", " ")}</strong>
        <span>{counterparty || "Counterparty not identified"}</span>
      </div>
      <small>
        {[eventTimeLabel(event), eventAmountLabel(event)].filter(Boolean).join(" · ")}
      </small>
      {sourceHref && (
        <a href={sourceHref} target="_blank" rel="noreferrer">
          {event.source_name || event.source_id}
        </a>
      )}
    </article>
  );
}
