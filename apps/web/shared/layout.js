const consoleLayout = {
  // Chart.js 인스턴스 보관 (재렌더링 시 destroy 처리용)
  charts: {
    mainSubChart: null,
    statsSubChart: null,
    statsSalesChart: null,
  },

  init() {
    window.addEventListener('hashchange', () => this.renderRoute());
    this.renderRoute();
    this.setupAdminLogin();
  },

  // 모든 활성 차트 안전하게 파기
  destroyCharts() {
    Object.keys(this.charts).forEach((key) => {
      if (this.charts[key]) {
        try {
          this.charts[key].destroy();
        } catch (e) {
          console.warn('Chart destroy error:', e);
        }
        this.charts[key] = null;
      }
    });
  },

  navigate(page, subView = 'list', id, { replace = false } = {}) {
    const segments = subView === 'list' ? [page] : [page, subView];
    if (id) segments.push(id);
    const hash = '#/' + segments.map(encodeURIComponent).join('/');
    if (window.location.hash !== hash) {
      if (replace) {
        window.history.replaceState(null, '', hash);
      } else {
        window.history.pushState(null, '', hash);
      }
    }
    this.renderRoute();
  },

  renderRoute() {
    if (!this.renderAdminAccess()) return;
    let [page, subView = 'list', id] = window.location.hash.slice(2).split('/');
    if (!window.location.hash.startsWith('#/') ||
        !['main', 'crawling', 'affiliate', 'customers', 'counseling', 'stats', 'admin-requests'].includes(page)) {
      page = 'main';
    }
    if (this.adminSession.role === 'support' && page !== 'counseling') {
      this.navigate('counseling', 'list', undefined, { replace: true });
      return;
    }

    this.state.currentPage = page;
    const demo = this.isLocalAuthDemo();
    if (page === 'affiliate') {
      const decodedId = id ? decodeURIComponent(id) : '';
      const product = subView === 'edit' && (
        this.getAffiliateItems().find((item) => item.id === decodedId || encodeURIComponent(item.id) === id) ||
        this.state.affiliateProducts.find((item) => item.id === decodedId || encodeURIComponent(item.id) === id)
      );
      const liveId = !demo && subView === 'edit' && this.isUuid(decodedId) ? decodedId.toLowerCase() : null;
      this.state.affiliateSubView = product || liveId ? 'edit' : subView === 'create' ? 'create' : 'list';
      if (product) this.state.selectedAffiliateId = product.id;
      else if (liveId) this.state.selectedAffiliateId = liveId;
    } else if (page === 'customers') {
      const decodedId = id ? decodeURIComponent(id) : '';
      const customer = subView === 'detail' &&
        this.getCustomerItems().find((item) => item.userId === decodedId || item.id === decodedId || encodeURIComponent(item.id) === id);
      const liveId = !demo && subView === 'detail' && this.isUuid(decodedId) ? decodedId.toLowerCase() : null;
      this.state.customerSubView = customer || liveId ? 'detail' : 'list';
      if (customer) this.state.selectedCustomerId = customer.userId || customer.id;
      else if (liveId) this.state.selectedCustomerId = liveId;
    } else if (page === 'counseling') {
      if (demo) {
        const counseling = subView === 'detail' &&
          this.state.counselingList.find((item) => encodeURIComponent(item.id) === id);
        this.state.counselingSubView = counseling ? 'detail' : subView === 'settings' ? 'settings' : 'list';
        if (counseling) this.state.selectedCounselingId = counseling.id;
      } else {
        const detail = subView === 'detail' && this.isUuid(id);
        this.state.counselingSubView = detail ? 'detail' : subView === 'settings' ? 'settings' : 'list';
        this.state.selectedCounselingId = detail ? id.toLowerCase() : null;
      }
    }
    this.state.showDeleteModal = false;
    this.renderSidebar();
    if (!demo) {
      if (page === 'main' || page === 'stats' || (page === 'affiliate' && this.state.affiliateSubView !== 'create')) {
        this.refreshLiveAffiliates();
      }
      if (page === 'main' || page === 'stats' || page === 'counseling') {
        this.refreshLiveCounseling();
      }
      if (page === 'counseling') {
        this.refreshLiveCounselingSettings();
      }
      if (page === 'main' || page === 'stats' || page === 'customers' ||
          (page === 'counseling' && this.adminSession.role === 'admin')) {
        this.refreshLiveCustomers();
      }
      if (page === 'main' || page === 'stats' || page === 'crawling') {
        this.refreshLiveOverview();
      }
      if (page === 'crawling') this.refreshLiveCatalog();
    }
    this.renderContent();
    this.renderModal();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  isUuid(value) {
    return /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value || '');
  },

  formatKstDateTime(value) {
    const utc = typeof value === 'number' ? value : Date.parse(value);
    if (!Number.isFinite(utc)) return '';
    return new Date(utc + 9 * 60 * 60 * 1000).toISOString().slice(0, 16).replaceAll('-', '.').replace('T', ' ');
  },

  async fetchAllCatalogOffers() {
    const offers = new Map();
    for (const domain of ['product', 'food']) {
      try {
        // Keep the /backend proxy prefix: new URL('/v2/...', base) would drop the base path.
        const url = new URL(this.getApiBase() + '/v2/offers');
        url.search = new URLSearchParams({
          selected_domain: domain, condition: 'all', availability: 'all', limit: '100',
        });
        const cursors = new Set();
        for (let page = 0; page < 5; page++) {
          const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
          if (!response.ok) break;
          const data = await response.json();
          if (!Array.isArray(data?.items)) break;
          for (const item of data.items) {
            offers.set(item.offer_id, { ...item, selected_domain: item.selected_domain || domain });
          }
          const cursor = data.next_cursor;
          if (!cursor || cursors.has(cursor)) break;
          cursors.add(cursor);
          url.searchParams.set('after', cursor);
        }
      } catch {
        // 개별 도메인 조회 실패 시 수집된 목록까지만 반환한다.
      }
    }
    return [...offers.values()];
  },

  async requestAdminList(path, token, cursorField) {
    const items = [];
    let cursor;
    do {
      const query = new URLSearchParams({ limit: '100' });
      if (cursor) query.set('after', cursor);
      const batch = await this.requestAdminAuth(`${path}?${query}`, { token });
      if (!Array.isArray(batch)) throw new Error('Invalid admin list response');
      items.push(...batch);
      if (!cursorField || batch.length < 100) return items;
      const next = batch.at(-1)[cursorField];
      if (!this.isUuid(next) || (cursor && next <= cursor)) throw new Error('Invalid list cursor');
      cursor = next;
    } while (true);
  },

  async refreshAdminData(key, load) {
    const session = this.adminSession;
    if (!session || this.isLocalAuthDemo()) return;
    const targetPage = this.state.currentPage;
    const prevItems = this[key]?.items || [];
    const view = { phase: 'loading', items: prevItems };
    this[key] = view;
    this.renderContent();
    try {
      Object.assign(view, await load(session.token), { phase: 'ready' });
    } catch (error) {
      view.phase = 'error';
      view.message = error.status === 403 ? '조회 권한이 없습니다.' :
        error.status === 401 ? '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.' :
          '팀 서버의 데이터를 불러오지 못했습니다.';
    }
    if (this[key] === view && this.adminSession === session && this.state.currentPage === targetPage) {
      this.renderContent();
    }
  },

  renderAdminDataStatus(view, retry) {
    return `
      <p class="mb-3 text-sm text-slate-600" role="status">${this.escapeHtml(view?.message || '팀 서버 데이터를 불러오는 중입니다.')}</p>
      ${view?.phase === 'error' ? retry : ''}
    `;
  },

  // 토스트 알림 헬퍼
  showToast(message) {
    const root = document.getElementById('toast-root');
    if (!root) return;
    const toast = document.createElement('div');
    toast.className = 'bg-[#1e2430] text-white text-sm px-4 py-3 rounded-lg shadow-lg border border-slate-700 flex items-center gap-2 pointer-events-auto transition-opacity duration-300';
    const dot = document.createElement('span');
    dot.className = 'w-2 h-2 rounded-full bg-[#0066ff] inline-block';
    const label = document.createElement('span');
    label.textContent = message;
    toast.append(dot, label);
    root.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 2600);
  },

  navigateMenu(page) {
    if (page === 'affiliate') {
      this.state.affiliateStatusFilter = '전체';
      this.state.affiliateSearch = '';
      this.state.affiliateForceEmpty = false;
    } else if (page === 'counseling') {
      this.state.counselingCategoryFilter = '전체';
      this.state.counselingSearch = '';
    }
    this.navigate(page);
  },

  // 좌측 사이드바 렌더링 (계층 및 활성 스타일 완벽 반영)
  renderSidebar() {
    const nav = document.getElementById('sidebar-nav');
    if (!nav) return;

    const p = this.state.currentPage;
    const isProductGroup = p === 'affiliate' || p === 'crawling';

    const itemClass = (active) =>
      'flex w-full items-center gap-2 rounded-lg border-l-[3px] px-2.5 py-2.5 text-left transition-colors ' +
      (active
        ? 'border-[#0066ff] bg-[#ebf3ff] text-[#0066ff] font-bold'
        : 'border-transparent text-slate-700 hover:bg-slate-100 font-medium');
    const icon = (path) => `<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"
      aria-hidden="true"><path d="${path}"/></svg>`;
    const menu = (page, label, path) => `
      <button type="button" onclick="app.navigateMenu('${page}')" class="${itemClass(p === page)}"
        ${p === page ? 'aria-current="page"' : ''}>
        ${icon(path)} <span>${label}</span>
      </button>`;

    const counselingMenu = menu('counseling', '고객상담', 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5');
    if (this.adminSession.role === 'support') {
      nav.innerHTML = counselingMenu;
      return;
    }
    nav.innerHTML = `
      ${menu('main', 'MAIN', 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z')}
      <div>
        <button type="button" onclick="app.navigateMenu('affiliate')" class="${itemClass(false)} ${isProductGroup ? 'text-[#0066ff]' : ''}">
          ${icon('M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10')} <span>상품관리</span>
        </button>
        <div class="mt-1 space-y-1 pl-3">
          ${menu('affiliate', '제휴상품', 'M5 4h7l7 7-7 7-7-7V4zM8 7h.01')}
          ${menu('crawling', '상품 크롤링 검토', 'M3 5h18M3 12h18M3 19h18M7 5v14')}
        </div>
      </div>
      ${counselingMenu}
      ${menu('stats', '통계', 'M4 4v16h16M8 16v-4M13 16V8M18 16V5')}
      ${menu('customers', '고객정보', 'M15 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM5 20v-2a7 7 0 0 1 14 0v2z')}
      ${menu('admin-requests', '관리자 가입 승인', 'M4 4h16v16H4zM8 12l3 3 5-6')}
    `;
  },

  renderStatusBadge(label) {
    const palette = {
      '제휴 중': 'bg-emerald-50 text-emerald-800 ring-emerald-600/20',
      '진행 중': 'bg-blue-50 text-blue-800 ring-blue-600/20',
      '대기': 'bg-indigo-50 text-indigo-800 ring-indigo-600/20',
      '종료 예정': 'bg-indigo-50 text-indigo-800 ring-indigo-600/20',
    };
    const style = Object.hasOwn(palette, label) ? palette[label] : 'bg-slate-100 text-slate-700 ring-slate-500/20';
    return `<span class="inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${style}">${this.escapeHtml(label)}</span>`;
  },

  // 우측 본문 공통 헤더 생성 헬퍼
  renderPageHeader(title, subtitle, extraRightHtml = '') {
    return `
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 mb-7">
        <div>
          <h1 class="text-3xl font-bold text-slate-900 tracking-tight">${title}</h1>
          <p class="text-sm text-slate-500 mt-1">${subtitle}</p>
        </div>
        <div class="flex items-center gap-3 self-end sm:self-auto">
          ${extraRightHtml}
          <span class="text-sm text-slate-500 font-normal whitespace-nowrap">${this.formatKstDateTime(Date.now()).slice(0, 10)} · KST</span>
        </div>
      </div>
    `;
  },

  // 메인 콘텐츠 분기 렌더링
  renderContent() {
    this.destroyCharts();
    const container = document.getElementById('app-content');
    if (!container) return;

    const p = this.state.currentPage;

    if (p === 'crawling') {
      container.innerHTML = this.getCrawlingHtml();
    } else if (p === 'affiliate') {
      container.innerHTML = this.getAffiliateHtml();
      const sub = this.state.affiliateSubView;
      if ((sub === 'create' || sub === 'edit') &&
          document.getElementById('aff-offer-search')) this.loadOfferCatalog();
    } else if (p === 'customers') {
      container.innerHTML = this.getCustomersHtml();
    } else if (p === 'admin-requests') {
      container.innerHTML = this.getAdminSignupRequestsHtml();
      this.loadAdminSignupRequests();
    } else if (p === 'counseling') {
      container.innerHTML = this.getCounselingHtml();
    } else if (p === 'stats') {
      container.innerHTML = this.getStatsHtml();
      this.initStatsCharts();
    } else if (p === 'main') {
      container.innerHTML = this.getMainDashboardHtml();
      this.initMainChart();
    }
  },

  parseDateRange(value, precision = 10) {
    const dates = value.trim().split(/\s*~\s*/);
    if (dates.length !== 2 || dates[0] > dates[1]) return null;

    const format = { 4: /^\d{4}$/, 7: /^\d{4}\.\d{2}$/, 10: /^\d{4}\.\d{2}\.\d{2}$/ }[precision];
    const suffix = { 4: '-01-01', 7: '-01', 10: '' }[precision];
    return dates.every((date) => {
      if (!format.test(date)) return false;
      const iso = date.replaceAll('.', '-') + suffix;
      const time = Date.parse(iso + 'T00:00:00Z');
      return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === iso;
    }) ? dates : null;
  },

  // HTML 이스케이프 유틸
  escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
};
