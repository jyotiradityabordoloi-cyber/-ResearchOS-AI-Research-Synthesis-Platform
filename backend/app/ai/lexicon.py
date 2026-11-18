"""Deterministic vocabularies.

- SENSITIVE: keyword rules for pricing / churn / competitive switching. Used with
  every provider (not just demo) as a safety net, because these findings require
  human approval and must not be missed if the LLM forgets to tag them.
- CONCEPTS / POSITIVE_CUES: used only by the offline demo engine and hash
  embedder to approximate semantics without a model.
"""

import re

SENSITIVE: dict[str, list[str]] = {
    "pricing": [
        "price", "pricing", "priced", "cost", "costs", "expensive", "cheap", "bill", "billing",
        "invoice", "per seat", "seat-based", "seats", "paying", "pay for", "budget", "discount",
        "plan costs", "too much money", "subscription fee",
    ],
    "churn": [
        "churn", "cancel", "cancelled", "canceled", "cancellation", "not renew", "won't renew",
        "stop using", "stopped using", "leave the product", "leaving", "downgrade", "downgraded",
        "unsubscribe",
    ],
    "competitive_switching": [
        "competitor", "competitors", "switch to", "switched to", "switching to", "moved to",
        "move to", "alternative", "alternatives", "instead of you", "looker", "tableau",
        "power bi", "metabase", "mode analytics", "amplitude", "mixpanel",
    ],
}

# concept -> trigger words/phrases. Order matters only for readability.
CONCEPTS: dict[str, list[str]] = {
    "integration": [
        "connector", "connectors", "connect", "connecting", "connected", "integration",
        "integrations", "data source", "warehouse", "postgres", "snowflake", "redshift",
        "bigquery", "hubspot", "stripe", "api", "sync", "import data", "setup", "set up",
        "setting up", "credentials",
    ],
    "sharing": [
        "share", "sharing", "shared", "leadership", "ceo", "board", "stakeholder", "stakeholders",
        "read-only", "read only", "client", "clients", "customers won't log in",
        "log in to see", "own seat", "create an account",
    ],
    "export": [
        "export", "exports", "exporting", "pdf", "csv", "excel", "slides", "screenshot",
        "screenshots", "download", "downloads", "formatting", "layout",
    ],
    "performance": [
        "slow", "slowly", "load", "loads", "loading", "refresh", "time out", "times out",
        "timeout", "timing out", "wait", "waiting", "minute", "minutes", "lag", "performance",
    ],
    "pricing": SENSITIVE["pricing"],
    "permissions": [
        "permission", "permissions", "access", "role", "roles", "contractor", "all-or-nothing",
        "security team", "grant", "admin",
    ],
    "compliance": [
        "soc 2", "soc2", "gdpr", "hipaa", "compliance", "audit", "security review",
        "data residency", "legal", "procurement",
    ],
    "onboarding": [
        "onboarding", "trial", "evaluate", "evaluating", "evaluation", "getting started",
        "first week", "tutorial", "documentation", "docs",
    ],
    "trust": ["trust", "disagree", "wrong numbers", "accuracy", "accurate", "reconcile", "mismatch"],
    "churn": SENSITIVE["churn"],
    "competitive_switching": SENSITIVE["competitive_switching"],
}

POSITIVE_CUES = [
    "easy", "easily", "smooth", "smoothly", "simple", "straightforward", "quick", "quickly",
    "fast", "no problem", "no problems", "no issues", "never had", "didn't have any", "worked fine",
    "just worked", "love", "loved", "great", "painless", "minutes to", "in ten minutes",
    "in five minutes", "under a minute", "not an issue", "wasn't an issue", "fine for us",
]

NEGATIVE_CUES = [
    "can't", "cannot", "couldn't", "won't", "hard", "difficult", "painful", "slow", "broken",
    "breaks", "fail", "failed", "fails", "frustrat", "annoy", "lost", "waste", "problem", "issue",
    "awkward", "confusing", "unclear", "no way", "never", "blocked", "blocks", "time out",
    "timing out", "timed out", "times out", "delay", "delays", "delayed", "stuck", "error", "errors",
    "crash", "crashes", "struggle", "struggled", "struggling", "fighting", "hate", "worse", "lost a",
    "took three days", "took days", "took weeks", "too slow", "too long",
]

HIGH_SEVERITY_CUES = [
    "blocked", "blocks", "blocker", "deal", "lost the", "can't buy", "cannot buy", "can't sign",
    "legal", "security", "compliance", "soc 2", "soc2", "churn", "cancel", "never saw real value",
    "gave up", "give up", "lost a week", "lost them",
]


def _contains(text: str, phrase: str) -> bool:
    if " " in phrase or "-" in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def match_terms(text: str, terms: list[str]) -> list[str]:
    t = text.lower()
    return [p for p in terms if _contains(t, p)]


def sensitive_tags(text: str) -> list[str]:
    return [tag for tag, terms in SENSITIVE.items() if match_terms(text, terms)]


def concepts(text: str) -> list[str]:
    return [c for c, terms in CONCEPTS.items() if match_terms(text, terms)]
