import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Banknote,
  CheckCircle2,
  Gift,
  Globe2,
  Loader2,
  Mail,
  MapPin,
  Phone,
  X,
  Vote
} from "lucide-react";
import { formatMoney } from "../map";
import type {
  ElectorateFeature,
  LoadState,
  RepresentativeContact,
  RepresentativeEvent,
  RepresentativeProfile
} from "../types";

type DetailsPanelProps = {
  feature: ElectorateFeature | null;
  caveat: string;
  partyColor: string;
  selectedPersonId: number | null;
  contactPersonId: number | null;
  representativeProfile: RepresentativeProfile | null;
  representativeProfileStatus: LoadState;
  onSelectRepresentative: (personId: number) => void;
  onCloseContact: () => void;
};

export function DetailsPanel({
  feature,
  caveat,
  partyColor,
  selectedPersonId,
  contactPersonId,
  representativeProfile,
  representativeProfileStatus,
  onSelectRepresentative,
  onCloseContact
}: DetailsPanelProps) {
  const [eventFamilyFilter, setEventFamilyFilter] = useState("all");
  const [expandedEventId, setExpandedEventId] = useState<number | null>(null);
  const recentEvents = representativeProfile?.recent_events ?? [];
  const totalRepresentativeEvents = useMemo(() => {
    return representativeProfile?.event_summary.reduce(
      (total, summary) => total + summary.event_count,
      0
    ) ?? 0;
  }, [representativeProfile]);
  const eventFamilyOptions = useMemo(() => {
    const summaries = representativeProfile?.event_summary ?? [];
    return [
      { key: "all", label: "All", count: totalRepresentativeEvents },
      ...summaries.map((summary) => ({
        key: summary.event_family,
        label: summary.event_family.replaceAll("_", " "),
        count: summary.event_count
      }))
    ];
  }, [representativeProfile, totalRepresentativeEvents]);
  const filteredEvents = useMemo(() => {
    const events =
      eventFamilyFilter === "all"
        ? recentEvents
        : recentEvents.filter((event) => event.event_family === eventFamilyFilter);
    return events.slice(0, 8);
  }, [eventFamilyFilter, recentEvents]);

  useEffect(() => {
    setEventFamilyFilter("all");
    setExpandedEventId(null);
  }, [selectedPersonId]);

  if (!feature) {
    return (
      <aside className="details-panel empty" aria-label="Selection details">
        <AlertCircle size={20} />
        <p>No electorate selected.</p>
      </aside>
    );
  }

  const properties = feature.properties;
  return (
    <aside className="details-panel" aria-label="Selection details">
      <div className="panel-header" style={{ borderColor: partyColor }}>
        <div>
          <p className="eyebrow">{properties.state_or_territory || "Federal"} · {properties.chamber}</p>
          <h2>{properties.electorate_name}</h2>
        </div>
        <span className="party-dot" style={{ background: partyColor }} />
      </div>

      <section className="panel-section">
        <h3>Current Representation</h3>
        {properties.map_geometry_scope && (
          <p className="scope-caption">
            Map geometry: {properties.map_geometry_scope.replaceAll("_", " ")}
          </p>
        )}
        <div className="rep-list">
          {properties.current_representatives.length ? (
            properties.current_representatives.map((representative) => {
              const isContactOpen = contactPersonId === representative.person_id;
              return (
                <div className="rep-item" key={representative.person_id}>
                  <button
                    className="rep-row"
                    data-selected={representative.person_id === selectedPersonId}
                    type="button"
                    aria-expanded={isContactOpen}
                    onClick={() => onSelectRepresentative(representative.person_id)}
                  >
                    <div>
                      <strong>{representative.display_name}</strong>
                      <span>{representative.party_name || "No party recorded"}</span>
                    </div>
                    <ArrowRight size={16} aria-hidden="true" />
                  </button>
                  {isContactOpen && (
                    <ContactPopup
                      profile={representativeProfile}
                      status={representativeProfileStatus}
                      onClose={onCloseContact}
                    />
                  )}
                </div>
              );
            })
          ) : (
            <p className="muted">No current representative is attached in the database.</p>
          )}
        </div>
      </section>

      <section className="panel-section">
        <h3>Representative-Linked Context</h3>
        <div className="fact-grid">
          <Fact
            icon={<CheckCircle2 size={17} />}
            label="Non-rejected records"
            value={properties.current_representative_lifetime_influence_event_count.toLocaleString("en-AU")}
            tooltip="Backend filter: influence_event rows linked to the current representative where review_status is not rejected. This is a disclosed-record count, not a wrongdoing claim."
          />
          <Fact
            icon={<Banknote size={17} />}
            label="Money records"
            value={properties.current_representative_lifetime_money_event_count.toLocaleString("en-AU")}
            tooltip="Backend event_family = money. These are AEC financial-disclosure rows directly linked to this representative only when the source supports that person-level attribution."
          />
          <Fact
            icon={<Gift size={17} />}
            label="Benefit records"
            value={properties.current_representative_lifetime_benefit_event_count.toLocaleString("en-AU")}
            tooltip="Backend event_family = benefit. Includes disclosed gifts, sponsored travel, hospitality, tickets, memberships, flights, meals, and similar register records where classified as benefits."
          />
          <Fact
            icon={<Vote size={17} />}
            label="Reported total"
            value={formatMoney(properties.current_representative_lifetime_reported_amount_total)}
            tooltip="Sum of reported monetary amounts for non-rejected person-linked records. Records with not-disclosed values stay in the count but not the total."
          />
        </div>
      </section>

      <section className="panel-section">
        <h3>Selected Representative Records</h3>
        {representativeProfileStatus === "loading" && (
          <p className="muted inline-loading">
            <Loader2 size={14} className="spin" aria-hidden="true" />
            Loading source-backed records
          </p>
        )}
        {representativeProfileStatus === "error" && (
          <p className="muted">Could not load representative records.</p>
        )}
        {representativeProfileStatus === "ready" && representativeProfile && (
          <>
            <div className="event-family-grid">
              {representativeProfile.event_summary.length ? (
                representativeProfile.event_summary.map((summary) => (
                  <div
                    className="event-family"
                    key={summary.event_family}
                    title={eventFamilyTooltip(summary)}
                  >
                    <small>{summary.event_family.replaceAll("_", " ")}</small>
                    <strong>{summary.event_count.toLocaleString("en-AU")}</strong>
                    <span>{formatMoney(summary.reported_amount_total)}</span>
                  </div>
                ))
              ) : (
                <p className="muted">No source-backed person-linked records are loaded yet.</p>
              )}
            </div>
            {eventFamilyOptions.length > 1 && (
              <div className="event-filter-row" aria-label="Record family filter">
                {eventFamilyOptions.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    aria-pressed={eventFamilyFilter === option.key}
                    onClick={() => {
                      setEventFamilyFilter(option.key);
                      setExpandedEventId(null);
                    }}
                  >
                    <span>{option.label}</span>
                    <strong>{option.count.toLocaleString("en-AU")}</strong>
                  </button>
                ))}
              </div>
            )}
            {totalRepresentativeEvents > 0 && (
              <p className="event-count-note">
                Showing {filteredEvents.length.toLocaleString("en-AU")} loaded records
                {totalRepresentativeEvents > filteredEvents.length
                  ? ` from ${totalRepresentativeEvents.toLocaleString("en-AU")} non-rejected person-linked records`
                  : ""}.
              </p>
            )}
            <div className="event-list">
              {filteredEvents.map((event) => (
                <EventRow
                  event={event}
                  expanded={expandedEventId === event.id}
                  key={event.id}
                  onToggle={() =>
                    setExpandedEventId((current) => (current === event.id ? null : event.id))
                  }
                />
              ))}
              {filteredEvents.length === 0 && eventFamilyFilter !== "all" && (
                <p className="muted">No loaded records match this filter.</p>
              )}
            </div>
          </>
        )}
      </section>

      <section className="panel-section">
        <h3>Party Breakdown</h3>
        <div className="party-breakdown">
          {properties.party_breakdown.length ? (
            properties.party_breakdown.map((party) => (
              <div className="party-row" key={`${party.party_id}:${party.party_name}`}>
                <span>{party.party_name || "No party recorded"}</span>
                <strong>{party.representative_count}</strong>
              </div>
            ))
          ) : (
            <p className="muted">No party breakdown is available.</p>
          )}
        </div>
      </section>

      <p className="caveat">{caveat}</p>
    </aside>
  );
}

function eventTimeLabel(event: { event_date: string | null; reporting_period: string | null }) {
  if (event.event_date) return event.event_date;
  if (event.reporting_period) return `Reporting period ${event.reporting_period}`;
  return null;
}

function EventRow({
  event,
  expanded,
  onToggle
}: {
  event: RepresentativeEvent;
  expanded: boolean;
  onToggle: () => void;
}) {
  const sourceHref = event.source_final_url || event.source_url;
  const sourceName = event.source_name || event.source_id || "Source document";
  const tooltip = eventBackendTooltip(event);
  return (
    <article className="event-row" data-expanded={expanded} title={tooltip}>
      <button
        type="button"
        className="event-summary-button"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <div>
          <strong>{event.event_type.replaceAll("_", " ")}</strong>
          <span>{event.source_entity_name || event.source_raw_name || "Source not identified"}</span>
        </div>
        <small>
          {[eventTimeLabel(event), formatMoney(event.amount)]
            .filter(Boolean)
            .join(" · ")}
        </small>
      </button>
      <p>{event.description}</p>
      <div className="event-chip-row">
        <span>{event.event_family.replaceAll("_", " ")}</span>
        <span>{event.evidence_status.replaceAll("_", " ")}</span>
        <span>{event.review_status.replaceAll("_", " ")}</span>
      </div>
      {expanded && (
        <div className="event-detail">
          <DetailLine label="Backend family">{event.event_family}</DetailLine>
          <DetailLine label="Backend type">
            {[event.event_type, event.event_subtype].filter(Boolean).join(" / ")}
          </DetailLine>
          <DetailLine label="Disclosure system">{event.disclosure_system}</DetailLine>
          <DetailLine label="Extraction method">{event.extraction_method}</DetailLine>
          <DetailLine label="Source">
            {sourceHref ? (
              <a href={sourceHref} target="_blank" rel="noreferrer">
                {sourceName}
              </a>
            ) : (
              sourceName
            )}
          </DetailLine>
          <DetailLine label="Source ref">{event.source_ref || "Not recorded"}</DetailLine>
          <DetailLine label="Amount status">
            {[event.amount_status.replaceAll("_", " "), event.currency].filter(Boolean).join(" · ")}
          </DetailLine>
          <DetailLine label="Disclosure threshold">
            {event.disclosure_threshold || "Not recorded"}
          </DetailLine>
          <DetailLine label="Missing fields">
            {formatMissingFlags(event.missing_data_flags)}
          </DetailLine>
        </div>
      )}
    </article>
  );
}

function eventFamilyTooltip(summary: {
  event_family: string;
  event_count: number;
  reported_amount_event_count: number;
  reported_amount_total: number | null;
  first_event_date: string | null;
  last_event_date: string | null;
}) {
  const dateSpan =
    summary.first_event_date || summary.last_event_date
      ? `${summary.first_event_date || "unknown"} to ${summary.last_event_date || "unknown"}`
      : "no event dates disclosed";
  return [
    `Backend event_family: ${summary.event_family}`,
    `Non-rejected person-linked rows: ${summary.event_count.toLocaleString("en-AU")}`,
    `Rows with reported amounts: ${summary.reported_amount_event_count.toLocaleString("en-AU")}`,
    `Reported total: ${formatMoney(summary.reported_amount_total)}`,
    `Date span: ${dateSpan}`
  ].join("\n");
}

function eventBackendTooltip(event: RepresentativeEvent) {
  return [
    `Backend family: ${event.event_family}`,
    `Backend type: ${[event.event_type, event.event_subtype].filter(Boolean).join(" / ")}`,
    `Disclosure system: ${event.disclosure_system}`,
    `Extraction method: ${event.extraction_method}`,
    `Evidence: ${event.evidence_status}`,
    `Review: ${event.review_status}`,
    `Amount status: ${event.amount_status}`,
    `Source ref: ${event.source_ref || "not recorded"}`
  ].join("\n");
}

function DetailLine({
  label,
  children
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="detail-line">
      <small>{label}</small>
      <span>{children}</span>
    </div>
  );
}

function formatMissingFlags(flags: unknown[]) {
  const cleaned = flags
    .map((flag) => String(flag).replaceAll("_", " "))
    .filter(Boolean);
  return cleaned.length ? cleaned.join(", ") : "No missing-field flags recorded";
}

function ContactPopup({
  profile,
  status,
  onClose
}: {
  profile: RepresentativeProfile | null;
  status: LoadState;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (status === "loading") {
    return (
      <div className="contact-popover" role="dialog" aria-label="Representative contact details">
        <div className="contact-popover-header">
          <strong>Public contact details</strong>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close contact details">
            <X size={15} aria-hidden="true" />
          </button>
        </div>
        <p className="muted inline-loading">
          <Loader2 size={14} className="spin" aria-hidden="true" />
          Loading public contact details
        </p>
      </div>
    );
  }
  if (status === "error" || !profile) {
    return (
      <div className="contact-popover" role="dialog" aria-label="Representative contact details">
        <div className="contact-popover-header">
          <strong>Public contact details</strong>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close contact details">
            <X size={15} aria-hidden="true" />
          </button>
        </div>
        <p className="muted">Could not load public contact details.</p>
      </div>
    );
  }

  const contact = profile.contact;
  return (
    <div className="contact-popover" role="dialog" aria-label="Representative contact details">
      <div className="contact-popover-header">
        <div>
          <small>Public contact details</small>
          <strong>{profile.person.display_name}</strong>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close contact details">
          <X size={15} aria-hidden="true" />
        </button>
      </div>

      <div className="contact-grid">
        <ContactLine
          icon={<Mail size={15} />}
          label="Email"
          value={contact.email}
          href={contact.email ? `mailto:${contact.email}` : null}
          fallback="Not published in loaded APH contact record"
        />
        <ContactLine
          icon={<Phone size={15} />}
          label="Electorate phone"
          value={contact.phones.electorate}
          href={telHref(contact.phones.electorate)}
          fallback="Not listed"
        />
        <ContactLine
          icon={<Phone size={15} />}
          label="Parliament phone"
          value={contact.phones.parliament}
          href={telHref(contact.phones.parliament)}
          fallback="Not listed"
        />
        <ContactLine
          icon={<MapPin size={15} />}
          label="Physical office"
          value={contact.addresses.physical_office}
          fallback="Not listed"
        />
        <ContactLine
          icon={<MapPin size={15} />}
          label="Postal address"
          value={contact.addresses.postal}
          fallback="Not listed"
        />
        <ContactLine
          icon={<Globe2 size={15} />}
          label="Web profile"
          value={contact.web.official_profile ? "APH profile/search" : null}
          href={contact.web.official_profile}
          fallback="Not listed"
        />
      </div>

      <div className="contact-source-row">
        <ContactSourceLink contact={contact} />
      </div>
      <p className="contact-note">{contact.source_note}</p>
    </div>
  );
}

function ContactLine({
  icon,
  label,
  value,
  href,
  fallback
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  href?: string | null;
  fallback: string;
}) {
  return (
    <div className="contact-line">
      <span className="contact-icon">{icon}</span>
      <div>
        <small>{label}</small>
        {value && href ? (
          <a href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
            {value}
          </a>
        ) : (
          <strong>{value || fallback}</strong>
        )}
      </div>
    </div>
  );
}

function ContactSourceLink({ contact }: { contact: RepresentativeContact }) {
  if (!contact.source_url) return <span>Source: APH public contact records</span>;
  return (
    <a href={contact.source_url} target="_blank" rel="noreferrer">
      Source: APH public contact records
    </a>
  );
}

function telHref(phone: string | null) {
  if (!phone) return null;
  const cleaned = phone.replace(/[^\d+]/g, "");
  return cleaned ? `tel:${cleaned}` : null;
}

function Fact({
  icon,
  label,
  value,
  tooltip
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tooltip?: string;
}) {
  return (
    <div className="fact" title={tooltip}>
      <span className="fact-icon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
