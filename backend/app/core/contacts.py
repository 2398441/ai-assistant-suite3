"""
Google Contacts — native People API client
==========================================

Calls the Google People API directly using the user's OAuth access token
retrieved from Composio's connected account. No Composio googlecontacts
toolkit involved.

Public interface
----------------
  search_contacts(user_id, query, limit)  →  JSON string (list of contacts)
  list_contacts(user_id, limit)           →  JSON string (list of contacts)

  TOOL_DEFINITION  — Anthropic ToolParam dict for "google_contacts"
"""

import json
import logging

import httpx
import truststore
truststore.inject_into_ssl()

from composio import Composio
from composio_anthropic import AnthropicProvider

from ..config.settings import settings

logger = logging.getLogger(__name__)

_PEOPLE_API = "https://people.googleapis.com/v1"
_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,organizations"

# ── Composio client (shared singleton) ───────────────────────────────────────

_composio = Composio(
    provider=AnthropicProvider(),
    api_key=settings.composio_api_key,
)


def _get_access_token(user_id: str) -> str:
    """
    Retrieve the Google OAuth access token for the given Composio user_id.
    Tries Gmail connection first, falls back to Calendar.
    Raises RuntimeError if no active connection is found.
    """
    for toolkit_slug in ("gmail", "googlecalendar"):
        try:
            accounts = _composio._client.connected_accounts.list(
                user_ids=[user_id],
                toolkit_slugs=[toolkit_slug],
                statuses=["ACTIVE"],
            )
            items = getattr(accounts, "items", []) or []
            for item in items:
                account_id = getattr(item, "id", None)
                if not account_id:
                    continue
                detail = _composio._client.connected_accounts.retrieve(nanoid=account_id)
                # OAuth2 connections expose access_token on the connection_data
                token = None
                conn_data = getattr(detail, "connection_data", None)
                if conn_data:
                    token = getattr(conn_data, "access_token", None)
                if not token:
                    token = getattr(detail, "access_token", None)
                if token:
                    return token
        except Exception as exc:
            logger.debug("_get_access_token: %s lookup failed: %s", toolkit_slug, exc)

    raise RuntimeError(f"No active Google connection found for user {user_id}")


def _format_contacts(people: list[dict]) -> list[dict]:
    """Normalise People API person objects into flat contact dicts."""
    results = []
    for person in people:
        contact: dict = {}

        names = person.get("names", [])
        if names:
            contact["name"] = names[0].get("displayName", "")

        emails = person.get("emailAddresses", [])
        if emails:
            primary = next((e for e in emails if e.get("metadata", {}).get("primary")), emails[0])
            contact["email"] = primary.get("value", "")
            if len(emails) > 1:
                contact["all_emails"] = [e.get("value", "") for e in emails]

        phones = person.get("phoneNumbers", [])
        if phones:
            primary = next((p for p in phones if p.get("metadata", {}).get("primary")), phones[0])
            contact["phone"] = primary.get("value", "")

        orgs = person.get("organizations", [])
        if orgs:
            org = orgs[0]
            parts = [org.get("title", ""), org.get("name", "")]
            contact["organization"] = " at ".join(p for p in parts if p)

        if contact.get("name") or contact.get("email"):
            results.append(contact)

    return results


def search_contacts(user_id: str, query: str, limit: int = 10) -> str:
    """Search Google Contacts by name, email, or phone. Returns JSON string."""
    try:
        token = _get_access_token(user_id)
        resp = httpx.get(
            f"{_PEOPLE_API}/people:searchContacts",
            params={"query": query, "readMask": _PERSON_FIELDS, "pageSize": min(limit, 30)},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        people = [r.get("person", {}) for r in data.get("results", [])]
        contacts = _format_contacts(people)
        if not contacts:
            return json.dumps({"contacts": [], "message": f"No contacts found matching '{query}'"})
        return json.dumps({"contacts": contacts, "total": len(contacts)})
    except RuntimeError as exc:
        return json.dumps({"error": str(exc)})
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": f"People API error {exc.response.status_code}: {exc.response.text[:200]}"})
    except Exception as exc:
        logger.exception("search_contacts failed for %s: %s", user_id, exc)
        return json.dumps({"error": str(exc)})


def list_contacts(user_id: str, limit: int = 20) -> str:
    """List the user's Google Contacts. Returns JSON string."""
    try:
        token = _get_access_token(user_id)
        resp = httpx.get(
            f"{_PEOPLE_API}/people/me/connections",
            params={
                "personFields": _PERSON_FIELDS,
                "pageSize": min(limit, 100),
                "sortOrder": "LAST_MODIFIED_DESCENDING",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        people = data.get("connections", [])
        contacts = _format_contacts(people)
        if not contacts:
            return json.dumps({"contacts": [], "message": "No contacts found"})
        return json.dumps({"contacts": contacts, "total": len(contacts)})
    except RuntimeError as exc:
        return json.dumps({"error": str(exc)})
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": f"People API error {exc.response.status_code}: {exc.response.text[:200]}"})
    except Exception as exc:
        logger.exception("list_contacts failed for %s: %s", user_id, exc)
        return json.dumps({"error": str(exc)})


# ── Tool definition (Anthropic ToolParam) ─────────────────────────────────────

TOOL_DEFINITION: dict = {
    "name": "google_contacts",
    "description": (
        "Search or list the user's Google Contacts. "
        "Use 'search' to find a contact by name, email address, or phone number. "
        "Use 'list' to retrieve recent contacts. "
        "Always look up a contact when the user refers to someone by name only, "
        "to resolve their email address before composing emails or creating calendar invites."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search", "list"],
                "description": "'search' to find a specific contact, 'list' to retrieve recent contacts.",
            },
            "query": {
                "type": "string",
                "description": "Search term (name, email, or phone). Required when action is 'search'.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of contacts to return (default 10, max 100).",
            },
        },
        "required": ["action"],
    },
}
