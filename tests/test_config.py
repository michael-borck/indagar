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
    monkeypatch.delenv("INDAGAR_LLM_PROVIDER", raising=False)

    assert Settings.from_env().llm_providers() == ()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    assert Settings.from_env().llm_providers() == ("anthropic",)


def test_llm_provider_normalization(monkeypatch):
    monkeypatch.setenv("INDAGAR_LLM_PROVIDER", "openai")

    assert Settings.from_env().llm_provider == "openai-compatible"


def test_concurrency_setting(monkeypatch):
    monkeypatch.setenv("INDAGAR_CONCURRENCY", "4")

    assert Settings.from_env().concurrency == 4


def test_retry_and_cost_settings(monkeypatch):
    monkeypatch.setenv("INDAGAR_LLM_MAX_RETRIES", "4")
    monkeypatch.setenv("INDAGAR_RETRY_BASE_SECONDS", "1.5")
    monkeypatch.setenv("INDAGAR_LLM_MIN_INTERVAL", "0.25")
    monkeypatch.setenv("INDAGAR_INPUT_COST_PER_MTOK", "3")
    monkeypatch.setenv("INDAGAR_OUTPUT_COST_PER_MTOK", "15")

    settings = Settings.from_env()

    assert settings.llm_max_retries == 4
    assert settings.retry_base_seconds == 1.5
    assert settings.llm_min_interval == 0.25
    assert settings.input_cost_per_mtok == 3.0
    assert settings.output_cost_per_mtok == 15.0


def test_llm_timeout_uses_seconds_not_temperature_bounds(monkeypatch):
    monkeypatch.setenv("INDAGAR_LLM_TIMEOUT", "60")

    assert Settings.from_env().llm_timeout == 60.0


def test_llm_models_and_provider_selection():
    settings = Settings(
        anthropic_api_key="anthropic-key",
        llm_model="global-model",
        planner_model="planner-model",
    )

    assert settings.selected_llm_provider() == "anthropic"
    assert settings.llm_model_for("planner") == "planner-model"
    assert settings.llm_model_for("writer") == "global-model"
    assert settings.llm_model_for("reader") == "global-model"
