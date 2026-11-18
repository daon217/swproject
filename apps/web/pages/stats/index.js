const statsPage = {
  liveOverview: null,

  getKstTodayDateStr() {
    return new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10).replaceAll('-', '.');
  },

  getDefaultStatsPeriod(unit) {
    const nowKst = new Date(Date.now() + 9 * 60 * 60 * 1000);
    const year = nowKst.getUTCFullYear();
    const month = nowKst.getUTCMonth(); // 0-indexed

    if (unit === 'monthly') {
      const endStr = `${year}.${String(month + 1).padStart(2, '0')}`;
      const startDate = new Date(Date.UTC(year, month - 6, 1));
      const startStr = `${startDate.getUTCFullYear()}.${String(startDate.getUTCMonth() + 1).padStart(2, '0')}`;
      return `${startStr} ~ ${endStr}`;
    }
    if (unit === 'yearly') {
      return `${year - 4} ~ ${year}`;
    }
    const endStr = nowKst.toISOString().slice(0, 10).replaceAll('-', '.');
    const startStr = new Date(nowKst.getTime() - 6 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10).replaceAll('-', '.');
    return `${startStr} ~ ${endStr}`;
  },

  async refreshLiveOverview() {
    const session = this.adminSession;
    if (!session || this.isLocalAuthDemo()) return;
    const targetPage = this.state.currentPage;
    const prev = this.liveOverview || {};
    const view = { ...prev, phase: 'loading' };
    this.liveOverview = view;
    this.renderContent();

    try {
      const [overviewRes, catalogRes] = await Promise.allSettled([
        this.requestAdminAuth('/v2/admin/overview', { token: session.token }),
        this.fetchAllCatalogOffers(),
      ]);

      const overview = overviewRes.status === 'fulfilled' ? overviewRes.value : null;
      const catalogOffers = catalogRes.status === 'fulfilled' ? catalogRes.value : [];
      if (catalogOffers.length) {
        this.state.offerCatalog = catalogOffers;
      }

      Object.assign(view, {
        phase: 'ready',
        overview,
        catalogCount: overview?.offers ?? catalogOffers.length,
        availableCatalogCount: overview?.available ?? catalogOffers.filter((o) => o.availability === 'available').length,
        crawlDays: overview?.crawl_days || null,
      });
    } catch {
      view.phase = 'error';
    }

    if (this.liveOverview === view && this.adminSession === session && this.state.currentPage === targetPage) {
      this.renderContent();
    }
  },

  refreshAllLiveStats() {
    this.refreshLiveAffiliates();
    this.refreshLiveCounseling();
    this.refreshLiveCustomers();
    this.refreshLiveOverview();
  },

  getLiveSummaryMetrics() {
    const todayKst = this.getKstTodayDateStr();
    const overview = this.liveOverview?.overview;
    const members = this.liveCustomers?.items || [];
    const affiliates = this.getAffiliateItems();
    const activeAffiliates = affiliates.filter((item) => this.getAffiliateStatus(item, Date.now()) === '제휴 중');
    const counseling = this.getCounselingItems();
    const resolvedCounseling = counseling.filter((c) => c.status === '완료');
    const catalogCount = this.liveOverview?.catalogCount ?? this.state.offerCatalog?.length ?? 0;
    const availableCount = this.liveOverview?.availableCatalogCount ??
      (this.state.offerCatalog || []).filter((o) => o.availability === 'available').length;

    const memberCount = overview?.members ?? members.length;
    const subscriberCount = overview?.subscribers ?? members.filter((m) => m.subscribed).length;
    let todaySubscriberCount = null;
    if (overview?.today_subscribers_date === todayKst.replaceAll('.', '-')) {
      todaySubscriberCount = overview.today_subscribers;
    } else if (this.liveCustomers?.phase === 'ready' &&
      (members.length < 100 || members.length === overview?.members)) {
      todaySubscriberCount = members.filter((member) =>
        this.formatKstDateTime(member.subscription_started_at).slice(0, 10) === todayKst
      ).length;
    }
    const mockRevenue = overview?.mock_revenue_krw != null ? Number(overview.mock_revenue_krw) : 0;

    return {
      todayKst,
      memberCount,
      subscriberCount,
      todaySubscriberCount,
      affiliateCount: affiliates.length,
      activeAffiliateCount: activeAffiliates.length,
      catalogCount,
      availableCount,
      counselingCount: counseling.length,
      resolvedCounselingCount: resolvedCounseling.length,
      mockRevenue,
    };
  },

  buildBucketsForRange(unit, periodText) {
    const [startStr, endStr] = (periodText || this.getDefaultStatsPeriod(unit)).split(' ~ ');
    const buckets = [];

    if (unit === 'yearly') {
      const startYear = Number(startStr.slice(0, 4));
      const endYear = Number(endStr.slice(0, 4));
      for (let y = startYear; y <= endYear && buckets.length < 20; y++) {
        const key = String(y);
        buckets.push({ key, label: key });
      }
      return buckets;
    }

    if (unit === 'monthly') {
      const [sy, sm] = startStr.split('.').map(Number);
      const [ey, em] = endStr.split('.').map(Number);
      const cur = new Date(Date.UTC(sy, (sm || 1) - 1, 1));
      const last = new Date(Date.UTC(ey, (em || 1) - 1, 1));
      while (cur <= last && buckets.length < 36) {
        const y = cur.getUTCFullYear();
        const m = String(cur.getUTCMonth() + 1).padStart(2, '0');
        buckets.push({ key: `${y}.${m}`, label: `${m}월` });
        cur.setUTCMonth(cur.getUTCMonth() + 1);
      }
      return buckets;
    }

    const [sy, sm, sd] = startStr.split('.').map(Number);
    const [ey, em, ed] = endStr.split('.').map(Number);
    const cur = new Date(Date.UTC(sy, (sm || 1) - 1, sd || 1));
    const last = new Date(Date.UTC(ey, (em || 1) - 1, ed || 1));
    while (cur <= last && buckets.length < 60) {
      const iso = cur.toISOString().slice(0, 10).replaceAll('-', '.');
      buckets.push({ key: iso, label: iso.slice(5, 10) });
      cur.setUTCDate(cur.getUTCDate() + 1);
    }
    return buckets;
  },

  getStatsDatasetByUnit(unit, customPeriod = null) {
    const unitLabel = unit === 'monthly' ? '월별' : unit === 'yearly' ? '연도별' : '일별';
    const defaultPeriod = this.getDefaultStatsPeriod(unit);
    const periodText = customPeriod || defaultPeriod;
    const buckets = this.buildBucketsForRange(unit, periodText);
    const keyLength = unit === 'yearly' ? 4 : unit === 'monthly' ? 7 : 10;

    const members = this.liveCustomers?.items || [];
    const subJoinCounts = new Map(buckets.map((b) => [b.key, 0]));
    const subLeaveCounts = new Map(buckets.map((b) => [b.key, 0]));
    for (const m of members) {
      if (m.subscription_started_at) {
        const startKst = this.formatKstDateTime(m.subscription_started_at);
        const startPrefix = startKst.slice(0, keyLength);
        if (subJoinCounts.has(startPrefix)) {
          subJoinCounts.set(startPrefix, subJoinCounts.get(startPrefix) + 1);
        }
      }
      if (!m.subscribed && m.subscription_started_at) {
        const endSource = m.subscription_ended_at || m.subscription_canceled_at || m.subscription_started_at;
        const endKst = this.formatKstDateTime(endSource);
        const endPrefix = endKst.slice(0, keyLength);
        if (subLeaveCounts.has(endPrefix)) {
          subLeaveCounts.set(endPrefix, subLeaveCounts.get(endPrefix) + 1);
        }
      }
    }

    const todayKey = this.getKstTodayDateStr().slice(0, keyLength);
    const mockRevenueKrw = Number(this.liveOverview?.overview?.mock_revenue_krw || 0);
    const revenueManWon = mockRevenueKrw > 0 ? Number((mockRevenueKrw / 10000).toFixed(2)) : 0;

    return {
      unitLabel,
      periodText: defaultPeriod,
      labels: buckets.map((b) => b.label),
      subJoin: buckets.map((b) => subJoinCounts.get(b.key) || 0),
      subLeave: buckets.map((b) => subLeaveCounts.get(b.key) || 0),
      subSales: buckets.map((b) => (b.key === todayKey ? revenueManWon : 0)),
      royaltySales: buckets.map(() => 0),
    };
  },

  getStatsHtml() {
    const demo = this.isLocalAuthDemo();
    const unit = this.state.statsUnit;
    const dataConfig = this.getStatsDatasetByUnit(unit, this.state.statsPeriodInput);
    const btnClass = (target) => (unit === target ? 'btn-primary' : 'btn-secondary');
    const metrics = this.getLiveSummaryMetrics();

    return `
      ${this.renderPageHeader(
        '통계',
        '팀 서버 DB 실시간 현황과 기간별 가입·해지 및 매출 추이를 확인합니다.',
        demo ? '' : '<button type="button" class="btn-secondary" onclick="app.refreshAllLiveStats()">새로고침</button>'
      )}

      <section aria-label="팀 서버 실시간 연동 지표" class="mb-6">
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div class="text-xs font-bold text-slate-500">전체 회원</div>
            <div class="text-2xl font-bold text-slate-900 mt-1 tabular-nums">${metrics.memberCount.toLocaleString()}명</div>
            <div class="text-xs text-slate-500 mt-1">구독 활성 ${metrics.subscriberCount.toLocaleString()}명</div>
          </div>
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div class="text-xs font-bold text-slate-500">등록 제휴상품</div>
            <div class="text-2xl font-bold text-[#0066ff] mt-1 tabular-nums">${metrics.affiliateCount.toLocaleString()}건</div>
            <div class="text-xs text-slate-500 mt-1">현재 제휴 중 ${metrics.activeAffiliateCount.toLocaleString()}건</div>
          </div>
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div class="text-xs font-bold text-slate-500">카탈로그 수집 상품</div>
            <div class="text-2xl font-bold text-slate-900 mt-1 tabular-nums">${metrics.catalogCount.toLocaleString()}건</div>
            <div class="text-xs text-slate-500 mt-1">판매 가능 ${metrics.availableCount.toLocaleString()}건</div>
          </div>
          <div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
            <div class="text-xs font-bold text-slate-500">고객상담 처리 현황</div>
            <div class="text-2xl font-bold text-slate-900 mt-1 tabular-nums">${metrics.counselingCount.toLocaleString()}건</div>
            <div class="text-xs text-slate-500 mt-1">답변 완료 ${metrics.resolvedCounselingCount.toLocaleString()}건</div>
          </div>
        </div>
      </section>

      <!-- 상단 필터 컨트롤 바 -->
      <div class="flex flex-wrap items-end gap-4 mb-6">
        <div class="flex items-center gap-2">
          <button onclick="app.changeStatsUnit('daily')" class="${btnClass('daily')}">일별</button>
          <button onclick="app.changeStatsUnit('monthly')" class="${btnClass('monthly')}">월별</button>
          <button onclick="app.changeStatsUnit('yearly')" class="${btnClass('yearly')}">연도별</button>
        </div>

        <div>
          <label for="stats-period-input" class="block text-xs font-bold text-slate-600 mb-1.5">조회 기간</label>
          <div class="flex flex-wrap items-center gap-2">
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
      </div>

      <div class="space-y-6">
        <!-- 차트 카드 1: 구독 가입 · 해지 추이 (명) -->
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <h2 class="text-base font-bold text-slate-900">${dataConfig.unitLabel} 구독 가입 · 해지 추이 (명)</h2>
          <p class="mt-1 text-xs text-slate-500">${this.escapeHtml(this.state.statsPeriodInput)} · KST · 실제 DB 구독 기준</p>
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

        <!-- 차트 카드 2: 매출 추이 (만원) -->
        <div class="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-sm">
          <h2 class="text-base font-bold text-slate-900">${dataConfig.unitLabel} 매출 추이 (만원)</h2>
          <p class="mt-1 text-xs text-slate-500">${this.escapeHtml(this.state.statsPeriodInput)} · KST · 실제 DB 기준</p>
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
        기간 집계 기준: KST &nbsp;·&nbsp; 팀 서버 DB에서 조회된 실제 구독 가입·해지 및 매출 데이터를 표시합니다.
      </div>
    `;
  },

  changeStatsUnit(unit) {
    this.state.statsUnit = unit;
    this.state.statsPeriodInput = this.getDefaultStatsPeriod(unit);
    this.renderContent();
  },

  applyStatsPeriod() {
    const input = document.getElementById('stats-period-input');
    const unit = this.state.statsUnit;
    const example = this.getDefaultStatsPeriod(unit);
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
    const cfg = this.getStatsDatasetByUnit(unit, this.state.statsPeriodInput);
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
              pointRadius: 2,
              pointHoverRadius: 4,
            },
            {
              label: 'URL 로열티 매출',
              data: cfg.royaltySales,
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
    }
  },
};
