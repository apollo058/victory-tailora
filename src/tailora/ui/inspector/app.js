/**
 * Tailora Inspector Frontend Application
 * - 순수 Vanilla JavaScript (외부 프레임워크 의존성 없음)
 * - State Machine: idle -> loading -> ready | empty | error | disabled
 * - API Client, DOM Renderer, 키보드 인터랙션 컨트롤러
 */

(function () {
  'use strict';

  // 1. Base URL 추출 (index.html 메타 태그로부터 획득)
  const metaTag = document.querySelector('meta[name="tailora-base-path"]');
  const BASE_PATH = metaTag ? metaTag.getAttribute('content') || '' : '';

  // 2. DOM 요소 참조 캐싱
  const elements = {
    serverStatusPill: document.getElementById('server-status-pill'),
    statusLabel: document.getElementById('status-label'),
    lastRefreshedTime: document.getElementById('last-refreshed-time'),
    btnRefresh: document.getElementById('btn-refresh'),
    requestCountBadge: document.getElementById('request-count-badge'),
    listContainer: document.getElementById('list-container'),
    aggregateContainer: document.getElementById('aggregate-container'),
    detailContainer: document.getElementById('detail-container'),
    detailActions: document.getElementById('detail-actions'),
  };

  // 3. 애플리케이션 상태 모델
  const state = {
    status: 'idle', // 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'disabled'
    requests: [],
    selectedRequestId: null,
    selectedRequestDetail: null,
    detailLoading: false,
    errorMessage: null,
    token: 0, // 레이스 컨디션 방지 토큰
  };

  // 4. API 클라이언트
  const api = {
    async checkHealth() {
      const resp = await fetch(`${BASE_PATH}/health`, { cache: 'no-store' });
      if (!resp.ok) {
        throw new Error(`Health check failed: ${resp.status}`);
      }
      return await resp.json();
    },

    async fetchRequests() {
      const resp = await fetch(`${BASE_PATH}/requests`, { cache: 'no-store' });
      if (!resp.ok) {
        throw new Error(`Failed to fetch requests: ${resp.status}`);
      }
      return await resp.json();
    },

    async fetchAggregates() {
      const resp = await fetch(`${BASE_PATH}/aggregates`, { cache: 'no-store' });
      if (!resp.ok) {
        throw new Error(`Failed to fetch aggregates: ${resp.status}`);
      }
      return await resp.json();
    },

    async fetchRequestDetail(requestId) {
      const resp = await fetch(`${BASE_PATH}/requests/${encodeURIComponent(requestId)}`, { cache: 'no-store' });
      if (resp.status === 404) {
        return null;
      }
      if (!resp.ok) {
        throw new Error(`Failed to fetch request detail: ${resp.status}`);
      }
      return await resp.json();
    },
  };

  // 5. 뷰 렌더러
  const renderer = {
    updateStatusPill(status, text) {
      if (!elements.serverStatusPill) return;
      let className = 'server-status';
      if (status === 'ok') {
        className += ' status-ok';
      } else if (status === 'disabled') {
        className += ' status-disabled';
      } else {
        className += ' status-err';
      }
      elements.serverStatusPill.className = className;
      if (elements.statusLabel) {
        elements.statusLabel.textContent = text;
      }
    },

    updateLastRefreshed() {
      if (!elements.lastRefreshedTime) return;
      const now = new Date();
      const timeStr = now.toTimeString().split(' ')[0];
      elements.lastRefreshedTime.textContent = timeStr;
    },

    renderListLoading() {
      elements.listContainer.innerHTML = `
        <div class="state-container state-loading">
          <div class="spinner" aria-hidden="true"></div>
          <p class="state-text">최근 요청을 조회하고 있습니다...</p>
        </div>
      `;
    },

    renderListEmpty() {
      elements.requestCountBadge.textContent = '0';
      elements.listContainer.innerHTML = `
        <div class="state-container state-empty">
          <div class="placeholder-icon" aria-hidden="true">📭</div>
          <h3 class="placeholder-title">기록된 요청이 없습니다</h3>
          <p class="placeholder-desc">애플리케이션에 API 요청을 보내면 여기에 실시간으로 기록됩니다.</p>
        </div>
      `;
    },

    renderListDisabled(msg) {
      elements.requestCountBadge.textContent = '-';
      elements.listContainer.innerHTML = `
        <div class="state-container state-disabled">
          <div class="placeholder-icon" aria-hidden="true">⏸️</div>
          <h3 class="placeholder-title">Inspector 비활성화 상태</h3>
          <p class="placeholder-desc">${escapeHtml(msg || '현재 애플리케이션의 Tailora Inspector 수집기가 비활성화되어 있습니다.')}</p>
          <button type="button" class="btn btn-primary error-action-btn" id="btn-retry-disabled">상태 다시 확인</button>
        </div>
      `;
      const btnRetry = document.getElementById('btn-retry-disabled');
      if (btnRetry) {
        btnRetry.addEventListener('click', () => controller.loadData());
      }
    },

    renderListError(msg) {
      elements.listContainer.innerHTML = `
        <div class="state-container state-error">
          <div class="placeholder-icon" aria-hidden="true">⚠️</div>
          <h3 class="placeholder-title">요청 목록을 불러올 수 없습니다</h3>
          <p class="placeholder-desc">${escapeHtml(msg || '네트워크 또는 서버 응답을 확인하세요.')}</p>
          <button type="button" class="btn btn-primary error-action-btn" id="btn-retry-list">다시 시도</button>
        </div>
      `;
      const btnRetry = document.getElementById('btn-retry-list');
      if (btnRetry) {
        btnRetry.addEventListener('click', () => controller.loadData());
      }
    },

    renderAggregateLoading() {
      if (!elements.aggregateContainer) return;
      elements.aggregateContainer.innerHTML = `
        <div class="state-container state-loading">
          <div class="spinner" aria-hidden="true"></div>
          <p class="state-text">집계 정보를 불러오고 있습니다...</p>
        </div>
      `;
    },

    renderAggregateError(msg) {
      if (!elements.aggregateContainer) return;
      elements.aggregateContainer.innerHTML = `
        <div class="state-container state-error">
          <p class="placeholder-desc">${escapeHtml(msg || '집계 정보를 불러올 수 없습니다.')}</p>
        </div>
      `;
    },

    renderAggregates(data) {
      if (!elements.aggregateContainer) return;
      const routes = Array.isArray(data && data.routes) ? data.routes : [];
      const fingerprints = Array.isArray(data && data.fingerprints)
        ? data.fingerprints
        : [];
      const scope = data && data.analysis_scope ? data.analysis_scope : {};

      if (routes.length === 0 && fingerprints.length === 0) {
        elements.aggregateContainer.innerHTML = `
          <div class="state-container state-empty">
            <p class="state-text">집계할 요청과 쿼리가 아직 없습니다.</p>
          </div>
        `;
        return;
      }

      elements.aggregateContainer.innerHTML = `
        <div class="aggregate-grid">
          ${renderAggregateTable(
            `Endpoint · ${formatInteger(scope.request_count)} requests`,
            'Endpoint 집계',
            ['Route', 'Count', 'Avg', 'SQL'],
            renderRouteRows(routes),
          )}
          ${renderAggregateTable(
            'SQL Fingerprint',
            'SQL fingerprint 집계',
            ['Fingerprint', 'Count', 'Requests', 'Avg'],
            renderFingerprintRows(fingerprints),
          )}
        </div>
      `;
    },

    renderList(items, selectedId) {
      elements.requestCountBadge.textContent = String(items.length);
      const ul = document.createElement('ul');
      ul.className = 'request-list';
      ul.setAttribute('role', 'listbox');
      ul.setAttribute('aria-label', '최근 요청 목록');
      items.forEach((item, index) => {
        ul.appendChild(createRequestListItem(item, index, selectedId));
      });

      elements.listContainer.innerHTML = '';
      elements.listContainer.appendChild(ul);
    },

    renderDetailPlaceholder(msg, title = '선택된 요청이 없습니다') {
      elements.detailActions.innerHTML = '';
      elements.detailContainer.innerHTML = `
        <div class="state-container state-unselected">
          <div class="placeholder-icon" aria-hidden="true">🔍</div>
          <h3 class="placeholder-title">${escapeHtml(title)}</h3>
          <p class="placeholder-desc">${escapeHtml(msg || '좌측 목록에서 요청을 클릭하거나 선택하여 세부 진단 결과와 쿼리를 확인하세요.')}</p>
        </div>
      `;
    },

    renderDetailLoading() {
      elements.detailContainer.innerHTML = `
        <div class="state-container state-loading">
          <div class="spinner" aria-hidden="true"></div>
          <p class="state-text">상세 진단 정보를 불러오고 있습니다...</p>
        </div>
      `;
    },

    renderDetail(detail) {
      if (!detail) {
        renderer.renderDetailPlaceholder('요청 데이터를 찾을 수 없거나 만료되었습니다.', '요청을 찾을 수 없음');
        return;
      }
      const sig = detail.signals || {};
      const appliedThresh = sig.applied_thresholds || {};
      const queries = detail.queries || [];
      renderDetailActions(detail.request_id);

      elements.detailContainer.innerHTML = `
        <div class="detail-content">
          ${renderDetailOverview(detail)}
          ${renderDetailError(detail.error)}
          ${renderSignalSection(detail, sig, appliedThresh, queries)}
          ${renderQueryTable(queries, sig)}
        </div>
      `;
    },
  };

  function renderRequestSignals(signals) {
    const pills = [];
    if (!signals) return '';
    if (signals.slow_request) {
      pills.push('<span class="signal-pill signal-slow" title="느린 요청 (임계값 초과)">SLOW</span>');
    }
    if (signals.has_duplicate_query) {
      pills.push('<span class="signal-pill signal-dup" title="중복 쿼리 (N+1 의심)">N+1 DUP</span>');
    }
    if (signals.has_slow_query) {
      pills.push('<span class="signal-pill signal-slow" title="느린 쿼리 포함">SLOW Q</span>');
    }
    if (signals.query_heavy) {
      pills.push('<span class="signal-pill signal-heavy" title="쿼리 실행 과다">HEAVY</span>');
    }
    return pills.join('');
  }

  function createRequestListItem(item, index, selectedId) {
    const isSelected = item.request_id === selectedId;
    const itemElement = document.createElement('li');
    const statusCategory = `${Math.floor(item.status_code / 100)}xx`;
    const methodUpper = (item.method || 'GET').toUpperCase();
    itemElement.className = `request-item ${isSelected ? 'selected' : ''}`;
    itemElement.setAttribute('role', 'option');
    itemElement.setAttribute('aria-selected', isSelected ? 'true' : 'false');
    itemElement.setAttribute('tabindex', '0');
    itemElement.dataset.requestId = item.request_id;
    itemElement.dataset.index = String(index);
    itemElement.innerHTML = `
      <div class="request-item-top">
        <div class="method-route">
          <span class="method-tag method-${methodUpper}">${methodUpper}</span>
          <span class="route-text" title="${escapeHtml(item.route_template)}">${escapeHtml(item.route_template)}</span>
        </div>
        <div class="status-duration">
          <span class="status-badge status-${statusCategory}">${item.status_code}</span>
          <span class="duration-text">${item.duration_ms.toFixed(1)}ms</span>
        </div>
      </div>
      <div class="request-item-bottom">
        <div class="query-summary">
          <span>SQL: ${item.query_count}건</span>
          <span>시간: ${item.query_time_ms.toFixed(1)}ms</span>
        </div>
        <div class="signals-container">${renderRequestSignals(item.signals)}</div>
      </div>
    `;
    bindRequestItemEvents(itemElement, item.request_id);
    return itemElement;
  }

  function bindRequestItemEvents(itemElement, requestId) {
    itemElement.addEventListener('click', () => controller.selectRequest(requestId));
    itemElement.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        controller.selectRequest(requestId);
        return;
      }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      const nextItem = event.key === 'ArrowDown'
        ? itemElement.nextElementSibling
        : itemElement.previousElementSibling;
      if (!nextItem) return;
      nextItem.focus();
      if (nextItem.dataset.requestId) {
        controller.selectRequest(nextItem.dataset.requestId);
      }
    });
  }

  function renderDetailActions(requestId) {
    elements.detailActions.innerHTML = `
      <button type="button" class="btn" id="btn-copy-id" title="요청 ID 복사">
        <span>ID 복사</span>
      </button>
    `;
    const copyButton = document.getElementById('btn-copy-id');
    if (!copyButton) return;
    copyButton.addEventListener('click', () => {
      navigator.clipboard.writeText(requestId);
      copyButton.innerHTML = '<span>복사됨!</span>';
      setTimeout(() => {
        copyButton.innerHTML = '<span>ID 복사</span>';
      }, 1500);
    });
  }

  function renderDetailError(error) {
    if (!error) return '';
    return `
      <div class="error-box">
        <div class="error-title">🚨 ${escapeHtml(error.type || 'Error')}</div>
        <div class="error-msg">${escapeHtml(error.message || '오류 상세 정보 없음')}</div>
      </div>
    `;
  }

  function formatRequestTime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return timestamp;
    return date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3,
    });
  }

  function renderDetailOverview(detail) {
    return `
      <div class="overview-card">
        <div class="overview-metric">
          <span class="metric-label">Route</span>
          <span class="metric-val" style="font-size:13px;">${escapeHtml(detail.method)} ${escapeHtml(detail.route_template)}</span>
        </div>
        <div class="overview-metric">
          <span class="metric-label">Framework</span>
          <span class="metric-val">${escapeHtml(detail.framework || 'FastAPI')}</span>
        </div>
        <div class="overview-metric">
          <span class="metric-label">Timestamp</span>
          <span class="metric-val" style="font-size:12px;">${escapeHtml(formatRequestTime(detail.timestamp))}</span>
        </div>
        <div class="overview-metric">
          <span class="metric-label">Status</span>
          <span class="metric-val">${detail.status_code}</span>
        </div>
        <div class="overview-metric">
          <span class="metric-label">Duration</span>
          <span class="metric-val">${detail.duration_ms.toFixed(1)}ms</span>
        </div>
        <div class="overview-metric">
          <span class="metric-label">SQL Count</span>
          <span class="metric-val">${detail.query_count}건</span>
        </div>
        <div class="overview-metric">
          <span class="metric-label">SQL Time</span>
          <span class="metric-val">${detail.query_time_ms.toFixed(1)}ms</span>
        </div>
      </div>
    `;
  }

  function renderSlowRequestCard(detail, thresholds, signals) {
    if (!signals.slow_request) return '';
    return `
      <div class="signal-card card-slow">
        <div class="signal-card-header">
          <strong class="signal-card-title">⚠️ 느린 요청 (Slow Request)</strong>
          <span class="signal-pill signal-slow">기준 초과</span>
        </div>
        <p class="signal-card-desc">
          소요 시간 <strong>${detail.duration_ms.toFixed(1)}ms</strong>가 설정된 임계값 <strong>${thresholds.slow_request_ms}ms</strong>를 초과했습니다.
        </p>
      </div>
    `;
  }

  function renderSlowQueryCard(signals, thresholds, queries) {
    if (!signals.slow_queries || signals.slow_queries.length === 0) return '';
    const items = signals.slow_queries.map((sequence) => {
      const query = queries.find((item) => item.sequence === sequence);
      const duration = query ? `${query.duration_ms.toFixed(1)}ms` : '기준 초과';
      return `<li>Query #${sequence}: <strong>${duration}</strong></li>`;
    }).join('');
    return `
      <div class="signal-card card-slow-query">
        <div class="signal-card-header">
          <strong class="signal-card-title">🐢 느린 쿼리 (Slow Queries)</strong>
          <span class="signal-pill signal-slow">${signals.slow_queries.length}건 감지</span>
        </div>
        <p class="signal-card-desc">
          임계값(<strong>${thresholds.slow_query_ms}ms</strong>) 이상 실행된 개별 SQL입니다:
        </p>
        <ul style="margin: 6px 0 0 16px; font-size: 11px; color: #475569;">${items}</ul>
      </div>
    `;
  }

  function renderDuplicateQueryCard(signals) {
    if (!signals.duplicate_queries || signals.duplicate_queries.length === 0) return '';
    const items = signals.duplicate_queries.map((duplicate) => `
      <li>중복 횟수: <strong>${duplicate.count}회</strong> (SQL Sequences: ${duplicate.sequences.join(', ')})<br>
        <span style="color:#64748b; font-family:var(--font-mono); font-size:10px;">${escapeHtml(duplicate.fingerprint || '')}</span>
      </li>
    `).join('');
    return `
      <div class="signal-card card-dup">
        <div class="signal-card-header">
          <strong class="signal-card-title">🔄 N+1 / 중복 쿼리 (Duplicate Queries)</strong>
          <span class="signal-pill signal-dup">${signals.duplicate_queries.length}개 패턴</span>
        </div>
        <p class="signal-card-desc">동일한 패턴의 SQL이 1개 요청 내에서 반복 실행되었습니다.</p>
        <ul style="margin: 6px 0 0 16px; font-size: 11px; color: #475569;">${items}</ul>
      </div>
    `;
  }

  function renderQueryHeavyCard(detail, signals) {
    if (!signals.query_heavy) return '';
    const reasons = (signals.query_heavy_reasons || []).join(', ');
    return `
      <div class="signal-card card-heavy">
        <div class="signal-card-header">
          <strong class="signal-card-title">⚡ 쿼리 과다 실행 (Query Heavy)</strong>
          <span class="signal-pill signal-heavy">${escapeHtml(reasons)}</span>
        </div>
        <p class="signal-card-desc">
          실행된 쿼리 수(<strong>${detail.query_count}건</strong>) 또는 총 실행 시간(<strong>${detail.query_time_ms.toFixed(1)}ms</strong>)이 임계값을 초과했습니다.
        </p>
      </div>
    `;
  }

  function renderSignalSection(detail, signals, thresholds, queries) {
    const cards = [
      renderSlowRequestCard(detail, thresholds, signals),
      renderSlowQueryCard(signals, thresholds, queries),
      renderDuplicateQueryCard(signals),
      renderQueryHeavyCard(detail, signals),
    ].join('');
    if (!cards) return '';
    return `
      <div class="signals-section">
        <h3 class="section-title">진단 분석 신호 (Signals)</h3>
        <div class="signal-cards-grid">${cards}</div>
      </div>
    `;
  }

  function renderQueryRow(query, slowSequences, duplicateSequences) {
    const badges = [];
    if (slowSequences.has(query.sequence)) {
      badges.push('<span class="signal-pill signal-slow" style="margin-right:4px;">SLOW</span>');
    }
    if (duplicateSequences.has(query.sequence)) {
      badges.push('<span class="signal-pill signal-dup">DUP</span>');
    }
    const fingerprint = query.fingerprint
      ? `<div class="query-fingerprint" title="SQL Fingerprint">${escapeHtml(query.fingerprint)}</div>`
      : '';
    return `
      <tr>
        <td class="query-seq">#${query.sequence}</td>
        <td class="query-time">${query.duration_ms.toFixed(1)}ms</td>
        <td class="query-db">${escapeHtml(query.database || 'db')}</td>
        <td><div class="query-sql">${escapeHtml(query.statement)}</div>${fingerprint}</td>
        <td>${badges.join('') || '<span style="color:#cbd5e1;">-</span>'}</td>
      </tr>
    `;
  }

  function renderQueryTable(queries, signals) {
    const slowSequences = new Set(signals.slow_queries || []);
    const duplicateSequences = new Set(
      (signals.duplicate_queries || []).flatMap((item) => item.sequences || []),
    );
    const rows = queries.length
      ? queries.map((query) => renderQueryRow(
        query,
        slowSequences,
        duplicateSequences,
      )).join('')
      : '<tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:24px;">이 요청에서 실행된 데이터베이스 쿼리가 없습니다.</td></tr>';
    return `
      <div class="query-section">
        <h3 class="section-title" style="margin-bottom: 10px;">실행된 SQL 쿼리 (${queries.length}건)</h3>
        <div class="query-table-container">
          <table class="query-table" aria-label="실행된 SQL 쿼리 목록">
            <thead><tr><th>#</th><th>시간</th><th>DB</th><th>SQL Statement &amp; Fingerprint</th><th>신호</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  // 6. 컨트롤러 (상태 관리 및 사용자 액션)
  const controller = {
    async init() {
      // 새로고침 버튼 바인딩
      if (elements.btnRefresh) {
        elements.btnRefresh.addEventListener('click', () => controller.loadData());
      }

      // 글로벌 단축키: 'r' 또는 'R' 키 입력 시 새로고침
      window.addEventListener('keydown', (e) => {
        if ((e.key === 'r' || e.key === 'R') && !isInputFocused(e)) {
          e.preventDefault();
          controller.loadData();
        }
      });

      await controller.loadData();
    },

    async loadData() {
      const currentToken = ++state.token;
      state.status = 'loading';
      renderer.renderListLoading();
      renderer.renderAggregateLoading();

      try {
        if (!await this.loadHealth(currentToken)) return;
        const data = await this.fetchDashboardData(currentToken);
        if (!data || currentToken !== state.token) return;
        await this.renderDashboardData(data, currentToken);
      } catch (err) {
        this.renderLoadError(err, currentToken);
      }
    },

    async loadHealth(token) {
      let health;
      try {
        health = await api.checkHealth();
      } catch (error) {
        if (token === state.token) this.renderDisabledState('Inspector Inactive');
        return false;
      }
      if (token !== state.token) return false;
      if (health.status !== 'ok') {
        state.status = 'disabled';
        renderer.updateStatusPill('disabled', 'Inspector Disabled');
        renderer.renderListDisabled('서버의 Inspector 상태가 정상(ok)이 아닙니다.');
        return false;
      }
      renderer.updateStatusPill(
        'ok',
        `Active (${health.stored_requests}/${health.capacity})`,
      );
      return true;
    },

    renderDisabledState(label) {
      state.status = 'disabled';
      renderer.updateStatusPill('disabled', label);
      renderer.renderListDisabled(
        'Inspector API 서비스에 연결할 수 없거나 비활성화되었습니다.',
      );
      renderer.renderAggregateError('Inspector 집계 API에 연결할 수 없습니다.');
      renderer.renderDetailPlaceholder(
        'Inspector가 비활성화되어 상세 정보를 조회할 수 없습니다.',
        '비활성 상태',
      );
    },

    async fetchDashboardData(token) {
      const [requestResult, aggregateResult] = await Promise.allSettled([
        api.fetchRequests(),
        api.fetchAggregates(),
      ]);
      if (token !== state.token) return null;
      if (requestResult.status === 'rejected') throw requestResult.reason;
      return { requestData: requestResult.value, aggregateResult };
    },

    async renderDashboardData(data, token) {
      state.requests = data.requestData.items || [];
      if (data.aggregateResult.status === 'fulfilled') {
        renderer.renderAggregates(data.aggregateResult.value);
      } else {
        renderer.renderAggregateError(data.aggregateResult.reason.message);
      }
      renderer.updateLastRefreshed();
      if (state.requests.length === 0) {
        state.status = 'empty';
        state.selectedRequestId = null;
        state.selectedRequestDetail = null;
        renderer.renderListEmpty();
        renderer.renderDetailPlaceholder();
        return;
      }
      state.status = 'ready';
      this.selectAvailableRequest();
      renderer.renderList(state.requests, state.selectedRequestId);
      await controller.loadDetail(state.selectedRequestId, token);
    },

    selectAvailableRequest() {
      const stillExists = state.requests.some(
        (request) => request.request_id === state.selectedRequestId,
      );
      if (!stillExists) state.selectedRequestId = state.requests[0].request_id;
    },

    renderLoadError(error, token) {
      if (token !== state.token) return;
      state.status = 'error';
      state.errorMessage = error.message;
      renderer.updateStatusPill('err', 'Disconnected');
      renderer.renderListError(error.message);
      renderer.renderAggregateError(error.message);
    },

    async selectRequest(requestId) {
      if (state.selectedRequestId === requestId && state.selectedRequestDetail) {
        return;
      }
      state.selectedRequestId = requestId;
      renderer.renderList(state.requests, state.selectedRequestId);

      state.token += 1;
      await controller.loadDetail(requestId, state.token);
    },

    async loadDetail(requestId, token) {
      renderer.renderDetailLoading();
      try {
        const detail = await api.fetchRequestDetail(requestId);
        if (token !== state.token) return;

        if (!detail) {
          // 404 상세 오류 처리: 기획 9.5 및 9.6 준수
          // 목록 선택 상태를 정리(null)하고 다시 선택할 수 있도록 목록 재조회 및 상황 안내
          state.selectedRequestId = null;
          state.selectedRequestDetail = null;
          renderer.renderDetailPlaceholder(
            '선택된 요청이 버퍼에서 삭제되었거나 만료되었습니다. 목록을 다시 갱신합니다.',
            '요청을 찾을 수 없음 (404)'
          );
          // 목록에서 selected 스타일 해제 후 목록 재조회
          controller.loadData();
          return;
        }

        state.selectedRequestDetail = detail;
        renderer.renderDetail(detail);

      } catch (err) {
        if (token !== state.token) return;
        renderer.renderDetailPlaceholder(`상세 정보를 불러오는 중 오류가 발생했습니다: ${err.message}`, '오류 발생');
      }
    },
  };

  // 7. 유틸리티 함수
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderAggregateTable(title, ariaLabel, headers, rows) {
    const headerHtml = headers
      .map((header) => `<th>${escapeHtml(header)}</th>`)
      .join('');
    const bodyHtml = rows || `<tr><td colspan="${headers.length}">데이터 없음</td></tr>`;
    return `
      <div class="aggregate-section">
        <h3 class="aggregate-section-title">${escapeHtml(title)}</h3>
        <table class="aggregate-table" aria-label="${escapeHtml(ariaLabel)}">
          <thead><tr>${headerHtml}</tr></thead>
          <tbody>${bodyHtml}</tbody>
        </table>
      </div>
    `;
  }

  function renderRouteRows(routes) {
    return routes.map((route) => {
      const template = route.route_template || '/';
      return `
        <tr>
          <td title="${escapeHtml(template)}">${escapeHtml(template)}</td>
          <td>${formatInteger(route.count)}</td>
          <td>${formatMilliseconds(route.avg_duration_ms)}</td>
          <td>${formatInteger(route.total_queries)}</td>
        </tr>
      `;
    }).join('');
  }

  function renderFingerprintRows(fingerprints) {
    return fingerprints.map((item) => {
      const fingerprint = item.fingerprint || '[없음]';
      return `
        <tr>
          <td title="${escapeHtml(fingerprint)}">${escapeHtml(fingerprint)}</td>
          <td>${formatInteger(item.count)}</td>
          <td>${formatInteger(item.request_count)}</td>
          <td>${formatMilliseconds(item.avg_duration_ms)}</td>
        </tr>
      `;
    }).join('');
  }

  function formatInteger(value) {
    const number = Number(value);
    return Number.isFinite(number) ? String(Math.max(0, Math.round(number))) : '0';
  }

  function formatMilliseconds(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `${Math.max(0, number).toFixed(1)}ms` : '0.0ms';
  }

  function isInputFocused(e) {
    const target = e.target;
    return target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
  }

  // DOM 로드 완료 시 애플리케이션 시작
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => controller.init());
  } else {
    controller.init();
  }

})();
