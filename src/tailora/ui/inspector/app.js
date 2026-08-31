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

    async fetchRequests(limit = 20) {
      const resp = await fetch(`${BASE_PATH}/requests?limit=${limit}`, { cache: 'no-store' });
      if (!resp.ok) {
        throw new Error(`Failed to fetch requests: ${resp.status}`);
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

    renderList(items, selectedId) {
      elements.requestCountBadge.textContent = String(items.length);
      const ul = document.createElement('ul');
      ul.className = 'request-list';
      ul.setAttribute('role', 'listbox');
      ul.setAttribute('aria-label', '최근 요청 목록');

      items.forEach((item, index) => {
        const isSelected = item.request_id === selectedId;
        const li = document.createElement('li');
        li.className = `request-item ${isSelected ? 'selected' : ''}`;
        li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        li.setAttribute('tabindex', '0');
        li.dataset.requestId = item.request_id;
        li.dataset.index = String(index);

        const statusCategory = `${Math.floor(item.status_code / 100)}xx`;
        const methodUpper = (item.method || 'GET').toUpperCase();

        // Signals 표시
        let signalsHtml = '';
        if (item.signals) {
          if (item.signals.slow_request) {
            signalsHtml += `<span class="signal-pill signal-slow" title="느린 요청 (임계값 초과)">SLOW</span>`;
          }
          if (item.signals.has_duplicate_query) {
            signalsHtml += `<span class="signal-pill signal-dup" title="중복 쿼리 (N+1 의심)">N+1 DUP</span>`;
          }
          if (item.signals.has_slow_query) {
            signalsHtml += `<span class="signal-pill signal-slow" title="느린 쿼리 포함">SLOW Q</span>`;
          }
          if (item.signals.query_heavy) {
            signalsHtml += `<span class="signal-pill signal-heavy" title="쿼리 실행 과다">HEAVY</span>`;
          }
        }

        li.innerHTML = `
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
            <div class="signals-container">
              ${signalsHtml}
            </div>
          </div>
        `;

        // 마우스 클릭 및 키보드 선택 이벤트
        li.addEventListener('click', () => controller.selectRequest(item.request_id));
        li.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            controller.selectRequest(item.request_id);
          } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            const next = li.nextElementSibling;
            if (next) {
              next.focus();
              const nextId = next.dataset.requestId;
              if (nextId) controller.selectRequest(nextId);
            }
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            const prev = li.previousElementSibling;
            if (prev) {
              prev.focus();
              const prevId = prev.dataset.requestId;
              if (prevId) controller.selectRequest(prevId);
            }
          }
        });

        ul.appendChild(li);
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

      // 1. 헤더 액션 (ID 복사 버튼)
      elements.detailActions.innerHTML = `
        <button type="button" class="btn" id="btn-copy-id" title="요청 ID 복사">
          <span>ID 복사</span>
        </button>
      `;
      const btnCopy = document.getElementById('btn-copy-id');
      if (btnCopy) {
        btnCopy.addEventListener('click', () => {
          navigator.clipboard.writeText(detail.request_id);
          btnCopy.innerHTML = '<span>복사됨!</span>';
          setTimeout(() => {
            btnCopy.innerHTML = '<span>ID 복사</span>';
          }, 1500);
        });
      }

      // 2. 에러 박스
      let errorHtml = '';
      if (detail.error) {
        errorHtml = `
          <div class="error-box">
            <div class="error-title">🚨 ${escapeHtml(detail.error.type || 'Error')}</div>
            <div class="error-msg">${escapeHtml(detail.error.message || '오류 상세 정보 없음')}</div>
          </div>
        `;
      }

      // 3. 신호 상세 카드
      let signalCardsHtml = '';
      const sig = detail.signals || {};
      const appliedThresh = sig.applied_thresholds || {};
      const queries = detail.queries || [];

      // 3.1 Slow Request 카드
      if (sig.slow_request) {
        signalCardsHtml += `
          <div class="signal-card card-slow">
            <div class="signal-card-header">
              <strong class="signal-card-title">⚠️ 느린 요청 (Slow Request)</strong>
              <span class="signal-pill signal-slow">기준 초과</span>
            </div>
            <p class="signal-card-desc">
              소요 시간 <strong>${detail.duration_ms.toFixed(1)}ms</strong>가 설정된 임계값 <strong>${appliedThresh.slow_request_ms}ms</strong>를 초과했습니다.
            </p>
          </div>
        `;
      }

      // 3.2 Slow Query 카드 (sequence 및 실제 실행 시간 표시)
      if (sig.slow_queries && sig.slow_queries.length > 0) {
        const slowQueryItems = sig.slow_queries.map(seq => {
          const matchedQ = queries.find(q => q.sequence === seq);
          const dur = matchedQ ? `${matchedQ.duration_ms.toFixed(1)}ms` : '기준 초과';
          return `<li>Query #${seq}: <strong>${dur}</strong></li>`;
        }).join('');

        signalCardsHtml += `
          <div class="signal-card card-slow-query">
            <div class="signal-card-header">
              <strong class="signal-card-title">🐢 느린 쿼리 (Slow Queries)</strong>
              <span class="signal-pill signal-slow">${sig.slow_queries.length}건 감지</span>
            </div>
            <p class="signal-card-desc">
              임계값(<strong>${appliedThresh.slow_query_ms}ms</strong>) 이상 실행된 개별 SQL입니다:
            </p>
            <ul style="margin: 6px 0 0 16px; font-size: 11px; color: #475569;">
              ${slowQueryItems}
            </ul>
          </div>
        `;
      }

      // 3.3 Duplicate Queries 카드
      if (sig.duplicate_queries && sig.duplicate_queries.length > 0) {
        const dupList = sig.duplicate_queries.map(d =>
          `<li>중복 횟수: <strong>${d.count}회</strong> (SQL Sequences: ${d.sequences.join(', ')})<br><span style="color:#64748b; font-family:var(--font-mono); font-size:10px;">${escapeHtml(d.fingerprint || '')}</span></li>`
        ).join('');
        signalCardsHtml += `
          <div class="signal-card card-dup">
            <div class="signal-card-header">
              <strong class="signal-card-title">🔄 N+1 / 중복 쿼리 (Duplicate Queries)</strong>
              <span class="signal-pill signal-dup">${sig.duplicate_queries.length}개 패턴</span>
            </div>
            <p class="signal-card-desc">동일한 패턴의 SQL이 1개 요청 내에서 반복 실행되었습니다.</p>
            <ul style="margin: 6px 0 0 16px; font-size: 11px; color: #475569;">
              ${dupList}
            </ul>
          </div>
        `;
      }

      // 3.4 Query Heavy 카드
      if (sig.query_heavy) {
        const reasons = (sig.query_heavy_reasons || []).join(', ');
        signalCardsHtml += `
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

      let signalsSectionHtml = '';
      if (signalCardsHtml) {
        signalsSectionHtml = `
          <div class="signals-section">
            <h3 class="section-title">진단 분석 신호 (Signals)</h3>
            <div class="signal-cards-grid">
              ${signalCardsHtml}
            </div>
          </div>
        `;
      }

      // 4. 쿼리 목록 표
      const slowSeqs = new Set(sig.slow_queries || []);
      const dupSeqSet = new Set();
      (sig.duplicate_queries || []).forEach(d => {
        (d.sequences || []).forEach(s => dupSeqSet.add(s));
      });

      let queryRowsHtml = '';
      if (queries.length === 0) {
        queryRowsHtml = `
          <tr>
            <td colspan="5" style="text-align: center; color: #94a3b8; padding: 24px;">
              이 요청에서 실행된 데이터베이스 쿼리가 없습니다.
            </td>
          </tr>
        `;
      } else {
        queryRowsHtml = queries.map(q => {
          let qBadge = '';
          if (slowSeqs.has(q.sequence)) {
            qBadge += `<span class="signal-pill signal-slow" style="margin-right:4px;">SLOW</span>`;
          }
          if (dupSeqSet.has(q.sequence)) {
            qBadge += `<span class="signal-pill signal-dup">DUP</span>`;
          }

          const fpText = q.fingerprint ? `<div class="query-fingerprint" title="SQL Fingerprint">${escapeHtml(q.fingerprint)}</div>` : '';

          return `
            <tr>
              <td class="query-seq">#${q.sequence}</td>
              <td class="query-time">${q.duration_ms.toFixed(1)}ms</td>
              <td class="query-db">${escapeHtml(q.database || 'db')}</td>
              <td>
                <div class="query-sql">${escapeHtml(q.statement)}</div>
                ${fpText}
              </td>
              <td>${qBadge || '<span style="color:#cbd5e1;">-</span>'}</td>
            </tr>
          `;
        }).join('');
      }

      // 타임스탬프 변환 (로컬 시간)
      let formattedTime = detail.timestamp || '-';
      try {
        if (detail.timestamp) {
          const d = new Date(detail.timestamp);
          formattedTime = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionDigit: 3 });
        }
      } catch (e) {}

      elements.detailContainer.innerHTML = `
        <div class="detail-content">
          <!-- 상단 메트릭 요약 카드 (framework, timestamp 포함) -->
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
              <span class="metric-val" style="font-size:12px;">${escapeHtml(formattedTime)}</span>
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

          <!-- 에러 박스 (존재 시) -->
          ${errorHtml}

          <!-- 진단 신호 카드 (존재 시) -->
          ${signalsSectionHtml}

          <!-- 쿼리 실행 표 (Statement 및 Fingerprint 행 단위 표시) -->
          <div class="query-section">
            <h3 class="section-title" style="margin-bottom: 10px;">
              실행된 SQL 쿼리 (${queries.length}건)
            </h3>
            <div class="query-table-container">
              <table class="query-table" aria-label="실행된 SQL 쿼리 목록">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>시간</th>
                    <th>DB</th>
                    <th>SQL Statement &amp; Fingerprint</th>
                    <th>신호</th>
                  </tr>
                </thead>
                <tbody>
                  ${queryRowsHtml}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      `;
    },
  };

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
      state.token += 1;
      const currentToken = state.token;

      state.status = 'loading';
      renderer.renderListLoading();

      try {
        // 1. Health 체크
        let health;
        try {
          health = await api.checkHealth();
        } catch (healthErr) {
          if (currentToken !== state.token) return;
          state.status = 'disabled';
          renderer.updateStatusPill('disabled', 'Inspector Inactive');
          renderer.renderListDisabled('Inspector API 서비스에 연결할 수 없거나 비활성화되었습니다.');
          renderer.renderDetailPlaceholder('Inspector가 비활성화되어 상세 정보를 조회할 수 없습니다.', '비활성 상태');
          return;
        }

        if (currentToken !== state.token) return;

        if (health.status !== 'ok') {
          state.status = 'disabled';
          renderer.updateStatusPill('disabled', 'Inspector Disabled');
          renderer.renderListDisabled('서버의 Inspector 상태가 정상(ok)이 아닙니다.');
          return;
        }

        renderer.updateStatusPill('ok', `Active (${health.stored_requests}/${health.capacity})`);

        // 2. 최근 요청 목록 조회
        const data = await api.fetchRequests(20);
        if (currentToken !== state.token) return;

        state.requests = data.items || [];
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

        // 기존에 선택된 항목이 현재 목록에 남아있는지 확인
        const stillExists = state.requests.some(r => r.request_id === state.selectedRequestId);
        if (!stillExists) {
          // 기존 선택 항목이 없거나 사라진 경우 첫 번째 항목을 자동 선택
          state.selectedRequestId = state.requests[0].request_id;
        }

        renderer.renderList(state.requests, state.selectedRequestId);
        await controller.loadDetail(state.selectedRequestId, currentToken);

      } catch (err) {
        if (currentToken !== state.token) return;
        state.status = 'error';
        state.errorMessage = err.message;
        renderer.updateStatusPill('err', 'Disconnected');
        renderer.renderListError(err.message);
      }
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
