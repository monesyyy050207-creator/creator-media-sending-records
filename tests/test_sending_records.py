import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from sending_records import InfraiClient, records_for_domain


def test_media_sender_publishes_spf_dkim_and_dmarc_before_verification():
    calls = []

    def fake_transport(method, path, body, query):
        calls.append((method, path, body, query))
        if path == "/dns/domain/add":
            return 200, {"ok": True, "data": {"zone_id": "zone-media-7"}}, {}
        if path == "/email/domain/verify":
            return 200, {"ok": True, "data": {"verification": {"status": "verified"}}}, {}
        return 200, {"ok": True, "data": {}}, {}

    result = InfraiClient("test-key", transport=fake_transport).publish_domain(
        "studio.example", "v=DKIM1; k=rsa; p=abc"
    )

    assert result["zone_id"] == "zone-media-7"
    assert result["verification"]["status"] == "verified"
    writes = [call for call in calls if call[1] == "/dns/record/upsert"]
    assert [call[2]["record_type"] for call in writes] == ["TXT", "TXT", "TXT"]
    assert [call[2]["name"] for call in writes] == [record.name for record in records_for_domain("studio.example", "v=DKIM1; k=rsa; p=abc")]
    assert calls[-1][1] == "/email/domain/verify"


def test_rotate_dkim_uses_path_domain_and_no_unsupported_body_field():
    calls = []

    def fake_transport(method, path, body, query):
        calls.append((method, path, body, query))
        return 200, {"ok": True, "data": {}}, {}

    InfraiClient("test-key", transport=fake_transport).rotate_dkim("studio.example")

    assert calls == [("POST", "/email/domain/rotate_dkim/studio.example", {}, {})]
