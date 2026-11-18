const dashboardPage = {
  getMainDashboardHtml() {
    if (!this.isLocalAuthDemo()) {
      return `
        ${this.renderPageHeader('MAIN · 대시보드', '팀 서버의 상담과 제휴 현황을 확인합니다.')}
        ${this.getDashboardTasksHtml()}
        <p class="text-sm text-slate-600">전체 구독·매출 집계는 현재 팀 서버에서 제공하지 않습니다.</p>
      `;
    }
    return `
      ${this.renderPageHeader(
        'MAIN · 대시보드',
        '구독 현황과 매출을 한눈에 확인하세요. · 표시된 수치는 예시 데이터입니다.'
      )}

      ${this.getDashboardTasksHtml()}

      <!-- 상단 3열 요약 카드 -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <div class="text-xs font-bold text-slate-500">누적 구독자수</div>
          <div class="text-3xl tabular-nums tracking-tight font-bold text-slate-900 mt-2">12,480명</div>
          <div class="text-xs text-slate-500 mt-2">2026.10.12까지 누적</div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <div class="text-xs font-bold text-slate-500">당일 구독 가입자수</div>
          <div class="text-3xl tabular-nums tracking-tight font-bold text-[#0066ff] mt-2">86명</div>
          <div class="text-xs text-slate-500 mt-1.5">2026.10.12 가입 완료</div>
        </div>
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <div class="text-xs font-bold text-slate-500">당일 구독 해지인원수</div>
          <div class="text-3xl tabular-nums tracking-tight font-bold text-[#e11d48] mt-2">12명</div>
          <div class="text-xs text-slate-500 mt-1.5">2026.10.12 해지 완료</div>
        </div>
      </div>

      <!-- 중단 차트 카드 (일자별 구독 가입 · 해지) -->
      <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm mb-6">
        <h2 class="text-base font-bold text-slate-900">일자별 구독 가입 · 해지</h2>
        <p class="mt-1 text-xs text-slate-500">2026.10.06 ~ 2026.10.12 · KST</p>
        <div class="flex items-center gap-4 mt-1.5 mb-4 text-xs text-slate-600 font-medium">
          <span class="flex items-center gap-1.5">
            <span class="w-3.5 h-0.5 bg-[#0066ff] inline-block"></span>
            가입
          </span>
          <span class="flex items-center gap-1.5">
            <span class="w-3.5 h-0.5 bg-[#e11d48] inline-block"></span>
            해지
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
            <div class="text-2xl tabular-nums font-bold text-slate-900 mt-2">₩24,800,000</div>
            <div class="mt-2 text-xs text-slate-500">2026.10.01 ~ 2026.10.12</div>
          </div>
          <div class="bg-slate-50 border border-slate-200/80 rounded-lg p-5">
            <div class="text-xs font-bold text-slate-500">금일 누적 매출금액</div>
            <div class="text-2xl tabular-nums font-bold text-[#0066ff] mt-2">₩860,000</div>
            <div class="mt-2 text-xs text-slate-500">2026.10.12</div>
          </div>
        </div>
      </div>

      <!-- 하단 캡션 -->
      <div class="mt-4 text-sm text-slate-500">
        집계 기준 · KST 00:00–23:59 &nbsp;&nbsp;/&nbsp;&nbsp; 구독 당월 매출: 10.01–10.12
      </div>
    `;
  },

  getDashboardTasksHtml() {
    const waiting = this.getCounselingItems().filter((item) => item.status === '대기').length;
    const phase = this.isLocalAuthDemo() ? 'ready' : this.liveCounseling?.phase;
    const waitingLabel = phase === 'ready' ? `${waiting}건` : phase === 'error' ? '조회 실패' : '조회 중';
    const now = Date.now();
    const ending = this.getAffiliateItems().filter((item) => this.isAffiliateEndingSoon(item, now)).length;
    const affiliatePhase = this.isLocalAuthDemo() ? 'ready' : this.liveAffiliates?.phase;
    const endingLabel = affiliatePhase === 'ready' ? `${ending}건` : affiliatePhase === 'error' ? '조회 실패' : '조회 중';

    return `
      <section aria-labelledby="dashboard-tasks-title" class="mb-6">
        <h2 id="dashboard-tasks-title" class="text-base font-bold text-slate-900 mb-3">처리할 일</h2>
        <ul class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <li>
            <button type="button" class="group flex h-full w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-colors hover:border-[#0066ff] hover:bg-[#ebf3ff] focus-visible:outline-[#0066ff]" onclick="app.openWaitingCounseling()">
              <span><span class="block text-sm font-semibold text-slate-700">답변 대기 상담</span>
              <span class="mt-2 block text-3xl font-bold tracking-tight tabular-nums text-[#0066ff]">${waitingLabel}</span></span>
              <span aria-hidden="true" class="rounded-full bg-[#ebf3ff] px-3 py-2 text-[#0066ff] group-hover:bg-white">→</span>
            </button>
          </li>
          <li>
            <button type="button" class="group flex h-full w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-colors hover:border-[#0066ff] hover:bg-[#ebf3ff] focus-visible:outline-[#0066ff]" onclick="app.openEndingAffiliates()">
              <span><span class="block text-sm font-semibold text-slate-700">7일 이내 종료되는 제휴상품</span>
              <span class="mt-2 block text-3xl font-bold tracking-tight tabular-nums text-[#0066ff]">${endingLabel}</span></span>
              <span aria-hidden="true" class="rounded-full bg-[#ebf3ff] px-3 py-2 text-[#0066ff] group-hover:bg-white">→</span>
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

  openEndingAffiliates() {
    this.state.affiliateSearch = '';
    this.state.affiliateStatusFilter = '종료 예정';
    this.state.affiliateForceEmpty = false;
    this.state.selectedAffiliateId = null;
    this.navigate('affiliate');
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
};
