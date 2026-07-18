import React from "react";
import AlertsTable from "./AlertsTable";
import DashboardMetrics from "./DashboardMetrics";
import DashboardVisuals from "./DashboardVisuals";
import { WorkspaceInitialState, WorkspaceRefreshState } from "./WorkspaceAsyncState";

function DashboardSection({
  metrics,
  topIPChartData,
  alertTimelineData,
  mapMarkers,
  alerts,
  alertsTableRef,
  canTakeAlertActions,
  onOpenResponseRegistry,
  onReviewIncident,
  searchTerm,
  setSearchTerm,
  sortOption,
  setSortOption,
  operationalScope,
  setOperationalScope,
  severityFilter,
  setSeverityFilter,
  sourceFilter,
  setSourceFilter,
  selectedAlertId,
  setSelectedAlertId,
  getSeverityBadgeStyle,
  onUpdateStatus,
  statusFilter,
  setStatusFilter,
  metricsGridStyle,
  metricCardStyle,
  metricLabelStyle,
  metricValueStyle,
  chartsGridStyle,
  tooltipStyle,
  tooltipLabelStyle,
  tooltipItemStyle,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  timelineRange,
  onTimelineRangeChange,
  timelineMeta,
  summaryPendingLabel,
  summaryBusy,
  filterWrapperStyle,
  filterLabelStyle,
  selectStyle,
  emptyStateStyle,
  emptyStateTextStyle,
  tableWrapperStyle,
  tableStyle,
  headerCellStyle,
  bodyCellStyle,
  monoCellStyle,
  tableRowStyle,
  expandedCellStyle,
  expandedContentStyle,
  expandedLabelStyle,
  expandedTextStyle,
  displaySettings,
  loading,
  error,
  refreshing,
  refreshError,
  onRetry,
  totalAlerts,
  pageOffset,
  pageLimit,
  pageEnd,
  canGoToPreviousPage,
  canGoToNextPage,
  onPreviousPage,
  onNextPage,
  onRefreshAlerts,
  alertsPendingLabel,
  alertsBusy,
  exactSourceIp,
  exactTargetIp,
  exactAlertId,
  canResetFilters,
  onResetFilters,
  onAskAi = null,
  aiEnabled = false,
}) {
  if (loading || error) {
    return (
      <WorkspaceInitialState
        loading={loading}
        error={error}
        loadingLabel="Loading dashboard alerts…"
        errorLabel={error}
        onRetry={onRetry}
      />
    );
  }

  return (
    <>
      <WorkspaceRefreshState refreshing={refreshing} refreshError={refreshError} />
      <DashboardMetrics
        metrics={metrics}
        metricsGridStyle={metricsGridStyle}
        metricCardStyle={metricCardStyle}
        metricLabelStyle={metricLabelStyle}
        metricValueStyle={metricValueStyle}
        onAskAi={onAskAi}
        aiEnabled={aiEnabled}
      />

      <DashboardVisuals
        metrics={metrics}
        topIPChartData={topIPChartData}
        alertTimelineData={alertTimelineData}
        mapMarkers={mapMarkers}
        chartsGridStyle={chartsGridStyle}
        tooltipStyle={tooltipStyle}
        tooltipLabelStyle={tooltipLabelStyle}
        tooltipItemStyle={tooltipItemStyle}
        cardStyle={cardStyle}
        cardHeaderStyle={cardHeaderStyle}
        cardTitleStyle={cardTitleStyle}
        cardSubtitleStyle={cardSubtitleStyle}
        timelineRange={timelineRange}
        onTimelineRangeChange={onTimelineRangeChange}
        timelineMeta={timelineMeta}
        summaryPendingLabel={summaryPendingLabel}
        summaryBusy={summaryBusy}
        displaySettings={displaySettings}
        onOpenResponseRegistry={onOpenResponseRegistry}
        onAskAi={onAskAi}
        aiEnabled={aiEnabled}
      />
      <div ref={alertsTableRef} data-navigation-target="recent-alerts" aria-label="Recent Alerts">
        <AlertsTable
          alerts={alerts}
          canTakeAlertActions={canTakeAlertActions}
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          sortOption={sortOption}
          setSortOption={setSortOption}
          operationalScope={operationalScope}
          setOperationalScope={setOperationalScope}
          severityFilter={severityFilter}
          setSeverityFilter={setSeverityFilter}
          sourceFilter={sourceFilter}
          setSourceFilter={setSourceFilter}
          selectedAlertId={selectedAlertId}
          setSelectedAlertId={setSelectedAlertId}
          getSeverityBadgeStyle={getSeverityBadgeStyle}
          cardStyle={cardStyle}
          cardHeaderStyle={cardHeaderStyle}
          cardTitleStyle={cardTitleStyle}
          cardSubtitleStyle={cardSubtitleStyle}
          exactSourceIp={exactSourceIp}
          exactTargetIp={exactTargetIp}
          exactAlertId={exactAlertId}
          canResetFilters={canResetFilters}
          onResetFilters={onResetFilters}
          alertsPendingLabel={alertsPendingLabel}
          alertsBusy={alertsBusy}
          filterWrapperStyle={filterWrapperStyle}
          filterLabelStyle={filterLabelStyle}
          selectStyle={selectStyle}
          emptyStateStyle={emptyStateStyle}
          emptyStateTextStyle={emptyStateTextStyle}
          tableWrapperStyle={tableWrapperStyle}
          tableStyle={tableStyle}
          headerCellStyle={headerCellStyle}
          bodyCellStyle={bodyCellStyle}
          monoCellStyle={monoCellStyle}
          tableRowStyle={tableRowStyle}
          expandedCellStyle={expandedCellStyle}
          expandedContentStyle={expandedContentStyle}
          expandedLabelStyle={expandedLabelStyle}
          expandedTextStyle={expandedTextStyle}
          displaySettings={displaySettings}
          onUpdateStatus={onUpdateStatus}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          onOpenResponseRegistry={onOpenResponseRegistry}
          onReviewIncident={onReviewIncident}
          totalAlerts={totalAlerts}
          pageOffset={pageOffset}
          pageLimit={pageLimit}
          pageEnd={pageEnd}
          canGoToPreviousPage={canGoToPreviousPage}
          canGoToNextPage={canGoToNextPage}
          onPreviousPage={onPreviousPage}
          onNextPage={onNextPage}
          onRefreshAlerts={onRefreshAlerts}
          onAskAi={onAskAi}
          aiEnabled={aiEnabled}
        />
      </div>
    </>
  );
}

export default DashboardSection;
