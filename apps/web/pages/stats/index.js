const statsPage = {
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
          <label for="stats-period-input" class="block text-xs font-bold text-slate-600 mb-1.5">조회 기간</label>
          <input
            id="stats-period-input"
            type="text"
            value="${this.escapeHtml(this.state.statsPeriodInput)}"
            class="form-input max-w-full w-[280px]"
            onkeydown="if(event.key==='Enter') app.applyStatsPeriod()"
          />
          <button type="button" onclick="app.applyStatsPeriod()" class="btn-primary">조회</button>
        </div>
      </div>

      <div class="space-y-6">
        <!-- 차트 카드 1: 일별 구독 가입 · 해지 추이 (명) -->
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <h2 class="text-base font-bold text-slate-900">${dataConfig.unitLabel} 구독 가입 · 해지 추이 (명)</h2>
          <p class="mt-1 text-xs text-slate-500">${this.escapeHtml(this.state.statsPeriodInput)} · KST</p>
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
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <h2 class="text-base font-bold text-slate-900">${dataConfig.unitLabel} 매출 추이 (만원)</h2>
          <p class="mt-1 text-xs text-slate-500">${this.escapeHtml(this.state.statsPeriodInput)} · KST</p>
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
        기간 집계 기준: KST &nbsp;·&nbsp; 선택한 기간의 가입·해지 및 매출을 표시합니다.
      </div>
    `;
  },

  changeStatsUnit(unit) {
    this.state.statsUnit = unit;
    const cfg = this.getStatsDatasetByUnit(unit);
    this.state.statsPeriodInput = cfg.periodText;
    this.renderContent();
  },

  applyStatsPeriod() {
    const input = document.getElementById('stats-period-input');
    const unit = this.state.statsUnit;
    const example = this.getStatsDatasetByUnit(unit).periodText;
    const range = this.parseDateRange(input.value, example.split(' ~ ')[0].length);
    if (!range) {
      this.showToast(`조회 기간 형식을 확인해 주세요. 예: ${example}`);
      return;
    }
    this.state.statsPeriodInput = range.join(' ~ ');
    this.renderContent();
  },

  initStatsCharts() {
    const unit = this.state.statsUnit;
    const cfg = this.getStatsDatasetByUnit(unit);
    const [start, end] = this.state.statsPeriodInput.split(' ~ ');
    const [year, month = '01', day = '01'] = cfg.periodText.split(' ~ ')[0].split('.');
    const date = new Date(`${year}-${month}-${day}T00:00:00Z`);
    const included = cfg.labels.map(() => {
      const key = date.toISOString().slice(0, start.length).replaceAll('-', '.');
      if (unit === 'daily') date.setUTCDate(date.getUTCDate() + 1);
      if (unit === 'monthly') date.setUTCMonth(date.getUTCMonth() + 1);
      if (unit === 'yearly') date.setUTCFullYear(date.getUTCFullYear() + 1);
      return key >= start && key <= end;
    });
    const inRange = (values) => values.filter((_, index) => included[index]);
    const subCanvas = document.getElementById('stats-sub-chart');
    const salesCanvas = document.getElementById('stats-sales-chart');

    if (subCanvas && window.Chart) {
      if (this.charts.statsSubChart) {
        this.charts.statsSubChart.destroy();
      }
      this.charts.statsSubChart = new Chart(subCanvas.getContext('2d'), {
        type: 'line',
        data: {
          labels: inRange(cfg.labels),
          datasets: [
            {
              label: '구독 가입',
              data: inRange(cfg.subJoin),
              borderColor: '#0066ff',
              backgroundColor: '#0066ff',
              borderWidth: 2,
              tension: 0,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
            {
              label: '구독 해지',
              data: inRange(cfg.subLeave),
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
          labels: inRange(cfg.labels),
          datasets: [
            {
              label: '구독 매출',
              data: inRange(cfg.subSales),
              borderColor: '#0066ff',
              backgroundColor: '#0066ff',
              borderWidth: 2,
              tension: 0,
              pointRadius: 0,
              pointHoverRadius: 4,
            },
            {
              label: 'URL 로열티 매출',
              data: inRange(cfg.royaltySales),
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
};
