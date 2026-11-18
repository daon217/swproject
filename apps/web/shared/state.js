const consoleState = {
  // 현재 활성화된 화면 및 서브 상태
  state: {
    currentPage: 'main', // 'main' | 'affiliate' | 'crawling' | 'counseling' | 'stats' | 'customers'

    // [화면 1] 상품 크롤링 검토 상태
    crawlingPeriod: '2026.10.06 ~ 2026.10.12',
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
    nextAffiliateNumber: 4,
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
    offerCatalog: [],

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
        lastMessageAt: '2026-10-12T14:32:00+09:00',
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
        lastMessageAt: '2026-10-12T14:10:00+09:00',
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
        lastMessageAt: '2026-10-12T13:55:00+09:00',
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
        lastMessageAt: '2026-10-11T17:08:00+09:00',
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
        lastMessageAt: '2026-10-11T15:24:00+09:00',
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
};

Object.assign(consoleState.state, {affiliateProducts:[],customers:[],counselingList:[],crawlingData:[],crawlingPeriod:"최근 30일",overview:null});
