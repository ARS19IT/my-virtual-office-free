from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

from token_optimizer import SafariA6APIController, A6API_TAB_TITLE, SellerRow


class MockSafari:
    def __init__(self, title=A6API_TAB_TITLE):
        self.title = title
        self.calls = []
        self.rows = [
            {"seller": "slow-cheap", "model": "m", "price": 1, "success_rate": .90},
            {"seller": "reliable", "model": "m", "price": 2, "success_rate": .99},
        ]

    def current_tab_title(self): return self.title
    def refresh(self): self.calls.append("refresh")
    def open_marketplace(self): self.calls.append("marketplace")
    def select_agent_token(self, agent, token_id): self.calls.append(("agent_token", agent, token_id))
    def select_model(self, model): self.calls.append(("model", model))
    def seller_rows(self): return self.rows
    def route(self): return {"agent": "a", "model": "m", "seller": "reliable"}
    def usage_log(self): return [{"model": "m", "count": 2}]


def test_safari_controller_is_dry_run_and_allowlisted():
    browser = MockSafari()
    controller = SafariA6APIController(browser)
    assert controller.refresh() is False
    assert controller.open_marketplace() is False
    assert controller.select_agent_token("agent", "token-id") is False
    assert controller.select_model("m") is False
    assert browser.calls == []
    assert controller.choose_minimum_price() == SellerRow("slow-cheap", "m", 1.0, .90)
    assert controller.confirm_route_fixed(expected={"agent": "a", "model": "m", "seller": "reliable"})
    assert controller.inspect_usage_log() == ({"model": "m", "count": 2},)


def test_apply_executes_only_allowlisted_actions_on_current_tab():
    browser = MockSafari()
    controller = SafariA6APIController(browser, apply=True)
    assert controller.refresh() is True
    assert controller.open_marketplace() is True
    assert controller.select_agent_token("agent", "token-id") is True
    assert controller.select_model("m") is True
    assert browser.calls == ["refresh", "marketplace", ("agent_token", "agent", "token-id"), ("model", "m")]


def test_wrong_tab_blocks_reads_and_writes():
    browser = MockSafari("Other tab")
    controller = SafariA6APIController(browser, apply=True)
    for action in (controller.refresh, controller.inspect_seller_rows, controller.inspect_usage_log):
        try:
            action()
        except PermissionError:
            pass
        else:
            raise AssertionError("wrong tab was not blocked")


def test_secret_values_are_rejected_and_never_stored():
    browser = MockSafari()
    controller = SafariA6APIController(browser, apply=True)
    for value in ("api_key=secret", "my-password", "bearer-token"):
        try:
            controller.select_model(value)
        except ValueError:
            pass
        else:
            raise AssertionError("secret-looking identifier accepted")
    try:
        controller.inspect_seller_rows.__self__._row({"seller": "x", "api_key": "do-not-read"})
    except ValueError:
        pass
    else:
        raise AssertionError("secret field accepted")
