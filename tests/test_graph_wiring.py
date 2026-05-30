"""WP-B module wiring test.

Verifies the four real WP-B node modules are importable with the correct
callable names. Does NOT invoke the graph (WP-D owns wiring + edges, WP-I
owns full integration tests). The compile-only stub graph is unchanged.
"""
import inspect

from src.graph import build_graph


def test_stub_graph_still_compiles():
    """Foundation stub graph must compile unmodified (WP-D owns build_graph)."""
    app = build_graph()
    nodes = set(app.get_graph().nodes)
    assert {"router", "news_analyst", "fundamentals_analyst", "technicals_analyst"} <= nodes


def test_real_router_is_importable_and_async():
    from src.agents.router import router
    assert inspect.iscoroutinefunction(router)


def test_real_news_analyst_is_importable_and_async():
    from src.agents.analysts.news import news_analyst
    assert inspect.iscoroutinefunction(news_analyst)


def test_real_fundamentals_analyst_is_importable_and_async():
    from src.agents.analysts.fundamentals import fundamentals_analyst
    assert inspect.iscoroutinefunction(fundamentals_analyst)


def test_real_technicals_analyst_is_importable_and_async():
    from src.agents.analysts.technicals import technicals_analyst
    assert inspect.iscoroutinefunction(technicals_analyst)
