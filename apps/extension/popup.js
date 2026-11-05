document.getElementById('check').addEventListener('click', async () => {
  const result = document.getElementById('result');
  result.textContent = '연결 중…';
  try {
    const response = await fetch('http://127.0.0.1:18000/health', {signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('API 오류');
    const data = await response.json();
    result.textContent = data.status === 'ok' ? '공통 API 연결 성공' : 'API 상태 확인 필요';
  } catch { result.textContent = '연결 실패: 터널과 호스트 실행 상태를 확인하세요.'; }
});
