from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel, Field
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class LowStockAlert(InventoryItem):
    shortfall: int
    reorder_cost: float
    severity: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: float
    lead_time_days: int

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

class RestockItem(BaseModel):
    sku: str
    name: str
    trend: str
    quantity: int
    unit_cost: float
    line_total: float
    lead_time_days: int

class RestockRecommendation(BaseModel):
    budget: float
    items: List[RestockItem]
    total_cost: float
    remaining_budget: float
    full_cost: float

# Upper limit on budgets: infinite or enormous floats would overflow when converted to cents
MAX_RESTOCK_BUDGET = 1_000_000_000

class CreateRestockOrderRequest(BaseModel):
    budget: float = Field(ge=0, le=MAX_RESTOCK_BUDGET, allow_inf_nan=False)

class RestockOrder(BaseModel):
    id: str
    order_number: str
    items: List[RestockItem]
    budget: float
    total_cost: float
    status: str
    order_date: str
    lead_time_days: int
    expected_delivery: str

# Submitted restocking orders. Held in memory only, so they reset on restart.
# Kept apart from customer orders so they don't affect revenue or dashboard totals.
restocking_orders = []

def to_cents(amount: float) -> int:
    """Convert a dollar amount to whole cents"""
    return round(amount * 100)

def ranked_restock_candidates() -> list:
    """Get forecast items worth restocking, most urgent first, with the units needed"""
    candidates = []
    for forecast in demand_forecasts:
        gap = forecast["forecasted_demand"] - forecast["current_demand"]
        # Decreasing items are never restocked, even if they show a positive gap
        if forecast["trend"].lower() == "decreasing" or gap <= 0:
            continue
        candidates.append({**forecast, "gap": gap})

    # Increasing items outrank every stable item, however large the stable gap is.
    # Python's sort is stable, so equal gaps keep their order in the forecast file,
    # which keeps the recommendation the same between requests.
    candidates.sort(key=lambda c: (c["trend"].lower() != "increasing", -c["gap"]))
    return candidates

def recommend_restock(budget: float) -> dict:
    """Recommend what to restock for a budget, filling it in priority order"""
    candidates = ranked_restock_candidates()

    # Work in whole cents: float division can lose a unit at an exact budget boundary
    remaining = to_cents(budget)
    items = []
    for candidate in candidates:
        unit_cents = to_cents(candidate["unit_cost"])
        quantity = min(candidate["gap"], remaining // unit_cents)
        # Keep going when an item doesn't fit: a cheaper, lower-ranked item may still fit
        if quantity <= 0:
            continue
        remaining -= quantity * unit_cents
        items.append({
            "sku": candidate["item_sku"],
            "name": candidate["item_name"],
            "trend": candidate["trend"],
            "quantity": quantity,
            "unit_cost": candidate["unit_cost"],
            "line_total": quantity * unit_cents / 100,
            "lead_time_days": candidate["lead_time_days"]
        })

    full_cost_cents = sum(c["gap"] * to_cents(c["unit_cost"]) for c in candidates)
    return {
        "budget": budget,
        "items": items,
        "total_cost": (to_cents(budget) - remaining) / 100,
        "remaining_budget": remaining / 100,
        "full_cost": full_cost_cents / 100
    }

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

# Declared before /api/inventory/{item_id}, which would otherwise capture "alerts" as an ID
@app.get("/api/inventory/alerts", response_model=List[LowStockAlert])
def get_low_stock_alerts(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get items at or below their reorder point, most severe first"""
    alerts = []
    for item in apply_filters(inventory_items, warehouse, category):
        # Same low-stock rule as the dashboard count, so the two numbers always agree
        if item["quantity_on_hand"] > item["reorder_point"]:
            continue
        shortfall = item["reorder_point"] - item["quantity_on_hand"]
        alerts.append({
            **item,
            "shortfall": shortfall,
            "reorder_cost": shortfall * to_cents(item["unit_cost"]) / 100,
            # Critical means at or below half the reorder point
            "severity": "critical" if item["quantity_on_hand"] * 2 <= item["reorder_point"] else "warning"
        })

    # Critical first, then largest shortfall. SKU breaks ties so the order is stable between requests.
    alerts.sort(key=lambda a: (a["severity"] != "critical", -a["shortfall"], a["sku"]))
    return alerts

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get quarterly performance reports with optional filtering"""
    # Calculate quarterly statistics from orders
    quarters = {}
    filtered_orders = filter_by_month(apply_filters(orders, warehouse, category, status), month)

    for order in filtered_orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get month-over-month trends with optional filtering"""
    months = {}
    filtered_orders = filter_by_month(apply_filters(orders, warehouse, category, status), month)

    for order in filtered_orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

@app.get("/api/restocking/recommendations", response_model=RestockRecommendation)
def get_restock_recommendations(budget: float = Query(ge=0, le=MAX_RESTOCK_BUDGET, allow_inf_nan=False)):
    """Get recommended items to restock for a budget"""
    return recommend_restock(budget)

@app.post("/api/restocking/orders", response_model=RestockOrder, status_code=201)
def create_restock_order(request: CreateRestockOrderRequest):
    """Submit a restocking order for a budget"""
    # Recalculate from the budget rather than accepting items from the client,
    # so prices and quantities can't be altered in the request
    recommendation = recommend_restock(request.budget)
    if not recommendation["items"]:
        raise HTTPException(status_code=400, detail="Budget is too low to restock any items")

    # The order isn't complete until its slowest item arrives
    lead_time_days = max(item["lead_time_days"] for item in recommendation["items"])
    order_date = datetime.now().replace(microsecond=0)
    number = len(restocking_orders) + 1
    order = {
        "id": str(number),
        "order_number": f"RST-{number:04d}",
        "items": recommendation["items"],
        "budget": request.budget,
        "total_cost": recommendation["total_cost"],
        "status": "Submitted",
        "order_date": order_date.isoformat(),
        "lead_time_days": lead_time_days,
        "expected_delivery": (order_date + timedelta(days=lead_time_days)).isoformat()
    }
    restocking_orders.append(order)
    return order

@app.get("/api/restocking/orders", response_model=List[RestockOrder])
def get_restock_orders():
    """Get submitted restocking orders, newest first"""
    return list(reversed(restocking_orders))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
