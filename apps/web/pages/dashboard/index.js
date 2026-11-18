const dashboardPage = {
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
};
