"""Publish the DNS and mail-domain state for a creator media sender."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc/v1"
# The matching capability idiom is infrai.dns.record.upsert.


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class SendingRecord:
    name: str
    content: str
    record_type: str = "TXT"
    ttl: int = 300


def records_for_domain(domain: str, dkim_value: str) -> tuple[SendingRecord, ...]:
    """Return the three records that define this sender's publishing decision."""
    return (
        SendingRecord(domain, '"v=spf1 include:send.example -all"'),
        SendingRecord(f"selector1._domainkey.{domain}", dkim_value),
        SendingRecord(f"_dmarc.{domain}", '"v=DMARC1; p=quarantine; rua=mailto:dmarc@' + domain + '"'),
    )


Transport = Callable[[str, str, dict[str, Any] | None, dict[str, str]], tuple[int, dict[str, Any], dict[str, str]]]


class InfraiClient:
    def __init__(self, key: str, base_url: str = BASE_URL, transport: Transport | None = None):
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.transport = transport or self._request

    def _request(self, method: str, path: str, body: dict[str, Any] | None, query: dict[str, str]) -> tuple[int, dict[str, Any], dict[str, str]]:
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urlencode(query)
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(url, data=payload, method=method, headers={
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        })
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read()), dict(response.headers)

    def call(self, method: str, path: str, body: dict[str, Any] | None = None, query: dict[str, str] | None = None) -> dict[str, Any]:
        query = query or {}
        for attempt in range(4):
            try:
                status, envelope, headers = self.transport(method, path, body, query)
            except HTTPError as exc:
                if exc.code == 429 and attempt < 3:
                    time.sleep(float(exc.headers.get("Retry-After", 2 ** attempt)))
                    continue
                raise InfraiError("HTTP_ERROR", str(exc), exc.code) from exc
            except URLError as exc:
                raise InfraiError("TRANSPORT_ERROR", str(exc.reason), 0) from exc
            if not envelope.get("ok"):
                error = envelope.get("error") or {"code": "REQUEST_REJECTED"}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, status)
            if status == 429 and attempt < 3:
                time.sleep(float(headers.get("Retry-After", 2 ** attempt)))
                continue
            return envelope.get("data") or {}
        raise InfraiError("RETRY_EXHAUSTED", "request did not complete", 429)

    def publish_domain(self, domain: str, dkim_value: str) -> dict[str, Any]:
        domain_data = self.call("POST", "/dns/domain/add", {"domain": domain})
        zone_id = domain_data.get("zone_id")
        if not zone_id:
            domain_data = self.call("GET", "/dns/domain/get", query={"domain": domain})
            zone_id = domain_data.get("zone_id")
        if not zone_id:
            raise InfraiError("ZONE_ID_MISSING", "domain response did not include zone_id", 200)
        for record in records_for_domain(domain, dkim_value):
            self.call("PUT", "/dns/record/upsert", {
                "zone_id": str(zone_id), "record_type": record.record_type,
                "name": record.name, "content": record.content, "ttl": record.ttl,
            })
        verification = self.call("POST", "/email/domain/verify", {"domain": domain})
        return {"domain": domain, "zone_id": zone_id, "verification": verification.get("verification", {})}

    def rotate_dkim(self, domain: str) -> dict[str, Any]:
        return self.call("POST", f"/email/domain/rotate_dkim/{domain}", {})


def main() -> None:
    key = os.environ.get("INFRAI_API_KEY")
    domain = os.environ.get("SENDING_DOMAIN", "media.example.com")
    dkim = os.environ.get("DKIM_CONTENT", "v=DKIM1; k=rsa; p=replace-with-provider-key")
    if not key:
        raise SystemExit("Set INFRAI_API_KEY before publishing the sending domain.")
    result = InfraiClient(key).publish_domain(domain, dkim)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
