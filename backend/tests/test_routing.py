from radar.assess.routing import clamp_score, decide_route
from radar.models import Route


def test_thresholds_split_immediate_digest_inbox():
    kwargs = dict(immediate_threshold=75, digest_threshold=50)
    assert decide_route(90, **kwargs) == Route.immediate
    assert decide_route(75, **kwargs) == Route.immediate
    assert decide_route(60, **kwargs) == Route.digest
    assert decide_route(50, **kwargs) == Route.digest
    assert decide_route(49, **kwargs) == Route.inbox
    assert decide_route(0, **kwargs) == Route.inbox


def test_muted_and_thin_content_never_interrupt():
    assert decide_route(99, immediate_threshold=75, digest_threshold=50, competitor_muted=True) == Route.muted
    assert decide_route(99, immediate_threshold=75, digest_threshold=50, is_substantive=False) == Route.inbox


def test_clamp_score():
    assert clamp_score(-4) == 0
    assert clamp_score(140) == 100
    assert clamp_score(73) == 73
