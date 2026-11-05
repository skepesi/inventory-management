"""
Tests for the low-stock alerts API endpoint.
"""
import pytest

import main


def make_item(sku, quantity_on_hand, reorder_point, unit_cost=10.0,
              warehouse="London", category="Sensors"):
    """Build an inventory record with only the values a test cares about varying."""
    return {
        "id": sku,
        "sku": sku,
        "name": f"Item {sku}",
        "category": category,
        "warehouse": warehouse,
        "quantity_on_hand": quantity_on_hand,
        "reorder_point": reorder_point,
        "unit_cost": unit_cost,
        "location": "Warehouse A-1",
        "last_updated": "2025-09-30T10:30:00",
    }


@pytest.fixture
def use_inventory(monkeypatch):
    """Replace the inventory with controlled records so boundaries can be tested exactly."""
    def _use(*items):
        monkeypatch.setattr(main, "inventory_items", list(items))
    return _use


class TestLowStockAlertEndpoints:
    """Test suite for GET /api/inventory/alerts."""

    def test_get_all_alerts(self, client):
        """Test that alerts return the inventory fields plus the alert fields."""
        response = client.get("/api/inventory/alerts")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        for field in ("id", "sku", "name", "warehouse", "quantity_on_hand",
                      "reorder_point", "shortfall", "reorder_cost", "severity"):
            assert field in data[0], f"Missing field: {field}"

    def test_alerts_route_not_captured_by_item_route(self, client):
        """Test that 'alerts' is not treated as an inventory item ID."""
        response = client.get("/api/inventory/alerts")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_alert_count_matches_dashboard(self, client):
        """Test that the alert count agrees with the dashboard for each filter."""
        for query in ("", "?warehouse=London", "?category=Sensors",
                      "?warehouse=Tokyo&category=Sensors"):
            alerts = client.get(f"/api/inventory/alerts{query}").json()
            summary = client.get(f"/api/dashboard/summary{query}").json()
            assert len(alerts) == summary["low_stock_items"], f"Mismatch for '{query}'"

    def test_get_alerts_by_warehouse(self, client):
        """Test filtering alerts by warehouse."""
        data = client.get("/api/inventory/alerts?warehouse=London").json()
        for alert in data:
            assert alert["warehouse"] == "London"

    def test_get_alerts_by_category(self, client):
        """Test filtering alerts by category, ignoring case."""
        data = client.get("/api/inventory/alerts?category=sensors").json()
        for alert in data:
            assert alert["category"].lower() == "sensors"

    def test_get_alerts_with_all_filter(self, client):
        """Test that the 'all' filter value returns every alert."""
        unfiltered = client.get("/api/inventory/alerts").json()
        filtered = client.get("/api/inventory/alerts?warehouse=all&category=all").json()
        assert filtered == unfiltered

    def test_get_alerts_no_matches(self, client):
        """Test that an unknown warehouse gives an empty list, not an error."""
        response = client.get("/api/inventory/alerts?warehouse=Nowhere")
        assert response.status_code == 200
        assert response.json() == []

    def test_alert_threshold_is_inclusive(self, client, use_inventory):
        """Test that an item exactly at its reorder point alerts and one above does not."""
        use_inventory(make_item("AT", 100, 100), make_item("ABOVE", 101, 100))

        data = client.get("/api/inventory/alerts").json()
        assert [a["sku"] for a in data] == ["AT"]
        assert data[0]["shortfall"] == 0
        assert data[0]["reorder_cost"] == 0

    def test_alert_severity_boundary(self, client, use_inventory):
        """Test that severity becomes critical at exactly half the reorder point."""
        use_inventory(
            make_item("HALF", 50, 100),
            make_item("OVER-HALF", 51, 100),
            make_item("ODD-BELOW", 49, 99),
            make_item("ODD-ABOVE", 50, 99),
        )

        severity = {a["sku"]: a["severity"]
                    for a in client.get("/api/inventory/alerts").json()}
        assert severity == {
            "HALF": "critical",
            "OVER-HALF": "warning",
            "ODD-BELOW": "critical",
            "ODD-ABOVE": "warning",
        }

    def test_alert_out_of_stock(self, client, use_inventory):
        """Test empty items, including one with a reorder point of zero."""
        use_inventory(make_item("EMPTY", 0, 40), make_item("NO-POINT", 0, 0))

        alerts = {a["sku"]: a for a in client.get("/api/inventory/alerts").json()}
        assert alerts["EMPTY"]["severity"] == "critical"
        assert alerts["EMPTY"]["shortfall"] == 40
        assert alerts["NO-POINT"]["severity"] == "critical"
        assert alerts["NO-POINT"]["shortfall"] == 0

    def test_alert_reorder_cost_calculation(self, client, use_inventory):
        """Test that reorder cost is an exact money amount, calculated in whole cents."""
        # 0.07 * 3 is 0.21000000000000002 with float multiplication
        use_inventory(make_item("COST", 7, 10, unit_cost=0.07))

        data = client.get("/api/inventory/alerts").json()
        assert data[0]["reorder_cost"] == 0.21

    def test_alerts_sorted_by_severity_then_shortfall(self, client, use_inventory):
        """Test critical items come first, then largest shortfall, with SKU breaking ties."""
        use_inventory(
            make_item("WARN-BIG", 600, 1000),      # warning, shortfall 400
            make_item("CRIT-SMALL", 5, 10),        # critical, shortfall 5
            make_item("CRIT-B", 10, 100),          # critical, shortfall 90
            make_item("CRIT-A", 10, 100),          # critical, shortfall 90
        )

        data = client.get("/api/inventory/alerts").json()
        assert [a["sku"] for a in data] == ["CRIT-A", "CRIT-B", "CRIT-SMALL", "WARN-BIG"]

    def test_alerts_do_not_mutate_inventory(self, client):
        """Test that alert fields are not written back onto the shared inventory records."""
        client.get("/api/inventory/alerts")

        for item in client.get("/api/inventory").json():
            assert "shortfall" not in item
        for record in main.inventory_items:
            assert "severity" not in record
