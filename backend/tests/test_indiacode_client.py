import httpx

from app.ingest.indiacode_client import IndiaCodeClient, choose_english_pdf, choose_exact_item


def _metadata(value):
    return [{"value": value}]


def test_exact_title_match_ignores_similar_search_results():
    payload = {
        "_embedded": {"searchResult": {"_embedded": {"objects": [
            {"_embedded": {"indexableObject": {"uuid": "wrong", "metadata": {"dc.title": _metadata("Information Technology Rules, 2001")}}}},
            {"_embedded": {"indexableObject": {"uuid": "right", "metadata": {"dc.title": _metadata("The Information Technology Act, 2000")}}}},
        ]}}}
    }
    assert [item["uuid"] for item in choose_exact_item(payload, "The Information Technology Act, 2000")] == ["right"]


def test_english_pdf_is_preferred_over_hindi_bitstream():
    payload = {"_embedded": {"bitstreams": [
        {"uuid": "hi", "name": "H200021.pdf", "metadata": {"dc.title.language": _metadata("Hindi")}},
        {"uuid": "en", "name": "A200021.pdf", "metadata": {"dc.title.language": _metadata("English")}},
    ]}}
    assert choose_english_pdf(payload)["uuid"] == "en"


def test_resolver_walks_item_original_bundle_and_english_pdf():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/discover/search/objects"):
            return httpx.Response(200, json={
                "_embedded": {"searchResult": {"_embedded": {"objects": [
                    {"_embedded": {"indexableObject": {
                        "uuid": "item-1",
                        "metadata": {
                            "dc.title": _metadata("The Information Technology Act, 2000"),
                            "dc.identifier.act_id": _metadata("official-act-id"),
                        },
                    }}},
                ]}}},
            })
        if path.endswith("/core/items/item-1/bundles"):
            return httpx.Response(200, json={"_embedded": {"bundles": [{"uuid": "bundle-1", "name": "ORIGINAL"}]}})
        if path.endswith("/core/bundles/bundle-1/bitstreams"):
            return httpx.Response(200, json={"_embedded": {"bitstreams": [
                {"uuid": "hindi", "name": "H200021.pdf", "metadata": {"dc.title.language": _metadata("Hindi")}},
                {"uuid": "english", "name": "A200021.pdf", "metadata": {"dc.title.language": _metadata("English")}},
            ]}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    raw_client = httpx.Client(base_url="https://indiacode.gov.in/server/api", transport=transport)
    resolver = IndiaCodeClient(client=raw_client)
    result = resolver.resolve("The Information Technology Act, 2000", "collection")

    assert result.item_uuid == "item-1"
    assert result.act_id == "official-act-id"
    assert result.bitstream_uuid == "english"
    assert result.source_url.endswith("/core/bitstreams/english/content")
