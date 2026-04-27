from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from au_politics_money.config import PROCESSED_DIR


CLASSIFIER_NAME = "public_interest_sector_rules_v1"

PUBLIC_INTEREST_SECTORS: tuple[dict[str, str], ...] = (
    {"code": "fossil_fuels", "label": "Fossil fuels"},
    {"code": "mining", "label": "Mining and resources"},
    {"code": "renewable_energy", "label": "Renewable energy"},
    {"code": "property_development", "label": "Property development and real estate"},
    {"code": "construction", "label": "Construction and infrastructure"},
    {"code": "gambling", "label": "Gambling and wagering"},
    {"code": "alcohol", "label": "Alcohol and hospitality"},
    {"code": "tobacco", "label": "Tobacco"},
    {"code": "finance", "label": "Finance and investment"},
    {"code": "superannuation", "label": "Superannuation"},
    {"code": "insurance", "label": "Insurance"},
    {"code": "banking", "label": "Banking"},
    {"code": "technology", "label": "Technology"},
    {"code": "telecoms", "label": "Telecommunications"},
    {"code": "defence", "label": "Defence"},
    {"code": "consulting", "label": "Consulting and lobbying"},
    {"code": "law", "label": "Law"},
    {"code": "accounting", "label": "Accounting and audit"},
    {"code": "healthcare", "label": "Healthcare"},
    {"code": "pharmaceuticals", "label": "Pharmaceuticals"},
    {"code": "education", "label": "Education"},
    {"code": "media", "label": "Media"},
    {"code": "sport_entertainment", "label": "Sport and entertainment"},
    {"code": "transport", "label": "Transport and logistics"},
    {"code": "aviation", "label": "Aviation"},
    {"code": "agriculture", "label": "Agriculture"},
    {"code": "unions", "label": "Unions and worker organisations"},
    {"code": "business_associations", "label": "Business and industry associations"},
    {"code": "charities_nonprofits", "label": "Charities and nonprofits"},
    {"code": "foreign_government", "label": "Foreign government"},
    {"code": "government_owned", "label": "Government and public sector"},
    {"code": "political_entity", "label": "Political entity"},
    {"code": "individual_uncoded", "label": "Individual, uncoded"},
    {"code": "unknown", "label": "Unknown or uncoded"},
)

PUBLIC_INTEREST_SECTOR_LABELS = {
    sector["code"]: sector["label"] for sector in PUBLIC_INTEREST_SECTORS
}


@dataclass(frozen=True)
class ClassificationRule:
    rule_id: str
    public_sector: str
    entity_type: str
    confidence: str
    evidence_note: str
    patterns: tuple[str, ...]


RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        "foreign_government_names",
        "foreign_government",
        "foreign_government",
        "fuzzy_high",
        "Name indicates a foreign diplomatic or government body.",
        (
            r"\bembassy\b",
            r"\bhigh commission\b",
            r"\bconsulate\b",
            r"\bforeign government\b",
        ),
    ),
    ClassificationRule(
        "australian_public_sector",
        "government_owned",
        "government",
        "fuzzy_high",
        "Name indicates an Australian public sector or electoral body.",
        (
            r"\baustralian electoral commission\b",
            r"\belectoral commission\b",
            r"\baustralian taxation office\b",
            r"\btaxation office\b",
            r"\bdepartment of\b",
            r"\baustralian national audit office\b",
            r"\bparliament\b",
            r"\bgovernment\b",
            r"\bcity council\b",
            r"\bshire council\b",
            r"\btown council\b",
        ),
    ),
    ClassificationRule(
        "political_party_names",
        "political_entity",
        "political_party",
        "fuzzy_high",
        "Name indicates a political party, branch, or party-associated entity.",
        (
            r"\baustralian labor party\b",
            r"\blabor holdings\b",
            r"\bliberal party\b",
            r"\bnational party\b",
            r"\baustralian greens\b",
            r"\bcountry liberal party\b",
            r"\bcormack foundation\b",
            r"\bpolitical party\b",
            r"\bparty$",
            r"\bparty \(",
            r"\bparty of\b",
            r"\bparty australia\b",
            r"\bparty national\b",
        ),
    ),
    ClassificationRule(
        "union_names",
        "unions",
        "union",
        "fuzzy_high",
        "Name indicates a union, worker association, or union-linked fund.",
        (
            r"\bunion\b",
            r"\btrade union\b",
            r"\bcfmeu\b",
            r"\bc f m e u\b",
            r"\bcfmmeu\b",
            r"\bcepu\b",
            r"\betu\b",
            r"\bawu\b",
            r"\bsda\b",
            r"\bcpsu\b",
            r"\bamwu\b",
            r"\basu\b",
            r"\bhsu\b",
            r"\bmua\b",
            r"\btwu\b",
            r"\buwu\b",
            r"\bfsu\b",
            r"\bincolink\b",
            r"\bbert training fund\b",
            r"\bmining energy workers\b",
            r"\bmeu mining energy\b",
            r"\bnurses and midwives association\b",
        ),
    ),
    ClassificationRule(
        "fossil_fuel_names",
        "fossil_fuels",
        "company",
        "fuzzy_high",
        "Name indicates coal, oil, gas, or petroleum activity.",
        (
            r"\bcoal\b",
            r"\boil\b",
            r"\bgas\b",
            r"\bpetroleum\b",
            r"\bsantos\b",
            r"\bwoodside\b",
            r"\borigin energy\b",
            r"\bbeach energy\b",
            r"\bwhitehaven\b",
            r"\bnew hope\b",
        ),
    ),
    ClassificationRule(
        "mining_names",
        "mining",
        "company",
        "fuzzy_high",
        "Name indicates mining, minerals, or resources activity.",
        (
            r"\bmining\b",
            r"\bminerals?\b",
            r"\bmineralogy\b",
            r"\bsino iron\b",
            r"\biron ore\b",
            r"\bnickel\b",
            r"\bbhp\b",
            r"\brio tinto\b",
            r"\bfortescue\b",
            r"\bglencore\b",
            r"\bhancock prospecting\b",
            r"\bresources? (limited|ltd|pty|nl|p l)\b",
            r"\bresources? council\b",
        ),
    ),
    ClassificationRule(
        "renewable_energy_names",
        "renewable_energy",
        "company",
        "fuzzy_high",
        "Name indicates renewable energy activity.",
        (
            r"\brenewable\b",
            r"\bsolar\b",
            r"\bwind farm\b",
            r"\bclean energy\b",
            r"\bgreen energy\b",
        ),
    ),
    ClassificationRule(
        "banking_names",
        "banking",
        "company",
        "fuzzy_high",
        "Name indicates a bank, credit union, or deposit-taking institution.",
        (
            r"\bwestpac\b",
            r"\bcommonwealth bank\b",
            r"\bcba\b",
            r"\banz\b",
            r"\bnab\b",
            r"\bnational australia bank\b",
            r"\bbank(ing)? (corporation|limited|ltd|australia|group)\b",
            r"\b(bank|banking)$",
            r"\bbank of\b",
            r"\bcredit union\b",
            r"\bing\b",
            r"\bmacquarie bank\b",
        ),
    ),
    ClassificationRule(
        "superannuation_names",
        "superannuation",
        "company",
        "fuzzy_high",
        "Name indicates a superannuation fund.",
        (
            r"\bsuperannuation\b",
            r"\bsuper fund\b",
            r"\baustralian ?super\b",
            r"\bcbus\b",
            r"\bhostplus\b",
            r"\bunisuper\b",
            r"\bhesta\b",
            r"\baware super\b",
        ),
    ),
    ClassificationRule(
        "insurance_names",
        "insurance",
        "company",
        "fuzzy_high",
        "Name indicates insurance activity.",
        (
            r"\binsurance\b",
            r"\bnrma\b",
            r"\biag\b",
            r"\ballianz\b",
            r"\bsuncorp\b",
        ),
    ),
    ClassificationRule(
        "finance_names",
        "finance",
        "company",
        "fuzzy_high",
        "Name indicates finance, investment, funds management, or payments activity.",
        (
            r"\bfinancial\b",
            r"\bfinance\b",
            r"\bcapital\b",
            r"\binvestments?\b",
            r"\bsecurities\b",
            r"\bwealth\b",
            r"\bmorgans\b",
            r"\bfunds? management\b",
            r"\btrust company\b",
            r"\bcardtronics\b",
            r"\beze atm\b",
            r"\batm\b",
        ),
    ),
    ClassificationRule(
        "property_names",
        "property_development",
        "company",
        "fuzzy_high",
        "Name indicates property, real estate, or development activity.",
        (
            r"\bproperty\b",
            r"\bproperties\b",
            r"\breal estate\b",
            r"\bdevelopment\b",
            r"\bdeveloper\b",
            r"\bgpt\b",
            r"\bjones lang lasalle\b",
            r"\bjll\b",
            r"\blendlease\b",
            r"\bmirvac\b",
            r"\bstockland\b",
            r"\bdexus\b",
            r"\bgoodman\b",
            r"\bmeriton\b",
            r"\bfrasers\b",
        ),
    ),
    ClassificationRule(
        "construction_names",
        "construction",
        "company",
        "fuzzy_high",
        "Name indicates construction, building, or infrastructure activity.",
        (
            r"\bconstruction\b",
            r"\bbuilders?\b",
            r"\bbuilding\b",
            r"\binfrastructure\b",
            r"\bmaster builders\b",
        ),
    ),
    ClassificationRule(
        "gambling_names",
        "gambling",
        "company",
        "fuzzy_high",
        "Name indicates gambling, wagering, casino, or gaming activity.",
        (
            r"\bcasino\b",
            r"\bgaming\b",
            r"\bwagering\b",
            r"\bsportsbet\b",
            r"\btabcorp\b",
            r"\btab\b",
            r"\bcrown\b",
            r"\bstar entertainment\b",
            r"\bclubs?nsw\b",
        ),
    ),
    ClassificationRule(
        "alcohol_hospitality_names",
        "alcohol",
        "company",
        "fuzzy_high",
        "Name indicates alcohol or hospitality activity.",
        (
            r"\bbrewery\b",
            r"\bbrewing\b",
            r"\bwine\b",
            r"\bwinery\b",
            r"\bliquor\b",
            r"\bhotel\b",
            r"\bnovotel\b",
            r"\brydges\b",
            r"\baccor\b",
            r"\bhotels? association\b",
        ),
    ),
    ClassificationRule(
        "tobacco_names",
        "tobacco",
        "company",
        "fuzzy_high",
        "Name indicates tobacco activity.",
        (r"\btobacco\b", r"\bphilip morris\b", r"\bbritish american tobacco\b"),
    ),
    ClassificationRule(
        "aviation_names",
        "aviation",
        "company",
        "fuzzy_high",
        "Name indicates aviation or airport activity.",
        (
            r"\bqantas\b",
            r"\bvirgin australia\b",
            r"\bairways?\b",
            r"\bairlines?\b",
            r"\bairport\b",
        ),
    ),
    ClassificationRule(
        "telecoms_names",
        "telecoms",
        "company",
        "fuzzy_high",
        "Name indicates telecommunications activity.",
        (
            r"\btelstra\b",
            r"\boptus\b",
            r"\btpg\b",
            r"\bvodafone\b",
            r"\btelecom\b",
            r"\btelecommunications\b",
        ),
    ),
    ClassificationRule(
        "technology_names",
        "technology",
        "company",
        "fuzzy_high",
        "Name indicates technology, software, or digital services.",
        (
            r"\btechnology\b",
            r"\bsoftware\b",
            r"\bgoogle\b",
            r"\bmeta\b",
            r"\bmicrosoft\b",
            r"\bamazon web services\b",
            r"\bpalantir\b",
            r"\bdigital\b",
        ),
    ),
    ClassificationRule(
        "defence_names",
        "defence",
        "company",
        "fuzzy_high",
        "Name indicates defence or aerospace activity.",
        (
            r"\bdefence\b",
            r"\baerospace\b",
            r"\blockheed\b",
            r"\bboeing\b",
            r"\bthales\b",
            r"\bbae\b",
            r"\braytheon\b",
            r"\bnorthrop\b",
        ),
    ),
    ClassificationRule(
        "accounting_names",
        "accounting",
        "company",
        "fuzzy_high",
        "Name indicates accounting, audit, or professional services.",
        (
            r"\baccounting\b",
            r"\baccountants?\b",
            r"\bchartered accountants?\b",
            r"\bdeloitte\b",
            r"\bpwc\b",
            r"\bkpmg\b",
            r"\bernst young\b",
            r"\bey\b",
        ),
    ),
    ClassificationRule(
        "law_names",
        "law",
        "company",
        "fuzzy_high",
        "Name indicates legal services.",
        (
            r"\blaw\b",
            r"\blawyers?\b",
            r"\blegal\b",
            r"\bsolicitors?\b",
            r"\bbarristers?\b",
        ),
    ),
    ClassificationRule(
        "consulting_lobbying_names",
        "consulting",
        "company",
        "fuzzy_high",
        "Name indicates consulting, lobbying, advisory, or public affairs services.",
        (
            r"\bconsulting\b",
            r"\bconsultants?\b",
            r"\badvisory\b",
            r"\blobby\b",
            r"\bpublic affairs\b",
            r"\bgovernment relations\b",
            r"\bstrategic\b",
        ),
    ),
    ClassificationRule(
        "pharma_names",
        "pharmaceuticals",
        "company",
        "fuzzy_high",
        "Name indicates pharmaceutical activity.",
        (r"\bpharma\b", r"\bpharmaceutical\b", r"\bmedicines?\b"),
    ),
    ClassificationRule(
        "healthcare_names",
        "healthcare",
        "company",
        "fuzzy_high",
        "Name indicates healthcare, hospital, or medical activity.",
        (
            r"\bhealth\b",
            r"\bhospital\b",
            r"\bmedical\b",
            r"\bclinic\b",
        ),
    ),
    ClassificationRule(
        "education_names",
        "education",
        "association",
        "fuzzy_high",
        "Name indicates education activity.",
        (
            r"\buniversity\b",
            r"\bschool\b",
            r"\bcollege\b",
            r"\btafe\b",
            r"\beducation\b",
        ),
    ),
    ClassificationRule(
        "media_names",
        "media",
        "company",
        "fuzzy_high",
        "Name indicates media, broadcasting, or publishing activity.",
        (
            r"\bnews corp\b",
            r"\bmedia\b",
            r"\bnetwork\b",
            r"\bsupernetwork\b",
            r"\bfoxtel\b",
            r"\bnine\b",
            r"\bseven\b",
            r"\babc\b",
            r"\bradio\b",
            r"\btelevision\b",
            r"\bnewspaper\b",
        ),
    ),
    ClassificationRule(
        "sport_entertainment_names",
        "sport_entertainment",
        "company",
        "fuzzy_high",
        "Name indicates sport, racing, club, or entertainment activity.",
        (
            r"\bfootball\b",
            r"\bafl\b",
            r"\bnrl\b",
            r"\bcricket\b",
            r"\bracing\b",
            r"\bstadium\b",
            r"\bentertainment\b",
            r"\btheatre\b",
            r"\bclub\b",
        ),
    ),
    ClassificationRule(
        "transport_names",
        "transport",
        "company",
        "fuzzy_high",
        "Name indicates transport or logistics activity.",
        (
            r"\btransport\b",
            r"\blogistics\b",
            r"\brail\b",
            r"\bbus\b",
            r"\btoll\b",
            r"\btransurban\b",
            r"\bports?\b",
            r"\bfreight\b",
        ),
    ),
    ClassificationRule(
        "agriculture_names",
        "agriculture",
        "company",
        "fuzzy_high",
        "Name indicates agriculture, farming, livestock, or primary production activity.",
        (
            r"\bfarm\b",
            r"\bfarms\b",
            r"\bpastoral\b",
            r"\bagriculture\b",
            r"\blivestock\b",
            r"\bmeat\b",
            r"\bdairy\b",
            r"\bgrain\b",
            r"\bcotton\b",
            r"\bwool\b",
            r"\bforestry\b",
            r"\bvineyard\b",
        ),
    ),
    ClassificationRule(
        "business_association_names",
        "business_associations",
        "association",
        "fuzzy_high",
        "Name indicates a business, industry, or professional association.",
        (
            r"\bchamber of commerce\b",
            r"\bbusiness council\b",
            r"\bindustry association\b",
            r"\bassociation\b",
            r"\binstitute\b",
        ),
    ),
    ClassificationRule(
        "charity_nonprofit_names",
        "charities_nonprofits",
        "association",
        "fuzzy_high",
        "Name indicates a charity, nonprofit, or community organisation.",
        (
            r"\bcharity\b",
            r"\bcharitable\b",
            r"\bfoundation\b",
            r"\bchurch\b",
            r"\brotary\b",
            r"\bsalvation army\b",
            r"\bred cross\b",
        ),
    ),
)

NON_VALUE_NAMES = {
    "",
    "n a",
    "na",
    "nil",
    "none",
    "not applicable",
    "unknown",
    "the",
}

ORG_INDICATOR_PATTERNS = (
    r"\bpty\b",
    r"\bltd\b",
    r"\blimited\b",
    r"\binc\b",
    r"\bcorp\b",
    r"\bcorporation\b",
    r"\bcompany\b",
    r"\bco\b",
    r"\btrust\b",
    r"\bfoundation\b",
    r"\bassociation\b",
    r"\bparty\b",
    r"\bbank\b",
    r"\bgroup\b",
    r"\bholdings?\b",
    r"\bfund\b",
)

BANKING_EXCLUSION_PATTERNS = (
    r"\bsouth bank\b",
    r"\bblood bank\b",
    r"\bfood bank\b",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_name(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _latest_file(directory: Path, pattern: str) -> Path | None:
    candidates = sorted(directory.glob(pattern), reverse=True)
    return candidates[0] if candidates else None


def latest_money_flows_jsonl(processed_dir: Path = PROCESSED_DIR) -> Path | None:
    return _latest_file(processed_dir / "aec_annual_money_flows", "*.jsonl")


def latest_house_interest_records_jsonl(processed_dir: Path = PROCESSED_DIR) -> Path | None:
    return _latest_file(processed_dir / "house_interest_records", "*.jsonl")


def latest_senate_interest_records_jsonl(processed_dir: Path = PROCESSED_DIR) -> Path | None:
    return _latest_file(processed_dir / "senate_interest_records", "*.jsonl")


def _matches(pattern: str, normalized_name: str) -> bool:
    return re.search(pattern, normalized_name, flags=re.IGNORECASE) is not None


def _looks_like_company_or_trust(normalized_name: str) -> tuple[str, str] | None:
    if _matches(r"\b(atf|as trustee|trustee|trust)\b", normalized_name):
        return ("trust", "Name contains trust or trustee wording.")
    if _matches(r"\b(pty|ltd|limited|proprietary|inc|corp|corporation|company)\b", normalized_name):
        return ("company", "Name contains company suffix or corporate wording.")
    return None


def _looks_like_individual(raw_name: str, normalized_name: str) -> bool:
    if any(_matches(pattern, normalized_name) for pattern in ORG_INDICATOR_PATTERNS):
        return False
    words = normalized_name.split()
    if len(words) < 2 or len(words) > 5:
        return False
    if "&" not in raw_name and any(word in {"and", "of", "for", "from", "with"} for word in words):
        return False
    if "&" in raw_name:
        return True
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]+", raw_name)
    if len(tokens) < 2:
        return False
    return sum(1 for token in tokens if token[:1].isupper()) >= 2


def classify_name(raw_name: str) -> dict[str, Any]:
    canonical_name = " ".join((raw_name or "").split())
    normalized_name = normalize_name(canonical_name)

    if normalized_name in NON_VALUE_NAMES:
        return {
            "canonical_name": canonical_name or "Unknown",
            "normalized_name": normalized_name or "unknown",
            "entity_type": "unknown",
            "public_sector": "unknown",
            "public_sector_label": PUBLIC_INTEREST_SECTOR_LABELS["unknown"],
            "method": "rule_based",
            "confidence": "unresolved",
            "matched_rule_id": "non_value_placeholder",
            "evidence_note": "Raw name is empty or a non-value placeholder.",
            "review_recommended": True,
        }

    for rule in RULES:
        if rule.rule_id == "banking_names" and any(
            _matches(pattern, normalized_name) for pattern in BANKING_EXCLUSION_PATTERNS
        ):
            continue
        if any(_matches(pattern, normalized_name) for pattern in rule.patterns):
            return {
                "canonical_name": canonical_name,
                "normalized_name": normalized_name,
                "entity_type": rule.entity_type,
                "public_sector": rule.public_sector,
                "public_sector_label": PUBLIC_INTEREST_SECTOR_LABELS[rule.public_sector],
                "method": "rule_based",
                "confidence": rule.confidence,
                "matched_rule_id": rule.rule_id,
                "evidence_note": rule.evidence_note,
                "review_recommended": rule.confidence in {"fuzzy_low", "unresolved"},
            }

    company_or_trust = _looks_like_company_or_trust(normalized_name)
    if company_or_trust is not None:
        entity_type, note = company_or_trust
        return {
            "canonical_name": canonical_name,
            "normalized_name": normalized_name,
            "entity_type": entity_type,
            "public_sector": "unknown",
            "public_sector_label": PUBLIC_INTEREST_SECTOR_LABELS["unknown"],
            "method": "rule_based",
            "confidence": "fuzzy_low",
            "matched_rule_id": f"{entity_type}_suffix_uncoded",
            "evidence_note": f"{note} Sector remains uncoded pending better evidence.",
            "review_recommended": True,
        }

    if _looks_like_individual(canonical_name, normalized_name):
        return {
            "canonical_name": canonical_name,
            "normalized_name": normalized_name,
            "entity_type": "individual",
            "public_sector": "individual_uncoded",
            "public_sector_label": PUBLIC_INTEREST_SECTOR_LABELS["individual_uncoded"],
            "method": "rule_based",
            "confidence": "fuzzy_low",
            "matched_rule_id": "individual_name_shape",
            "evidence_note": "Name shape suggests an individual; no industry is inferred.",
            "review_recommended": True,
        }

    return {
        "canonical_name": canonical_name,
        "normalized_name": normalized_name,
        "entity_type": "unknown",
        "public_sector": "unknown",
        "public_sector_label": PUBLIC_INTEREST_SECTOR_LABELS["unknown"],
        "method": "rule_based",
        "confidence": "unresolved",
        "matched_rule_id": "no_rule_match",
        "evidence_note": "No conservative rule matched this name.",
        "review_recommended": True,
    }


def _amount(value: str) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _empty_aggregate() -> dict[str, Any]:
    return {
        "raw_names": Counter(),
        "source_contexts": Counter(),
        "money_flow_source_count": 0,
        "money_flow_recipient_count": 0,
        "gift_interest_source_count": 0,
        "total_source_amount_aud": Decimal("0"),
        "total_recipient_amount_aud": Decimal("0"),
        "sample_source_ids": set(),
    }


def _add_name(
    aggregates: dict[str, dict[str, Any]],
    raw_name: str,
    *,
    context: str,
    source_id: str = "",
    amount_aud: Decimal = Decimal("0"),
) -> None:
    normalized_name = normalize_name(raw_name)
    if not normalized_name:
        return
    aggregate = aggregates[normalized_name]
    aggregate["raw_names"][raw_name.strip()] += 1
    aggregate["source_contexts"][context] += 1
    if source_id and len(aggregate["sample_source_ids"]) < 10:
        aggregate["sample_source_ids"].add(source_id)
    if context == "money_flow_source":
        aggregate["money_flow_source_count"] += 1
        aggregate["total_source_amount_aud"] += amount_aud
    elif context == "money_flow_recipient":
        aggregate["money_flow_recipient_count"] += 1
        aggregate["total_recipient_amount_aud"] += amount_aud
    elif context == "gift_interest_source":
        aggregate["gift_interest_source_count"] += 1


def aggregate_entity_names(processed_dir: Path = PROCESSED_DIR) -> dict[str, dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = defaultdict(_empty_aggregate)

    money_path = latest_money_flows_jsonl(processed_dir=processed_dir)
    if money_path is not None:
        with money_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                amount = _amount(record.get("amount_aud", ""))
                source_id = record.get("source_id", "")
                _add_name(
                    aggregates,
                    record.get("source_raw_name", ""),
                    context="money_flow_source",
                    source_id=source_id,
                    amount_aud=amount,
                )
                _add_name(
                    aggregates,
                    record.get("recipient_raw_name", ""),
                    context="money_flow_recipient",
                    source_id=source_id,
                    amount_aud=amount,
                )

    for path_getter in (latest_house_interest_records_jsonl, latest_senate_interest_records_jsonl):
        path = path_getter(processed_dir=processed_dir)
        if path is None:
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                _add_name(
                    aggregates,
                    record.get("counterparty_raw_name", ""),
                    context="gift_interest_source",
                    source_id=record.get("source_id", ""),
                )

    return aggregates


def _classification_record(
    normalized_name: str,
    aggregate: dict[str, Any],
) -> dict[str, Any]:
    canonical_name = aggregate["raw_names"].most_common(1)[0][0]
    classification = classify_name(canonical_name)
    classification["normalized_name"] = normalized_name
    classification["raw_name_variants"] = [
        {"raw_name": name, "count": count}
        for name, count in aggregate["raw_names"].most_common(10)
    ]
    classification["source_contexts"] = dict(sorted(aggregate["source_contexts"].items()))
    classification["money_flow_source_count"] = aggregate["money_flow_source_count"]
    classification["money_flow_recipient_count"] = aggregate["money_flow_recipient_count"]
    classification["gift_interest_source_count"] = aggregate["gift_interest_source_count"]
    classification["total_source_amount_aud"] = str(aggregate["total_source_amount_aud"])
    classification["total_recipient_amount_aud"] = str(aggregate["total_recipient_amount_aud"])
    classification["sample_source_ids"] = sorted(aggregate["sample_source_ids"])
    classification["classifier_name"] = CLASSIFIER_NAME
    return classification


def classify_entity_names(processed_dir: Path = PROCESSED_DIR) -> Path:
    timestamp = _timestamp()
    target_dir = processed_dir / "entity_classifications"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    aggregates = aggregate_entity_names(processed_dir=processed_dir)

    sector_counts: Counter[str] = Counter()
    entity_type_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    review_recommended_count = 0
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for normalized_name in sorted(aggregates):
            record = _classification_record(normalized_name, aggregates[normalized_name])
            sector_counts[record["public_sector"]] += 1
            entity_type_counts[record["entity_type"]] += 1
            confidence_counts[record["confidence"]] += 1
            if record["review_recommended"]:
                review_recommended_count += 1
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    classified_count = sum(count for sector, count in sector_counts.items() if sector != "unknown")
    summary = {
        "classifier_name": CLASSIFIER_NAME,
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "entity_name_count": len(aggregates),
        "classified_count": classified_count,
        "unknown_count": sector_counts["unknown"],
        "review_recommended_count": review_recommended_count,
        "public_sector_counts": dict(sorted(sector_counts.items())),
        "entity_type_counts": dict(sorted(entity_type_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "sector_taxonomy": PUBLIC_INTEREST_SECTORS,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def latest_entity_classifications_jsonl(processed_dir: Path = PROCESSED_DIR) -> Path:
    path = _latest_file(processed_dir / "entity_classifications", "*.jsonl")
    if path is None:
        raise FileNotFoundError("No entity classification JSONL artifact found.")
    return path
