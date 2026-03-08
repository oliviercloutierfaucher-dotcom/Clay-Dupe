"""Salesforce client — wraps simple-salesforce for domain dedup checks.

NOT an enrichment provider (not in ProviderName enum).
Used as a pre-enrichment gate to flag companies already in Salesforce.
"""
from __future__ import annotations

import logging
from typing import Iterator, Optional

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceAuthenticationFailed, SalesforceExpiredSession

logger = logging.getLogger(__name__)

BATCH_SIZE = 150  # SOQL IN clause limit


def _normalize_domain(url: str) -> str:
    """Normalize a URL/domain: strip protocol, www, trailing slash, lowercase."""
    v = url.strip().lower()
    for prefix in ("https://", "http://"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    if v.startswith("www."):
        v = v[4:]
    v = v.rstrip("/")
    return v


def _chunked(lst: list, n: int) -> Iterator[list]:
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


class SalesforceClient:
    """Wraps simple-salesforce with project-specific methods.

    Provides health_check() and check_domains_batch() for Salesforce integration.
    """

    def __init__(self, username: str, password: str, security_token: str):
        self._username = username
        self._password = password
        self._security_token = security_token
        self._sf: Optional[Salesforce] = None

    def _connect(self) -> Salesforce:
        """Lazy-connect, returning cached Salesforce instance."""
        if self._sf is None:
            self._sf = Salesforce(
                username=self._username,
                password=self._password,
                security_token=self._security_token,
            )
        return self._sf

    def health_check(self) -> dict:
        """Create a FRESH connection and verify credentials.

        Returns dict with connected, org_name, account_count, sf_instance.
        Raises SalesforceAuthenticationFailed on bad credentials.
        """
        # Always create fresh instance for health check (not cached)
        sf = Salesforce(
            username=self._username,
            password=self._password,
            security_token=self._security_token,
        )

        org_result = sf.query("SELECT Name FROM Organization LIMIT 1")
        org_name = org_result["records"][0]["Name"] if org_result["records"] else "Unknown"

        count_result = sf.query("SELECT COUNT() FROM Account")
        account_count = count_result.get("totalSize", 0)

        return {
            "connected": True,
            "org_name": org_name,
            "account_count": account_count,
            "sf_instance": sf.sf_instance,
        }

    def check_domains_batch(self, domains: list[str]) -> dict[str, dict]:
        """Check which domains exist in Salesforce as Accounts.

        Strategy:
        1. Normalize all domains
        2. Query Unique_Domain__c field (exact match via IN clause)
        3. For unmatched domains, fallback to Website LIKE match
        4. Return {normalized_domain: {sf_account_id, sf_account_name, sf_instance_url}}

        Handles session expiry by reconnecting once.
        """
        if not domains:
            return {}

        normalized = [_normalize_domain(d) for d in domains]
        # Deduplicate while preserving order
        seen = set()
        unique_domains = []
        for d in normalized:
            if d not in seen:
                seen.add(d)
                unique_domains.append(d)

        try:
            return self._do_check_domains(unique_domains)
        except SalesforceExpiredSession:
            logger.info("Salesforce session expired, reconnecting...")
            self._sf = None
            return self._do_check_domains(unique_domains)

    def _do_check_domains(self, domains: list[str]) -> dict[str, dict]:
        """Internal: run the two-phase domain check."""
        sf = self._connect()
        instance_url = sf.sf_instance
        results: dict[str, dict] = {}
        unmatched = set(domains)

        # Phase 1: Unique_Domain__c exact match
        for chunk in _chunked(domains, BATCH_SIZE):
            in_clause = ", ".join(f"'{d}'" for d in chunk)
            soql = (
                f"SELECT Id, Name, Unique_Domain__c, Website "
                f"FROM Account "
                f"WHERE Unique_Domain__c IN ({in_clause})"
            )
            response = sf.query_all(soql)
            for record in response.get("records", []):
                unique_domain = record.get("Unique_Domain__c")
                if unique_domain:
                    nd = _normalize_domain(unique_domain)
                    if nd in unmatched:
                        results[nd] = {
                            "sf_account_id": record["Id"],
                            "sf_account_name": record["Name"],
                            "sf_instance_url": instance_url,
                        }
                        unmatched.discard(nd)

        # Phase 2: Website LIKE fallback for unmatched
        if unmatched:
            unmatched_list = list(unmatched)
            for chunk in _chunked(unmatched_list, BATCH_SIZE):
                like_clauses = " OR ".join(
                    f"Website LIKE '%{d}%'" for d in chunk
                )
                soql = (
                    f"SELECT Id, Name, Website "
                    f"FROM Account "
                    f"WHERE {like_clauses}"
                )
                response = sf.query_all(soql)
                for record in response.get("records", []):
                    website = record.get("Website")
                    if website:
                        nw = _normalize_domain(website)
                        # Match against our unmatched domains
                        for domain in list(unmatched):
                            if domain == nw or nw.endswith(domain) or domain in nw:
                                results[domain] = {
                                    "sf_account_id": record["Id"],
                                    "sf_account_name": record["Name"],
                                    "sf_instance_url": instance_url,
                                }
                                unmatched.discard(domain)
                                break

        return results
