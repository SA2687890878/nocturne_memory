import pytest

import embedding


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body or {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}
        self.text = text
        self.is_error = status_code >= 400

    def json(self):
        return self._body


class FakeAsyncClient:
    last_request = None
    response = FakeResponse()

    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        FakeAsyncClient.last_request = {"url": url, "headers": headers, "json": json}
        return FakeAsyncClient.response


@pytest.mark.asyncio
async def test_embed_texts_reads_key_from_config_and_sends_nvidia_payload(monkeypatch):
    monkeypatch.setattr(embedding.config, "get", lambda key: {
        "base_url": "https://example.invalid/v1/embeddings",
        "model": "nvidia/nemotron-3-embed-1b",
        "api_key": "test-secret",
        "timeout_seconds": 17,
    } if key == "embedding" else None)
    monkeypatch.setattr(embedding.httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.response = FakeResponse(body={"data": [
        {"index": 1, "embedding": [0.3, 0.4]},
        {"index": 0, "embedding": [0.1, 0.2]},
    ]})

    vectors = await embedding.embed_texts(["query one", "query two"], input_type="query")

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    request = FakeAsyncClient.last_request
    assert request["headers"]["Authorization"] == "Bearer test-secret"
    assert request["json"]["model"] == "nvidia/nemotron-3-embed-1b"
    assert request["json"]["input_type"] == "query"
    assert request["json"]["input"] == ["query one", "query two"]


@pytest.mark.asyncio
async def test_embed_texts_requires_api_key(monkeypatch):
    monkeypatch.setattr(embedding.config, "get", lambda key: {"api_key": ""})
    with pytest.raises(embedding.EmbeddingConfigurationError, match="api_key"):
        await embedding.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_embed_texts_rejects_api_error_without_leaking_key(monkeypatch):
    monkeypatch.setattr(embedding.config, "get", lambda key: {
        "base_url": "https://example.invalid/v1/embeddings",
        "model": "test-model",
        "api_key": "test-secret",
    })
    monkeypatch.setattr(embedding.httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.response = FakeResponse(status_code=401, text="unauthorized")
    with pytest.raises(embedding.EmbeddingAPIError, match="HTTP 401") as exc:
        await embedding.embed_texts(["hello"])
    assert "test-secret" not in str(exc.value)


@pytest.mark.asyncio
async def test_embed_texts_empty_input_returns_empty_list():
    assert await embedding.embed_texts([]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), True])
async def test_embed_texts_rejects_non_finite_and_boolean_values(monkeypatch, bad_value):
    monkeypatch.setattr(embedding.config, "get", lambda key: {
        "base_url": "https://example.invalid/v1/embeddings",
        "model": "test-model",
        "api_key": "test-secret",
    })
    monkeypatch.setattr(embedding.httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.response = FakeResponse(body={"data": [{"index": 0, "embedding": [0.1, bad_value]}]})
    with pytest.raises(embedding.EmbeddingAPIError, match="non-finite or non-numeric"):
        await embedding.embed_texts(["hello"])
