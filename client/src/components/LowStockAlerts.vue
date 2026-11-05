<template>
  <div ref="rootRef" class="low-stock-alerts">
    <button
      ref="buttonRef"
      type="button"
      class="alerts-button"
      :aria-label="buttonLabel"
      aria-haspopup="true"
      :aria-expanded="isOpen ? 'true' : 'false'"
      aria-controls="low-stock-alerts-panel"
      @click="toggle"
    >
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M10 2.5C7.239 2.5 5 4.739 5 7.5V10.5L3.5 13.5H16.5L15 10.5V7.5C15 4.739 12.761 2.5 10 2.5Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M8 16C8.4 16.9 9.1 17.5 10 17.5C10.9 17.5 11.6 16.9 12 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <span v-if="count > 0" class="alerts-badge" aria-hidden="true">{{ count }}</span>
    </button>

    <div
      v-if="isOpen"
      id="low-stock-alerts-panel"
      class="alerts-dropdown"
      role="region"
      :aria-label="t('alerts.heading', { count })"
    >
      <div class="alerts-header">{{ t('alerts.heading', { count }) }}</div>

      <div class="alerts-body">
        <div v-if="loading" class="alerts-state" role="status">{{ t('alerts.loading') }}</div>
        <div v-else-if="error" class="alerts-state alerts-error" role="alert">
          <span>{{ t('alerts.error') }}</span>
          <button type="button" class="retry-button" @click="loadAlerts">{{ t('alerts.retry') }}</button>
        </div>
        <div v-else-if="alerts.length === 0" class="alerts-state">{{ t('alerts.empty') }}</div>
        <ul v-else class="alerts-list">
          <li v-for="item in alerts" :key="item.id" class="alert-row">
            <div class="alert-top">
              <span class="alert-sku">{{ item.sku }}</span>
              <span class="severity-badge" :class="item.severity">
                {{ severityLabel(item.severity) }}
              </span>
            </div>
            <div class="alert-name">{{ translateProductName(item.name) }}</div>
            <div class="alert-warehouse">{{ translateWarehouse(item.warehouse) }}</div>
            <dl class="alert-metrics">
              <div>
                <dt>{{ t('alerts.onHand') }}</dt>
                <dd>{{ item.quantity_on_hand }} / {{ item.reorder_point }}</dd>
              </div>
              <div>
                <dt>{{ t('alerts.shortfall') }}</dt>
                <dd>{{ item.shortfall }}</dd>
              </div>
              <div>
                <dt>{{ t('alerts.reorderCost') }}</dt>
                <dd>{{ formatCost(item.reorder_cost) }}</dd>
              </div>
            </dl>
          </li>
        </ul>
      </div>

      <div class="alerts-footer">
        <router-link to="/inventory" class="view-inventory" @click="close">
          {{ t('alerts.viewInventory') }}
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrencyWithDecimals } from '../utils/currency'

const route = useRoute()
const { selectedLocation, selectedCategory } = useFilters()
const { t, currentCurrency, translateProductName, translateWarehouse } = useI18n()

const rootRef = ref(null)
const buttonRef = ref(null)
const isOpen = ref(false)
const alerts = ref([])
const loading = ref(false)
const error = ref(false)

const count = computed(() => alerts.value.length)

const buttonLabel = computed(() =>
  count.value > 0 ? t('alerts.buttonLabel', { count: count.value }) : t('alerts.buttonLabelNone')
)

const severityLabel = (severity) => t(`alerts.severity.${severity}`)

// Shown in the selected language's currency (JPY is converted and has no decimals)
const formatCost = (amount) => formatCurrencyWithDecimals(amount, currentCurrency.value, 2)

// Incremented per request so a slow, older response cannot overwrite newer data
let requestCounter = 0

const loadAlerts = async () => {
  const requestId = ++requestCounter
  loading.value = true
  error.value = false
  try {
    // Only warehouse/category: inventory has no month/status dimension
    const data = await api.getLowStockAlerts({
      warehouse: selectedLocation.value,
      category: selectedCategory.value
    })
    if (requestId !== requestCounter) return
    alerts.value = data
  } catch (err) {
    if (requestId !== requestCounter) return
    // Contained here so a failed load never breaks the header
    error.value = true
    alerts.value = []
    console.error('Failed to load low stock alerts:', err)
  } finally {
    if (requestId === requestCounter) loading.value = false
  }
}

const close = () => {
  isOpen.value = false
}

const toggle = () => {
  isOpen.value = !isOpen.value
}

const handleDocumentMouseDown = (event) => {
  if (isOpen.value && rootRef.value && !rootRef.value.contains(event.target)) {
    close()
  }
}

const handleKeydown = (event) => {
  if (event.key === 'Escape' && isOpen.value) {
    close()
    // Return focus to the trigger so keyboard users keep their place
    nextTick(() => buttonRef.value?.focus())
  }
}

watch([selectedLocation, selectedCategory], loadAlerts)
watch(() => route.fullPath, close)

onMounted(() => {
  loadAlerts()
  document.addEventListener('mousedown', handleDocumentMouseDown)
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleDocumentMouseDown)
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.low-stock-alerts {
  position: relative;
}

.alerts-button {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 0.625rem;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
  color: #64748b;
}

.alerts-button:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
}

.alerts-button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.alerts-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 18px;
  padding: 0.0625rem 0.3rem;
  background: #dc2626;
  color: white;
  font-size: 0.688rem;
  font-weight: 700;
  line-height: 1.25;
  text-align: center;
  border-radius: 9px;
}

.alerts-dropdown {
  position: absolute;
  top: calc(100% + 0.5rem);
  right: 0;
  width: 400px;
  display: flex;
  flex-direction: column;
  max-height: min(520px, calc(100vh - 100px));
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  overflow: hidden;
}

/* Narrow screens: pin to the viewport so the panel cannot run off-screen */
@media (max-width: 900px) {
  .alerts-dropdown {
    position: fixed;
    top: 76px;
    left: 0.75rem;
    right: 0.75rem;
    width: auto;
  }
}

.alerts-header {
  padding: 0.875rem 1rem;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-size: 0.938rem;
  font-weight: 600;
  color: #0f172a;
}

.alerts-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.alerts-state {
  padding: 1.5rem 1rem;
  text-align: center;
  color: #64748b;
  font-size: 0.875rem;
}

.alerts-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.625rem;
  color: #991b1b;
}

.retry-button {
  padding: 0.375rem 0.875rem;
  background: white;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #991b1b;
  font-family: inherit;
  font-size: 0.813rem;
  font-weight: 500;
  cursor: pointer;
}

.retry-button:hover {
  background: #fef2f2;
}

.alerts-list {
  list-style: none;
}

.alert-row {
  padding: 0.75rem 1rem;
  border-top: 1px solid #f1f5f9;
}

.alert-row:first-child {
  border-top: none;
}

.alert-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.125rem;
}

.alert-sku {
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.025em;
}

.alert-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
}

.alert-warehouse {
  font-size: 0.813rem;
  color: #64748b;
  margin-bottom: 0.5rem;
}

.alert-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
}

.alert-metrics dt {
  font-size: 0.688rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.alert-metrics dd {
  font-size: 0.875rem;
  font-weight: 600;
  color: #334155;
}

.severity-badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  border-radius: 6px;
  font-size: 0.688rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.severity-badge.critical {
  background: #fecaca;
  color: #991b1b;
}

.severity-badge.warning {
  background: #fef08a;
  color: #854d0e;
}

.alerts-footer {
  padding: 0.625rem 1rem;
  border-top: 1px solid #e2e8f0;
  background: #f8fafc;
  text-align: center;
}

.view-inventory {
  font-size: 0.875rem;
  font-weight: 500;
  color: #2563eb;
  text-decoration: none;
}

.view-inventory:hover {
  text-decoration: underline;
}
</style>
