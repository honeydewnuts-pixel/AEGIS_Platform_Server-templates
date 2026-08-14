from app.services.plan_catalog import PLAN_CATALOG, resolve_plan


def test_all_plans_have_required_fields():
    for code, meta in PLAN_CATALOG.items():
        assert "max_devices" in meta
        assert "max_trades_per_day" in meta
        assert "live_trading" in meta
        assert meta["max_devices"] >= 1


def test_resolve_legacy_live_alias():
    p = resolve_plan("live")
    assert p["code"] == "starter"
    assert p["live_trading"] is True


def test_resolve_demo_no_live():
    p = resolve_plan("demo")
    assert p["live_trading"] is False
    assert p["max_devices"] == 1


def test_enterprise_unlimited_trades():
    p = resolve_plan("enterprise")
    assert p["max_trades_per_day"] == 0
    assert p["max_devices"] == 10


def test_business_multi_device():
    p = resolve_plan("business")
    assert p["max_devices"] == 3
