const loginPage = {
  adminSession: null,
  isLocalAuthDemo() {
    return window.location.origin === 'http://localhost:3001' &&
      new URLSearchParams(window.location.search).get('demo') === '1';
  },

  getAdminSessionKey() {
    return this.isLocalAuthDemo() ? 'kkulpick-demo-admin-session' : 'kkulpick-admin-session';
  },

  getAdminAuthOrigin() {
    return this.isLocalAuthDemo() ? window.location.origin : this.getApiBase();
  },

  async setupAdminLogin() {
    const submit = document.getElementById('admin-login-submit');
    const signupSubmit = document.getElementById('admin-signup-submit');
    const loginForm = document.getElementById('admin-login-form');
    const signupForm = document.getElementById('admin-signup-form');
    const demo = this.isLocalAuthDemo();
    document.getElementById('admin-login-demo').hidden = !demo;
    document.getElementById('admin-signup-demo').hidden = !demo;
    document.getElementById('admin-signup-role-hint').hidden = demo;
    loginForm.addEventListener('submit', (event) => {
      event.preventDefault();
      this.signInAdmin();
    });
    signupForm.addEventListener('submit', (event) => {
      event.preventDefault();
      this.signUpMember();
    });
    document.getElementById('admin-logout').addEventListener('click', () => this.signOutAdmin());
    if (window.location.protocol === 'file:') {
      loginForm.noValidate = true;
      signupForm.noValidate = true;
      submit.disabled = false;
      signupSubmit.disabled = false;
      document.getElementById('admin-login-server-link').hidden = false;
      document.getElementById('admin-signup-server-link').hidden = false;
      return;
    }
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(this.getAdminSessionKey()));
      if (saved?.apiBase === this.getAdminAuthOrigin() && saved.expiresAt > Date.now() && saved.token) {
        this.showAdminLoginMessage('관리자 권한을 확인하는 중입니다.');
        await this.activateAdminSession(saved);
      } else {
        this.saveAdminSession(null);
      }
    } catch {
      this.saveAdminSession(null);
      this.showAdminLoginMessage('이전 로그인 세션을 확인하지 못했습니다. 다시 로그인해 주세요.');
    } finally {
      submit.disabled = false;
      signupSubmit.disabled = false;
    }
  },

  async signUpMember() {
    const submit = document.getElementById('admin-signup-submit');
    if (submit.disabled || this.adminSession) return;
    const form = document.getElementById('admin-signup-form');
    const value = (field) => document.getElementById(`admin-signup-${field}`).value;
    const message = document.getElementById('admin-signup-message');
    if (window.location.protocol === 'file:') {
      message.textContent = '위의 웹 서버 링크에서 회원가입을 진행해 주세요.';
      return;
    }
    const loginId = value('id');
    const password = value('password');
    const confirmation = value('confirmation');
    const consent = document.getElementById('admin-signup-consent');
    if (!form.reportValidity()) return;
    if (password !== confirmation) {
      message.textContent = '비밀번호와 비밀번호 확인이 일치하지 않습니다.';
      document.getElementById('admin-signup-confirmation').focus();
      return;
    }

    submit.disabled = true;
    message.textContent = '회원가입을 처리하는 중입니다.';
    try {
      const account = await this.requestAdminAuth('/v2/auth/signup', {
        method: 'POST',
        body: {
          login_id: loginId,
          password,
          password_confirmation: confirmation,
          consent_version: document.getElementById('admin-signup-terms').dataset.version,
          consent_accepted: consent.checked,
        },
      });
      if (typeof account?.user_id !== 'string' || !account.user_id) {
        throw new Error('Invalid signup response');
      }
      form.reset();
      message.textContent = '';
      document.getElementById('admin-login-id').value = loginId;
      this.showAdminLoginMessage(this.isLocalAuthDemo()
        ? '로컬 데모 계정을 만들었습니다. 가입한 아이디와 비밀번호로 로그인해 주세요.'
        : '가입했습니다. 관리자 또는 상담 담당자 권한을 부여받은 뒤 로그인해 주세요.');
      if (window.location.hash === '#/signup') {
        this.navigate('login', 'list', undefined, { replace: true });
        document.getElementById('admin-login-password').focus();
      }
    } catch (error) {
      const messages = {
        409: '이미 사용 중인 아이디입니다.',
        422: '아이디, 비밀번호, 개인정보 수집 동의를 확인해 주세요.',
        429: '가입 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.',
      };
      message.textContent = messages[error.status] ||
        '가입 결과를 확인하지 못했습니다. 서버 연결을 확인해 주세요.';
    } finally {
      submit.disabled = false;
    }
  },

  getApiBase() {
    return new URL(document.querySelector('meta[name="api-base"]').content).origin;
  },

  async requestAdminAuth(path, { method = 'GET', token, body } = {}) {
    const endpoint = this.isLocalAuthDemo() ? `/__local-demo${path}` : path;
    const headers = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body) headers['Content-Type'] = 'application/json';
    const response = await fetch(new URL(endpoint, this.getAdminAuthOrigin()), {
      method, headers, body: body && JSON.stringify(body), signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      throw Object.assign(new Error('Authentication request failed'), { status: response.status });
    }
    return response.status === 204 ? null : (await response.json()).data;
  },

  async activateAdminSession(session) {
    const account = await this.requestAdminAuth('/v2/admin/me', { token: session.token });
    if (account?.role !== 'admin' && account?.role !== 'support') {
      throw Object.assign(new Error('Unsupported administrator role'), { status: 403 });
    }
    this.adminSession = { ...session, role: account.role };
    this.saveAdminSession(session);
    this.showAdminLoginMessage('');
    this.renderRoute();
  },

  async signInAdmin() {
    const submit = document.getElementById('admin-login-submit');
    if (submit.disabled) return;
    if (window.location.protocol === 'file:') {
      this.showAdminLoginMessage('위의 웹 서버 링크에서 로그인해 주세요.');
      return;
    }
    const loginId = document.getElementById('admin-login-id');
    const password = document.getElementById('admin-login-password');
    submit.disabled = true;
    this.showAdminLoginMessage('로그인하는 중입니다.');
    let token;
    try {
      const session = await this.requestAdminAuth('/v2/auth/login', {
        method: 'POST', body: { login_id: loginId.value, password: password.value },
      });
      if (typeof session?.token !== 'string' || !session.token ||
          !Number.isFinite(session.expires_in) || session.expires_in <= 0) {
        throw new Error('Invalid session response');
      }
      token = session.token;
      await this.activateAdminSession({
        token, expiresAt: Date.now() + session.expires_in * 1000, apiBase: this.getAdminAuthOrigin(),
      });
    } catch (error) {
      if (token) this.requestAdminAuth('/v2/auth/logout', { method: 'POST', token }).catch(() => {});
      const messages = {
        401: '아이디 또는 비밀번호를 확인해 주세요.',
        403: '관리자 또는 상담 담당자 권한이 필요합니다.',
        422: '아이디와 비밀번호 형식을 확인해 주세요.',
        429: '로그인 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.',
      };
      this.showAdminLoginMessage(messages[error.status] ||
        '로그인 서버에 연결하지 못했습니다. API 주소와 서버 상태를 확인해 주세요.');
    } finally {
      password.value = '';
      submit.disabled = false;
    }
  },

  async signOutAdmin() {
    const token = this.adminSession?.token;
    this.adminSession = null;
    this.saveAdminSession(null);
    this.renderRoute();
    if (!token) return;
    const submit = document.getElementById('admin-login-submit');
    submit.disabled = true;
    try {
      await this.requestAdminAuth('/v2/auth/logout', { method: 'POST', token });
      this.showAdminLoginMessage('로그아웃했습니다.');
    } catch (error) {
      this.showAdminLoginMessage(error.status === 401 ? '로그아웃했습니다.' :
        '이 탭에서 로그아웃했습니다. 서버 세션 종료는 확인하지 못했습니다.');
    } finally {
      submit.disabled = false;
    }
  },

  saveAdminSession(session) {
    const key = this.getAdminSessionKey();
    try {
      if (session) window.sessionStorage.setItem(key, JSON.stringify(session));
      else window.sessionStorage.removeItem(key);
    } catch {
      // 브라우저 저장소를 사용할 수 없는 경우 현재 페이지에서만 세션을 유지한다.
    }
  },

  showAdminLoginMessage(message) {
    document.getElementById('admin-login-message').textContent = message;
  },

  renderAdminAccess() {
    if (this.adminSession && this.adminSession.expiresAt <= Date.now()) {
      this.adminSession = null;
      this.saveAdminSession(null);
      this.showAdminLoginMessage('로그인 세션이 만료되었습니다. 다시 로그인해 주세요.');
    }
    const signedIn = Boolean(this.adminSession);
    const showingSignup = !signedIn && window.location.hash === '#/signup';
    document.getElementById('admin-login').hidden = signedIn || showingSignup;
    document.getElementById('admin-signup').hidden = !showingSignup;
    document.getElementById('admin-header').hidden = !signedIn;
    document.getElementById('admin-workspace').hidden = !signedIn;
    if (signedIn) {
      document.getElementById('admin-role').textContent =
        this.isLocalAuthDemo() ? '로컬 데모 · 관리자' : this.adminSession.role === 'admin' ? '관리자' : '상담 담당자';
    } else {
      this.liveCounseling = null;
      this.liveAffiliates = null;
      this.liveCustomers = null;
      this.liveCatalog = null;
      this.state.offerCatalog = [];
      this.destroyCharts();
      document.getElementById('app-content').innerHTML = '';
      document.getElementById('modal-root').innerHTML = '';
    }
    return signedIn;
  },
};
