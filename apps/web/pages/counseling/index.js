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
};
