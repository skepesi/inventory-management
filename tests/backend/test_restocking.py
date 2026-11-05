"""
Tests for restocking API endpoints.
"""
from datetime import datetime, timedelta

import pytest

import main

RECOMMENDATIONS_URL = "/api/restocking/recommendations"
ORDERS_URL = "/api/restocking/orders"


@pytest.fixture(autouse=True)
def clear_restocking_orders():
    """Submitted orders live in module state, so reset them around every test."""
    main.restocking_orders.clear()
    yield
    main.restocking_orders.clear()


def get_full_cost(client):
    """Get the budget needed to cover every recommended item in full."""
    return client.get(f"{RECOMMENDATIONS_URL}?budget=0").json()["full_cost"]


class TestRestockForecastFields:
    """Test suite for the forecast fields restocking depends on."""

    def test_demand_forecast_has_restock_fields(self, client):
        """Test that every forecast has a usable cost and lead time."""
        data = client.get("/api/demand").json()
        assert len(data) > 0

        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["unit_cost"] > 0
            assert forecast["lead_time_days"] > 0

    def test_psu_501_cost_matches_inventory(self, client):
        """Test that the one SKU also in inventory uses its real inventory cost."""
        forecasts = client.get("/api/demand").json()
        inventory = client.get("/api/inventory").json()

        forecast_cost = next(f["unit_cost"] for f in forecasts if f["item_sku"] == "PSU-501")
        inventory_cost = next(i["unit_cost"] for i in inventory if i["sku"] == "PSU-501")

        assert forecast_cost == inventory_cost


class TestRestockRecommendations:
    """Test suite for the restocking recommendation endpoint."""

    def test_get_recommendations_structure(self, client):
        """Test that recommendations have the expected structure."""
        response = client.get(f"{RECOMMENDATIONS_URL}?budget=5000")
        assert response.status_code == 200

        data = response.json()
        assert data["budget"] == 5000
        assert len(data["items"]) > 0
        for field in ["total_cost", "remaining_budget", "full_cost"]:
            assert isinstance(data[field], (int, float))

        for item in data["items"]:
            for field in ["sku", "name", "trend", "quantity", "unit_cost", "line_total", "lead_time_days"]:
                assert field in item

    @pytest.mark.parametrize("budget", [1, 100, 1234.56, 5000, 9000, 50000])
    def test_recommendations_never_exceed_budget(self, client, budget):
        """Test that the recommended total stays within the budget."""
        data = client.get(f"{RECOMMENDATIONS_URL}?budget={budget}").json()

        assert data["total_cost"] <= budget
        assert abs(data["total_cost"] + data["remaining_budget"] - budget) < 0.01

    def test_recommendations_total_cost_calculation(self, client):
        """Test that line totals and the order total add up."""
        # Use the full budget: a smaller one can buy a single item, which proves nothing about the sum
        data = client.get(f"{RECOMMENDATIONS_URL}?budget={get_full_cost(client)}").json()
        assert len(data["items"]) > 1

        for item in data["items"]:
            assert abs(item["line_total"] - item["quantity"] * item["unit_cost"]) < 0.01

        assert abs(data["total_cost"] - sum(i["line_total"] for i in data["items"])) < 0.01

    def test_recommendations_exclude_decreasing_items(self, client):
        """Test that decreasing items are not recommended, even with unlimited budget."""
        data = client.get(f"{RECOMMENDATIONS_URL}?budget=1000000").json()

        assert "MTR-304" not in [item["sku"] for item in data["items"]]
        assert all(item["trend"].lower() != "decreasing" for item in data["items"])

    def test_recommendations_rank_increasing_before_stable(self, client):
        """Test that all increasing items come before all stable items."""
        data = client.get(f"{RECOMMENDATIONS_URL}?budget=1000000").json()
        trends = [item["trend"].lower() for item in data["items"]]

        assert "stable" in trends
        assert trends.index("stable") == trends.count("increasing")

    def test_recommendations_rank_by_gap_within_trend(self, client):
        """Test that larger demand gaps come first within each trend."""
        data = client.get(f"{RECOMMENDATIONS_URL}?budget=1000000").json()

        for trend in ["increasing", "stable"]:
            quantities = [i["quantity"] for i in data["items"] if i["trend"].lower() == trend]
            assert quantities == sorted(quantities, reverse=True)

    def test_recommendations_buy_partial_quantity(self, client):
        """Test that a short budget buys part of the top item, not none of it."""
        forecasts = client.get("/api/demand").json()
        top_sku = client.get(f"{RECOMMENDATIONS_URL}?budget=1000000").json()["items"][0]["sku"]
        top = next(f for f in forecasts if f["item_sku"] == top_sku)
        gap = top["forecasted_demand"] - top["current_demand"]

        budget = top["unit_cost"] * (gap - 1)
        first_item = client.get(f"{RECOMMENDATIONS_URL}?budget={budget}").json()["items"][0]

        assert first_item["sku"] == top_sku
        assert first_item["quantity"] == gap - 1

    def test_recommendations_skip_unaffordable_items(self, client):
        """Test that a cheaper lower-ranked item is still bought when the top item doesn't fit."""
        data = client.get(f"{RECOMMENDATIONS_URL}?budget=20").json()

        # $20 can't buy the $45 top-ranked widget, but covers cheaper items further down
        assert "WDG-001" not in [item["sku"] for item in data["items"]]
        assert len(data["items"]) > 0

    def test_recommendations_exact_budget_boundary(self, client):
        """Test that the full cost as a budget covers everything, with no float rounding loss."""
        full_cost = get_full_cost(client)
        data = client.get(f"{RECOMMENDATIONS_URL}?budget={full_cost}").json()

        assert data["total_cost"] == full_cost
        assert data["remaining_budget"] == 0

    def test_full_budget_covers_every_gap(self, client):
        """Test that a full budget orders the whole gap for each non-decreasing item."""
        forecasts = client.get("/api/demand").json()
        expected = {
            f["item_sku"]: f["forecasted_demand"] - f["current_demand"]
            for f in forecasts
            if f["trend"].lower() != "decreasing"
        }

        data = client.get(f"{RECOMMENDATIONS_URL}?budget={get_full_cost(client)}").json()

        assert {item["sku"]: item["quantity"] for item in data["items"]} == expected

    def test_zero_budget_returns_no_items(self, client):
        """Test that a budget of zero recommends nothing."""
        response = client.get(f"{RECOMMENDATIONS_URL}?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["full_cost"] > 0

    @pytest.mark.parametrize("budget", ["-1", "inf", "nan", "1e308", "abc"])
    def test_invalid_budget_rejected(self, client, budget):
        """Test that unusable budgets are validation errors, not server crashes."""
        response = client.get(f"{RECOMMENDATIONS_URL}?budget={budget}")
        assert response.status_code == 422

    def test_missing_budget_rejected(self, client):
        """Test that the budget parameter is required."""
        response = client.get(RECOMMENDATIONS_URL)
        assert response.status_code == 422


class TestRestockOrders:
    """Test suite for submitting and listing restocking orders."""

    def test_get_orders_empty(self, client):
        """Test that no orders are listed before any are placed."""
        response = client.get(ORDERS_URL)
        assert response.status_code == 200
        assert response.json() == []

    def test_create_order(self, client):
        """Test that an order matches the recommendation for its budget."""
        recommendation = client.get(f"{RECOMMENDATIONS_URL}?budget=5000").json()

        response = client.post(ORDERS_URL, json={"budget": 5000})
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"] == "RST-0001"
        assert order["status"] == "Submitted"
        assert order["budget"] == 5000
        assert order["items"] == recommendation["items"]
        assert order["total_cost"] == recommendation["total_cost"]

    def test_create_order_uses_slowest_lead_time(self, client):
        """Test that an order's lead time is that of its slowest item."""
        # Use the full budget so the order mixes lead times; a one-item order can't
        # tell the slowest item apart from the first, the fastest or any other rule
        order = client.post(ORDERS_URL, json={"budget": get_full_cost(client)}).json()
        lead_times = [item["lead_time_days"] for item in order["items"]]
        assert len(set(lead_times)) > 1

        forecasts = client.get("/api/demand").json()
        slowest = max(
            f["lead_time_days"] for f in forecasts if f["trend"].lower() != "decreasing"
        )
        assert order["lead_time_days"] == slowest
        assert lead_times[0] != slowest

    def test_create_order_expected_delivery(self, client):
        """Test that expected delivery is the order date plus the lead time."""
        order = client.post(ORDERS_URL, json={"budget": 5000}).json()

        order_date = datetime.fromisoformat(order["order_date"])
        expected = datetime.fromisoformat(order["expected_delivery"])

        assert expected - order_date == timedelta(days=order["lead_time_days"])

    def test_create_order_ignores_client_items(self, client):
        """Test that prices and quantities sent by the client are not used."""
        recommendation = client.get(f"{RECOMMENDATIONS_URL}?budget=5000").json()

        order = client.post(ORDERS_URL, json={
            "budget": 5000,
            "total_cost": 1,
            "items": [{"sku": "WDG-001", "quantity": 9999, "unit_cost": 0.01}]
        }).json()

        assert order["items"] == recommendation["items"]
        assert order["total_cost"] == recommendation["total_cost"]

    def test_create_order_budget_too_low(self, client):
        """Test that an order which can't afford anything is rejected and not stored."""
        response = client.post(ORDERS_URL, json={"budget": 1})
        assert response.status_code == 400
        assert "detail" in response.json()

        assert client.get(ORDERS_URL).json() == []

    @pytest.mark.parametrize("body", [{"budget": -1}, {"budget": "abc"}, {}, {"budget": 1e308}])
    def test_create_order_invalid_budget(self, client, body):
        """Test that an invalid or missing budget is a validation error, not a server crash."""
        response = client.post(ORDERS_URL, json=body)
        assert response.status_code == 422
        assert client.get(ORDERS_URL).json() == []

    def test_get_orders_newest_first(self, client):
        """Test that submitted orders are listed newest first with unique numbers."""
        client.post(ORDERS_URL, json={"budget": 1000})
        client.post(ORDERS_URL, json={"budget": 2000})

        data = client.get(ORDERS_URL).json()

        assert [order["order_number"] for order in data] == ["RST-0002", "RST-0001"]

    def test_restock_orders_kept_out_of_customer_orders(self, client):
        """Test that placing an order leaves customer orders and the dashboard unchanged."""
        orders_before = client.get("/api/orders").json()
        summary_before = client.get("/api/dashboard/summary").json()

        client.post(ORDERS_URL, json={"budget": 5000})

        assert client.get("/api/orders").json() == orders_before
        assert client.get("/api/dashboard/summary").json() == summary_before
