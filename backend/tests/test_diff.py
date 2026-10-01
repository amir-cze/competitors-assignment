from radar.ingest.diff import diff_page_text, render_diff_for_llm


def test_date_and_counter_noise_is_not_a_change():
    before = "Security for AI models\nUpdated January 12, 2025\n12,481 customers\nProtect your models."
    after = "Security for AI models\nUpdated March 3, 2026\n12,902 customers\nProtect your models."
    diff = diff_page_text(before, after)
    assert diff.is_empty
    assert diff.changed_chars == 0


def test_cookie_banner_is_ignored():
    before = "Accept all cookies\nAgent security platform"
    after = "Reject cookies\nAgent security platform"
    diff = diff_page_text(before, after)
    assert diff.is_empty


def test_substantive_rewrite_is_reported():
    before = "Protect your models from adversarial attacks.\nBook a demo."
    after = "Discover, protect and govern every agent in your enterprise.\nBook a demo."
    diff = diff_page_text(before, after)
    assert "Protect your models from adversarial attacks." in diff.removed
    assert "Discover, protect and govern every agent in your enterprise." in diff.added
    assert diff.changed_chars > 40
    rendered = render_diff_for_llm(diff)
    assert "REMOVED" in rendered and "ADDED" in rendered


def test_moved_lines_are_not_a_change():
    before = "Alpha claim\nBeta claim\nGamma claim"
    after = "Gamma claim\nAlpha claim\nBeta claim"
    diff = diff_page_text(before, after)
    assert diff.is_empty
