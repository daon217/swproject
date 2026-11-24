const dashboardPage = {
  getMainDashboardHtml() {
    const demo = this.isLocalAuthDemo();
    const metrics = this.getLiveSummaryMetrics();
    const subscriberStatus = !demo && this.liveCustomers?.phase === 'error' ? '조회 실패' :
      !demo && this.liveCustomers?.phase !== 'ready' ? '조회 중' : '조회 불가';
    const todaySubscribers = metrics.todaySubscriberCount == null
      ? subscriberStatus : `${metrics.todaySubscriberCount.toLocaleString()}명`;
    const dailyPeriod = this.getDefaultStatsPeriod('daily');
    const monthStart = `${metrics.todayKst.slice(0, 7)}.01`;
    const affiliateCount = this.getAffiliateItems().length;
    const affiliatePhase = demo ? 'ready' : this.liveAffiliates?.phase;
    const affiliateLabel = affiliatePhase === 'ready' || affiliateCount ? `${affiliateCount.toLocaleString()}건` : affiliatePhase === 'error' ? '조회 실패' : '조회 중';

    return `
      ${this.renderPageHeader(
        'MAIN · 대시보드',
        '팀 서버의 상담·제휴 현황 및 가입·매출 지표를 한눈에 확인합니다.',
        demo ? '' : '<button type="button" class="btn-secondary" onclick="app.refreshAllLiveStats()">새로고침</button>'
      )}

      <section aria-label="팀 서버 연동 현황" class="mb-5">
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div class="text-xs font-bold text-slate-500">전체 회원</div>
            <div class="text-2xl font-bold text-slate-900 mt-1 tabular-nums">${metrics.memberCount.toLocaleString()}명</div>
          </div>
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm cursor-pointer hover:border-[#0066ff] transition-colors" onclick="app.openRegisteredAffiliates()">
            <div class="text-xs font-bold text-slate-500">등록 제휴상품</div>
            <div class="text-2xl font-bold text-[#0066ff] mt-1 tabular-nums">${affiliateLabel}</div>
          </div>
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div class="text-xs font-bold text-slate-500">카탈로그 수집 상품</div>
            <div class="text-2xl font-bold text-slate-900 mt-1 tabular-nums">${metrics.catalogCount.toLocaleString()}건</div>
          </div>
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div class="text-xs font-bold text-slate-500">상담 내역</div>
            <div class="text-2xl font-bold text-slate-900 mt-1 tabular-nums">${metrics.counselingCount.toLocaleString()}건</div>
          </div>
        </div>
      </section>

      <!-- 상단 3열 요약 카드 -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <div class="text-xs font-bold text-slate-500">누적 구독자수</div>
          <div class="text-3xl tabular-nums tracking-tight font-bold text-slate-900 mt-2">${metrics.subscriberCount.toLocaleString()}명</div>
          <div class="text-xs text-slate-500 mt-2">${metrics.todayKst} 기준 (전체 회원 ${metrics.memberCount.toLocaleString()}명)</div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <div class="text-xs font-bold text-slate-500">당일 구독자 수</div>
          <div class="text-3xl tabular-nums tracking-tight font-bold text-[#0066ff] mt-2">${todaySubscribers}</div>
          <div class="text-xs text-slate-500 mt-1.5">${metrics.todayKst} 구독 시작</div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <div class="text-xs font-bold text-slate-500">당일 해지인원수</div>
          <div class="text-3xl tabular-nums tracking-tight font-bold text-[#e11d48] mt-2">0명</div>
          <div class="text-xs text-slate-500 mt-1.5">${metrics.todayKst} 해지 완료</div>
        </div>
      </div>

      <!-- 중단 영역: 좌측 차트 카드(2/3) + 우측 처리할 일 독립 패널(1/3) -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6 items-stretch">
        <div class="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm flex flex-col justify-between">
          <div>
            <h2 class="text-base font-bold text-slate-900">일자별 구독 가입 · 해지</h2>
            <p class="mt-1 text-xs text-slate-500">${this.escapeHtml(dailyPeriod)} · KST · 실제 DB 구독 기준</p>
            <div class="flex items-center gap-4 mt-1.5 mb-4 text-xs text-slate-600 font-medium">
              <span class="flex items-center gap-1.5">
                <span class="w-3.5 h-0.5 bg-[#0066ff] inline-block"></span>
                구독 가입
              </span>
              <span class="flex items-center gap-1.5">
                <span class="w-3.5 h-0.5 bg-[#e11d48] inline-block"></span>
                구독 해지
              </span>
            </div>
          </div>
          <div class="h-[220px] w-full">
            <canvas id="main-sub-chart"></canvas>
          </div>
        </div>

        ${this.getDashboardTasksHtml()}
      </div>

      <!-- 하단 매출 카드 (구독 매출) -->
      <div class="bg-white border border-slate-200 rounded-xl p-6">
        <h2 class="text-base font-bold text-slate-900 mb-4">구독 매출</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div class="bg-slate-50 border border-slate-200/80 rounded-lg p-5">
            <div class="text-xs font-bold text-slate-500">당월 누적 매출금액</div>
            <div class="text-2xl tabular-nums font-bold text-slate-900 mt-2">₩${(metrics.mockRevenue || 0).toLocaleString()}</div>
            <div class="mt-2 text-xs text-slate-500">${monthStart} ~ ${metrics.todayKst}</div>
          </div>
          <div class="bg-slate-50 border border-slate-200/80 rounded-lg p-5">
            <div class="text-xs font-bold text-slate-500">금일 누적 매출금액</div>
            <div class="text-2xl tabular-nums font-bold text-[#0066ff] mt-2">₩${(metrics.todayRevenue || 0).toLocaleString()}</div>
            <div class="mt-2 text-xs text-slate-500">${metrics.todayKst}</div>
          </div>
        </div>
      </div>

      <!-- 하단 캡션 -->
      <div class="mt-4 text-sm text-slate-500">
        집계 기준 · KST 00:00–23:59 &nbsp;&nbsp;/&nbsp;&nbsp; 팀 서버 DB 실시간 조회 기준
      </div>
    `;
  },

  getDashboardTasksHtml() {
    const waiting = this.getCounselingItems().filter((item) => item.status === '대기').length;
    const phase = this.isLocalAuthDemo() ? 'ready' : this.liveCounseling?.phase;
    const waitingLabel = phase === 'ready' || this.getCounselingItems().length ? `${waiting}건` : phase === 'error' ? '조회 실패' : '조회 중';
    const now = Date.now();
    const ending = this.getAffiliateItems().filter((item) => this.isAffiliateEndingSoon(item, now)).length;
    const affiliatePhase = this.isLocalAuthDemo() ? 'ready' : this.liveAffiliates?.phase;
    const endingLabel = affiliatePhase === 'ready' || this.getAffiliateItems().length ? `${ending.toLocaleString()}건` : affiliatePhase === 'error' ? '조회 실패' : '조회 중';

    return `
      <section aria-labelledby="dashboard-tasks-title" class="rounded-xl border border-[#0066ff]/25 bg-[#ebf3ff]/60 p-5 shadow-sm flex flex-col justify-between">
        <div class="flex items-center justify-between mb-3">
          <h2 id="dashboard-tasks-title" class="text-base font-bold text-slate-900">처리할 일</h2>
          <span class="rounded-full bg-[#0066ff] px-2.5 py-0.5 text-[11px] font-semibold text-white">Action</span>
        </div>
        <ul class="grid grid-cols-1 gap-3 flex-1">
          <li class="flex">
            <button type="button" class="group flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-4 text-left shadow-sm transition-colors hover:border-[#0066ff] focus-visible:outline-[#0066ff]" onclick="app.openWaitingCounseling()">
              <span>
                <span class="block text-xs font-bold text-slate-600">답변 대기 상담</span>
                <span class="mt-1.5 block text-2xl font-bold tracking-tight tabular-nums text-[#0066ff]">${waitingLabel}</span>
              </span>
              <span aria-hidden="true" class="rounded-full bg-[#ebf3ff] px-2.5 py-1.5 text-sm font-bold text-[#0066ff] group-hover:bg-[#0066ff] group-hover:text-white transition-colors">→</span>
            </button>
          </li>
          <li class="flex">
            <button type="button" class="group flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-4 text-left shadow-sm transition-colors hover:border-[#0066ff] focus-visible:outline-[#0066ff]" onclick="app.openEndingAffiliates()">
              <span>
                <span class="block text-xs font-bold text-slate-600">7일 이내 종료되는 제휴상품</span>
                <span class="mt-1.5 block text-2xl font-bold tracking-tight tabular-nums text-[#0066ff]">${endingLabel}</span>
              </span>
              <span aria-hidden="true" class="rounded-full bg-[#ebf3ff] px-2.5 py-1.5 text-sm font-bold text-[#0066ff] group-hover:bg-[#0066ff] group-hover:text-white transition-colors">→</span>
            </button>
          </li>
        </ul>
      </section>
    `;
  },

  openWaitingCounseling() {
    this.state.counselingSearch = '';
    this.state.counselingCategoryFilter = '대기';
    this.navigate('counseling');
  },

  openRegisteredAffiliates() {
    this.state.affiliateSearch = '';
    this.state.affiliateStatusFilter = '전체';
    this.state.affiliateForceEmpty = false;
    this.state.selectedAffiliateId = null;
    this.navigate('affiliate');
  },

  openEndingAffiliates() {
    this.state.affiliateSearch = '';
    this.state.affiliateStatusFilter = '종료 예정';
    this.state.affiliateForceEmpty = false;
    this.state.selectedAffiliateId = null;
    this.navigate('affiliate');
  },

  openWaitingAffiliatesOrEnding() {
    this.openEndingAffiliates();
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
            pointRadius: 2,
            pointHoverRadius: 4,
          },
          {
            label: '구독 해지',
            data: cfg.subLeave,
            borderColor: '#e11d48',
            backgroundColor: '#e11d48',
            borderWidth: 2,
            tension: 0,
            pointRadius: 2,
            pointHoverRadius: 4,
          },
        ],
      },
      options: this.createCommonLineChartOptions(),
    });
  },
};
