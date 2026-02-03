"""
Svenska juridiska förkortningar - mappning för query expansion.

Expanderar förkortningar i användarfrågor för att förbättra RAG-retrieval.
"""

import re
from typing import Dict, Tuple

# Grundlagar och konstitutionella dokument
CONSTITUTIONAL_LAWS: Dict[str, str] = {
    "RF": "Regeringsformen",
    "TF": "Tryckfrihetsförordningen",
    "YGL": "Yttrandefrihetsgrundlagen",
    "SO": "Successionsordningen",
    "RO": "Riksdagsordningen",
}

# Balkar (civilrätt)
CIVIL_CODES: Dict[str, str] = {
    "JB": "Jordabalken",
    "ÄB": "Ärvdabalken",
    "GB": "Giftermålsbalken",
    "FB": "Föräldrabalken",
    "HB": "Handelsbalken",
    "SjöL": "Sjölagen",
    "UB": "Utsökningsbalken",
}

# Straffrätt
CRIMINAL_CODES: Dict[str, str] = {
    "BrB": "Brottsbalken",
    "RB": "Rättegångsbalken",
    "BrP": "Brottsdatalagen",
}

# Offentlig rätt och förvaltning
PUBLIC_LAW: Dict[str, str] = {
    "FL": "Förvaltningslagen",
    "FPL": "Förvaltningsprocesslagen",
    "KL": "Kommunallagen",
    "OSL": "Offentlighets- och sekretesslagen",
    "SekrL": "Sekretesslagen",
    "LOA": "Lagen om offentlig anställning",
    "LOU": "Lagen om offentlig upphandling",
    "LUF": "Lagen om upphandling inom försörjningssektorerna",
}

# Dataskydd och integritet
DATA_PROTECTION: Dict[str, str] = {
    "GDPR": "Dataskyddsförordningen",
    "PuL": "Personuppgiftslagen",
    "DSL": "Dataskyddslagen",
    "LEK": "Lagen om elektronisk kommunikation",
}

# Arbetsrätt
LABOR_LAW: Dict[str, str] = {
    "LAS": "Lagen om anställningsskydd",
    "MBL": "Medbestämmandelagen",
    "AML": "Arbetsmiljölagen",
    "SemL": "Semesterlagen",
    "ATL": "Arbetstidslagen",
    "DiskrL": "Diskrimineringslagen",
}

# Skatterätt och ekonomi
TAX_LAW: Dict[str, str] = {
    "IL": "Inkomstskattelagen",
    "ML": "Mervärdesskattelagen",
    "SFL": "Skatteförfarandelagen",
    "SBL": "Skattebetalningslagen",
    "ABL": "Aktiebolagslagen",
    "BFL": "Bokföringslagen",
    "ÅRL": "Årsredovisningslagen",
    "KonkL": "Konkurslagen",
}

# Socialrätt
SOCIAL_LAW: Dict[str, str] = {
    "SoL": "Socialtjänstlagen",
    "LSS": "Lagen om stöd och service till vissa funktionshindrade",
    "LVU": "Lagen med särskilda bestämmelser om vård av unga",
    "LVM": "Lagen om vård av missbrukare",
    "HSL": "Hälso- och sjukvårdslagen",
    "PSL": "Patientsäkerhetslagen",
    "SFB": "Socialförsäkringsbalken",
}

# Miljö och plan
ENVIRONMENT_LAW: Dict[str, str] = {
    "MB": "Miljöbalken",
    "PBL": "Plan- och bygglagen",
    "PBF": "Plan- och byggförordningen",
    "ExprL": "Expropriationslagen",
}

# Utlännings- och migrationsrätt
MIGRATION_LAW: Dict[str, str] = {
    "UtlL": "Utlänningslagen",
    "MedbL": "Medborgarskapslagen",
    "LMA": "Lagen om mottagande av asylsökande",
}

# Övriga viktiga lagar
OTHER_LAWS: Dict[str, str] = {
    "AvtL": "Avtalslagen",
    "KöpL": "Köplagen",
    "KKL": "Konsumentköplagen",
    "SkL": "Skadeståndslagen",
    "PreskrL": "Preskriptionslagen",
    "URL": "Upphovsrättslagen",
    "VML": "Varumärkeslagen",
    "PatL": "Patentlagen",
    "TL": "Trafikskadelagen",
    "FAL": "Försäkringsavtalslagen",
    "BankL": "Bankrörelselagen",
}

# EU-rättsliga förkortningar
EU_LAW: Dict[str, str] = {
    "FEUF": "Fördraget om Europeiska unionens funktionssätt",
    "FEU": "Fördraget om Europeiska unionen",
    "EKMR": "Europakonventionen om de mänskliga rättigheterna",
    "EU-stadgan": "Europeiska unionens stadga om de grundläggande rättigheterna",
}

# Myndigheter och institutioner
AUTHORITIES: Dict[str, str] = {
    "HD": "Högsta domstolen",
    "HFD": "Högsta förvaltningsdomstolen",
    "RegR": "Regeringsrätten",
    "JO": "Justitieombudsmannen",
    "JK": "Justitiekanslern",
    "DO": "Diskrimineringsombudsmannen",
    "SKV": "Skatteverket",
    "IMY": "Integritetsskyddsmyndigheten",
    "ARN": "Allmänna reklamationsnämnden",
}

# Dokumenttyper i Riksdagen
DOCUMENT_TYPES: Dict[str, str] = {
    "prop": "proposition",
    "mot": "motion",
    "bet": "betänkande",
    "SOU": "Statens offentliga utredningar",
    "Ds": "Departementsserien",
    "SFS": "Svensk författningssamling",
    "NJA": "Nytt juridiskt arkiv",
    "RÅ": "Regeringsrättens årsbok",
}


def _build_master_dict() -> Dict[str, str]:
    """Bygg komplett förkortningslexikon från alla kategorier."""
    master = {}
    for category in [
        CONSTITUTIONAL_LAWS,
        CIVIL_CODES,
        CRIMINAL_CODES,
        PUBLIC_LAW,
        DATA_PROTECTION,
        LABOR_LAW,
        TAX_LAW,
        SOCIAL_LAW,
        ENVIRONMENT_LAW,
        MIGRATION_LAW,
        OTHER_LAWS,
        EU_LAW,
        AUTHORITIES,
        DOCUMENT_TYPES,
    ]:
        master.update(category)
    return master


# Komplett lexikon för snabb lookup
LEGAL_ABBREVIATIONS: Dict[str, str] = _build_master_dict()

# Pre-kompilerade regex patterns för effektivitet
_ABBREV_PATTERNS: Dict[str, re.Pattern] = {}


def _get_pattern(abbr: str) -> re.Pattern:
    """Hämta eller skapa regex pattern för en förkortning."""
    if abbr not in _ABBREV_PATTERNS:
        # Matcha hela ord, case-insensitive
        _ABBREV_PATTERNS[abbr] = re.compile(rf"\b{re.escape(abbr)}\b", re.IGNORECASE)
    return _ABBREV_PATTERNS[abbr]


def expand_abbreviations(query: str) -> Tuple[str, list[str]]:
    """
    Expandera kända juridiska förkortningar i en fråga.

    Args:
        query: Användarens fråga

    Returns:
        Tuple med (expanderad fråga, lista över funna förkortningar)

    Exempel:
        >>> expand_abbreviations("Vad är TF?")
        ("Vad är TF (Tryckfrihetsförordningen)?", ["TF"])

        >>> expand_abbreviations("Skillnad mellan RF och YGL")
        ("Skillnad mellan RF (Regeringsformen) och YGL (Yttrandefrihetsgrundlagen)", ["RF", "YGL"])
    """
    expanded = query
    found_abbreviations = []

    for abbr, full_name in LEGAL_ABBREVIATIONS.items():
        pattern = _get_pattern(abbr)
        if pattern.search(expanded):
            # Ersätt med "ABBR (fullständigt namn)" format
            # Men bara om expansionen inte redan finns
            expansion = f"{abbr} ({full_name})"
            if full_name.lower() not in expanded.lower():
                expanded = pattern.sub(expansion, expanded)
                found_abbreviations.append(abbr)

    return expanded, found_abbreviations


def get_full_name(abbreviation: str) -> str | None:
    """
    Hämta fullständigt namn för en förkortning.

    Args:
        abbreviation: Förkortning att slå upp (case-insensitive)

    Returns:
        Fullständigt namn eller None om okänd
    """
    # Prova exakt match först
    if abbreviation in LEGAL_ABBREVIATIONS:
        return LEGAL_ABBREVIATIONS[abbreviation]

    # Prova case-insensitive
    abbr_upper = abbreviation.upper()
    for key, value in LEGAL_ABBREVIATIONS.items():
        if key.upper() == abbr_upper:
            return value

    return None


def detect_abbreviations(text: str) -> list[Tuple[str, str]]:
    """
    Identifiera alla kända förkortningar i en text.

    Args:
        text: Text att analysera

    Returns:
        Lista med tupler (förkortning, fullständigt namn)
    """
    found = []
    for abbr, full_name in LEGAL_ABBREVIATIONS.items():
        pattern = _get_pattern(abbr)
        if pattern.search(text):
            found.append((abbr, full_name))
    return found


# Convenience exports
__all__ = [
    "LEGAL_ABBREVIATIONS",
    "CONSTITUTIONAL_LAWS",
    "expand_abbreviations",
    "get_full_name",
    "detect_abbreviations",
]
