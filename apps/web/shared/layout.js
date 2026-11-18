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
    let [page, subView = 'list', id] = window.location.hash.slice(2).split('/');
    if (!window.location.hash.startsWith('#/') ||
        !['main', 'crawling', 'affiliate', 'customers', 'counseling', 'stats'].includes(page)) {
      page = 'crawling';
    }

    this.state.currentPage = page;
    if (page === 'affiliate') {
      const product = subView === 'edit' &&
        this.state.affiliateProducts.find((item) => encodeURIComponent(item.id) === id);
      this.state.affiliateSubView = product ? 'edit' : subView === 'create' ? 'create' : 'list';
      if (product) this.state.selectedAffiliateId = product.id;
    } else if (page === 'customers') {
      const customer = subView === 'detail' &&
        this.state.customers.find((item) => encodeURIComponent(item.id) === id);
      this.state.customerSubView = customer ? 'detail' : 'list';
      if (customer) this.state.selectedCustomerId = customer.id;
    } else if (page === 'counseling') {
      const counseling = subView === 'detail' &&
        this.state.counselingList.find((item) => encodeURIComponent(item.id) === id);
      this.state.counselingSubView = counseling ? 'detail' : subView === 'settings' ? 'settings' : 'list';
      if (counseling) this.state.selectedCounselingId = counseling.id;
    }
    this.state.showDeleteModal = false;
    this.renderSidebar();
    this.renderContent();
    this.renderModal();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  // 토스트 알림 헬퍼
  showToast(message) {
    const root = document.getElementById('toast-root');
    if (!root) return;
    const toast = document.createElement('div');
    toast.className = 'bg-[#1e2430] text-white text-sm px-4 py-3 rounded-lg shadow-lg border border-slate-700 flex items-center gap-2 pointer-events-auto transition-opacity duration-300';
    toast.innerHTML = `<span class="w-2 h-2 rounded-full bg-[#0066ff] inline-block"></span><span>${message}</span>`;
    root.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 2600);
  },

  // 좌측 사이드바 렌더링 (계층 및 활성 스타일 완벽 반영)
  renderSidebar() {
    const nav = document.getElementById('sidebar-nav');
    if (!nav) return;

    const p = this.state.currentPage;
    const isProductGroup = p === 'affiliate' || p === 'crawling';

    const itemClass = (active) =>
      active
        ? 'block w-full text-left px-3 py-2.5 rounded-lg bg-[#ebf3ff] text-[#0066ff] font-bold transition-colors'
        : 'block w-full text-left px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-medium transition-colors';

    const parentProductClass = isProductGroup
      ? 'block w-full text-left px-3 py-2 text-[#0066ff] font-bold transition-colors'
      : 'block w-full text-left px-3 py-2 text-slate-700 hover:text-slate-900 font-medium transition-colors';

    nav.innerHTML = `
      <button onclick="app.navigate('main')" class="${itemClass(p === 'main')}">
        MAIN
      </button>

      <div class="pt-1">
        <!-- 상품관리: 상위 카테고리 라벨 역할, 클릭 시 기본으로 '제휴상품' 이동 -->
        <button onclick="app.navigate('affiliate', 'list')" class="${parentProductClass}">
          상품관리
        </button>
        <div class="mt-1 space-y-1 pl-4">
          <button onclick="app.navigate('affiliate', 'list')" class="${itemClass(p === 'affiliate')}">
            제휴상품
          </button>
          <button onclick="app.navigate('crawling')" class="${itemClass(p === 'crawling')}">
            상품 크롤링 검토
          </button>
        </div>
      </div>

      <button onclick="app.navigate('counseling', 'list')" class="${itemClass(p === 'counseling')}">
        고객상담
      </button>

      <button onclick="app.navigate('stats')" class="${itemClass(p === 'stats')}">
        통계
      </button>

      <button onclick="app.navigate('customers', 'list')" class="${itemClass(p === 'customers')}">
        고객정보
      </button>
    `;
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
          <span class="text-sm text-slate-500 font-normal whitespace-nowrap">2026.10.12 · KST</span>
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
    } else if (p === 'customers') {
      container.innerHTML = this.getCustomersHtml();
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
