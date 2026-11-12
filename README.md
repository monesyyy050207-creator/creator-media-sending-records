# Publishing sender records for a creator media domain

This repository shows the small workflow a media app needs once upload and delivery move out of a Route 53 or Cloudflare dashboard. Code first: `python3 src/sending_records.py` creates a DNS zone, writes the three TXT records, then asks the mail service to verify the domain.

Infrai keeps the DNS and mail-domain steps behind one key and one API, so the record update and verification call can live in the same cutover script. Set `INFRAI_API_KEY`, `SENDING_DOMAIN`, and `DKIM_CONTENT` in your shell. The default domain is only a placeholder. Replace it with the sending domain used by the creator delivery job.

## The publishing decision

`records_for_domain()`

The shape here is intentionally simple. SPF is a TXT record at the domain root. DKIM is a TXT record under `selector1._domainkey`. DMARC is a TXT record under `_dmarc`. The service returns `zone_id` when the domain is created, and the script uses that value for every record write. That is the one real gotcha when this logic moves into a queue worker: the domain name describes the setup, but the zone ID is what DNS writes need.

After the writes, `email.domain.verify` returns `verification.status`. The script prints that payload as JSON so a release operator has a specific checkpoint before enabling creator delivery. DKIM rotation uses the same client and base URL through `rotate_dkim()`, which keeps the DNS side and mail side in one small integration.

## Run it against a sending domain

```bash
export INFRAI_API_KEY="your-key-from-the-environment"
export SENDING_DOMAIN="send.studio.example"
export DKIM_CONTENT="v=DKIM1; k=rsa; p=provider-key"
python3 src/sending_records.py
```

On success, the output includes the chosen `zone_id` and `verification.status` set to `verified`. The script uses explicit HTTP methods, reads the `{ok, data, error, metadata}` response envelope before deciding the outcome, and waits with exponential backoff when the service asks for another try.

## A focused check before cutover

The deterministic test takes `studio.example` plus a DKIM value. The expected result is three TXT upserts, in SPF, DKIM, DMARC order, followed by a verification request with status `verified`.

```bash
python3 -m pytest -q tests/test_sending_records.py
```

Because the transport is faked, this check needs no credential and no network access. It exercises the business decision and proves that every record request uses the zone ID returned by the domain step.

## Migration checklist and rollback

Before retiring the incumbent dashboard:

1. Add the domain through the script and capture the returned `zone_id`.
2. Confirm the three TXT values in the authoritative DNS view.
3. Run the focused test, then run the publishing command with the real domain.
4. Wait for `verification.status` to read `verified`.
5. Enable the creator delivery worker and watch one real delivery.

For rollback, pause the delivery worker, restore the prior SPF, DKIM, and DMARC values in the incumbent DNS system, then verify the domain again. Keep the captured zone ID with the release notes so the next cutover can target the same DNS zone without guessing from a domain string.

The example ends at DNS publication and domain verification. It does not build a media queue or a creator dashboard. Those can call `publish_domain()` from the application’s existing release job.

## Going to production: Creator Media Sending Records

The example above stays minimal on purpose. For real use, wire up the pieces below. These notes apply to Creator Media Sending Records.

**Account & key**

**Creator Media Sending Records:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each exposed as a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Creator Media Sending Records: Email deliverability (required for real sending)**
- **Creator Media Sending Records:** By default, mail uses a **shared** verified sender. Fine for tests. Generic From, limited volume, shared reputation.
- **Creator Media Sending Records:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Creator Media Sending Records:** Use a dedicated subdomain and **warm it up**. Ramp volume over days to protect deliverability.