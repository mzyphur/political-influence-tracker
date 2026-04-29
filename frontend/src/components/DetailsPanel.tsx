import { useEffect, useMemo, useRef, useState } from "react";
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
  Megaphone,
  Network,
  PanelRightClose,
  Phone,
  X,
  Vote
} from "lucide-react";
import { fetchRepresentativeEvidence } from "../api";
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
  onOpenRepresentativeGraph: (personId: number, label: string) => void;
  onOpenPartyProfile: (partyId: number, label: string) => void;
  onCloseContact: () => void;
  onCollapse: () => void;
  collapseButtonRef?: React.Ref<HTMLButtonElement>;
};

type EvidencePageState = {
  events: RepresentativeEvent[];
  status: LoadState;
  error: string;
  hasMore: boolean | null;
};

const emptyEvidencePageState: EvidencePageState = {
  events: [],
  status: "idle",
  error: "",
  hasMore: null
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
  onOpenRepresentativeGraph,
  onOpenPartyProfile,
  onCloseContact,
  onCollapse,
  collapseButtonRef
}: DetailsPanelProps) {
  const [eventFamilyFilter, setEventFamilyFilter] = useState("all");
  const [expandedEventId, setExpandedEventId] = useState<number | null>(null);
  const [visibleDirectEventCount, setVisibleDirectEventCount] = useState(8);
  const [visibleCampaignSupportEventCount, setVisibleCampaignSupportEventCount] = useState(5);
  const [directEvidencePages, setDirectEvidencePages] = useState<Record<string, EvidencePageState>>({});
  const [campaignEvidencePage, setCampaignEvidencePage] =
    useState<EvidencePageState>(emptyEvidencePageState);
  const directEvidenceAbortRef = useRef<AbortController | null>(null);
  const campaignEvidenceAbortRef = useRef<AbortController | null>(null);
  const recentEvents = representativeProfile?.recent_events ?? [];
  const campaignSupportSummary = representativeProfile?.campaign_support_summary ?? [];
  const campaignSupportEvents = representativeProfile?.campaign_support_recent_events ?? [];
  const directPageKey = `${selectedPersonId ?? "none"}:${eventFamilyFilter}`;
  const directPageState = directEvidencePages[directPageKey] ?? emptyEvidencePageState;
  const topSectors = useMemo(
    () => (representativeProfile?.influence_by_sector ?? []).slice(0, 4),
    [representativeProfile]
  );
  const topVoteTopics = useMemo(
    () => (representativeProfile?.vote_topics ?? []).slice(0, 4),
    [representativeProfile]
  );
  const reviewedPolicyContexts = useMemo(
    () => (representativeProfile?.source_effect_context ?? []).slice(0, 3),
    [representativeProfile]
  );
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
  const matchingLoadedEvents = useMemo(() => {
    const baseEvents = eventFamilyFilter === "all"
      ? recentEvents
      : recentEvents.filter((event) => event.event_family === eventFamilyFilter);
    return mergeEvents(baseEvents, directPageState.events);
  }, [directPageState.events, eventFamilyFilter, recentEvents]);
  const visibleEvents = useMemo(
    () => matchingLoadedEvents.slice(0, visibleDirectEventCount),
    [matchingLoadedEvents, visibleDirectEventCount]
  );
  const selectedFamilyTotalCount = useMemo(() => {
    return eventFamilyOptions.find((option) => option.key === eventFamilyFilter)?.count ?? 0;
  }, [eventFamilyFilter, eventFamilyOptions]);
  const canRevealLoadedDirectEvents = matchingLoadedEvents.length > visibleEvents.length;
  const canLoadRemoteDirectEvents =
    selectedFamilyTotalCount > matchingLoadedEvents.length && directPageState.hasMore !== false;
  const campaignSupportTotalCount = useMemo(
    () => campaignSupportSummary.reduce((total, summary) => total + summary.event_count, 0),
    [campaignSupportSummary]
  );
  const loadedCampaignSupportEvents = useMemo(
    () => mergeEvents(campaignSupportEvents, campaignEvidencePage.events),
    [campaignEvidencePage.events, campaignSupportEvents]
  );
  const visibleCampaignSupportEvents = useMemo(
    () => loadedCampaignSupportEvents.slice(0, visibleCampaignSupportEventCount),
    [loadedCampaignSupportEvents, visibleCampaignSupportEventCount]
  );
  const canRevealLoadedCampaignSupportEvents =
    loadedCampaignSupportEvents.length > visibleCampaignSupportEvents.length;
  const canLoadRemoteCampaignSupportEvents =
    campaignSupportTotalCount > loadedCampaignSupportEvents.length &&
    campaignEvidencePage.hasMore !== false;

  useEffect(() => {
    directEvidenceAbortRef.current?.abort();
    campaignEvidenceAbortRef.current?.abort();
    setEventFamilyFilter("all");
    setExpandedEventId(null);
    setVisibleDirectEventCount(8);
    setVisibleCampaignSupportEventCount(5);
    setDirectEvidencePages({});
    setCampaignEvidencePage(emptyEvidencePageState);
  }, [selectedPersonId]);

  function loadMoreDirectEvents() {
    if (!selectedPersonId || !representativeProfile || directPageState.status === "loading") return;
    const cursor = matchingLoadedEvents.at(-1)?.pagination_cursor;
    const controller = new AbortController();
    const pageKey = directPageKey;
    directEvidenceAbortRef.current?.abort();
    directEvidenceAbortRef.current = controller;
    setDirectEvidencePages((current) => ({
      ...current,
      [pageKey]: {
        ...(current[pageKey] ?? emptyEvidencePageState),
        status: "loading",
        error: ""
      }
    }));
    fetchRepresentativeEvidence({
      personId: selectedPersonId,
      group: "direct",
      eventFamily: eventFamilyFilter === "all" ? undefined : eventFamilyFilter,
      cursor,
      limit: 25,
      signal: controller.signal
    })
      .then((payload) => {
        if (controller.signal.aborted) return;
        setDirectEvidencePages((current) => {
          const prior = current[pageKey]?.events ?? [];
          return {
            ...current,
            [pageKey]: {
              events: mergeEvents(prior, payload.events),
              status: "ready",
              error: "",
              hasMore: payload.has_more
            }
          };
        });
        setVisibleDirectEventCount((current) =>
          Math.max(current, Math.min(current + 8, matchingLoadedEvents.length + payload.events.length))
        );
      })
      .catch((error: Error) => {
        if (controller.signal.aborted) return;
        setDirectEvidencePages((current) => ({
          ...current,
          [pageKey]: {
            ...(current[pageKey] ?? emptyEvidencePageState),
            status: "error",
            error: error.message,
            hasMore: current[pageKey]?.hasMore ?? null
          }
        }));
      });
  }

  function loadMoreCampaignSupportEvents() {
    if (!selectedPersonId || !representativeProfile || campaignEvidencePage.status === "loading") return;
    const cursor = loadedCampaignSupportEvents.at(-1)?.pagination_cursor;
    const controller = new AbortController();
    campaignEvidenceAbortRef.current?.abort();
    campaignEvidenceAbortRef.current = controller;
    setCampaignEvidencePage((current) => ({
      ...current,
      status: "loading",
      error: ""
    }));
    fetchRepresentativeEvidence({
      personId: selectedPersonId,
      group: "campaign_support",
      cursor,
      limit: 25,
      signal: controller.signal
    })
      .then((payload) => {
        if (controller.signal.aborted) return;
        setCampaignEvidencePage((current) => ({
          events: mergeEvents(current.events, payload.events),
          status: "ready",
          error: "",
          hasMore: payload.has_more
        }));
        setVisibleCampaignSupportEventCount((current) =>
          Math.max(
            current,
            Math.min(current + 5, loadedCampaignSupportEvents.length + payload.events.length)
          )
        );
      })
      .catch((error: Error) => {
        if (controller.signal.aborted) return;
        setCampaignEvidencePage((current) => ({
          ...current,
          status: "error",
          error: error.message
        }));
      });
  }

  if (!feature) {
    return (
      <aside className="details-panel empty" id="selection-details-panel" aria-label="Selection details">
        <button
          ref={collapseButtonRef}
          type="button"
          className="panel-collapse-button details-collapse-button"
          aria-label="Collapse selection details"
          aria-controls="selection-details-panel"
          aria-expanded={true}
          title="Collapse selection details"
          onClick={onCollapse}
        >
          <PanelRightClose size={16} aria-hidden="true" />
        </button>
        <AlertCircle size={20} />
        <p>No electorate selected.</p>
        {caveat && <p className="caveat compact">{caveat}</p>}
      </aside>
    );
  }

  const properties = feature.properties;
  if (properties.chamber.toLowerCase() === "state") {
    return (
      <aside className="details-panel" id="selection-details-panel" aria-label="Selection details">
        <button
          ref={collapseButtonRef}
          type="button"
          className="panel-collapse-button details-collapse-button"
          aria-label="Collapse selection details"
          aria-controls="selection-details-panel"
          aria-expanded={true}
          title="Collapse selection details"
          onClick={onCollapse}
        >
          <PanelRightClose size={16} aria-hidden="true" />
        </button>
        <div className="panel-header" style={{ borderColor: partyColor }}>
          <div>
            <p className="eyebrow">{properties.state_or_territory || "State"} · State electorate</p>
            <h2>{properties.electorate_name}</h2>
          </div>
          <span className="party-dot" style={{ background: partyColor }} />
        </div>
        <section className="panel-section">
          <h3>State Map Layer</h3>
          <p className="scope-caption">
            This is a source-backed state electorate boundary. State disclosure rows are
            loaded in the State panel, but they are not yet attributed to this electorate
            or a current state MP unless the source supports that narrower link.
          </p>
          <div className="fact-grid">
            <Fact
              icon={<MapPin size={17} />}
              label="Boundary source"
              value={humanize(properties.boundary_set || "Loaded")}
              tooltip="Official QLD state electorate boundary geometry stored separately from disclosure records."
            />
            <Fact
              icon={<CheckCircle2 size={17} />}
              label="Geometry"
              value={properties.map_geometry_role === "display" ? "Land-clipped" : "Source"}
              tooltip="Display geometry may be clipped for map readability while source geometry remains preserved in the database."
            />
          </div>
        </section>
        <section className="panel-section">
          <h3>Representative Join Status</h3>
          <p className="scope-caption">
            State MP office-term joins are the next state-layer step. Until then, this
            panel avoids showing direct person-linked money, gifts, or campaign support
            for a state electorate.
          </p>
        </section>
        <p className="caveat">{caveat}</p>
      </aside>
    );
  }
  return (
    <aside className="details-panel" id="selection-details-panel" aria-label="Selection details">
      <button
        ref={collapseButtonRef}
        type="button"
        className="panel-collapse-button details-collapse-button"
        aria-label="Collapse selection details"
        aria-controls="selection-details-panel"
        aria-expanded={true}
        title="Collapse selection details"
        onClick={onCollapse}
      >
        <PanelRightClose size={16} aria-hidden="true" />
      </button>
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
                  <div className="rep-action-row">
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
                        <small>
                          {representative.chamber}
                          {representative.state_or_territory
                            ? ` · ${representative.state_or_territory}`
                            : ""}
                          {representative.term_start
                            ? ` · term from ${representative.term_start}`
                            : ""}
                        </small>
                      </div>
                      <ArrowRight size={16} aria-hidden="true" />
                    </button>
                    <button
                      className="graph-open-button"
                      type="button"
                      aria-label={`Open evidence network for ${representative.display_name}`}
                      title="Open source-backed evidence network"
                      onClick={() =>
                        onOpenRepresentativeGraph(
                          representative.person_id,
                          representative.display_name
                        )
                      }
                    >
                      <Network size={17} aria-hidden="true" />
                    </button>
                  </div>
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
        <h3>Representative-Linked Disclosures</h3>
        <p className="scope-caption">
          Published rows are source-backed records that have not been rejected by review.
          Counts are descriptive and do not imply wrongdoing.
        </p>
        <div className="fact-grid">
          <Fact
            icon={<CheckCircle2 size={17} />}
            label="Published records"
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
            icon={<Megaphone size={17} />}
            label="Campaign support"
            value={properties.current_representative_lifetime_campaign_support_event_count.toLocaleString("en-AU")}
            tooltip="Backend event_family = campaign_support. These are candidate, Senate group, party-channelled, third-party, or advertising campaign records. They are not treated as money personally received by the representative."
          />
          <Fact
            icon={<Vote size={17} />}
            label="Reported direct total"
            value={formatMoney(properties.current_representative_lifetime_reported_amount_total)}
            tooltip="Sum of reported monetary amounts for non-rejected person-linked direct records, excluding campaign-support records. Records with not-disclosed values stay in the count but not the total."
          />
        </div>
      </section>

      <section className="panel-section campaign-support-panel">
        <h3>Campaign and Party-Channelled Support</h3>
        <p className="scope-caption">
          Direct money and benefit counts are shown above. This section expands campaign,
          party-channelled, public-funding, and advertising context only; we deliberately do
          not sum these records into personal money received.
        </p>
        <div className="fact-grid">
          <Fact
            icon={<Megaphone size={17} />}
            label="Campaign support rows"
            value={properties.current_representative_lifetime_campaign_support_event_count.toLocaleString("en-AU")}
            tooltip="Candidate/Senate-group return rows, campaign expenditure, nil-return context, and related source-backed campaign activity where loaded."
          />
          <Fact
            icon={<Vote size={17} />}
            label="Campaign reported"
            value={formatMoney(
              properties.current_representative_campaign_support_reported_total
            )}
            tooltip="Reported monetary amounts for campaign-support rows. This is campaign support connected to the candidate/electorate context, not money personally received."
          />
        </div>
        {representativeProfileStatus === "ready" && representativeProfile && (
          <>
            {campaignSupportSummary.length ? (
              <div className="event-family-grid campaign-summary-grid">
                {campaignSupportSummary.map((summary) => (
                  <div
                    className="event-family campaign-family"
                    key={`${summary.event_type}:${summary.attribution_tier || "unknown"}`}
                    title={campaignSupportTooltip(summary)}
                  >
                    <small>{summary.event_type.replaceAll("_", " ")}</small>
                    <strong>{summary.event_count.toLocaleString("en-AU")}</strong>
                    <span>{formatMoney(summary.reported_amount_total)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">No campaign-support records are linked to this representative yet.</p>
            )}
            {representativeProfile.campaign_support_caveat && (
              <p className="event-count-note">{representativeProfile.campaign_support_caveat}</p>
            )}
            {loadedCampaignSupportEvents.length > 0 && (
              <div className="event-list campaign-event-list">
                {visibleCampaignSupportEvents.map((event) => (
                  <EventRow
                    event={event}
                    expanded={expandedEventId === event.id}
                    key={event.id}
                    onToggle={() =>
                      setExpandedEventId((current) => (current === event.id ? null : event.id))
                    }
                  />
                ))}
              </div>
            )}
            {campaignEvidencePage.status === "error" && (
              <p className="muted">Could not load more campaign-support records: {campaignEvidencePage.error}</p>
            )}
            {(canRevealLoadedCampaignSupportEvents ||
              canLoadRemoteCampaignSupportEvents ||
              campaignEvidencePage.status === "loading") && (
              <div className="event-list-actions">
                <button
                  type="button"
                  disabled={campaignEvidencePage.status === "loading"}
                  onClick={() => {
                    if (canRevealLoadedCampaignSupportEvents) {
                      setVisibleCampaignSupportEventCount((current) =>
                        Math.min(current + 5, loadedCampaignSupportEvents.length)
                      );
                    } else {
                      loadMoreCampaignSupportEvents();
                    }
                  }}
                >
                  {campaignEvidencePage.status === "loading" ? (
                    <>
                      <Loader2 size={14} className="spin" aria-hidden="true" />
                      Loading records
                    </>
                  ) : canRevealLoadedCampaignSupportEvents ? (
                    "Show more campaign-support records"
                  ) : (
                    "Load more campaign-support records"
                  )}
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {representativeProfileStatus === "ready" &&
        representativeProfile &&
        (topSectors.length > 0 ||
          topVoteTopics.length > 0 ||
          reviewedPolicyContexts.length > 0) && (
          <section className="panel-section evidence-signals-panel">
            <h3>Evidence Signals</h3>
            <p className="scope-caption">
              These are descriptive links in the database. They show disclosed sectors,
              voting-topic records, and reviewed sector-topic overlap; they do not claim
              causation or improper conduct.
            </p>
            {topSectors.length > 0 && (
              <SignalBlock title="Disclosed sectors">
                {topSectors.map((sector) => (
                  <SignalRow
                    key={sector.public_sector}
                    label={sector.public_sector.replaceAll("_", " ")}
                    value={`${sector.influence_event_count.toLocaleString("en-AU")} records`}
                    detail={[
                      sector.money_event_count
                        ? `${sector.money_event_count.toLocaleString("en-AU")} money`
                        : "",
                      sector.benefit_event_count
                        ? `${sector.benefit_event_count.toLocaleString("en-AU")} benefits`
                        : "",
                      formatMoney(sector.reported_amount_total)
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  />
                ))}
              </SignalBlock>
            )}
            {topVoteTopics.length > 0 && (
              <SignalBlock title="Vote topics">
                {topVoteTopics.map((topic) => (
                  <SignalRow
                    key={`${topic.chamber}:${topic.topic_slug}`}
                    label={topic.topic_label}
                    value={`${topic.division_vote_count.toLocaleString("en-AU")} divisions`}
                    detail={[
                      `${topic.aye_count.toLocaleString("en-AU")} aye`,
                      `${topic.no_count.toLocaleString("en-AU")} no`,
                      voteDateSpan(topic.first_division_date, topic.last_division_date)
                    ].join(" · ")}
                  />
                ))}
              </SignalBlock>
            )}
            {reviewedPolicyContexts.length > 0 && (
              <SignalBlock title="Reviewed source-policy overlap">
                {reviewedPolicyContexts.map((context) => (
                  <SignalRow
                    key={`${context.topic_label}:${context.public_sector}:${context.relationship}`}
                    label={`${context.public_sector.replaceAll("_", " ")} -> ${context.topic_label}`}
                    value={`${context.lifetime_influence_event_count.toLocaleString("en-AU")} context records`}
                    detail={[
                      context.relationship.replaceAll("_", " "),
                      `vote window: ${context.division_vote_count.toLocaleString("en-AU")} divisions`,
                      formatMoney(context.lifetime_reported_amount_total)
                    ].join(" · ")}
                  />
                ))}
              </SignalBlock>
            )}
          </section>
        )}

      <section className="panel-section">
        <h3>Direct Disclosed Person Records</h3>
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
            {totalRepresentativeEvents > 0 && (
              <p className="scope-caption">
                Most parliamentary register rows publish a category and source wording,
                but not a dollar value. Missing value means not disclosed in the loaded
                source, not zero.
              </p>
            )}
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
                      setVisibleDirectEventCount(8);
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
                Showing {visibleEvents.length.toLocaleString("en-AU")} of{" "}
                {matchingLoadedEvents.length.toLocaleString("en-AU")} loaded records
                {selectedFamilyTotalCount > matchingLoadedEvents.length
                  ? ` from ${selectedFamilyTotalCount.toLocaleString("en-AU")} published person-linked records`
                  : ""}.
              </p>
            )}
            <div className="event-list">
              {visibleEvents.map((event) => (
                <EventRow
                  event={event}
                  expanded={expandedEventId === event.id}
                  key={event.id}
                  onToggle={() =>
                    setExpandedEventId((current) => (current === event.id ? null : event.id))
                  }
                  />
              ))}
              {visibleEvents.length === 0 && eventFamilyFilter !== "all" && (
                <p className="muted">No loaded records match this filter.</p>
              )}
            </div>
            {directPageState.status === "error" && (
              <p className="muted">Could not load more source records: {directPageState.error}</p>
            )}
            {(canRevealLoadedDirectEvents ||
              canLoadRemoteDirectEvents ||
              directPageState.status === "loading") && (
              <div className="event-list-actions">
                <button
                  type="button"
                  disabled={directPageState.status === "loading"}
                  onClick={() => {
                    if (canRevealLoadedDirectEvents) {
                      setVisibleDirectEventCount((current) =>
                        Math.min(current + 8, matchingLoadedEvents.length)
                      );
                    } else {
                      loadMoreDirectEvents();
                    }
                  }}
                >
                  {directPageState.status === "loading" ? (
                    <>
                      <Loader2 size={14} className="spin" aria-hidden="true" />
                      Loading records
                    </>
                  ) : canRevealLoadedDirectEvents ? (
                    "Show more loaded records"
                  ) : (
                    "Load more source records"
                  )}
                </button>
              </div>
            )}
          </>
        )}
      </section>

      <section className="panel-section">
        <h3>Party Breakdown</h3>
        <div className="party-breakdown">
          {properties.party_breakdown.length ? (
            properties.party_breakdown.map((party) => {
              const label = party.party_name || "No party recorded";
              if (!party.party_id) {
                return (
                  <div className="party-row" key={`${party.party_id}:${party.party_name}`}>
                    <span>{label}</span>
                    <strong>{party.representative_count}</strong>
                  </div>
                );
              }
              return (
                <button
                  className="party-row"
                  key={`${party.party_id}:${party.party_name}`}
                  type="button"
                  title={`Open party money profile for ${label}`}
                  onClick={() => onOpenPartyProfile(Number(party.party_id), label)}
                >
                  <span>{label}</span>
                  <strong>{party.representative_count}</strong>
                </button>
              );
            })
          ) : (
            <p className="muted">No party breakdown is available.</p>
          )}
        </div>
      </section>

      <p className="caveat">{caveat}</p>
    </aside>
  );
}

function eventSummaryMeta(event: RepresentativeEvent): string {
  return [
    event.amount === null ? null : formatMoney(event.amount),
    event.event_date
  ]
    .filter((value): value is string => Boolean(value))
    .join(" · ");
}

function registerPeriodLabel(value: string): string {
  const cleaned = value.trim();
  if (!cleaned) return "";
  if (/^\d+$/.test(cleaned)) {
    const periodNumber = Number(cleaned);
    return `${periodNumber}${ordinalSuffix(periodNumber)} Parliament`;
  }
  return cleaned;
}

function ordinalSuffix(value: number): string {
  const mod100 = value % 100;
  if (mod100 >= 11 && mod100 <= 13) return "th";
  switch (value % 10) {
    case 1:
      return "st";
    case 2:
      return "nd";
    case 3:
      return "rd";
    default:
      return "th";
  }
}

function humanize(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\w/, (match) => match.toUpperCase());
}

function eventTypeLabel(event: RepresentativeEvent): string {
  const normalized = event.event_type.toLowerCase();
  const labels: Record<string, string> = {
    gift: "Gift or benefit",
    gift_in_kind: "Gift in kind",
    membership: "Membership or role",
    organisational_role: "Organisation role",
    sponsored_travel_or_hospitality: "Sponsored travel or hospitality",
    travel_or_hospitality: "Travel or hospitality"
  };
  return labels[normalized] ?? humanize(event.event_type);
}

function eventFamilyLabel(value: string): string {
  const labels: Record<string, string> = {
    benefit: "Benefit",
    money: "Money",
    organisational_role: "Role or membership",
    private_interest: "Private interest",
    access: "Access context"
  };
  return labels[value] ?? humanize(value);
}

function eventSourceLabel(event: RepresentativeEvent): string {
  return (
    (isUsefulRecordText(event.source_entity_name) ? event.source_entity_name : null) ||
    (isUsefulRecordText(event.source_raw_name) ? event.source_raw_name : null) ||
    (event.event_family === "benefit" ? "Provider not named" : "Source not named")
  );
}

function eventDetailMeta(event: RepresentativeEvent): string[] {
  return [
    event.date_reported ? `Reported ${event.date_reported}` : null
  ].filter((value): value is string => Boolean(value));
}

function eventChips(event: RepresentativeEvent): string[] {
  const evidenceStatus = normalizeStatusKey(event.evidence_status);
  const reviewStatus = normalizeStatusKey(event.review_status);
  return [
    eventFamilyLabel(event.event_family),
    event.amount !== null ? "Dollar value disclosed" : null,
    evidenceStatus && evidenceStatus !== "official_record_parsed"
      ? `Evidence: ${humanize(event.evidence_status)}`
      : null,
    reviewStatus && reviewStatus !== "needs_review"
      ? reviewStatus === "reviewed"
        ? "Human reviewed"
        : `Review: ${humanize(event.review_status)}`
      : null
  ].filter((value): value is string => Boolean(value));
}

function normalizeStatusKey(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function isUsefulRecordText(value: string | null | undefined): value is string {
  if (!value) return false;
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (!cleaned) return false;
  const normalized = cleaned
    .replace(/[()[\].,:;'"`]+/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
  return !new Set([
    "na",
    "n a",
    "n/a",
    "rna",
    "not applicable",
    "not disclosed",
    "source not identified",
    "provider not named",
    "source not named"
  ]).has(normalized);
}

function eventDescription(event: RepresentativeEvent): string | null {
  if (!isUsefulRecordText(event.description)) return null;
  const sourceLabel = eventSourceLabel(event);
  if (event.description.trim().toLowerCase() === sourceLabel.trim().toLowerCase()) return null;
  return event.description;
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
  const sourceHref = safeSourceHref(event.source_final_url || event.source_url);
  const sourceName = event.source_name || event.source_id || "Source document";
  const tooltip = eventBackendTooltip(event);
  const summaryMeta = eventSummaryMeta(event);
  const detailMeta = eventDetailMeta(event);
  const chips = eventChips(event);
  const description = eventDescription(event);
  return (
    <article className="event-row" data-expanded={expanded} title={tooltip}>
      <button
        type="button"
        className="event-summary-button"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <div>
          <strong>{eventTypeLabel(event)}</strong>
          <span>{eventSourceLabel(event)}</span>
        </div>
        {summaryMeta && <small>{summaryMeta}</small>}
      </button>
      {detailMeta.length > 0 && <small className="event-meta-line">{detailMeta.join(" · ")}</small>}
      {description && <p>{description}</p>}
      {chips.length > 0 && (
        <div className="event-chip-row">
          {chips.map((chip) => (
            <span key={chip}>{chip}</span>
          ))}
        </div>
      )}
      {expanded && (
        <div className="event-detail">
          <DetailLine label="Record category">{eventFamilyLabel(event.event_family)}</DetailLine>
          <DetailLine label="Detailed type">
            {[event.event_type, event.event_subtype].filter(Boolean).join(" / ")}
          </DetailLine>
          <DetailLine label="Public register">{event.disclosure_system}</DetailLine>
          <DetailLine label="How captured">{humanize(event.extraction_method)}</DetailLine>
          <DetailLine label="Evidence status">{humanize(event.evidence_status)}</DetailLine>
          <DetailLine label="Review status">{humanize(event.review_status)}</DetailLine>
          <DetailLine label="Source document">
            {sourceHref ? (
              <a href={sourceHref} target="_blank" rel="noreferrer">
                {sourceName}
              </a>
            ) : (
              sourceName
            )}
          </DetailLine>
          <DetailLine label="Source row">{event.source_ref || "Not recorded"}</DetailLine>
          {event.reporting_period && (
            <DetailLine label="Parliament/register period">
              {registerPeriodLabel(event.reporting_period)}
            </DetailLine>
          )}
          <DetailLine label="Dollar value">
            {[humanize(event.amount_status), event.currency].filter(Boolean).join(" · ")}
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

function mergeEvents(baseEvents: RepresentativeEvent[], additionalEvents: RepresentativeEvent[]) {
  const seen = new Set<number>();
  const merged: RepresentativeEvent[] = [];
  for (const event of [...baseEvents, ...additionalEvents]) {
    if (seen.has(event.id)) continue;
    seen.add(event.id);
    merged.push(event);
  }
  return merged;
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

function campaignSupportTooltip(summary: {
  event_type: string;
  attribution_tier: string | null;
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
    `Backend event_type: ${summary.event_type}`,
    `Attribution tier: ${summary.attribution_tier || "source-backed campaign support"}`,
    "Interpretation: campaign support connected to a candidate/electorate context, not personal receipt.",
    `Rows: ${summary.event_count.toLocaleString("en-AU")}`,
    `Rows with reported amounts: ${summary.reported_amount_event_count.toLocaleString("en-AU")}`,
    `Reported campaign-support total: ${formatMoney(summary.reported_amount_total)}`,
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

function SignalBlock({
  title,
  children
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="signal-block">
      <h4>{title}</h4>
      <div className="signal-list">{children}</div>
    </div>
  );
}

function SignalRow({
  label,
  value,
  detail
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="signal-row">
      <div>
        <strong>{label}</strong>
        <span>{detail}</span>
      </div>
      <small>{value}</small>
    </div>
  );
}

function voteDateSpan(first: string | null, last: string | null) {
  if (!first && !last) return "dates not disclosed";
  if (first && last && first !== last) return `${first} to ${last}`;
  return first || last || "dates not disclosed";
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
