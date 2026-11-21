from indagar.config import Settings


def test_search_order_and_configured_providers(monkeypatch):
    monkeypatch.setenv("INDAGAR_SEARCH_ORDER", "brave,firecrawl,searxng")
    monkeypatch.setenv("FIRECRAWL_URL", "http://localhost:3002")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-key")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("SEARXNG_URL", raising=False)

    settings = Settings.from_env()

    assert settings.search_order == ("brave", "firecrawl", "searxng")
    assert settings.configured_search_providers() == ("brave", "firecrawl")


def test_llm_provider_detection(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    assert Settings.from_env().llm_providers() == ()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    assert Settings.from_env().llm_providers() == ("anthropic",)
