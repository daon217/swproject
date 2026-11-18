const counselingPage = {
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
      ${this.renderPageHeader('상담관리', '문의 제목·분류·상태·담당자를 확인하세요. · DB 조회 (회원 최대 100명, 제휴/상담 최대 1,000건)')}

      <!-- 상단 검색 필터 바 -->
      <div class="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">문의 검색</label>
            <input
              type="text"
              value="${this.escapeHtml(this.state.counselingSearch)}"
              placeholder="문의 ID, 고객 ID 또는 제목"
              class="form-input max-w-full w-[360px]"
              oninput="app.handleCounselingFilterChange(this.value, null)"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">분류 / 상태</label>
            <select
              class="form-input max-w-full w-[220px] cursor-pointer"
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
      <div class="w-full overflow-x-auto">
        <div class="grid min-w-[820px] grid-cols-12 items-center px-6 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
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
        최근 메시지 시간순 · <span id="counseling-result-count">${filtered.length}</span> / ${this.state.counselingList.length}건
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

    return [...filtered]
      .sort((a, b) => Date.parse(b.lastMessageAt) - Date.parse(a.lastMessageAt))
      .map((item) => {
        return `
          <a
            href="#/counseling/detail/${this.escapeHtml(encodeURIComponent(item.id))}"
            class="grid min-w-[820px] grid-cols-12 items-center bg-white border border-slate-200 hover:border-[#0066ff] rounded-lg px-6 py-4 text-sm cursor-pointer transition-all"
          >
            <div class="col-span-2 font-semibold text-slate-900">${this.escapeHtml(item.id)}</div>
            <div class="col-span-2 text-slate-800 font-medium">${this.escapeHtml(item.customerId)}</div>
            <div class="col-span-3 font-medium text-slate-900 pr-2 truncate">${this.escapeHtml(item.title)}</div>
            <div class="col-span-1 text-slate-600">${this.escapeHtml(item.category)}</div>
            <div class="col-span-1">${this.renderStatusBadge(item.status)}</div>
            <div class="col-span-1 text-slate-700">${this.escapeHtml(item.agent)}</div>
            <div class="col-span-2 text-right text-slate-500">${this.escapeHtml(this.formatCounselingTime(item.lastMessageAt))}</div>
          </a>
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

    const count = document.getElementById('counseling-result-count');
    if (count) count.textContent = filtered.length;
    const tbody = document.getElementById('counseling-table-body');
    if (tbody) {
      tbody.innerHTML = this.getCounselingRowsHtml(filtered);
    }
  },

  openCounselingDetail(csId) {
    this.navigate('counseling', 'detail', csId);
  },

  // [4-2. 고객 상담 (1:1 대화 상세) 화면 (PPT 66p)]
  getCounselingDetailHtml() {
    const cs =
      this.state.counselingList.find((item) => item.id === this.state.selectedCounselingId) ||
      this.state.counselingList[0];

    const customer =
      this.state.customers.find((c) => c.id === cs.customerId) || {
        id: cs.customerId,
        ageGroup: '미등록',
        gender: '미등록'
      };

    return `
      ${this.renderPageHeader('고객 상담', `상담관리 / ${this.escapeHtml(cs.customerId)} · ${this.escapeHtml(cs.status)}`)}

      <!-- 상단 액션 버튼 (좌측 정렬) -->
      <div class="flex items-center gap-2.5 mb-6">
        <button onclick="app.navigate('counseling', 'list')" class="btn-secondary">
          목록으로
        </button>
        <button onclick="app.completeCounseling()" class="btn-primary disabled:opacity-50" ${cs.status === '완료' ? 'disabled' : ''}>
          상담 완료
        </button>
      </div>

      <!-- 본문 2열 분할 레이아웃 (좌측 대화 카드 약 68%, 우측 고객정보 카드 약 32%) -->
      <div class="flex flex-col lg:flex-row items-start gap-6">
        <!-- 좌측 대화 카드 (약 68%) -->
        <div class="w-full lg:w-[68%] bg-white border border-slate-200 rounded-xl p-6">
          <div class="mb-5">
            <h2 class="text-base font-bold text-slate-900">${this.escapeHtml(cs.customerId)} 고객과의 대화</h2>
            <p class="text-xs text-slate-500 mt-0.5">최근 메시지 · ${this.escapeHtml(this.formatCounselingTime(cs.lastMessageAt))}</p>
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
          ${cs.status === '완료' ? '<p class="text-sm text-slate-500">완료된 상담입니다.</p>' : `
          <form class="pt-2 border-t border-slate-100" onsubmit="event.preventDefault(); app.sendCounselingReply()">
            <label for="chat-reply-input" class="block text-sm font-bold text-slate-900 mb-2">답변</label>
            <div class="flex items-center gap-2.5">
              <input
                id="chat-reply-input"
                type="text"
                placeholder="메시지를 입력하세요"
                class="form-input min-w-0 flex-1"
              />
              <button type="submit" class="btn-primary">
                답변 추가
              </button>
            </div>
          </form>`}
        </div>

        <!-- 우측 고객정보 카드 (약 32%, 높이 자동 맞춤) -->
        <div class="w-full lg:w-[32%] bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-base font-bold text-slate-900 pb-3 mb-4 border-b border-slate-200">고객정보</h2>

          <div>
            <div class="text-xs text-slate-500">ID</div>
            <div class="text-lg font-bold text-slate-900 mt-0.5 mb-4">${this.escapeHtml(customer.id)}</div>

            <div class="text-xs text-slate-500">연령대</div>
            <div class="text-lg font-bold text-slate-900 mt-0.5 mb-4">${this.escapeHtml(customer.ageGroup)}</div>

            <div class="text-xs text-slate-500">성별</div>
            <div class="text-lg font-bold text-slate-900 mt-0.5 mb-4">${this.escapeHtml(customer.gender)}</div>
          </div>

          <!-- 카드 하단 안내 박스 -->
          <div class="bg-[#ebf3ff] text-slate-600 text-xs rounded-lg p-3 mt-2">
            상담 중 필요한 고객 기본정보를 확인하세요.
          </div>
        </div>
      </div>
    `;
  },

  completeCounseling(csId = this.state.selectedCounselingId) {
    const cs = this.state.counselingList.find((item) => item.id === csId);
    if (cs && cs.status !== '완료') {
      cs.status = '완료';
      this.renderContent();
      this.showToast(`${cs.customerId} 고객 상담이 '완료' 상태로 변경되었습니다.`);
    }
  },

  sendCounselingReply(csId = this.state.selectedCounselingId) {
    const input = document.getElementById('chat-reply-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;

    const cs = this.state.counselingList.find((item) => item.id === csId);
    if (!cs || cs.status === '완료') return;

    const now = new Date();
    cs.messages.push({
      sender: '김상담',
      text,
      time: this.formatCounselingTime(now),
    });
    cs.lastMessageAt = now.toISOString();
    if (cs.agent === '미배정') cs.agent = '김상담';

    this.renderContent();
    const newInput = document.getElementById('chat-reply-input');
    if (newInput) newInput.focus();
  },

  formatCounselingTime(value) {
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).format(new Date(value));
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
                type="time"
                value="${this.escapeHtml(s.startTime)}"
                class="form-input w-full"
              />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-600 mb-1.5">종료 시간</label>
              <input
                id="cs-setting-end"
                type="time"
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
          <p class="text-xs text-slate-500 mt-3">팀 공용 상담 안내 문구입니다. 현재 고객 화면 자동 표시는 제공하지 않습니다.</p>
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
    const startTime = document.getElementById('cs-setting-start')?.value || '';
    const endTime = document.getElementById('cs-setting-end')?.value || '';
    const awayMessage = document.getElementById('cs-setting-away')?.value || '';

    const time = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
    if (!time.test(startTime) || !time.test(endTime) || startTime >= endTime) {
      this.showToast('같은 날의 운영시간을 입력해 주세요. 종료 시간은 시작 시간보다 늦어야 합니다.');
      return;
    }

    this.state.counselingSettings = { days, startTime, endTime, awayMessage };
    this.showToast('현재 세션에 상담 가능시간 및 부재중 메시지를 반영했습니다.');
  },
};
