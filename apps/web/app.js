/**
 * 꿀픽 ADMIN 운영 콘솔 SPA Application (Vanilla JS + Tailwind CSS + Chart.js)
 * PPT 59p ~ 70p 모든 화면, 상태 분기, 모달 및 차트 인터랙션 100% 구현
 */

const app = {
  // 현재 활성화된 화면 및 서브 상태
  state: {
    currentPage: 'crawling', // 'main' | 'affiliate' | 'crawling' | 'counseling' | 'stats' | 'customers'

    // [화면 1] 상품 크롤링 검토 상태
    crawlingPeriod: '2026.10.06 ~ 2026.10.12',
    crawlingFilterQuery: '',
    crawlingData: [
      { date: '2026.10.12', count: 128 },
      { date: '2026.10.11', count: 342 },
      { date: '2026.10.10', count: 215 },
      { date: '2026.10.09', count: 186 },
      { date: '2026.10.08', count: 298 },
      { date: '2026.10.07', count: 264 },
      { date: '2026.10.06', count: 173 },
    ],

    // [화면 2] 제휴상품 관리 상태
    affiliateSubView: 'list', // 'list' | 'create' | 'edit'
    affiliateSearch: '',
    affiliateStatusFilter: '전체',
    affiliateForceEmpty: false, // 우측 상단 [빈 상태 토글] 테스트용
    selectedAffiliateId: 'AF-001',
    showDeleteModal: false,
    affiliateProducts: [
      {
        id: 'AF-001',
        partner: '엡손',
        name: 'M1120 흑백 프린터',
        price: '179,000원',
        rawPrice: '179,000',
        url: 'https://shop.example/products/OF-001',
        status: '제휴 중',
        period: '10.01 ~ 12.31',
        offerCode: 'OF-001 · 엡손 M1120',
        offerTitle: '일반 상품 · 엡손 M1120',
        offerSub: '179,000 KRW · 배송비 0 KRW',
        startDateTime: '2026.10.01 00:00',
        endDateTime: '2026.12.31 23:59',
        lastVerified: '2026.10.12 09:00',
        linkExpiry: '2026.10.13 09:00'
      },
      {
        id: 'AF-002',
        partner: '그레인',
        name: '라이스 크리스프',
        price: '12,000원',
        rawPrice: '12,000',
        url: 'https://shop.example/products/OF-002',
        status: '제휴 중',
        period: '10.01 ~ 종료 없음',
        offerCode: 'OF-002 · 그레인 라이스 크리스프',
        offerTitle: '일반 상품 · 그레인 라이스 크리스프',
        offerSub: '12,000 KRW · 배송비 2,500 KRW',
        startDateTime: '2026.10.01 00:00',
        endDateTime: '',
        lastVerified: '2026.10.12 09:00',
        linkExpiry: '2026.10.13 09:00'
      },
      {
        id: 'AF-003',
        partner: '베이직',
        name: '코튼 셔츠',
        price: '29,000원',
        rawPrice: '29,000',
        url: 'https://shop.example/products/OF-003',
        status: '제휴 중',
        period: '10.01 ~ 11.30',
        offerCode: 'OF-003 · 베이직 코튼 셔츠',
        offerTitle: '일반 상품 · 베이직 코튼 셔츠',
        offerSub: '29,000 KRW · 배송비 0 KRW',
        startDateTime: '2026.10.01 00:00',
        endDateTime: '2026.11.30 23:59',
        lastVerified: '2026.10.12 09:00',
        linkExpiry: '2026.10.13 09:00'
      }
    ],
    // 판매정보 카탈로그 (등록/편집 시 선택 가능)
    offerCatalog: [
      {
        code: 'OF-001 · 엡손 M1120',
        partner: '엡손',
        name: 'M1120 흑백 프린터',
        price: '179,000원',
        url: 'https://shop.example/products/OF-001',
        infoTitle: '일반 상품 · 엡손 M1120',
        infoSub: '179,000 KRW · 배송비 0 KRW'
      },
      {
        code: 'OF-002 · 그레인 라이스 크리스프',
        partner: '그레인',
        name: '라이스 크리스프',
        price: '12,000원',
        url: 'https://shop.example/products/OF-002',
        infoTitle: '일반 상품 · 그레인 라이스 크리스프',
        infoSub: '12,000 KRW · 배송비 2,500 KRW'
      },
      {
        code: 'OF-003 · 베이직 코튼 셔츠',
        partner: '베이직',
        name: '코튼 셔츠',
        price: '29,000원',
        url: 'https://shop.example/products/OF-003',
        infoTitle: '일반 상품 · 베이직 코튼 셔츠',
        infoSub: '29,000 KRW · 배송비 0 KRW'
      },
      {
        code: 'OF-004 · 로지텍 무소음 마우스',
        partner: '로지텍',
        name: 'M331 무소음 마우스',
        price: '24,900원',
        url: 'https://shop.example/products/OF-004',
        infoTitle: '일반 상품 · 로지텍 M331',
        infoSub: '24,900 KRW · 배송비 0 KRW'
      }
    ],

    // [화면 3] 고객정보 & 고객 세부정보 상태
    customerSubView: 'list', // 'list' | 'detail'
    customerSearch: '',
    customerTypeFilter: '전체',
    customerStatusFilter: '전체',
    selectedCustomerId: 'moa123',
    customers: [
      { id: 'moa123', subscribed: 'O', gender: '여성', ageGroup: '20대', status: '정상', subStartDate: '2026.10.12' },
      { id: 'honey24', subscribed: '', gender: '남성', ageGroup: '30대', status: '정상', subStartDate: '-' },
      { id: 'pick305', subscribed: 'O', gender: '여성', ageGroup: '40대', status: '정상', subStartDate: '2026.10.12' },
      { id: 'daily88', subscribed: '', gender: '남성', ageGroup: '20대', status: '정상', subStartDate: '-' },
      { id: 'green72', subscribed: 'O', gender: '여성', ageGroup: '30대', status: '정상', subStartDate: '2026.10.12' },
      { id: 'sunny10', subscribed: '', gender: '여성', ageGroup: '50대', status: '정상', subStartDate: '-' },
      { id: 'pick102', subscribed: 'O', gender: '남성', ageGroup: '40대', status: '정상', subStartDate: '2026.10.12' },
    ],

    // [화면 4] 고객상담 상태
    counselingSubView: 'list', // 'list' | 'detail' | 'settings'
    counselingSearch: '',
    counselingCategoryFilter: '전체',
    selectedCounselingId: 'CS-001',
    counselingSettings: {
      days: '월요일 ~ 금요일',
      startTime: '09:00',
      endTime: '18:00',
      awayMessage: '지금은 상담 가능시간이 아닙니다. 문의를 남겨주시면 운영시간에 순서대로 답변드리겠습니다.\n상담 가능시간: 평일 09:00–18:00'
    },
    counselingList: [
      {
        id: 'CS-001',
        customerId: 'moa123',
        title: '프리미엄 결제 확인',
        category: '결제',
        status: '진행 중',
        agent: '김상담',
        lastMessageTime: '10.12 14:32',
        messages: [
          { sender: 'moa123', text: '안녕하세요. 프리미엄 결제가 완료됐는지 확인하고 싶어요.', time: '14:30' },
          { sender: '김상담', text: '안녕하세요, 꿀픽입니다. 결제하신 시간을 알려주시면 확인해 드릴게요.', time: '14:31' },
          { sender: 'moa123', text: '오늘 오후 2시쯤 결제했어요.', time: '14:32' },
        ]
      },
      {
        id: 'CS-002',
        customerId: 'honey24',
        title: '알레르기 설정 변경',
        category: '이용 문의',
        status: '대기',
        agent: '미배정',
        lastMessageTime: '10.12 14:10',
        messages: [
          { sender: 'honey24', text: '프로필에서 알레르기 유발 성분을 추가로 등록하고 싶은데 어디서 하나요?', time: '14:10' }
        ]
      },
      {
        id: 'CS-003',
        customerId: 'pick305',
        title: '추천 상품 표시 오류',
        category: '오류',
        status: '대기',
        agent: '미배정',
        lastMessageTime: '10.12 13:55',
        messages: [
          { sender: 'pick305', text: '메인 화면에서 맞춤 추천 상품 이미지가 간헐적으로 보이지 않습니다.', time: '13:55' }
        ]
      },
      {
        id: 'CS-004',
        customerId: 'daily88',
        title: '계정 정보 변경',
        category: '계정',
        status: '완료',
        agent: '이상담',
        lastMessageTime: '10.11 17:08',
        messages: [
          { sender: 'daily88', text: '휴대폰 번호 변경은 마이페이지에서 바로 가능한가요?', time: '17:05' },
          { sender: '이상담', text: '네 고객님, 마이페이지 > 계정 설정에서 본인인증 후 변경하실 수 있습니다.', time: '17:08' }
        ]
      },
      {
        id: 'CS-005',
        customerId: 'green72',
        title: '구독 해지 문의',
        category: '구독',
        status: '완료',
        agent: '김상담',
        lastMessageTime: '10.11 15:24',
        messages: [
          { sender: 'green72', text: '이번 달 구독 해지 신청하면 언제까지 이용 가능한가요?', time: '15:20' },
          { sender: '김상담', text: '결제일 기준 다음 갱신일 전날까지 프리미엄 혜택이 그대로 유지됩니다.', time: '15:24' }
        ]
      }
    ],

    // [화면 5] 통계 상태
    statsUnit: 'daily', // 'daily' | 'monthly' | 'yearly'
    statsPeriodInput: '2026.10.06 ~ 2026.10.12',
  },

  // Chart.js 인스턴스 보관 (재렌더링 시 destroy 처리용)
  charts: {
    mainSubChart: null,
    statsSubChart: null,
    statsSalesChart: null,
  },

  init() {
    this.renderSidebar();
    this.renderContent();
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

  // 사이드바 메뉴 네비게이션 이동
  navigate(page, subView = 'list') {
    this.state.currentPage = page;
    if (page === 'affiliate') {
      this.state.affiliateSubView = subView;
    } else if (page === 'customers') {
      this.state.customerSubView = subView;
    } else if (page === 'counseling') {
      this.state.counselingSubView = subView;
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

  // =========================================================================
  // [화면 1] 상품 크롤링 검토 (PPT 59p, 64p)
  // =========================================================================
  getCrawlingHtml() {
    const query = this.state.crawlingFilterQuery.trim();
    const rows = this.state.crawlingData.filter((item) => {
      if (!query) return true;
      return item.date.includes(query) || String(item.count).includes(query);
    });

    const totalDays = rows.length;
    const totalCount = rows.reduce((acc, r) => acc + r.count, 0).toLocaleString();

    return `
      ${this.renderPageHeader('상품 크롤링 검토', '상품 데이터베이스 수집 내역을 날짜별로 확인하세요. · 예시 데이터')}

      <!-- 상단 검색 영역 -->
      <div class="mb-6">
        <label class="block text-xs font-bold text-slate-600 mb-1.5">조회 기간</label>
        <div class="flex flex-wrap items-center gap-2.5">
          <input
            id="crawling-period-input"
            type="text"
            value="${this.state.crawlingPeriod}"
            placeholder="2026.10.06 ~ 2026.10.12"
            class="form-input w-[360px]"
            onkeydown="if(event.key==='Enter') app.handleCrawlingSearch()"
          />
          <button onclick="app.handleCrawlingSearch()" class="btn-primary">
            조회
          </button>
        </div>
      </div>

      <!-- 데이터 테이블 -->
      <div class="w-full">
        <!-- 컬럼 헤더 -->
        <div class="flex items-center px-6 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
          <div class="w-[35%] text-left">크롤링 일자</div>
          <div class="w-[65%] text-left">크롤링 건수</div>
        </div>

        <!-- 각 행(Row)은 흰색 배경 박스 형태(bg-white)로 행 사이 간격 배치 -->
        <div class="space-y-2 mt-2">
          ${rows
            .map(
              (row) => `
            <div class="flex items-center bg-white border border-slate-200/90 rounded-lg px-6 py-3.5 text-sm text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.02)]">
              <div class="w-[35%] text-left font-medium text-slate-900">${row.date}</div>
              <div class="w-[65%] text-left font-semibold text-slate-800">${row.count}건</div>
            </div>
          `
            )
            .join('')}
        </div>
      </div>

      <!-- 하단 요약 문구 -->
      <div class="mt-4 text-sm text-slate-500">
        총 ${totalDays}일 · ${totalCount}건 &nbsp;&nbsp;/&nbsp;&nbsp; 날짜별 수집 건수입니다.
      </div>
    `;
  },

  handleCrawlingSearch() {
    const input = document.getElementById('crawling-period-input');
    if (input) {
      this.state.crawlingPeriod = input.value;
    }
    this.renderContent();
    this.showToast(`조회 기간(${this.state.crawlingPeriod}) 내역을 불러왔습니다.`);
  },

  // =========================================================================
  // [화면 2] 제휴상품 관리 (목록 / 빈 상태 / 등록 / 편집 / 삭제 모달)
  // =========================================================================
  getAffiliateHtml() {
    const sub = this.state.affiliateSubView;
    if (sub === 'create') {
      return this.getAffiliateFormHtml('create');
    }
    if (sub === 'edit') {
      return this.getAffiliateFormHtml('edit');
    }
    return this.getAffiliateListHtml();
  },

  getAffiliateListHtml() {
    const search = this.state.affiliateSearch.trim().toLowerCase();
    const statusFilter = this.state.affiliateStatusFilter;

    const filtered = this.state.affiliateForceEmpty
      ? []
      : this.state.affiliateProducts.filter((item) => {
          const matchesSearch =
            !search ||
            item.name.toLowerCase().includes(search) ||
            item.partner.toLowerCase().includes(search) ||
            item.id.toLowerCase().includes(search);
          const matchesStatus = statusFilter === '전체' || item.status === statusFilter;
          return matchesSearch && matchesStatus;
        });

    const toggleBtnHtml = `
      <button
        onclick="app.toggleAffiliateEmptyState()"
        class="text-xs px-2.5 py-1 rounded border ${
          this.state.affiliateForceEmpty
            ? 'bg-blue-50 border-blue-300 text-[#0066ff] font-semibold'
            : 'bg-white border-slate-200 text-slate-500 hover:text-slate-700'
        } transition-colors"
        title="PPT 60페이지 빈 상태 화면을 즉시 확인합니다"
      >
        [빈 상태 토글${this.state.affiliateForceEmpty ? ': ON' : ''}]
      </button>
    `;

    return `
      ${this.renderPageHeader(
        '제휴상품 관리',
        '제휴사별 상품명, 금액 및 URL을 관리하세요. · 예시 데이터',
        toggleBtnHtml
      )}

      <!-- 상단 컨트롤 바 (한 줄 배치) -->
      <div class="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">제휴상품 검색</label>
            <input
              id="affiliate-search-input"
              type="text"
              value="${this.escapeHtml(this.state.affiliateSearch)}"
              placeholder="상품명 또는 제휴사 검색"
              class="form-input w-[340px]"
              oninput="app.handleAffiliateFilterChange(this.value, null)"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">상태</label>
            <select
              class="form-input w-[140px] cursor-pointer"
              onchange="app.handleAffiliateFilterChange(null, this.value)"
            >
              <option value="전체" ${statusFilter === '전체' ? 'selected' : ''}>전체</option>
              <option value="제휴 중" ${statusFilter === '제휴 중' ? 'selected' : ''}>제휴 중</option>
              <option value="종료" ${statusFilter === '종료' ? 'selected' : ''}>종료</option>
            </select>
          </div>
        </div>

        <!-- 우측 버튼 3개 나란히 -->
        <div class="flex items-center gap-2.5">
          <button onclick="app.openAffiliateCreate()" class="btn-primary">
            새 제휴 상품 등록
          </button>
          <button onclick="app.openAffiliateEdit()" class="btn-secondary">
            선택 편집
          </button>
          <button onclick="app.openAffiliateDeleteModal()" class="btn-secondary">
            선택 삭제
          </button>
        </div>
      </div>

      <!-- 테이블 영역 -->
      <div class="w-full">
        <!-- 테이블 컬럼 헤더 -->
        <div class="grid grid-cols-12 items-center px-5 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
          <div class="col-span-1">제휴상품 ID</div>
          <div class="col-span-1">제휴사</div>
          <div class="col-span-2">상품명</div>
          <div class="col-span-1">금액</div>
          <div class="col-span-3">URL</div>
          <div class="col-span-1">제휴 상태</div>
          <div class="col-span-2">유효기간</div>
          <div class="col-span-1 text-right">선택</div>
        </div>

        <!-- 데이터 목록 또는 빈 상태 분기 -->
        <div id="affiliate-table-body" class="mt-2">
          ${this.getAffiliateRowsHtml(filtered)}
        </div>
      </div>
    `;
  },

  getAffiliateRowsHtml(filtered) {
    if (filtered.length === 0) {
      // 빈 상태 (Empty State - PPT 60p, 63p 화면)
      return `
        <div class="bg-slate-100/80 text-slate-500 rounded-lg p-4 text-sm">
          등록된 제휴상품이 없습니다.
        </div>
      `;
    }

    return `
      <div class="space-y-2">
        ${filtered
          .map((item) => {
            const isSelected = item.id === this.state.selectedAffiliateId;
            const rowBorder = isSelected
              ? 'border-[#0066ff] ring-1 ring-[#0066ff]/20 bg-white'
              : 'border-slate-200 bg-white hover:border-slate-300';
            return `
              <div
                onclick="app.selectAffiliateItem('${item.id}')"
                class="grid grid-cols-12 items-center px-5 py-4 rounded-lg border ${rowBorder} text-sm cursor-pointer transition-all"
              >
                <div class="col-span-1 font-semibold text-slate-900">${item.id}</div>
                <div class="col-span-1 text-slate-700">${this.escapeHtml(item.partner)}</div>
                <div class="col-span-2 font-medium text-slate-900 pr-2 truncate">${this.escapeHtml(item.name)}</div>
                <div class="col-span-1 text-slate-800">${this.escapeHtml(item.price)}</div>
                <div class="col-span-3 text-slate-500 pr-3 truncate text-xs">${this.escapeHtml(item.url)}</div>
                <div class="col-span-1">
                  <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-[#ebf3ff] text-[#0066ff]">
                    ${this.escapeHtml(item.status)}
                  </span>
                </div>
                <div class="col-span-2 text-slate-600 text-xs">${this.escapeHtml(item.period)}</div>
                <div class="col-span-1 text-right">
                  <span class="${
                    isSelected ? 'text-[#0066ff] font-bold' : 'text-slate-400 hover:text-slate-600 font-medium'
                  }">
                    ${isSelected ? '선택됨' : '선택'}
                  </span>
                </div>
              </div>
            `;
          })
          .join('')}
      </div>
    `;
  },

  toggleAffiliateEmptyState() {
    this.state.affiliateForceEmpty = !this.state.affiliateForceEmpty;
    this.renderContent();
  },

  handleAffiliateFilterChange(searchVal, statusVal) {
    if (searchVal !== null) {
      this.state.affiliateSearch = searchVal;
    }
    if (statusVal !== null) {
      this.state.affiliateStatusFilter = statusVal;
    }

    const search = this.state.affiliateSearch.trim().toLowerCase();
    const statusFilter = this.state.affiliateStatusFilter;
    const filtered = this.state.affiliateForceEmpty
      ? []
      : this.state.affiliateProducts.filter((item) => {
          const matchesSearch =
            !search ||
            item.name.toLowerCase().includes(search) ||
            item.partner.toLowerCase().includes(search) ||
            item.id.toLowerCase().includes(search);
          const matchesStatus = statusFilter === '전체' || item.status === statusFilter;
          return matchesSearch && matchesStatus;
        });

    const tbody = document.getElementById('affiliate-table-body');
    if (tbody) {
      tbody.innerHTML = this.getAffiliateRowsHtml(filtered);
    }
  },

  selectAffiliateItem(id) {
    this.state.selectedAffiliateId = id;
    this.handleAffiliateFilterChange(null, null);
  },

  openAffiliateCreate() {
    this.state.affiliateSubView = 'create';
    this.renderContent();
  },

  openAffiliateEdit() {
    if (this.state.affiliateForceEmpty || this.state.affiliateProducts.length === 0) {
      this.showToast('편집할 제휴 상품이 없습니다.');
      return;
    }
    let current = this.state.affiliateProducts.find((p) => p.id === this.state.selectedAffiliateId);
    if (!current) {
      current = this.state.affiliateProducts[0];
      this.state.selectedAffiliateId = current.id;
    }
    this.state.affiliateSubView = 'edit';
    this.renderContent();
  },

  openAffiliateDeleteModal() {
    if (this.state.affiliateForceEmpty || this.state.affiliateProducts.length === 0) {
      this.showToast('삭제할 제휴 상품이 없습니다.');
      return;
    }
    let current = this.state.affiliateProducts.find((p) => p.id === this.state.selectedAffiliateId);
    if (!current) {
      current = this.state.affiliateProducts[0];
      this.state.selectedAffiliateId = current.id;
    }
    this.state.showDeleteModal = true;
    this.renderModal();
  },

  closeDeleteModal() {
    this.state.showDeleteModal = false;
    this.renderModal();
  },

  confirmDeleteAffiliate() {
    const targetId = this.state.selectedAffiliateId;
    this.state.affiliateProducts = this.state.affiliateProducts.filter((p) => p.id !== targetId);
    this.state.showDeleteModal = false;
    if (this.state.affiliateProducts.length > 0) {
      this.state.selectedAffiliateId = this.state.affiliateProducts[0].id;
    } else {
      this.state.selectedAffiliateId = '';
    }
    this.renderModal();
    this.renderContent();
    this.showToast(`${targetId} 제휴 상품이 삭제되었습니다.`);
  },

  // 새 제휴 상품 등록 / 제휴 상품 편집 공통 폼 화면
  getAffiliateFormHtml(mode) {
    const isEdit = mode === 'edit';
    const item = isEdit
      ? this.state.affiliateProducts.find((p) => p.id === this.state.selectedAffiliateId) ||
        this.state.affiliateProducts[0]
      : null;

    const title = isEdit ? '제휴 상품 편집' : '새 제휴 상품 등록';
    const subtitle = '제휴사, 금액, 판매정보 및 URL을 입력하세요.';

    const partnerVal = isEdit ? item.partner : '';
    const priceVal = isEdit ? item.price : '';
    const offerVal = isEdit ? item.offerCode : '';
    const urlVal = isEdit ? item.url : '';
    const startVal = isEdit ? item.startDateTime : '';
    const endVal = isEdit ? item.endDateTime : '';

    const infoBoxTitle = isEdit ? item.offerTitle : '상품명 · 브랜드 · 구분';
    const infoBoxSub = isEdit ? item.offerSub : '판매정보를 선택하면 가격과 판매 URL이 표시됩니다.';

    const autoManageText = isEdit
      ? `제휴상품 ID &nbsp;<strong class="text-slate-800">${item.id}</strong> &nbsp;&nbsp;·&nbsp;&nbsp; 최근 검증 &nbsp;<strong class="text-slate-800">${item.lastVerified}</strong> &nbsp;&nbsp;·&nbsp;&nbsp; 링크 유효기한 &nbsp;<strong class="text-slate-800">${item.linkExpiry}</strong>`
      : '제휴상품 ID, 최근 검증일시, 링크 유효기한은 등록·검증 결과에 따라 자동 표시됩니다.';

    return `
      ${this.renderPageHeader(title, subtitle)}

      <div class="space-y-5">
        <!-- 카드 1 (제휴 연결 정보) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-sm font-bold text-slate-900 mb-4">제휴 연결 정보</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <!-- 좌상단: 제휴사 * -->
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">제휴사 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-partner"
                type="text"
                value="${this.escapeHtml(partnerVal)}"
                placeholder="제휴사명 입력"
                class="form-input w-full"
              />
            </div>

            <!-- 우상단: 금액 * -->
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">금액 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-price"
                type="text"
                value="${this.escapeHtml(priceVal)}"
                placeholder="금액 입력 (원)"
                class="form-input w-full"
              />
            </div>

            <!-- 좌하단: 판매정보 * 셀렉트 -->
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">판매정보 <span class="text-[#0066ff]">*</span></label>
              <select
                id="aff-form-offer"
                class="form-input w-full cursor-pointer"
                onchange="app.handleOfferSelectChange(this.value)"
              >
                <option value="" ${!isEdit ? 'selected' : ''}>판매정보 ID 또는 상품명 검색</option>
                ${this.state.offerCatalog
                  .map(
                    (cat) => `
                  <option value="${this.escapeHtml(cat.code)}" ${offerVal === cat.code ? 'selected' : ''}>
                    ${this.escapeHtml(cat.code)}
                  </option>
                `
                  )
                  .join('')}
              </select>
            </div>

            <!-- 우하단: 회색 안내 박스 -->
            <div class="flex flex-col justify-end">
              <div id="aff-offer-info-box" class="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 min-h-[64px] flex flex-col justify-center">
                <div id="aff-offer-info-title" class="text-xs font-bold ${isEdit ? 'text-slate-800' : 'text-slate-600'}">
                  ${this.escapeHtml(infoBoxTitle)}
                </div>
                <div id="aff-offer-info-sub" class="text-xs text-slate-500 mt-0.5">
                  ${this.escapeHtml(infoBoxSub)}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 카드 2 (URL 및 유효일시) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6 space-y-5">
          <!-- 상단 전체 너비 URL 입력 * -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">URL 입력 <span class="text-[#0066ff]">*</span></label>
            <input
              id="aff-form-url"
              type="text"
              value="${this.escapeHtml(urlVal)}"
              placeholder="URL을 입력해 주세요"
              class="form-input w-full"
            />
          </div>

          <!-- 하단 2열 유효 시작일시 / 유효 종료일시 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">유효 시작일시 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-start"
                type="text"
                value="${this.escapeHtml(startVal)}"
                placeholder="YYYY.MM.DD HH:mm"
                class="form-input w-full"
              />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">유효 종료일시 (선택)</label>
              <input
                id="aff-form-end"
                type="text"
                value="${this.escapeHtml(endVal)}"
                placeholder="종료일 없음"
                class="form-input w-full"
              />
            </div>
          </div>
        </div>

        <!-- 카드 3 (자동 관리 정보) -->
        <div class="bg-white border border-slate-200 rounded-xl p-5">
          <div class="text-xs font-bold text-slate-500 mb-1">자동 관리 정보</div>
          <div class="text-sm text-slate-600">
            ${autoManageText}
          </div>
        </div>

        <!-- 우측 하단 버튼 -->
        <div class="flex items-center justify-end gap-3 pt-2">
          <button onclick="app.navigate('affiliate', 'list')" class="btn-secondary">
            취소
          </button>
          <button onclick="app.submitAffiliateForm('${mode}')" class="btn-primary">
            ${isEdit ? '변경사항 저장' : '제휴 상품 등록'}
          </button>
        </div>
      </div>
    `;
  },

  handleOfferSelectChange(code) {
    const found = this.state.offerCatalog.find((c) => c.code === code);
    const titleEl = document.getElementById('aff-offer-info-title');
    const subEl = document.getElementById('aff-offer-info-sub');
    const partnerEl = document.getElementById('aff-form-partner');
    const priceEl = document.getElementById('aff-form-price');
    const urlEl = document.getElementById('aff-form-url');

    if (found) {
      if (titleEl) {
        titleEl.textContent = found.infoTitle;
        titleEl.className = 'text-xs font-bold text-slate-800';
      }
      if (subEl) subEl.textContent = found.infoSub;
      if (partnerEl && !partnerEl.value.trim()) partnerEl.value = found.partner;
      if (priceEl && !priceEl.value.trim()) priceEl.value = found.price;
      if (urlEl && !urlEl.value.trim()) urlEl.value = found.url;
    } else {
      if (titleEl) {
        titleEl.textContent = '상품명 · 브랜드 · 구분';
        titleEl.className = 'text-xs font-bold text-slate-600';
      }
      if (subEl) subEl.textContent = '판매정보를 선택하면 가격과 판매 URL이 표시됩니다.';
    }
  },

  submitAffiliateForm(mode) {
    const partner = (document.getElementById('aff-form-partner')?.value || '').trim() || '신규제휴사';
    let price = (document.getElementById('aff-form-price')?.value || '').trim() || '19,000원';
    if (!price.endsWith('원')) price += '원';

    const offerCode = document.getElementById('aff-form-offer')?.value || 'OF-001 · 엡손 M1120';
    const url = (document.getElementById('aff-form-url')?.value || '').trim() || 'https://shop.example/products/OF-NEW';
    const start = (document.getElementById('aff-form-start')?.value || '').trim() || '2026.10.01 00:00';
    const end = (document.getElementById('aff-form-end')?.value || '').trim();

    const matchedCatalog = this.state.offerCatalog.find((c) => c.code === offerCode);
    const productName = matchedCatalog ? matchedCatalog.name : offerCode.split('·')[1]?.trim() || '제휴 상품';

    // 기간 포맷 (예: 10.01 ~ 12.31 또는 10.01 ~ 종료 없음)
    const formatShortDate = (dtStr) => {
      const m = dtStr.match(/(\d{2})\.(\d{2})/);
      if (dtStr.length >= 10 && dtStr.includes('.')) {
        const parts = dtStr.split(' ')[0].split('.');
        if (parts.length >= 3) return `${parts[1]}.${parts[2]}`;
      }
      return m ? m[0] : '10.01';
    };

    const startShort = formatShortDate(start);
    const periodStr = end ? `${startShort} ~ ${formatShortDate(end)}` : `${startShort} ~ 종료 없음`;

    if (mode === 'edit') {
      const idx = this.state.affiliateProducts.findIndex((p) => p.id === this.state.selectedAffiliateId);
      if (idx !== -1) {
        this.state.affiliateProducts[idx] = {
          ...this.state.affiliateProducts[idx],
          partner,
          name: productName,
          price,
          url,
          period: periodStr,
          offerCode,
          offerTitle: matchedCatalog ? matchedCatalog.infoTitle : `일반 상품 · ${partner} ${productName}`,
          offerSub: matchedCatalog ? matchedCatalog.infoSub : `${price.replace('원', '')} KRW · 배송비 0 KRW`,
          startDateTime: start,
          endDateTime: end,
        };
      }
      this.showToast('제휴 상품 변경사항이 저장되었습니다.');
    } else {
      const nextNum = this.state.affiliateProducts.length + 1;
      const newId = `AF-00${nextNum}`;
      const newItem = {
        id: newId,
        partner,
        name: productName,
        price,
        url,
        status: '제휴 중',
        period: periodStr,
        offerCode,
        offerTitle: matchedCatalog ? matchedCatalog.infoTitle : `일반 상품 · ${partner} ${productName}`,
        offerSub: matchedCatalog ? matchedCatalog.infoSub : `${price.replace('원', '')} KRW · 배송비 0 KRW`,
        startDateTime: start,
        endDateTime: end,
        lastVerified: '2026.10.12 09:00',
        linkExpiry: '2026.10.13 09:00',
      };
      this.state.affiliateProducts.unshift(newItem);
      this.state.selectedAffiliateId = newId;
      this.state.affiliateForceEmpty = false;
      this.showToast(`새 제휴 상품(${newId})이 등록되었습니다.`);
    }

    this.state.affiliateSubView = 'list';
    this.renderContent();
  },

  // 삭제 확인 모달 렌더링 (PPT 62p)
  renderModal() {
    const modalRoot = document.getElementById('modal-root');
    if (!modalRoot) return;

    if (!this.state.showDeleteModal) {
      modalRoot.innerHTML = '';
      return;
    }

    const item =
      this.state.affiliateProducts.find((p) => p.id === this.state.selectedAffiliateId) ||
      this.state.affiliateProducts[0];

    if (!item) {
      modalRoot.innerHTML = '';
      return;
    }

    modalRoot.innerHTML = `
      <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
        <div class="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-[420px] p-6">
          <h3 class="text-xl font-bold text-slate-900">제휴 상품을 삭제할까요?</h3>
          <p class="font-bold text-slate-900 mt-4 text-sm">
            ${this.escapeHtml(item.id)} &nbsp;·&nbsp; ${this.escapeHtml(item.partner)} ${this.escapeHtml(item.name)}
          </p>
          <p class="text-sm text-slate-500 mt-1.5">
            해당 상품의 제휴 연결이 삭제됩니다.
          </p>
          <div class="grid grid-cols-2 gap-3 mt-6">
            <button onclick="app.closeDeleteModal()" class="btn-secondary w-full">
              취소
            </button>
            <button onclick="app.confirmDeleteAffiliate()" class="btn-danger w-full">
              삭제
            </button>
          </div>
        </div>
      </div>
    `;
  },

  // =========================================================================
  // [화면 3] 고객정보 & 고객 세부정보 (PPT 61p, 62p, 68p, 69p)
  // =========================================================================
  getCustomersHtml() {
    if (this.state.customerSubView === 'detail') {
      return this.getCustomerDetailHtml();
    }
    return this.getCustomerListHtml();
  },

  getCustomerListHtml() {
    const search = this.state.customerSearch.trim().toLowerCase();
    const typeFilter = this.state.customerTypeFilter;
    const statusFilter = this.state.customerStatusFilter;

    const filtered = this.state.customers.filter((c) => {
      const matchSearch = !search || c.id.toLowerCase().includes(search);
      const matchType =
        typeFilter === '전체' ||
        (typeFilter === '구독' && c.subscribed === 'O') ||
        (typeFilter === '미구독' && c.subscribed !== 'O');
      const matchStatus = statusFilter === '전체' || c.status === statusFilter;
      return matchSearch && matchType && matchStatus;
    });

    return `
      ${this.renderPageHeader('고객정보', '회원 계정과 프로필 정보를 확인하세요. · 예시 데이터')}

      <!-- 상단 검색 필터 바 -->
      <div class="flex flex-wrap items-end gap-3 mb-6">
        <div>
          <label class="block text-xs font-bold text-slate-600 mb-1.5">ID / 닉네임</label>
          <input
            type="text"
            value="${this.escapeHtml(this.state.customerSearch)}"
            placeholder="검색어 입력"
            class="form-input w-[320px]"
            oninput="app.handleCustomerFilterChange(this.value, null, null)"
          />
        </div>
        <div>
          <label class="block text-xs font-bold text-slate-600 mb-1.5">회원 유형</label>
          <select
            class="form-input w-[190px] cursor-pointer"
            onchange="app.handleCustomerFilterChange(null, this.value, null)"
          >
            <option value="전체" ${typeFilter === '전체' ? 'selected' : ''}>전체</option>
            <option value="구독" ${typeFilter === '구독' ? 'selected' : ''}>구독자 (O)</option>
            <option value="미구독" ${typeFilter === '미구독' ? 'selected' : ''}>미구독자</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-bold text-slate-600 mb-1.5">계정 상태</label>
          <select
            class="form-input w-[190px] cursor-pointer"
            onchange="app.handleCustomerFilterChange(null, null, this.value)"
          >
            <option value="전체" ${statusFilter === '전체' ? 'selected' : ''}>전체</option>
            <option value="정상" ${statusFilter === '정상' ? 'selected' : ''}>정상</option>
            <option value="휴면" ${statusFilter === '휴면' ? 'selected' : ''}>휴면</option>
          </select>
        </div>
      </div>

      <!-- 테이블 -->
      <div class="w-full">
        <div class="grid grid-cols-5 items-center px-6 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
          <div>ID</div>
          <div>구독여부</div>
          <div>성별</div>
          <div>연령대</div>
          <div>계정 상태</div>
        </div>

        <div id="customer-table-body" class="space-y-2 mt-2">
          ${this.getCustomerRowsHtml(filtered)}
        </div>
      </div>

      <!-- 하단 안내 캡션 -->
      <div class="mt-4 text-sm text-slate-500">
        구독자는 O, 미구독자는 공백으로 표시합니다. · 성별·생년월일 미입력 시 미등록으로 표시합니다.
      </div>
    `;
  },

  getCustomerRowsHtml(filtered) {
    if (filtered.length === 0) {
      return `
        <div class="bg-slate-100/80 text-slate-500 rounded-lg p-4 text-sm">
          조건에 일치하는 고객정보가 없습니다.
        </div>
      `;
    }

    return filtered
      .map(
        (c) => `
        <div class="grid grid-cols-5 items-center bg-white border border-slate-200 rounded-lg px-6 py-3.5 text-sm">
          <div>
            <span
              onclick="app.openCustomerDetail('${c.id}')"
              class="text-blue-600 underline cursor-pointer font-medium hover:text-blue-800"
            >${c.id}</span>
          </div>
          <div class="font-semibold text-slate-900">${c.subscribed}</div>
          <div class="text-slate-700">${c.gender || '미등록'}</div>
          <div class="text-slate-700">${c.ageGroup || '미등록'}</div>
          <div class="text-slate-800 font-medium">${c.status}</div>
        </div>
      `
      )
      .join('');
  },

  handleCustomerFilterChange(searchVal, typeVal, statusVal) {
    if (searchVal !== null) this.state.customerSearch = searchVal;
    if (typeVal !== null) this.state.customerTypeFilter = typeVal;
    if (statusVal !== null) this.state.customerStatusFilter = statusVal;

    const search = this.state.customerSearch.trim().toLowerCase();
    const typeFilter = this.state.customerTypeFilter;
    const statusFilter = this.state.customerStatusFilter;

    const filtered = this.state.customers.filter((c) => {
      const matchSearch = !search || c.id.toLowerCase().includes(search);
      const matchType =
        typeFilter === '전체' ||
        (typeFilter === '구독' && c.subscribed === 'O') ||
        (typeFilter === '미구독' && c.subscribed !== 'O');
      const matchStatus = statusFilter === '전체' || c.status === statusFilter;
      return matchSearch && matchType && matchStatus;
    });

    const tbody = document.getElementById('customer-table-body');
    if (tbody) {
      tbody.innerHTML = this.getCustomerRowsHtml(filtered);
    }
  },

  openCustomerDetail(customerId) {
    this.state.selectedCustomerId = customerId;
    this.state.customerSubView = 'detail';
    this.renderContent();
  },

  // [3-2. 고객 세부정보 화면 (PPT 69p)]
  getCustomerDetailHtml() {
    const c =
      this.state.customers.find((item) => item.id === this.state.selectedCustomerId) ||
      this.state.customers[0];

    const isSub = c.subscribed === 'O';
    const subText = isSub ? '구독 중' : '미구독';
    const subDateText = isSub ? c.subStartDate : '-';

    return `
      ${this.renderPageHeader('고객 세부정보', `고객정보 / ${c.id} · 예시 데이터`)}

      <!-- 정보 카드 (흰색 큰 박스 내 가로 구분선 리스트) -->
      <div class="bg-white border border-slate-200 rounded-xl px-7 py-2">
        <div class="flex items-center py-4 border-b border-slate-200 text-sm">
          <div class="w-[180px] text-slate-500">ID</div>
          <div class="font-bold text-slate-900">${c.id}</div>
        </div>
        <div class="flex items-center py-4 border-b border-slate-200 text-sm">
          <div class="w-[180px] text-slate-500">성별</div>
          <div class="font-bold text-slate-900">${c.gender || '미등록'}</div>
        </div>
        <div class="flex items-center py-4 border-b border-slate-200 text-sm">
          <div class="w-[180px] text-slate-500">연령대</div>
          <div class="font-bold text-slate-900">${c.ageGroup || '미등록'}</div>
        </div>
        <div class="flex items-center py-4 border-b border-slate-200 text-sm">
          <div class="w-[180px] text-slate-500">구독 여부</div>
          <div class="font-bold text-slate-900">${subText}</div>
        </div>
        <div class="flex items-center py-4 text-sm">
          <div class="w-[180px] text-slate-500">구독 시작일자</div>
          <div class="font-bold text-slate-900">${subDateText}</div>
        </div>
      </div>

      <!-- 하단 버튼 영역 (좌측 정렬) -->
      <div class="flex items-center gap-3 mt-6">
        <button onclick="app.resetCustomerPassword('${c.id}')" class="btn-primary">
          비밀번호 초기화
        </button>
        <button onclick="app.navigate('customers', 'list')" class="btn-secondary">
          목록
        </button>
      </div>
    `;
  },

  resetCustomerPassword(customerId) {
    alert('비밀번호 초기화 안내가 발송되었습니다.');
    this.showToast(`${customerId} 고객님께 비밀번호 초기화 안내가 발송되었습니다.`);
  },

  // =========================================================================
  // [화면 4] 고객상담 (상담관리 목록 / 고객 상담 채팅 상세 / 상담설정)
  // =========================================================================
  getCounselingHtml() {
    const sub = this.state.counselingSubView;
    if (sub === 'detail') {
      return this.getCounselingDetailHtml();
    }
    if (sub === 'settings') {
      return this.getCounselingSettingsHtml();
    }
    return this.getCounselingListHtml();
  },

  // [4-1. 상담관리 목록 화면 (PPT 61p, 65p)]
  getCounselingListHtml() {
    const search = this.state.counselingSearch.trim().toLowerCase();
    const catFilter = this.state.counselingCategoryFilter;

    const filtered = this.state.counselingList.filter((item) => {
      const matchSearch =
        !search ||
        item.id.toLowerCase().includes(search) ||
        item.customerId.toLowerCase().includes(search) ||
        item.title.toLowerCase().includes(search);
      const matchCat =
        catFilter === '전체' || item.category === catFilter || item.status === catFilter;
      return matchSearch && matchCat;
    });

    return `
      ${this.renderPageHeader('상담관리', '문의 제목·분류·상태·담당자를 확인하세요. · 예시 데이터')}

      <!-- 상단 검색 필터 바 -->
      <div class="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">문의 검색</label>
            <input
              type="text"
              value="${this.escapeHtml(this.state.counselingSearch)}"
              placeholder="문의 ID, 고객 ID 또는 제목"
              class="form-input w-[360px]"
              oninput="app.handleCounselingFilterChange(this.value, null)"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">분류 / 상태</label>
            <select
              class="form-input w-[220px] cursor-pointer"
              onchange="app.handleCounselingFilterChange(null, this.value)"
            >
              <option value="전체" ${catFilter === '전체' ? 'selected' : ''}>전체</option>
              <option value="진행 중" ${catFilter === '진행 중' ? 'selected' : ''}>상태: 진행 중</option>
              <option value="대기" ${catFilter === '대기' ? 'selected' : ''}>상태: 대기</option>
              <option value="완료" ${catFilter === '완료' ? 'selected' : ''}>상태: 완료</option>
              <option value="결제" ${catFilter === '결제' ? 'selected' : ''}>분류: 결제</option>
              <option value="이용 문의" ${catFilter === '이용 문의' ? 'selected' : ''}>분류: 이용 문의</option>
              <option value="오류" ${catFilter === '오류' ? 'selected' : ''}>분류: 오류</option>
              <option value="계정" ${catFilter === '계정' ? 'selected' : ''}>분류: 계정</option>
              <option value="구독" ${catFilter === '구독' ? 'selected' : ''}>분류: 구독</option>
            </select>
          </div>
        </div>

        <!-- 우측 상담설정 버튼 -->
        <div>
          <button
            onclick="app.navigate('counseling', 'settings')"
            class="bg-white border border-[#cbd5e1] text-[#0066ff] font-bold rounded-lg px-5 py-2.5 text-sm h-[44px] hover:bg-slate-50 transition-colors"
          >
            상담설정
          </button>
        </div>
      </div>

      <!-- 테이블 -->
      <div class="w-full">
        <div class="grid grid-cols-12 items-center px-6 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
          <div class="col-span-2">문의 ID</div>
          <div class="col-span-2">고객 ID</div>
          <div class="col-span-3">문의 제목</div>
          <div class="col-span-1">분류</div>
          <div class="col-span-1">상태</div>
          <div class="col-span-1">담당자</div>
          <div class="col-span-2 text-right">최근 메시지</div>
        </div>

        <div id="counseling-table-body" class="space-y-2 mt-2">
          ${this.getCounselingRowsHtml(filtered)}
        </div>
      </div>

      <!-- 하단 캡션 -->
      <div class="mt-4 text-sm text-slate-500">
        최근 메시지 시간순 · 1–${filtered.length} / ${this.state.counselingList.length}건
      </div>
    `;
  },

  getCounselingRowsHtml(filtered) {
    if (filtered.length === 0) {
      return `
        <div class="bg-slate-100/80 text-slate-500 rounded-lg p-4 text-sm">
          검색된 상담 내역이 없습니다.
        </div>
      `;
    }

    return filtered
      .map((item) => {
        let statusStyle = 'text-slate-700 font-semibold';
        if (item.status === '진행 중') statusStyle = 'text-[#0066ff] font-bold';
        else if (item.status === '대기') statusStyle = 'text-amber-600 font-bold';
        else if (item.status === '완료') statusStyle = 'text-slate-500 font-semibold';

        return `
          <div
            onclick="app.openCounselingDetail('${item.id}')"
            class="grid grid-cols-12 items-center bg-white border border-slate-200 hover:border-[#0066ff] rounded-lg px-6 py-4 text-sm cursor-pointer transition-all"
          >
            <div class="col-span-2 font-semibold text-slate-900">${item.id}</div>
            <div class="col-span-2 text-slate-800 font-medium">${item.customerId}</div>
            <div class="col-span-3 font-medium text-slate-900 pr-2 truncate">${this.escapeHtml(item.title)}</div>
            <div class="col-span-1 text-slate-600">${item.category}</div>
            <div class="col-span-1 ${statusStyle}">${item.status}</div>
            <div class="col-span-1 text-slate-700">${item.agent}</div>
            <div class="col-span-2 text-right text-slate-500">${item.lastMessageTime}</div>
          </div>
        `;
      })
      .join('');
  },

  handleCounselingFilterChange(searchVal, catVal) {
    if (searchVal !== null) this.state.counselingSearch = searchVal;
    if (catVal !== null) this.state.counselingCategoryFilter = catVal;

    const search = this.state.counselingSearch.trim().toLowerCase();
    const catFilter = this.state.counselingCategoryFilter;
    const filtered = this.state.counselingList.filter((item) => {
      const matchSearch =
        !search ||
        item.id.toLowerCase().includes(search) ||
        item.customerId.toLowerCase().includes(search) ||
        item.title.toLowerCase().includes(search);
      const matchCat =
        catFilter === '전체' || item.category === catFilter || item.status === catFilter;
      return matchSearch && matchCat;
    });

    const tbody = document.getElementById('counseling-table-body');
    if (tbody) {
      tbody.innerHTML = this.getCounselingRowsHtml(filtered);
    }
  },

  openCounselingDetail(csId) {
    this.state.selectedCounselingId = csId;
    this.state.counselingSubView = 'detail';
    this.renderContent();
  },

  // [4-2. 고객 상담 (1:1 대화 상세) 화면 (PPT 66p)]
  getCounselingDetailHtml() {
    const cs =
      this.state.counselingList.find((item) => item.id === this.state.selectedCounselingId) ||
      this.state.counselingList[0];

    const customer =
      this.state.customers.find((c) => c.id === cs.customerId) || {
        id: cs.customerId,
        ageGroup: '20대',
        gender: '여성'
      };

    return `
      ${this.renderPageHeader('고객 상담', `상담관리 / ${cs.customerId} · ${cs.status}`)}

      <!-- 상단 액션 버튼 (좌측 정렬) -->
      <div class="flex items-center gap-2.5 mb-6">
        <button onclick="app.navigate('counseling', 'list')" class="btn-secondary">
          목록으로
        </button>
        <button onclick="app.completeCounseling('${cs.id}')" class="btn-primary">
          상담 완료
        </button>
      </div>

      <!-- 본문 2열 분할 레이아웃 (좌측 대화 카드 약 68%, 우측 고객정보 카드 약 32%) -->
      <div class="flex flex-col lg:flex-row items-start gap-6">
        <!-- 좌측 대화 카드 (약 68%) -->
        <div class="w-full lg:w-[68%] bg-white border border-slate-200 rounded-xl p-6">
          <div class="mb-5">
            <h2 class="text-base font-bold text-slate-900">${cs.customerId} 고객과의 대화</h2>
            <p class="text-xs text-slate-500 mt-0.5">2026년 10월 12일</p>
          </div>

          <!-- 대화 메시지 리스트 -->
          <div id="chat-message-list" class="space-y-3 mb-6">
            ${cs.messages
              .map(
                (m) => `
              <div class="bg-[#f1f5f9] rounded-lg p-4 mb-3">
                <div class="font-bold text-sm text-slate-900">${this.escapeHtml(m.sender)}</div>
                <div class="text-sm text-slate-800 mt-1">${this.escapeHtml(m.text)}</div>
                <div class="text-xs text-slate-500 mt-1.5">${this.escapeHtml(m.time)}</div>
              </div>
            `
              )
              .join('')}
          </div>

          <!-- 하단 답변 입력 영역 -->
          <div class="pt-2 border-t border-slate-100">
            <label class="block text-sm font-bold text-slate-900 mb-2">답변</label>
            <div class="flex items-center gap-2.5">
              <input
                id="chat-reply-input"
                type="text"
                placeholder="메시지를 입력하세요"
                class="form-input flex-1"
                onkeydown="if(event.key==='Enter') app.sendCounselingReply('${cs.id}')"
              />
              <button onclick="app.sendCounselingReply('${cs.id}')" class="btn-primary">
                전송
              </button>
            </div>
          </div>
        </div>

        <!-- 우측 고객정보 카드 (약 32%, 높이 자동 맞춤) -->
        <div class="w-full lg:w-[32%] bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-base font-bold text-slate-900 pb-3 mb-4 border-b border-slate-200">고객정보</h2>

          <div>
            <div class="text-xs text-slate-500">ID</div>
            <div class="text-lg font-bold text-slate-900 mt-0.5 mb-4">${customer.id}</div>

            <div class="text-xs text-slate-500">연령대</div>
            <div class="text-lg font-bold text-slate-900 mt-0.5 mb-4">${customer.ageGroup}</div>

            <div class="text-xs text-slate-500">성별</div>
            <div class="text-lg font-bold text-slate-900 mt-0.5 mb-4">${customer.gender}</div>
          </div>

          <!-- 카드 하단 안내 박스 -->
          <div class="bg-[#ebf3ff] text-slate-600 text-xs rounded-lg p-3 mt-2">
            상담 중 필요한 고객 기본정보를 확인하세요.
          </div>
        </div>
      </div>
    `;
  },

  completeCounseling(csId) {
    const cs = this.state.counselingList.find((item) => item.id === csId);
    if (cs) {
      cs.status = '완료';
      this.renderContent();
      this.showToast(`${cs.customerId} 고객 상담이 '완료' 상태로 변경되었습니다.`);
    }
  },

  sendCounselingReply(csId) {
    const input = document.getElementById('chat-reply-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    const cs = this.state.counselingList.find((item) => item.id === csId);
    if (!cs) return;

    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const timeStr = `${hh}:${mm}`;

    cs.messages.push({
      sender: '김상담',
      text,
      time: timeStr,
    });
    cs.lastMessageTime = `10.12 ${timeStr}`;
    if (cs.agent === '미배정') cs.agent = '김상담';

    this.renderContent();
    const newInput = document.getElementById('chat-reply-input');
    if (newInput) newInput.focus();
  },

  // [4-3. 상담설정 화면 (PPT 67p)]
  getCounselingSettingsHtml() {
    const s = this.state.counselingSettings;

    return `
      ${this.renderPageHeader('상담설정', '상담 가능시간과 부재중 안내 메시지를 관리하세요.')}

      <!-- 상단 전환 탭 버튼 (좌측 정렬) -->
      <div class="flex items-center gap-2.5 mb-6">
        <button onclick="app.navigate('counseling', 'list')" class="btn-secondary">
          상담관리
        </button>
        <button class="btn-primary">
          상담설정
        </button>
      </div>

      <div class="space-y-5">
        <!-- 카드 1 (상담 가능시간) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-base font-bold text-slate-900 mb-4">상담 가능시간</h2>
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="md:col-span-2">
              <label class="block text-xs font-bold text-slate-600 mb-1.5">운영 요일</label>
              <input
                id="cs-setting-days"
                type="text"
                value="${this.escapeHtml(s.days)}"
                class="form-input w-full"
              />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-600 mb-1.5">시작 시간</label>
              <input
                id="cs-setting-start"
                type="text"
                value="${this.escapeHtml(s.startTime)}"
                class="form-input w-full"
              />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-600 mb-1.5">종료 시간</label>
              <input
                id="cs-setting-end"
                type="text"
                value="${this.escapeHtml(s.endTime)}"
                class="form-input w-full"
              />
            </div>
          </div>
          <p class="text-xs text-slate-500 mt-3">대한민국 표준시(KST) 기준으로 표시됩니다.</p>
        </div>

        <!-- 카드 2 (부재중 메시지) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-base font-bold text-slate-900 mb-4">부재중 메시지</h2>
          <textarea
            id="cs-setting-away"
            class="w-full h-[120px] bg-slate-50 border border-slate-200 rounded-lg p-4 text-sm text-slate-800 outline-none focus:border-[#0066ff] resize-none leading-relaxed"
          >${this.escapeHtml(s.awayMessage)}</textarea>
          <p class="text-xs text-slate-500 mt-3">상담 가능시간 외에 고객에게 표시되는 메시지입니다.</p>
        </div>

        <!-- 하단 저장 버튼 (좌측 정렬) -->
        <div class="pt-1">
          <button onclick="app.saveCounselingSettings()" class="btn-primary">
            설정 저장
          </button>
        </div>
      </div>
    `;
  },

  saveCounselingSettings() {
    const days = document.getElementById('cs-setting-days')?.value || '월요일 ~ 금요일';
    const startTime = document.getElementById('cs-setting-start')?.value || '09:00';
    const endTime = document.getElementById('cs-setting-end')?.value || '18:00';
    const awayMessage = document.getElementById('cs-setting-away')?.value || '';

    this.state.counselingSettings = { days, startTime, endTime, awayMessage };
    alert('상담 설정이 저장되었습니다.');
    this.showToast('상담 가능시간 및 부재중 메시지가 저장되었습니다.');
  },

  // =========================================================================
  // [화면 5] 통계 (PPT 70p)
  // =========================================================================
  getStatsDatasetByUnit(unit) {
    if (unit === 'monthly') {
      return {
        unitLabel: '월별',
        periodText: '2026.04 ~ 2026.10',
        labels: ['04월', '05월', '06월', '07월', '08월', '09월', '10월'],
        subJoin: [48, 56, 62, 74, 79, 88, 94],
        subLeave: [9, 11, 10, 13, 12, 14, 11],
        subSales: [50, 58, 65, 72, 80, 89, 95],
        royaltySales: [11, 13, 14, 15, 17, 19, 21]
      };
    }
    if (unit === 'yearly') {
      return {
        unitLabel: '연도별',
        periodText: '2022 ~ 2026',
        labels: ['2022', '2023', '2024', '2025', '2026'],
        subJoin: [35, 52, 68, 84, 96],
        subLeave: [7, 9, 11, 13, 12],
        subSales: [38, 55, 71, 85, 97],
        royaltySales: [8, 11, 14, 18, 22]
      };
    }
    // 기본값: 일별 (PPT 70p 명세 100% 일치)
    return {
      unitLabel: '일별',
      periodText: '2026.10.06 ~ 2026.10.12',
      labels: ['10.06', '10.07', '10.08', '10.09', '10.10', '10.11', '10.12'],
      subJoin: [52, 71, 63, 81, 66, 91, 86],
      subLeave: [10, 12, 8, 15, 11, 10, 12],
      subSales: [52, 71, 63, 81, 66, 91, 86],
      royaltySales: [10, 12, 11, 14, 13, 16, 15]
    };
  },

  getStatsHtml() {
    const unit = this.state.statsUnit;
    const dataConfig = this.getStatsDatasetByUnit(unit);

    const btnClass = (target) => (unit === target ? 'btn-primary' : 'btn-secondary');

    return `
      ${this.renderPageHeader('통계', '가입·해지와 매출 추이를 기간별로 확인하세요. · 예시 데이터')}

      <!-- 상단 필터 컨트롤 바 -->
      <div class="flex flex-wrap items-end gap-4 mb-6">
        <div class="flex items-center gap-2">
          <button onclick="app.changeStatsUnit('daily')" class="${btnClass('daily')}">일별</button>
          <button onclick="app.changeStatsUnit('monthly')" class="${btnClass('monthly')}">월별</button>
          <button onclick="app.changeStatsUnit('yearly')" class="${btnClass('yearly')}">연도별</button>
        </div>

        <div>
          <label class="block text-xs font-bold text-slate-600 mb-1.5">조회 기간</label>
          <input
            type="text"
            value="${this.escapeHtml(this.state.statsPeriodInput)}"
            class="form-input w-[280px]"
            onchange="app.state.statsPeriodInput = this.value"
          />
        </div>
      </div>

      <div class="space-y-6">
        <!-- 차트 카드 1: 일별 구독 가입 · 해지 추이 (명) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-base font-bold text-slate-900">${dataConfig.unitLabel} 구독 가입 · 해지 추이 (명)</h2>
          <!-- 커스텀 범례 -->
          <div class="flex items-center gap-5 mt-2 mb-4 text-xs text-slate-600 font-medium">
            <div class="flex items-center gap-2">
              <span class="w-4 h-0.5 bg-[#0066ff] inline-block"></span>
              <span>구독 가입</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="w-4 h-0.5 bg-[#e11d48] inline-block"></span>
              <span>구독 해지</span>
            </div>
          </div>
          <div class="h-[220px] w-full">
            <canvas id="stats-sub-chart"></canvas>
          </div>
        </div>

        <!-- 차트 카드 2: 일별 매출 추이 (만원) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-base font-bold text-slate-900">${dataConfig.unitLabel} 매출 추이 (만원)</h2>
          <!-- 커스텀 범례 -->
          <div class="flex items-center gap-5 mt-2 mb-4 text-xs text-slate-600 font-medium">
            <div class="flex items-center gap-2">
              <span class="w-4 h-0.5 bg-[#0066ff] inline-block"></span>
              <span>구독 매출</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="w-4 h-0.5 bg-[#e11d48] inline-block"></span>
              <span>URL 로열티 매출</span>
            </div>
          </div>
          <div class="h-[220px] w-full">
            <canvas id="stats-sales-chart"></canvas>
          </div>
        </div>
      </div>

      <!-- 하단 안내 캡션 -->
      <div class="mt-4 text-sm text-slate-500">
        기간 집계 기준: KST &nbsp;·&nbsp; 선택한 기간의 가입·해지 및 매출을 합산합니다.
      </div>
    `;
  },

  changeStatsUnit(unit) {
    this.state.statsUnit = unit;
    const cfg = this.getStatsDatasetByUnit(unit);
    this.state.statsPeriodInput = cfg.periodText;
    this.renderContent();
  },

  createCommonLineChartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false, // 커스텀 범례 사용
        },
        tooltip: {
          mode: 'index',
          intersect: false,
        },
      },
      scales: {
        x: {
          grid: {
            color: '#f1f5f9',
          },
          ticks: {
            color: '#64748b',
            font: {
              family: 'Pretendard',
              size: 12,
            },
          },
        },
        y: {
          min: 0,
          max: 100,
          afterBuildTicks: (axis) => {
            axis.ticks = [{ value: 0 }, { value: 33 }, { value: 67 }, { value: 100 }];
          },
          grid: {
            color: '#f1f5f9',
          },
          ticks: {
            color: '#64748b',
            font: {
              family: 'Pretendard',
              size: 12,
            },
          },
        },
      },
    };
  },

  initStatsCharts() {
    const cfg = this.getStatsDatasetByUnit(this.state.statsUnit);
    const subCanvas = document.getElementById('stats-sub-chart');
    const salesCanvas = document.getElementById('stats-sales-chart');

    if (subCanvas && window.Chart) {
      if (this.charts.statsSubChart) {
        this.charts.statsSubChart.destroy();
      }
      this.charts.statsSubChart = new Chart(subCanvas.getContext('2d'), {
        type: 'line',
        data: {
          labels: cfg.labels,
          datasets: [
            {
              label: '구독 가입',
              data: cfg.subJoin,
              borderColor: '#0066ff',
              backgroundColor: '#0066ff',
              borderWidth: 2,
              tension: 0,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
            {
              label: '구독 해지',
              data: cfg.subLeave,
              borderColor: '#e11d48',
              backgroundColor: '#e11d48',
              borderWidth: 2,
              tension: 0,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
          ],
        },
        options: this.createCommonLineChartOptions(),
      });
    }

    if (salesCanvas && window.Chart) {
      if (this.charts.statsSalesChart) {
        this.charts.statsSalesChart.destroy();
      }
      this.charts.statsSalesChart = new Chart(salesCanvas.getContext('2d'), {
        type: 'line',
        data: {
          labels: cfg.labels,
          datasets: [
            {
              label: '구독 매출',
              data: cfg.subSales,
              borderColor: '#0066ff',
              backgroundColor: '#0066ff',
              borderWidth: 2,
              tension: 0,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
            {
              label: 'URL 로열티 매출',
              data: cfg.royaltySales,
              borderColor: '#e11d48',
              backgroundColor: '#e11d48',
              borderWidth: 2,
              tension: 0,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
          ],
        },
        options: this.createCommonLineChartOptions(),
      });
    }
  },

  // =========================================================================
  // [화면 6] MAIN · 대시보드 (사이드바 첫 번째 MAIN 메뉴 클릭 시 화면)
  // =========================================================================
  getMainDashboardHtml() {
    return `
      ${this.renderPageHeader(
        'MAIN · 대시보드',
        '구독 현황과 매출을 한눈에 확인하세요. · 표시된 수치는 예시 데이터입니다.'
      )}

      <!-- 상단 3열 요약 카드 -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <div class="text-xs font-bold text-slate-500">누적 구독자수</div>
          <div class="text-2xl font-bold text-slate-900 mt-2">12,480명</div>
          <div class="text-xs text-slate-500 mt-1.5">전체 기간 누적 가입</div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <div class="text-xs font-bold text-slate-500">당일 구독 가입자수</div>
          <div class="text-2xl font-bold text-[#0066ff] mt-2">86명</div>
          <div class="text-xs text-slate-500 mt-1.5">2026.10.12 가입 완료</div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <div class="text-xs font-bold text-slate-500">당일 구독 해지인원수</div>
          <div class="text-2xl font-bold text-rose-600 mt-2">12명</div>
          <div class="text-xs text-slate-500 mt-1.5">2026.10.12 해지 완료</div>
        </div>
      </div>

      <!-- 중단 차트 카드 (일자별 구독 가입 · 해지) -->
      <div class="bg-white border border-slate-200 rounded-xl p-6 mb-6">
        <h2 class="text-base font-bold text-slate-900">일자별 구독 가입 · 해지</h2>
        <div class="flex items-center gap-4 mt-1.5 mb-4 text-xs text-slate-600 font-medium">
          <span class="flex items-center gap-1.5">
            <span class="w-3.5 h-0.5 bg-[#0066ff] inline-block"></span>
            가입 — 파랑
          </span>
          <span class="flex items-center gap-1.5">
            <span class="w-3.5 h-0.5 bg-[#e11d48] inline-block"></span>
            해지 — 빨강
          </span>
        </div>
        <div class="h-[220px] w-full">
          <canvas id="main-sub-chart"></canvas>
        </div>
      </div>

      <!-- 하단 매출 카드 (구독 매출) -->
      <div class="bg-white border border-slate-200 rounded-xl p-6">
        <h2 class="text-base font-bold text-slate-900 mb-4">구독 매출</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div class="bg-slate-50 border border-slate-200/80 rounded-lg p-5">
            <div class="text-xs font-bold text-slate-500">당월 누적 매출금액</div>
            <div class="text-2xl font-bold text-slate-900 mt-2">₩24,800,000</div>
          </div>
          <div class="bg-slate-50 border border-slate-200/80 rounded-lg p-5">
            <div class="text-xs font-bold text-slate-500">금일 누적 매출금액</div>
            <div class="text-2xl font-bold text-[#0066ff] mt-2">₩860,000</div>
          </div>
        </div>
      </div>

      <!-- 하단 캡션 -->
      <div class="mt-4 text-sm text-slate-500">
        집계 기준 · KST 00:00–23:59 &nbsp;&nbsp;/&nbsp;&nbsp; 구독 당월 매출: 10.01–10.12
      </div>
    `;
  },

  initMainChart() {
    const canvas = document.getElementById('main-sub-chart');
    if (!canvas || !window.Chart) return;

    if (this.charts.mainSubChart) {
      this.charts.mainSubChart.destroy();
    }

    const cfg = this.getStatsDatasetByUnit('daily');
    this.charts.mainSubChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: cfg.labels,
        datasets: [
          {
            label: '구독 가입',
            data: cfg.subJoin,
            borderColor: '#0066ff',
            backgroundColor: '#0066ff',
            borderWidth: 2,
            tension: 0,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
          {
            label: '구독 해지',
            data: cfg.subLeave,
            borderColor: '#e11d48',
            backgroundColor: '#e11d48',
            borderWidth: 2,
            tension: 0,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
        ],
      },
      options: this.createCommonLineChartOptions(),
    });
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

window.addEventListener('DOMContentLoaded', () => {
  app.init();
});

