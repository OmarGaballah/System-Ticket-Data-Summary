"""Central constants — the single source of truth for every business rule.

Every value that encodes domain knowledge (category codes, product mapping,
source/output column names, the NZ realignment anchor, phases, languages,
provider models) lives here so a change is a one-file edit. ``engine/prompts.py``
and ``engine/schema.py`` both build off ``PHASES`` here so the prompt and the
JSON contract can never drift apart.
"""

from __future__ import annotations

from src.structs import Phase


NA_TOKENS: list[str] = ["", "N/A", "n/a", "NA", "null", "NULL"]


DATETIME_FORMAT: str = "%m/%d/%Y %H:%M"


TICKET_COL = "ORDER_NUMBER"
ACCEPTANCE_COL = "ACCEPTANCE_TIME"
COMPLETION_COL = "COMPLETION_TIME"
CUSTOMER_COL = "CUSTOMER_NUMBER"
ORDER_TYPE_COL = "ORDER_TYPE"
STATUS_COL = "PROCESSING_STATUS"
CATEGORY_COL = "SERVICE_CATEGORY"

DATETIME_COLUMNS: list[str] = [ACCEPTANCE_COL, COMPLETION_COL]

ANCHOR_COL = "NETWORK_LEVEL"
ANCHOR_VALUE = "NZ"

OUTCOME_SRC_COL = "COMPLETION_NOTE_MAXIMUM"          
CAUSE_SRC_COL = "CAUSE"                              
TEAM_SRC_COL = "PLANNING_GROUP_KB"                   
ACTION_SRC_COL = "COMPLETION_RESULT_KB"              
REFERENCE_SRC_COL = "REFERENCE_COMPLETION_RESULT"    
RESOLVER_SRC_COL = "REFERENCE_ERROR_CAUSE"           


ANCHOR_OFFSETS: dict[str, int] = {
    "team": -4, "action": -3, "reference": -2, "outcome": -1,
    "cause": +1, "resolver": +2,
}

DETAILS_COLS: list[str] = [
    "ORDER_DESCRIPTION_1",
    "ORDER_DESCRIPTION_2",
    "ORDER_DESCRIPTION_3_MAXIMUM",
    "ADDITIONAL_ORDER_DESCRIPTION_MAXIMUM",
    "NOTE_MAXIMUM",
]

STATUS_NORMALIZE: dict[str, str] = {"ab": "Completed"}

ORDER_TYPE_NORMALIZE: dict[str, str] = {"Kurzticket": "Short Ticket", "Aufgabe": "Task"}

KEEP_CATEGORIES: list[str] = ["HDW", "NET", "KAI", "KAV", "GIGA", "VOD", "KAD"]

PRODUCT_MAP: dict[str, str] = {
    "KAI": "Broadband",
    "NET": "Broadband",
    "KAV": "Voice",
    "KAD": "TV",
    "GIGA": "GIGA",
    "VOD": "VOD",
    "HDW": "Hardware",
}


PRODUCTS: list[str] = list(dict.fromkeys(PRODUCT_MAP.values()))

OUT_ORDER = "order_number"
OUT_ACCEPT = "acceptance_time"
OUT_COMPLETE = "completion_time"
OUT_CUSTOMER = "customer"
OUT_ORDER_TYPE = "order_type"
OUT_STATUS = "status"
OUT_CATEGORY = "category"
OUT_PRODUCT = "product"
OUT_OUTCOME = "outcome"   
OUT_CAUSE = "cause"
OUT_ACTION = "action"             
OUT_REFERENCE = "reference_result" 
OUT_RESOLVER = "resolver"         
OUT_TEAM = "team"                 
OUT_DETAILS = "details" 

EPISODE_GAP_HOURS: float = 12.0

CLEAN_COLUMNS: list[str] = [
    OUT_ORDER, OUT_ACCEPT, OUT_COMPLETE, OUT_CUSTOMER, OUT_ORDER_TYPE,
    OUT_STATUS, OUT_CATEGORY, OUT_OUTCOME, OUT_CAUSE, OUT_ACTION,
    OUT_REFERENCE, OUT_RESOLVER, OUT_TEAM, OUT_DETAILS,
]

NO_ACTIVITY = "No activity."

NO_ACTIVITY_DISPLAY: dict[str, str] = {
    "English": NO_ACTIVITY,
    "German": "Keine Aktivität.",
}


def no_activity_text(language: str | None = None) -> str:
    """The 'nothing happened here' line as the reader should see it."""
    return NO_ACTIVITY_DISPLAY.get(language or DEFAULT_LANGUAGE, NO_ACTIVITY)


OUTCOME_OK = "OK"
OUTCOME_ERROR = "Error"
OUTCOME_UNKNOWN = "Unknown"


PHASES: list[Phase] = [
    Phase("initial_issue", "Initial Issue",
          "The first problems recorded for this product: what was reported "
          "and the first actions support took."),
    Phase("follow_ups", "Follow-ups",
          "Further tickets raised after the initial contact: what was "
          "reported again, and what support did next."),
    Phase("developments", "Developments",
          "Changes in the course of the issues: new problems appearing, or "
          "recorded progress toward resolving existing ones."),
    Phase("later_incidents", "Later Incidents",
          "Problems that recurred or newly emerged later in the period, and "
          "how they were handled."),
    Phase("recent_events", "Recent Events",
          "The most recent tickets in the data: what was reported and what "
          "outcome was recorded."),
]

PHASE_IDS: list[str] = [p.id for p in PHASES]

LANGUAGES: dict[str, str] = {"English": "English", "German": "German"}
DEFAULT_LANGUAGE: str = "English"

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_GEMINI = "gemini"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_OLLAMA = "ollama"

PROVIDER_MODELS: dict[str, str] = {
    PROVIDER_ANTHROPIC: "claude-sonnet-5",
    PROVIDER_OPENAI: "gpt-5.6-terra",
    PROVIDER_GEMINI: "gemini-3.5-flash",
    PROVIDER_DEEPSEEK: "deepseek-v4-flash",
    PROVIDER_OLLAMA: "qwen2.5:3b",
}

DEFAULT_PROVIDER: str = PROVIDER_ANTHROPIC

FALLBACK_ORDER: list[str] = [PROVIDER_ANTHROPIC, PROVIDER_OPENAI, PROVIDER_GEMINI,
                             PROVIDER_DEEPSEEK, PROVIDER_OLLAMA]

assert set(FALLBACK_ORDER) == set(PROVIDER_MODELS), (
    "FALLBACK_ORDER and PROVIDER_MODELS must cover the same providers")
