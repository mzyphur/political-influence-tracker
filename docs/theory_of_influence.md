# Operating Theory of Political Influence

Last updated: 2026-04-29

This project is not only a software system. It is an empirical model of how
political influence may operate in a liberal democracy under unequal resource
conditions. The code, database, user interface, and public language should all
reflect the same theory and the same limits of inference.

## Democratic Premise

The democratic benchmark is political equality: citizens should be able to see
who attempts to influence public officials, through which channels, and whether
those channels are concentrated among particular sectors, firms, associations,
or wealthy individuals.

The project does not assume that every disclosed money flow, gift, interest, or
lobbying relationship is improper. It assumes that concentrated, unequal, and
opaque influence is democratically important even when it is lawful. The public
interest is transparency, comparability, and disciplined inference.

## Core Mechanisms

The system should track separate mechanisms rather than flattening them into a
single corruption score.

1. Direct material transfer
   - Donations, gifts, debts, loans, benefits, hospitality, sponsored travel,
     tickets, subscriptions, memberships, and similar resources disclosed at a
     person, candidate, Senate group, party, or entity level.
   - Observable indicators: source, recipient, amount/value where disclosed,
     date, disclosure category, document/page/row reference.

2. Party-channelled influence
   - Money or benefits move through parties, branches, campaign committees,
     associated entities, foundations, unions, business groups, or third-party
     campaigners before becoming relevant to individual representatives.
   - Observable indicators: `source_entity -> party/entity -> party ->
     representative` paths, with direct, campaign, party/entity, and modelled
     tiers kept separate.

3. Access and social proximity
   - Hospitality, private travel, sporting/event tickets, memberships, dinners,
     lounge access, and repeated social settings can plausibly create access,
     familiarity, agenda-setting opportunities, or reciprocal obligations even
     without a direct donation.
   - Observable indicators: disclosed benefits, provider, category/subtype,
     timing, recurrence, source sector, and whether the provider also appears
     in money/lobbying records.

4. Organisational and career embeddedness
   - MPs and Senators may hold memberships, offices, directorships, shares,
     trusts, property interests, liabilities, or other roles that shape their
     social and economic position.
   - Observable indicators: register-of-interests categories, source entities,
     sector classifications, dates, and role types.

5. Lobbying and client networks
   - Lobbyists, firms, clients, donors, and regulated sectors can form networks
     of access and representation.
   - Observable indicators: official lobbyist registers, client lists, entity
     identifiers, meetings where available, and links to policy topics.

6. Policy behaviour and agenda alignment
   - Voting, speeches, questions, committee work, ministerial action, and policy
     agenda-setting may align with sectors that provide material support or
     access.
   - Observable indicators: votes/divisions, topics, timing windows, party-line
     behaviour, rebellion indicators, committee/portfolio context, and reviewed
     sector-policy links.

7. Structural and regime-level influence
   - Disclosure rules, thresholds, nil returns, party aggregation, missing
     values, and jurisdictional differences shape what can be seen.
   - Observable indicators: missing-data flags, disclosure thresholds, return
     type, source regime, amendment history, and records that cannot be linked
     honestly to individuals.

## Operating Hypotheses

These are research hypotheses and product questions, not conclusions.

- H1: Disclosed money and benefit flows are concentrated among particular
  sectors and recipient parties/representatives.
- H2: Individual-level sparsity is partly structural because party-handled
  campaign activity and aggregate party returns obscure candidate-level flows.
- H3: Non-cash benefits such as travel, hospitality, memberships, tickets, and
  private transport are important access mechanisms even when values are missing.
- H4: Party/entity networks mediate influence; indirect paths may be more
  informative than direct person-level records alone.
- H5: Sectoral exposure before policy behaviour may identify areas for further
  scrutiny, but it does not establish causation by itself.
- H6: Missingness is politically meaningful: non-disclosure, thresholds, and
  unparseable records are part of the accountability environment.
- H7: Cross-jurisdiction comparison can reveal how disclosure regimes shape
  observable influence, but only if each regime's legal categories and gaps are
  preserved.

## Engineering Implications

Every substantial engineering decision should document the theory it serves.

- Source preservation serves auditability and source-fact claims.
- The unified `influence_event` table serves comparability across money,
  benefits, interests, access, and policy behaviour.
- Event families prevent direct donations, campaign support, benefits, private
  interests, lobbying access, and modelled allocations from being collapsed.
- Review queues operationalize uncertainty and prevent machine guesses from
  becoming public claims.
- Entity resolution and sector classification operationalize hypotheses about
  sectoral concentration.
- Network edges operationalize indirect influence, while edge types and evidence
  tiers prevent overclaiming.
- UI caveats operationalize epistemic humility: users should see what is known,
  what is inferred, and what is missing.

## Claim Discipline

The project may show:

- source-backed flows;
- normalized flows and entity matches;
- sector classifications with confidence;
- network paths and indirect exposure;
- temporal co-occurrence between influence inputs and policy behaviour;
- patterns, concentrations, and anomalies that justify scrutiny.

The project must not claim, without stronger evidence:

- that a lawful disclosed record is a bribe;
- that an MP or Senator personally received party-level money;
- that a donor caused a vote or policy decision;
- that a missing value means a hidden value is high;
- that association alone proves improper conduct.

## Documentation Rule

For every new data family, parser, model, allocation method, graph edge, or major
UI surface, document:

- the influence mechanism being operationalized;
- the observable indicator used;
- the evidence tier and source type;
- what public claim is allowed;
- what public claim is not allowed;
- missing-data and disclosure-regime limitations;
- how the choice affects democratic transparency.

This rule applies equally to engineering notes, methodology docs, public app
copy, academic articles, and popular-press writing.

