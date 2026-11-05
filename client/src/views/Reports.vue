<template>
  <div class="reports">
    <div class="page-header">
      <h2>{{ t('reports.title') }}</h2>
      <p>{{ t('reports.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('reports.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="isEmpty" class="loading">{{ t('reports.noData') }}</div>
    <div v-else>
      <!-- Quarterly Performance -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.quarterlyPerformance') }}</h3>
        </div>
        <div class="table-container">
          <table class="reports-table">
            <thead>
              <tr>
                <th>{{ t('reports.table.quarter') }}</th>
                <th>{{ t('reports.table.totalOrders') }}</th>
                <th>{{ t('reports.table.totalRevenue') }}</th>
                <th>{{ t('reports.table.avgOrderValue') }}</th>
                <th>{{ t('reports.table.fulfillmentRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="q in quarterlyData" :key="q.quarter">
                <td><strong>{{ q.quarter }}</strong></td>
                <td>{{ q.total_orders }}</td>
                <td>{{ formatMoney(q.total_revenue) }}</td>
                <td>{{ formatMoney(q.avg_order_value) }}</td>
                <td>
                  <span :class="getFulfillmentClass(q.fulfillment_rate)">
                    {{ q.fulfillment_rate }}%
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Monthly Trends Chart -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.monthlyRevenueTrend') }}</h3>
        </div>
        <div class="chart-container">
          <div class="bar-chart">
            <div v-for="month in monthlyRows" :key="month.month" class="bar-wrapper">
              <div class="bar-container">
                <div
                  class="bar"
                  :style="{ height: month.barHeight + 'px' }"
                  :title="formatMoney(month.revenue)"
                ></div>
              </div>
              <div class="bar-label">{{ formatMonth(month.month) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Month-over-Month Comparison -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.monthOverMonth') }}</h3>
        </div>
        <div class="table-container">
          <table class="reports-table">
            <thead>
              <tr>
                <th>{{ t('reports.table.month') }}</th>
                <th>{{ t('reports.table.orders') }}</th>
                <th>{{ t('reports.table.revenue') }}</th>
                <th>{{ t('reports.table.change') }}</th>
                <th>{{ t('reports.table.growthRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="month in monthlyRows" :key="month.month">
                <td><strong>{{ formatMonth(month.month) }}</strong></td>
                <td>{{ month.order_count }}</td>
                <td>{{ formatMoney(month.revenue) }}</td>
                <td>
                  <span :class="getChangeClass(month.change)">{{ formatChange(month.change) }}</span>
                </td>
                <td>
                  <span :class="getChangeClass(month.change)">{{ formatGrowthRate(month) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Summary Stats -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.totalRevenue') }}</div>
          <div class="stat-value">{{ formatMoney(totalRevenue) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.avgMonthlyRevenue') }}</div>
          <div class="stat-value">{{ formatMoney(avgMonthlyRevenue) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.totalOrders') }}</div>
          <div class="stat-value">{{ totalOrders }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.bestQuarter') }}</div>
          <div class="stat-value">{{ bestQuarter }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

const MAX_BAR_HEIGHT = 200
const MONTH_KEYS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']

export default {
  name: 'Reports',
  setup() {
    const { t, currentLocale, currentCurrency } = useI18n()
    const {
      selectedPeriod,
      selectedLocation,
      selectedCategory,
      selectedStatus,
      getCurrentFilters
    } = useFilters()

    const loading = ref(true)
    const error = ref(null)
    const quarterlyData = ref([])
    const monthlyData = ref([])

    // Incremented per request. A slow earlier response must not overwrite the result
    // of a newer filter selection, so only the latest request id may apply its result.
    let requestCounter = 0

    const isEmpty = computed(() => quarterlyData.value.length === 0 && monthlyData.value.length === 0)

    const totalRevenue = computed(() => monthlyData.value.reduce((sum, month) => sum + month.revenue, 0))
    const totalOrders = computed(() => monthlyData.value.reduce((sum, month) => sum + month.order_count, 0))
    const avgMonthlyRevenue = computed(() =>
      monthlyData.value.length > 0 ? totalRevenue.value / monthlyData.value.length : 0
    )

    const bestQuarter = computed(() => {
      if (quarterlyData.value.length === 0) return '-'
      return quarterlyData.value.reduce((best, quarter) =>
        quarter.total_revenue > best.total_revenue ? quarter : best
      ).quarter
    })

    // Bar heights and month-over-month values are calculated once per data change,
    // rather than rescanning the list from the template for every row on every render
    const monthlyRows = computed(() => {
      const maxRevenue = Math.max(0, ...monthlyData.value.map(month => month.revenue))

      return monthlyData.value.map((month, index) => {
        const previous = index > 0 ? monthlyData.value[index - 1].revenue : null
        return {
          ...month,
          barHeight: maxRevenue > 0 ? (month.revenue / maxRevenue) * MAX_BAR_HEIGHT : 0,
          previousRevenue: previous,
          // The first row has nothing to compare against
          change: previous === null ? null : month.revenue - previous
        }
      })
    })

    const loadData = async () => {
      const requestId = ++requestCounter
      loading.value = true
      error.value = null

      try {
        const filters = getCurrentFilters()
        const [quarterly, monthly] = await Promise.all([
          api.getQuarterlyReports(filters),
          api.getMonthlyTrends(filters)
        ])
        if (requestId !== requestCounter) return // superseded by a newer request

        quarterlyData.value = quarterly
        monthlyData.value = monthly
      } catch (err) {
        if (requestId !== requestCounter) return
        error.value = t('reports.loadError')
        console.error('Failed to load reports:', err)
      } finally {
        // Only the latest request controls the loading state
        if (requestId === requestCounter) {
          loading.value = false
        }
      }
    }

    const formatMoney = (amount) => formatCurrency(amount, currentCurrency.value)

    const formatMonth = (monthStr) => {
      const [year, month] = monthStr.split('-')
      const key = MONTH_KEYS[parseInt(month, 10) - 1]
      if (!key) return monthStr

      const monthName = t(`months.${key}`)
      return currentLocale.value === 'ja' ? `${year}年${monthName}` : `${monthName} ${year}`
    }

    const getFulfillmentClass = (rate) => {
      if (rate >= 90) return 'badge success'
      if (rate >= 75) return 'badge warning'
      return 'badge danger'
    }

    const getChangeClass = (change) => {
      if (change > 0) return 'positive-change'
      if (change < 0) return 'negative-change'
      return ''
    }

    const formatChange = (change) => {
      if (change === null) return '-'
      const sign = change > 0 ? '+' : change < 0 ? '-' : ''
      return sign + formatMoney(Math.abs(change))
    }

    const formatGrowthRate = (month) => {
      if (month.change === null) return '-'
      if (month.previousRevenue === 0) return t('reports.notAvailable')

      const rate = (month.change / month.previousRevenue) * 100
      return (rate > 0 ? '+' : '') + rate.toFixed(1) + '%'
    }

    watch([selectedPeriod, selectedLocation, selectedCategory, selectedStatus], loadData)

    onMounted(loadData)

    return {
      t,
      loading,
      error,
      isEmpty,
      quarterlyData,
      monthlyRows,
      totalRevenue,
      avgMonthlyRevenue,
      totalOrders,
      bestQuarter,
      formatMoney,
      formatMonth,
      getFulfillmentClass,
      getChangeClass,
      formatChange,
      formatGrowthRate
    }
  }
}
</script>

<style scoped>
.reports {
  padding: 0;
}

.card {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.card-header {
  margin-bottom: 1.5rem;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
}

.reports-table {
  width: 100%;
  border-collapse: collapse;
}

.reports-table th {
  background: #f8fafc;
  padding: 0.75rem;
  text-align: left;
  font-weight: 600;
  color: #64748b;
  border-bottom: 2px solid #e2e8f0;
}

.reports-table td {
  padding: 0.75rem;
  border-bottom: 1px solid #e2e8f0;
}

.reports-table tr:hover {
  background: #f8fafc;
}

.chart-container {
  padding: 2rem 1rem;
  min-height: 300px;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  height: 250px;
  gap: 0.5rem;
}

.bar-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  max-width: 80px;
}

.bar-container {
  height: 200px;
  display: flex;
  align-items: flex-end;
  width: 100%;
}

.bar {
  width: 100%;
  background: linear-gradient(to top, #3b82f6, #60a5fa);
  border-radius: 4px 4px 0 0;
  transition: all 0.3s;
  cursor: pointer;
}

.bar:hover {
  background: linear-gradient(to top, #2563eb, #3b82f6);
}

.bar-label {
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: #64748b;
  text-align: center;
  transform: rotate(-45deg);
  white-space: nowrap;
  margin-top: 1.5rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
  margin-top: 1.5rem;
}

.stat-card {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #3b82f6;
}

.stat-label {
  font-size: 0.875rem;
  color: #64748b;
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 1.875rem;
  font-weight: 700;
  color: #0f172a;
}

.badge {
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 500;
}

.badge.success {
  background: #dcfce7;
  color: #166534;
}

.badge.warning {
  background: #fef3c7;
  color: #92400e;
}

.badge.danger {
  background: #fee2e2;
  color: #991b1b;
}

.positive-change {
  color: #16a34a;
  font-weight: 600;
}

.negative-change {
  color: #dc2626;
  font-weight: 600;
}

.loading {
  text-align: center;
  padding: 3rem;
  color: #64748b;
}

.error {
  background: #fee2e2;
  color: #991b1b;
  padding: 1rem;
  border-radius: 8px;
  margin: 1rem 0;
}
</style>
