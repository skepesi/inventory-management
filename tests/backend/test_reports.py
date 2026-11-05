"""
Tests for report API endpoints.
"""
import pytest

import main

QUARTERLY_URL = "/api/reports/quarterly"
MONTHLY_URL = "/api/reports/monthly-trends"


def expected_orders(warehouse=None, category=None, status=None, month=None):
    """Get the orders a filter combination should count, using the shared helpers."""
    return main.filter_by_month(main.apply_filters(main.orders, warehouse, category, status), month)


class TestMonthlyTrendsFilters:
    """Test suite for filtering /api/reports/monthly-trends."""

    def test_no_filters_counts_all_orders(self, client):
        """Test that the unfiltered report covers every dated order."""
        response = client.get(MONTHLY_URL)

        assert response.status_code == 200
        dated_orders = [order for order in main.orders if order.get("order_date")]
        assert sum(row["order_count"] for row in response.json()) == len(dated_orders)

    @pytest.mark.parametrize("params", [
        {"warehouse": "San Francisco"},
        {"category": "sensors"},
        {"status": "delivered"},
        {"month": "2025-01"},
        {"month": "Q1-2025"},
        {"warehouse": "London", "category": "sensors", "status": "shipped", "month": "Q2-2025"},
    ])
    def test_filters_limit_counts_and_revenue(self, client, params):
        """Test that each filter combination only counts matching orders."""
        response = client.get(MONTHLY_URL, params=params)

        assert response.status_code == 200
        matching = expected_orders(**params)
        data = response.json()
        assert sum(row["order_count"] for row in data) == len(matching)
        assert sum(row["revenue"] for row in data) == pytest.approx(
            sum(order["total_value"] for order in matching)
        )

    def test_month_filter_returns_only_that_month(self, client):
        """Test that a month filter returns a single matching row."""
        data = client.get(MONTHLY_URL, params={"month": "2025-01"}).json()

        assert [row["month"] for row in data] == ["2025-01"]

    def test_all_values_are_not_filters(self, client):
        """Test that 'all' behaves the same as sending no filter."""
        params = {"warehouse": "all", "category": "all", "status": "all", "month": "all"}

        assert client.get(MONTHLY_URL, params=params).json() == client.get(MONTHLY_URL).json()

    def test_no_matches_returns_empty_list(self, client):
        """Test that a filter matching nothing returns an empty list."""
        response = client.get(MONTHLY_URL, params={"warehouse": "Nowhere"})

        assert response.status_code == 200
        assert response.json() == []


class TestQuarterlyReportFilters:
    """Test suite for filtering /api/reports/quarterly."""

    @pytest.mark.parametrize("params", [
        {"warehouse": "Tokyo"},
        {"category": "actuators"},
        {"status": "processing"},
        {"month": "2025-02"},
        {"month": "Q3-2025"},
    ])
    def test_filters_limit_counts_and_revenue(self, client, params):
        """Test that each filter only counts matching orders in 2025 quarters."""
        response = client.get(QUARTERLY_URL, params=params)

        assert response.status_code == 200
        matching = [
            order for order in expected_orders(**params)
            if order.get("order_date", "").startswith("2025-")
        ]
        data = response.json()
        assert sum(row["total_orders"] for row in data) == len(matching)
        assert sum(row["total_revenue"] for row in data) == pytest.approx(
            sum(order["total_value"] for order in matching)
        )

    def test_quarter_filter_returns_only_that_quarter(self, client):
        """Test that a quarter filter returns a single matching row."""
        data = client.get(QUARTERLY_URL, params={"month": "Q2-2025"}).json()

        assert [row["quarter"] for row in data] == ["Q2-2025"]

    def test_status_filter_sets_fulfillment_rate(self, client):
        """Test that the rate is recalculated from the filtered orders."""
        data = client.get(QUARTERLY_URL, params={"status": "delivered"}).json()

        assert data
        assert all(row["fulfillment_rate"] == 100.0 for row in data)

    def test_no_matches_returns_empty_list(self, client):
        """Test that a filter matching nothing returns an empty list."""
        response = client.get(QUARTERLY_URL, params={"category": "nothing"})

        assert response.status_code == 200
        assert response.json() == []
