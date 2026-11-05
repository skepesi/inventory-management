<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <div class="budget-row">
        <label for="restock-budget" class="budget-label">{{ t('restocking.budgetLabel') }}</label>
        <span class="budget-value">{{ formatMoney(budget) }}</span>
      </div>
      <input
        id="restock-budget"
        type="range"
        class="budget-slider"
        min="0"
        :max="maxBudget"
        step="100"
        :value="budget"
        :disabled="submitting"
        :aria-valuetext="formatMoney(budget)"
        @input="onBudgetInput"
      />
      <div class="budget-scale">
        <span>{{ formatMoney(0) }}</span>
        <span>{{ formatMoney(maxBudget) }}</span>
      </div>
    </div>

    <div v-if="initialLoading" class="loading">{{ t('common.loading') }}</div>
    <div v-else>
      <div v-if="error" class="error" role="alert">{{ error }}</div>

      <div v-if="orderError" class="error" role="alert">{{ orderError }}</div>

      <div v-if="placedOrder" class="success-message" role="status">
        <span>{{ t('restocking.orderPlaced', { orderNumber: placedOrder.order_number }) }}</span>
        <router-link to="/orders" class="orders-link">{{ t('restocking.viewOrders') }}</router-link>
      </div>

      <template v-if="!error">
        <div class="stats-grid">
          <div class="stat-card info">
            <div class="stat-label">{{ t('restocking.totalCost') }}</div>
            <div class="stat-value">{{ formatMoney(totalCost, 2) }}</div>
          </div>
          <div class="stat-card success">
            <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
            <div class="stat-value">{{ formatMoney(remainingBudget, 2) }}</div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <h3 class="card-title">{{ t('restocking.recommendedItems') }}</h3>
            <div class="header-actions">
              <span v-if="busy" class="updating">{{ t('restocking.updating') }}</span>
              <button
                type="button"
                class="place-order-btn"
                :disabled="!canPlaceOrder"
                @click="placeOrder"
              >
                {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
              </button>
            </div>
          </div>

          <div v-if="items.length === 0" class="empty-state">{{ t('restocking.empty') }}</div>
          <div v-else class="table-container" :class="{ stale: busy }">
            <table>
              <thead>
                <tr>
                  <th>{{ t('restocking.table.sku') }}</th>
                  <th>{{ t('restocking.table.name') }}</th>
                  <th>{{ t('restocking.table.trend') }}</th>
                  <th class="num">{{ t('restocking.table.quantity') }}</th>
                  <th class="num">{{ t('restocking.table.unitCost') }}</th>
                  <th class="num">{{ t('restocking.table.lineTotal') }}</th>
                  <th class="num">{{ t('restocking.table.leadTime') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in items" :key="item.sku">
                  <td><strong>{{ item.sku }}</strong></td>
                  <td>{{ translateProductName(item.name) }}</td>
                  <td>
                    <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                  </td>
                  <td class="num">{{ item.quantity }}</td>
                  <td class="num">{{ formatMoney(item.unit_cost, 2) }}</td>
                  <td class="num"><strong>{{ formatMoney(item.line_total, 2) }}</strong></td>
                  <td class="num">{{ t('restocking.days', { days: item.lead_time_days }) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const DEBOUNCE_MS = 200
const STEP = 100
const DEFAULT_BUDGET = 5000
// Placeholder slider range until the first response supplies the real one
const INITIAL_MAX_BUDGET = 10000

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    // Budget and slider max are always in USD; only display is converted to yen
    const budget = ref(DEFAULT_BUDGET)
    const maxBudget = ref(INITIAL_MAX_BUDGET)

    const items = ref([])
    const totalCost = ref(0)
    const remainingBudget = ref(0)

    const initialLoading = ref(true)
    const error = ref(null)

    // True while a debounce timer is waiting to fire (the list is about to change)
    const pending = ref(false)
    // True while a recommendations request is in flight
    const fetching = ref(false)
    const submitting = ref(false)
    const orderError = ref(null)
    const placedOrder = ref(null)

    let debounceTimer = null
    // Incremented per request. A slow earlier response must not overwrite the result
    // of a newer slider position, so only the latest request id may apply its result.
    let requestCounter = 0

    const busy = computed(() => pending.value || fetching.value)

    // The button is also disabled during the debounce window (pending), otherwise a
    // user could submit a budget whose displayed list is about to be replaced.
    // It stays disabled after a successful order until the budget changes, because the
    // list doesn't change after ordering and a second click would silently duplicate it.
    const canPlaceOrder = computed(() =>
      !busy.value && !submitting.value && !error.value && !placedOrder.value && items.value.length > 0
    )

    const formatMoney = (amount, decimals = 0) => {
      return decimals > 0
        ? formatCurrencyWithDecimals(amount, currentCurrency.value, decimals)
        : formatCurrency(amount, currentCurrency.value)
    }

    const loadRecommendations = async () => {
      const requestId = ++requestCounter
      fetching.value = true
      try {
        const data = await api.getRestockRecommendations(budget.value)
        if (requestId !== requestCounter) return // superseded by a newer request
        items.value = data.items
        totalCost.value = data.total_cost
        remainingBudget.value = data.remaining_budget
        // Round UP to the next step: rounding down could make the largest budget
        // unreachable by the slider, so the full recommendation could never be bought.
        // Never below one step so the range stays usable.
        maxBudget.value = Math.max(STEP, Math.ceil(data.full_cost / STEP) * STEP)
        error.value = null
      } catch (err) {
        if (requestId !== requestCounter) return
        // Clear the list so a stale recommendation can't be ordered after a failure
        items.value = []
        totalCost.value = 0
        remainingBudget.value = 0
        error.value = t('restocking.loadError')
        console.error('Failed to load recommendations:', err)
      } finally {
        // Only the latest request controls the loading flags
        if (requestId === requestCounter) {
          fetching.value = false
          initialLoading.value = false
        }
      }
    }

    const onBudgetInput = (event) => {
      budget.value = Number(event.target.value)
      // A previous confirmation/error no longer describes what is on screen
      placedOrder.value = null
      orderError.value = null
      pending.value = true
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        pending.value = false
        loadRecommendations()
      }, DEBOUNCE_MS)
    }

    const placeOrder = async () => {
      if (!canPlaceOrder.value) return
      submitting.value = true
      orderError.value = null
      placedOrder.value = null
      try {
        // Only the budget is sent; the server recalculates the items itself
        placedOrder.value = await api.createRestockOrder(budget.value)
      } catch (err) {
        // Server error text is English only, so show the translated message and just log the detail
        orderError.value = t('restocking.orderError')
        console.error('Failed to place order:', err.response?.data?.detail || err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)

    onBeforeUnmount(() => {
      clearTimeout(debounceTimer)
      // Invalidate any in-flight request so it can't update an unmounted view
      requestCounter++
    })

    return {
      t,
      budget,
      maxBudget,
      items,
      totalCost,
      remainingBudget,
      initialLoading,
      error,
      busy,
      submitting,
      orderError,
      placedOrder,
      canPlaceOrder,
      formatMoney,
      onBudgetInput,
      placeOrder,
      translateProductName
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #475569;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #0f172a;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #64748b;
  margin-top: 0.25rem;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.updating {
  font-size: 0.813rem;
  color: #64748b;
}

.place-order-btn {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}

.place-order-btn:hover:not(:disabled) {
  background: #1e293b;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.num {
  text-align: right;
}

.stale {
  opacity: 0.6;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.success-message {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin: 1rem 0;
  font-size: 0.938rem;
}

.orders-link {
  color: #1e40af;
  font-weight: 600;
}
</style>
