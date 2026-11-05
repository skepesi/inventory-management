<template>
  <div class="inventory">
    <div class="page-header">
      <h2>{{ t('inventory.title') }}</h2>
      <p>{{ t('inventory.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">
            {{ t('inventory.stockLevels') }} ({{ filteredItems.length }} {{ t('inventory.skus') }})
          </h3>
          <div class="header-actions">
            <div class="search-box">
              <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path
                  fill-rule="evenodd"
                  d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z"
                  clip-rule="evenodd"
                />
              </svg>
              <input
                v-model="searchQuery"
                type="text"
                :placeholder="t('inventory.searchPlaceholder')"
                class="search-input"
              />
              <button
                v-if="searchQuery"
                @click="searchQuery = ''"
                class="clear-search"
                :title="t('inventory.clearSearch')"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fill-rule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clip-rule="evenodd"
                  />
                </svg>
              </button>
            </div>
            <button type="button" class="export-btn" :disabled="filteredItems.length === 0" @click="exportCsv">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path
                  fill-rule="evenodd"
                  d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                  clip-rule="evenodd"
                />
              </svg>
              {{ t('inventory.exportCsv') }}
            </button>
          </div>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('inventory.table.sku') }}</th>
                <th>{{ t('inventory.table.itemName') }}</th>
                <th>{{ t('inventory.table.category') }}</th>
                <th>{{ t('inventory.table.quantityOnHand') }}</th>
                <th>{{ t('inventory.table.reorderPoint') }}</th>
                <th>{{ t('inventory.table.unitCost') }}</th>
                <th>{{ t('inventory.table.totalValue') }}</th>
                <th>{{ t('inventory.table.location') }}</th>
                <th>{{ t('inventory.table.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredItems" :key="item.id" class="clickable-row" @click="showItemDetail(item)">
                <td>
                  <strong>{{ item.sku }}</strong>
                </td>
                <td>{{ translateProductName(item.name) }}</td>
                <td>{{ translateCategory(item.category) }}</td>
                <td>
                  <strong>{{ item.quantity_on_hand }}</strong>
                </td>
                <td>{{ item.reorder_point }}</td>
                <td>{{ currencySymbol }}{{ item.unit_cost.toFixed(2) }}</td>
                <td>
                  <strong
                    >{{ currencySymbol
                    }}{{
                      (item.quantity_on_hand * item.unit_cost).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                      })
                    }}</strong
                  >
                </td>
                <td>{{ translateWarehouse(item.location) }}</td>
                <td>
                  <span :class="['badge', getStockStatusClass(item)]">
                    {{ getStockStatus(item) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <InventoryDetailModal :is-open="showItemModal" :inventory-item="selectedItem" @close="showItemModal = false" />
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import InventoryDetailModal from '../components/InventoryDetailModal.vue'

export default {
  name: 'Inventory',
  components: {
    InventoryDetailModal
  },
  setup() {
    const { t, currentCurrency, translateProductName, translateWarehouse } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const loading = ref(true)
    const error = ref(null)
    const items = ref([])
    const searchQuery = ref('')

    // Modal state
    const showItemModal = ref(false)
    const selectedItem = ref(null)

    // Use shared filters
    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    // Stock status order for sorting (using status keys)
    const STATUS_ORDER = { lowStock: 0, adequate: 1, inStock: 2 }

    // Get stock status key (for sorting and translation)
    const getStockStatusKey = (item) => {
      if (item.quantity_on_hand <= item.reorder_point) {
        return 'lowStock'
      } else if (item.quantity_on_hand <= item.reorder_point * 1.5) {
        return 'adequate'
      } else {
        return 'inStock'
      }
    }

    // Computed property to filter items by search query and sort by stock status
    const filteredItems = computed(() => {
      let filtered = items.value

      // Apply search filter if query exists
      if (searchQuery.value.trim()) {
        const query = searchQuery.value.toLowerCase().trim()
        filtered = filtered.filter((item) => item.name.toLowerCase().includes(query))
      }

      // Sort by stock status: Low Stock first, then Adequate, then In Stock
      // Always create a copy to avoid mutating the original array
      return filtered.slice().sort((a, b) => {
        const statusA = getStockStatusKey(a)
        const statusB = getStockStatusKey(b)
        return STATUS_ORDER[statusA] - STATUS_ORDER[statusB]
      })
    })

    const loadInventory = async () => {
      try {
        loading.value = true
        const filters = getCurrentFilters()
        // Inventory doesn't support month/status filters, only warehouse and category
        items.value = await api.getInventory({
          warehouse: filters.warehouse,
          category: filters.category
        })
      } catch (err) {
        error.value = 'Failed to load inventory: ' + err.message
      } finally {
        loading.value = false
      }
    }

    // Watch for filter changes and reload data
    watch([selectedLocation, selectedCategory], () => {
      loadInventory()
    })

    const getStockStatus = (item) => {
      const key = getStockStatusKey(item)
      return t(`status.${key}`)
    }

    const getStockStatusClass = (item) => {
      if (item.quantity_on_hand <= item.reorder_point) {
        return 'danger'
      } else if (item.quantity_on_hand <= item.reorder_point * 1.5) {
        return 'warning'
      } else {
        return 'success'
      }
    }

    const translateCategory = (category) => {
      const categoryMap = {
        'Circuit Boards': t('categories.circuitBoards'),
        Sensors: t('categories.sensors'),
        Actuators: t('categories.actuators'),
        Controllers: t('categories.controllers'),
        'Power Supplies': t('categories.powerSupplies')
      }
      return categoryMap[category] || category
    }

    const showItemDetail = (item) => {
      selectedItem.value = item
      showItemModal.value = true
    }

    // Escape a text field for CSV (RFC 4180) and neutralise spreadsheet formulas.
    const csvText = (value) => {
      let s = String(value ?? '')
      // Formula injection: Excel/Sheets treat cells starting with these characters
      // as formulas, so prefix a single quote to force them to be read as text.
      if (/^[=+\-@\t\r]/.test(s)) s = "'" + s
      // Quote fields containing comma, quote, CR or LF; double embedded quotes.
      return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }

    const exportCsv = () => {
      if (filteredItems.value.length === 0) return
      const headers = [
        'sku',
        'itemName',
        'category',
        'quantityOnHand',
        'reorderPoint',
        'unitCost',
        'totalValue',
        'location',
        'status'
      ].map((key) => csvText(t(`inventory.table.${key}`)))

      // Same rows/order as the table (filteredItems). Numeric columns are written raw
      // (no currency symbol or thousands separators) and are not run through csvText,
      // so legitimate negative numbers are not prefixed with a quote.
      const rows = filteredItems.value.map((item) =>
        [
          csvText(item.sku),
          csvText(translateProductName(item.name)),
          csvText(translateCategory(item.category)),
          item.quantity_on_hand,
          item.reorder_point,
          item.unit_cost.toFixed(2),
          (item.quantity_on_hand * item.unit_cost).toFixed(2),
          csvText(translateWarehouse(item.location)),
          csvText(getStockStatus(item))
        ].join(',')
      )

      // UTF-8 BOM so Excel detects the encoding; without it Japanese text is garbled.
      const csv = String.fromCharCode(0xfeff) + [headers.join(','), ...rows].join('\r\n') + '\r\n'

      // Local date (toISOString would give the UTC date).
      const d = new Date()
      const pad = (n) => String(n).padStart(2, '0')
      const filename = `inventory-${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}.csv`

      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }

    onMounted(loadInventory)

    return {
      t,
      loading,
      error,
      items,
      searchQuery,
      filteredItems,
      getStockStatus,
      getStockStatusClass,
      translateCategory,
      showItemModal,
      selectedItem,
      showItemDetail,
      exportCsv,
      currencySymbol,
      translateProductName,
      translateWarehouse
    }
  }
}
</script>

<style scoped>
.page-header {
  margin-bottom: 1.5rem;
}

.page-header h2 {
  margin-bottom: 0.25rem;
}

.page-header p {
  color: #64748b;
  font-size: 0.875rem;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.export-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.875rem;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.875rem;
  color: #0f172a;
  background: white;
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.2s;
}

.export-btn svg {
  width: 16px;
  height: 16px;
  color: #64748b;
}

.export-btn:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #94a3b8;
}

.export-btn:focus-visible {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.export-btn:disabled {
  color: #94a3b8;
  background: #f1f5f9;
  border-color: #e2e8f0;
  cursor: not-allowed;
}

.export-btn:disabled svg {
  color: #cbd5e1;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  min-width: 300px;
}

.search-icon {
  position: absolute;
  left: 0.75rem;
  width: 18px;
  height: 18px;
  color: #94a3b8;
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 0.5rem 2.5rem 0.5rem 2.5rem;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.875rem;
  color: #0f172a;
  background: #f8fafc;
  transition: all 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: #3b82f6;
  background: white;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.search-input::placeholder {
  color: #94a3b8;
}

.clear-search {
  position: absolute;
  right: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.25rem;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-search:hover {
  background: #e2e8f0;
  color: #64748b;
}

.clear-search svg {
  width: 18px;
  height: 18px;
}

.loading,
.error {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.error {
  color: #ef4444;
}

.clickable-row {
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.clickable-row:hover {
  background: #eff6ff !important;
}
</style>
