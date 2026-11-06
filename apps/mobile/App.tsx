import { useState } from 'react';
import { Button, SafeAreaView, Text, View } from 'react-native';
export default function App() {
  const [status, setStatus] = useState('API 연결을 확인하세요.');
  async function check() {
    const base = process.env.EXPO_PUBLIC_API_URL;
    if (!base) { setStatus('EXPO_PUBLIC_API_URL을 설정하세요.'); return; }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(base + '/health', { signal: controller.signal });
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      setStatus(data.status === 'ok' ? 'API 연결 성공' : 'API 확인 필요');
    } catch { setStatus('연결 실패: API 실행 상태와 에뮬레이터 주소를 확인하세요.'); }
    finally { clearTimeout(timer); }
  }
  return <SafeAreaView><View style={{padding:32,gap:20}}><Text style={{fontSize:26}}>꿀픽 모바일 개발환경</Text><Text>연결 확인용입니다. 다른 앱 캡처·오버레이는 아직 구현되지 않았습니다.</Text><Button title="API 확인" onPress={check}/><Text>{status}</Text></View></SafeAreaView>;
}
