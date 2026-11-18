const getInitialKstRange = (days = 6) => {
  const nowKst = Date.now() + 9 * 60 * 60 * 1000;
  const end = new Date(nowKst).toISOString().slice(0, 10).replaceAll('-', '.');
  const start = new Date(nowKst - days * 24 * 60 * 60 * 1000).toISOString().slice(0, 10).replaceAll('-', '.');
  return `${start} ~ ${end}`;
};

const consoleState = {
  // 현재 활성화된 화면 및 서브 상태
  state: {
    currentPage: 'main', // 'main' | 'affiliate' | 'crawling' | 'counseling' | 'stats' | 'customers'

    // [화면 1] 상품 크롤링 검토 상태
    crawlingPeriod: getInitialKstRange(6),
    crawlingData: [],

    // [화면 2] 제휴상품 관리 상태
    affiliateSubView: 'list', // 'list' | 'create' | 'edit'
    affiliateSearch: '',
    affiliateStatusFilter: '전체',
    affiliateForceEmpty: false,
    selectedAffiliateId: null,
    nextAffiliateNumber: 1,
    showDeleteModal: false,
    affiliateProducts: [],
    offerCatalog: [],

    // [화면 3] 고객정보 & 고객 세부정보 상태
    customerSubView: 'list', // 'list' | 'detail'
    customerSearch: '',
    customerTypeFilter: '전체',
    customerStatusFilter: '전체',
    selectedCustomerId: null,
    customers: [],

    // [화면 4] 고객상담 상태
    counselingSubView: 'list', // 'list' | 'detail' | 'settings'
    counselingSearch: '',
    counselingCategoryFilter: '전체',
    selectedCounselingId: null,
    counselingSettings: {
      days: '월요일 ~ 금요일',
      startTime: '09:00',
      endTime: '18:00',
      awayMessage: '지금은 상담 가능시간이 아닙니다. 문의를 남겨주시면 운영시간에 순서대로 답변드리겠습니다.\n상담 가능시간: 평일 09:00–18:00'
    },
    counselingList: [],

    // [화면 5] 통계 상태
    statsUnit: 'daily', // 'daily' | 'monthly' | 'yearly'
    statsPeriodInput: getInitialKstRange(6),
  },
};
