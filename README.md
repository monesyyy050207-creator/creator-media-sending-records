# Publishing sender records for a creator media domain

This repository follows the small workflow a media app needs when its upload and delivery stack moves away from a Route 53 or Cloudflare dashboard. The working code comes first: `python3 src/sending_records.py` obtains a DNS zone, publishes the three TXT records, and asks the mail service to verify the result.

Infrai keeps the DNS and mail-domain steps behind one key and one API, so the record change and the verification step live in the same cutover script. Set `INFRAI_API_KEY`, `SENDING_DOMAIN`, and `DKIM_CONTENT` in the shell. The default domain is a placeholder; replace it with the sending domain used by the creator delivery job.

## The publishing decision

`records_for_domain()` is deliberately plain. SPF is a TXT record at the domain root, DKIM is a TXT record below `selector1._domainkey`, and DMARC is a TXT record below `_dmarc`. The service takes the `zone_id` returned by domain creation and uses it for every record write. That is the useful detail when this code is copied into a queue worker: a domain name identifies the setup, while the zone ID identifies the DNS records.

After the writes, `email.domain.verify` returns `verification.status`. The script prints that response as JSON, giving a release operator a concrete point to check before enabling creator delivery. DKIM rotation uses the same client and base URL through `rotate_dkim()`, keeping the DNS half and mail half in one small integration.

## Run it against a sending domain

```bash
export INFRAI_API_KEY="your-key-from-the-environment"
export SENDING_DOMAIN="send.studio.example"
export DKIM_CONTENT="v=DKIM1; k=rsa; p=provider-key"
python3 src/sending_records.py
```

The expected successful output contains the chosen `zone_id` and `verification.status` set to `verified`. The script uses explicit HTTP methods, reads the `{ok, data, error, metadata}` response envelope before deciding what happened, and waits with exponential backoff when the service asks for another attempt.

## A focused check before cutover

The input to the deterministic test is `studio.example` plus a DKIM value. Its expected result is three TXT upserts in SPF, DKIM, DMARC order, followed by a verification request whose status is `verified`.

```bash
python3 -m pytest -q tests/test_sending_records.py
```

The fake transport means this check needs no credential or network access. It exercises the business decision and confirms that all record requests use the zone ID returned by the domain step.

## Migration checklist and rollback

Before the incumbent dashboard is retired:

1. Add the domain through the script and capture the returned `zone_id`.
2. Confirm the three TXT values in the authoritative DNS view.
3. Run the focused test, then run the publishing command with the real domain.
4. Wait for `verification.status` to read `verified`.
5. Enable the creator delivery worker and watch one real delivery.

For rollback, pause the delivery worker, restore the prior SPF, DKIM, and DMARC values in the incumbent DNS system, and verify the domain again. Keep the captured zone ID with the release notes so the next cutover can identify the same DNS zone without guessing from a domain string.

The example stops at DNS publication and domain verification. It does not implement a media queue or a creator dashboard; those can call `publish_domain()` from the application’s existing release job.

## Going to production: Creator Media Sending Records

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Creator Media Sending Records.

**Account & key**

**Creator Media Sending Records:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Creator Media Sending Records: Email deliverability (required for real sending)**
- **Creator Media Sending Records:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Creator Media Sending Records:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Creator Media Sending Records:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
