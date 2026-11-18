const customersPage = {
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
            class="form-input max-w-full w-[320px]"
            oninput="app.handleCustomerFilterChange(this.value, null, null)"
          />
        </div>
        <div>
          <label class="block text-xs font-bold text-slate-600 mb-1.5">회원 유형</label>
          <select
            class="form-input max-w-full w-[190px] cursor-pointer"
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
            class="form-input max-w-full w-[190px] cursor-pointer"
            onchange="app.handleCustomerFilterChange(null, null, this.value)"
          >
            <option value="전체" ${statusFilter === '전체' ? 'selected' : ''}>전체</option>
            <option value="정상" ${statusFilter === '정상' ? 'selected' : ''}>정상</option>
            <option value="휴면" ${statusFilter === '휴면' ? 'selected' : ''}>휴면</option>
          </select>
        </div>
      </div>

      <!-- 테이블 -->
      <div class="w-full overflow-x-auto">
        <div class="grid min-w-[540px] grid-cols-5 items-center px-6 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
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
        <div class="grid min-w-[540px] grid-cols-5 items-center bg-white border border-slate-200 rounded-lg px-6 py-3.5 text-sm">
          <div>
            <a
              href="#/customers/detail/${this.escapeHtml(encodeURIComponent(c.id))}"
              class="text-blue-600 underline cursor-pointer font-medium hover:text-blue-800"
            >${this.escapeHtml(c.id)}</a>
          </div>
          <div class="font-semibold text-slate-900">${this.escapeHtml(c.subscribed)}</div>
          <div class="text-slate-700">${this.escapeHtml(c.gender || '미등록')}</div>
          <div class="text-slate-700">${this.escapeHtml(c.ageGroup || '미등록')}</div>
          <div class="text-slate-800 font-medium">${this.escapeHtml(c.status)}</div>
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
    this.navigate('customers', 'detail', customerId);
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
      ${this.renderPageHeader('고객 세부정보', `고객정보 / ${this.escapeHtml(c.id)} · 예시 데이터`)}

      <!-- 정보 카드 (흰색 큰 박스 내 가로 구분선 리스트) -->
      <div class="bg-white border border-slate-200 rounded-xl px-7 py-2">
        <div class="flex items-center py-4 border-b border-slate-200 text-sm">
          <div class="w-[180px] text-slate-500">ID</div>
          <div class="font-bold text-slate-900">${this.escapeHtml(c.id)}</div>
        </div>
        <div class="flex items-center py-4 border-b border-slate-200 text-sm">
          <div class="w-[180px] text-slate-500">성별</div>
          <div class="font-bold text-slate-900">${this.escapeHtml(c.gender || '미등록')}</div>
        </div>
        <div class="flex items-center py-4 border-b border-slate-200 text-sm">
          <div class="w-[180px] text-slate-500">연령대</div>
          <div class="font-bold text-slate-900">${this.escapeHtml(c.ageGroup || '미등록')}</div>
        </div>
        <div class="flex items-center py-4 border-b border-slate-200 text-sm">
          <div class="w-[180px] text-slate-500">구독 여부</div>
          <div class="font-bold text-slate-900">${this.escapeHtml(subText)}</div>
        </div>
        <div class="flex items-center py-4 text-sm">
          <div class="w-[180px] text-slate-500">구독 시작일자</div>
          <div class="font-bold text-slate-900">${this.escapeHtml(subDateText)}</div>
        </div>
      </div>

      <!-- 하단 버튼 영역 (좌측 정렬) -->
      <div class="flex items-center gap-3 mt-6">
        <button onclick="app.resetCustomerPassword()" class="btn-primary">
          비밀번호 초기화
        </button>
        <button onclick="app.navigate('customers', 'list')" class="btn-secondary">
          목록
        </button>
      </div>
    `;
  },

  resetCustomerPassword() {
    this.showToast('비밀번호 초기화 안내를 보내려면 회원 API 연결이 필요합니다.');
  },
};
