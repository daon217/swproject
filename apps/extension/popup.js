document.getElementById('check').addEventListener('click', async () => {
  const result = document.getElementById('result');
  result.textContent = '연결 중…';
  try {
    const port = Number(document.getElementById('port').value);
    if (!Number.isInteger(port) || port < 1024 || port > 65535) {
      result.textContent = 'API 포트는 1024~65535 사이 정수로 입력하세요.';
      return;
    }
    const response = await fetch(`http://127.0.0.1:${port}/health`, {signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('API 오류');
    const data = await response.json();
    result.textContent = data.status === 'ok' ? 'API 연결 성공' : 'API 상태 확인 필요';
  } catch { result.textContent = '연결 실패: 자기 PC의 백엔드 실행 상태와 API 포트를 확인하세요.'; }
});
