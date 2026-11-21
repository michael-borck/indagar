from indagar.classify import classify_url


def test_classifies_academic_sources():
    assert classify_url("https://arxiv.org/abs/2501.00001") == ("academic", "high")
    assert classify_url("https://www.nature.com/articles/example") == (
        "academic",
        "high",
    )
    assert classify_url("https://example.edu/paper") == ("academic", "high")


def test_classifies_institutions_and_news():
    assert classify_url("https://www.cdc.gov/report") == ("institution", "high")
    assert classify_url("https://www.who.int/news/item") == ("institution", "high")
    assert classify_url("https://www.reuters.com/world/example") == ("news", "medium")
    assert classify_url("https://example.com/news/example") == ("news", "medium")


def test_classifies_media_practitioner_and_web():
    assert classify_url("https://www.youtube.com/watch?v=1") == ("media", "low")
    assert classify_url("https://example.substack.com/p/example") == (
        "practitioner",
        "low",
    )
    assert classify_url("https://example.com/page") == ("web", "low")
    assert classify_url("not a url") == ("web", "low")
