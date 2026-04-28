"""Legacy fuzzy account-name matcher used by the receipt/payment shortcuts.

Newer tools take account IDs directly (the LLM picks them after listing); this
module exists only to preserve the existing high-level shortcuts."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("wave-mcp-server.fuzzy")

EXPENSE_SYNONYMS: Dict[str, List[str]] = {
    "food": ["meals", "restaurant", "dining", "eating", "lunch", "dinner", "breakfast"],
    "gas": ["fuel", "gasoline", "petrol", "diesel"],
    "travel": ["transportation", "transport", "trip", "journey"],
    "office": ["supplies", "equipment", "materials", "stationery"],
    "car": ["vehicle", "auto", "automobile", "automotive"],
    "phone": ["mobile", "cellular", "telecommunications", "telecom"],
    "internet": ["web", "online", "broadband", "wifi"],
    "insurance": ["coverage", "policy", "premium"],
    "rent": ["rental", "lease", "leasing"],
    "utilities": ["electric", "electricity", "water", "gas", "power"],
    "marketing": ["advertising", "promotion", "ads"],
    "software": ["subscription", "saas", "app", "application"],
    "training": ["education", "learning", "course", "workshop"],
    "legal": ["attorney", "lawyer", "law", "professional"],
    "accounting": ["bookkeeping", "tax", "financial"],
    "maintenance": ["repair", "service", "upkeep"],
    "entertainment": ["client", "business"],
}

INCOME_SYNONYMS: Dict[str, List[str]] = {
    "sales": ["revenue", "income", "receipts", "earnings"],
    "consulting": ["services", "professional", "advisory", "expertise"],
    "freelance": ["contract", "project", "gig", "independent"],
    "commission": ["referral", "bonus", "incentive"],
    "interest": ["dividend", "investment", "return"],
    "rental": ["rent", "lease", "property", "real estate", "rental income", "rent income", "property income", "leasing", "tenant"],
    "royalty": ["licensing", "intellectual property", "patent"],
    "other": ["miscellaneous", "misc", "various", "general"],
}


def find_best_account_match(
    user_category: str,
    accounts: List[Dict[str, Any]],
    account_type: str,
    user_context: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], float, str]:
    """Find the best matching account for `user_category` among `accounts`.

    Returns (account_id, account_name, score, explanation).
    Preserved verbatim from the legacy implementation; new code should not depend on it."""
    if not user_category:
        return None, None, 0.0, "No category provided"

    filtered_accounts = [
        acc["node"] for acc in accounts
        if acc["node"]["type"]["name"] == account_type
        and not acc["node"]["isArchived"]
    ]
    if not filtered_accounts:
        filtered_accounts = [
            acc["node"] for acc in accounts
            if acc["node"]["type"]["name"].lower() == account_type.lower()
            and not acc["node"]["isArchived"]
        ]
    if not filtered_accounts and account_type == "Income":
        income_variations = ["Income", "INCOME", "Revenue", "REVENUE", "income"]
        filtered_accounts = [
            acc["node"] for acc in accounts
            if acc["node"]["type"]["name"] in income_variations
            and not acc["node"]["isArchived"]
        ]
    if not filtered_accounts and account_type == "Income":
        income_subtypes = ["INCOME", "REVENUE", "SALES", "OTHER_INCOME"]
        filtered_accounts = [
            acc["node"] for acc in accounts
            if (acc["node"].get("subtype", {}).get("name", "") in income_subtypes)
            and not acc["node"]["isArchived"]
        ]
    if not filtered_accounts:
        return None, None, 0.0, f"No {account_type.lower()} accounts found."

    user_category_lower = user_category.lower().strip()
    best_match = None
    best_score = 0.0
    best_explanation = ""

    synonyms = EXPENSE_SYNONYMS if account_type == "Expenses" else INCOME_SYNONYMS

    apartment_numbers: List[str] = []
    all_user_text = f"{user_category} {user_context or ''}"
    number_patterns = [
        r"\b(14[2-6])\b",
        r"\bapartment\s+(\d+)\b",
        r"\bunit\s+(\d+)\b",
        r"\b(\d{3})\b",
    ]
    for pattern in number_patterns:
        apartment_numbers.extend(re.findall(pattern, all_user_text.lower()))
    apartment_numbers = list(set(apartment_numbers))

    if apartment_numbers and account_type == "Income":
        for number in apartment_numbers:
            for account in filtered_accounts:
                acc_lower = account["name"].lower()
                if number in acc_lower and "rental" in acc_lower:
                    return account["id"], account["name"], 0.98, f"Apartment-specific match: Found apartment {number} in '{account['name']}'"

    for account in filtered_accounts:
        acc_lower = account["name"].lower()
        if user_category_lower in acc_lower:
            return account["id"], account["name"], 1.0, f"Exact substring match: '{user_category}' found in '{account['name']}'"
        if acc_lower.startswith(user_category_lower):
            return account["id"], account["name"], 0.95, f"Prefix match: '{account['name']}' starts with '{user_category}'"
        words_in_account = acc_lower.split()
        if words_in_account and user_category_lower.startswith(words_in_account[0]):
            return account["id"], account["name"], 0.92, f"Category prefix match: '{user_category}' starts with '{words_in_account[0]}' from '{account['name']}'"

    for account in filtered_accounts:
        acc_lower = account["name"].lower()
        similarity = SequenceMatcher(None, user_category_lower, acc_lower).ratio()
        if similarity > best_score:
            best_match = account
            best_score = similarity
            best_explanation = f"Direct fuzzy match (score: {similarity:.2f})"
        for word in acc_lower.split():
            word_similarity = SequenceMatcher(None, user_category_lower, word).ratio()
            if word_similarity > best_score:
                best_match = account
                best_score = word_similarity
                best_explanation = f"Word match: '{user_category}' ~ '{word}' (score: {word_similarity:.2f})"
        for key, synonym_list in synonyms.items():
            if user_category_lower == key or user_category_lower in synonym_list:
                if key in acc_lower:
                    score = 0.9
                    if score > best_score:
                        best_match = account
                        best_score = score
                        best_explanation = f"Synonym match: '{user_category}' relates to '{key}' found in '{account['name']}'"
                for synonym in synonym_list:
                    if synonym in acc_lower:
                        score = 0.85
                        if score > best_score:
                            best_match = account
                            best_score = score
                            best_explanation = f"Synonym match: '{user_category}' relates to '{synonym}' found in '{account['name']}'"
            if user_category_lower in [key] + synonym_list:
                for synonym in [key] + synonym_list:
                    if synonym in acc_lower:
                        score = 0.88
                        if score > best_score:
                            best_match = account
                            best_score = score
                            best_explanation = f"Synonym match: '{user_category}' relates to '{synonym}' in '{account['name']}'"

    if best_match and best_score >= 0.6:
        return best_match["id"], best_match["name"], best_score, best_explanation

    if best_match and best_score > 0.3:
        explanation = f"Best available match (low confidence): {best_explanation}. Available accounts: {', '.join([acc['name'] for acc in filtered_accounts[:3]])}"
        return best_match["id"], best_match["name"], best_score, explanation

    relevant_keywords: List[str] = []
    for key, synonym_list in synonyms.items():
        if user_category_lower == key or user_category_lower in synonym_list:
            relevant_keywords.extend([key] + synonym_list)
            break
    if relevant_keywords:
        for account in filtered_accounts:
            acc_lower = account["name"].lower()
            for keyword in relevant_keywords:
                if keyword in acc_lower:
                    explanation = f"Fallback match: Found '{keyword}' in '{account['name']}' based on category '{user_category}'."
                    return account["id"], account["name"], 0.5, explanation

    if user_category_lower in ["rent", "rental", "property"] and len(filtered_accounts) > 1:
        avoid_terms = ["foreign", "exchange", "gain", "loss", "interest", "dividend"]
        for account in filtered_accounts:
            acc_lower = account["name"].lower()
            if not any(av in acc_lower for av in avoid_terms):
                explanation = f"Smart fallback: Selected '{account['name']}' (avoided unrelated)."
                return account["id"], account["name"], 0.2, explanation

    first_account = filtered_accounts[0]
    explanation = f"No good match for '{user_category}'. Using default: '{first_account['name']}'."
    return first_account["id"], first_account["name"], 0.1, explanation
