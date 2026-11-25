import { Redirect } from 'expo-router';
import { useEffect, useRef, useState, type ComponentRef } from 'react';
import { KeyboardAvoidingView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useSession } from '../session';
import { api } from '../shared/api';
import { formatDate, formatTime } from '../shared/format';
import { uuid } from '../shared/platform';
import { ApiError, type SupportConversation, type SupportMessage } from '../shared/types';
import { Button, ErrorText, SubHeader } from '../ui/components';
import { C } from '../ui/theme';
import { KEYBOARD_BEHAVIOR, useKeyboardVisible } from '../ui/useKeyboard';

/** 상담원이 상담을 끝냈는지(서버 status가 resolved·closed) */
const isClosed = (c: SupportConversation | null) => c?.status === 'resolved' || c?.status === 'closed';

// 고객지원 상담 채팅 (Figma 05). 확장의 SupportScreen과 같은 규칙.
// 상담이 종료되면 대화 끝에 '상담이 종료되었습니다.'를 보여주고 입력창을 막는다. 새 상담은 버튼으로 시작한다.
export default function SupportScreen() {
  const insets = useSafeAreaInsets();
  const { me, loading } = useSession();
  const [conv, setConv] = useState<SupportConversation | null>(null);
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const keyboard = useKeyboardVisible();
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const convId = conv?.conversation_id;
  const closed = isClosed(conv);

  // 처음 열 때: 진행 중인 상담이 있으면 그것을, 없으면 가장 최근 상담(종료됐으면 종료 상태로)을 보여준다.
  // 상담 기록이 하나도 없을 때만 새 상담을 연다(POST는 종료된 상담 대신 새 상담을 만든다).
  useEffect(() => {
    if (!me) return;
    let alive = true;
    (async () => {
      const list = await api.listSupportConversations().catch(() => [] as SupportConversation[]);
      return list[0] ?? (await api.getSupportConversation());
    })()
      .then((c) => {
        if (alive) setConv(c);
      })
      .catch(() => {
        if (alive) setError('상담을 불러오지 못했어요.');
      });
    return () => {
      alive = false;
    };
  }, [me]);

  // 메시지와 상담 상태를 3초마다 갱신한다(실시간 채널 확정 전까지 폴링). 종료되면 더 묻지 않는다.
  useEffect(() => {
    if (!convId) return;
    let alive = true;
    const load = async () => {
      const [m, list] = await Promise.all([
        api.listSupportMessages(convId).catch(() => null),
        api.listSupportConversations().catch(() => null),
      ]);
      if (!alive) return;
      if (m) setMessages(m);
      const cur = list?.find((c) => c.conversation_id === convId);
      if (cur) setConv((prev) => (prev && prev.status !== cur.status ? { ...prev, status: cur.status } : prev));
    };
    void load();
    if (closed) {
      return () => {
        alive = false;
      };
    }
    const timer = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [convId, closed]);

  if (!loading && !me) return <Redirect href="/login" />;

  const send = async () => {
    const body = text.trim();
    if (!body || !conv || closed) return;
    setText('');
    try {
      const msg = await api.sendSupportMessage(conv.conversation_id, body, uuid());
      setMessages((prev) => (prev.some((m) => m.message_id === msg.message_id) ? prev : [...prev, msg]));
    } catch (e) {
      setText(body);
      // 보내는 사이 상담이 종료됐으면 종료 상태로 바꾼다.
      if (e instanceof ApiError && e.code === 'CONVERSATION_CLOSED') setConv((prev) => (prev ? { ...prev, status: 'resolved' } : prev));
      else setError('메시지를 보내지 못했어요.');
    }
  };

  const startNew = async () => {
    setStarting(true);
    setError(null);
    try {
      const c = await api.getSupportConversation();
      setMessages([]);
      setText('');
      setConv(c);
    } catch {
      setError('새 상담을 시작하지 못했어요.');
    } finally {
      setStarting(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: C.surfaceMuted }} behavior={KEYBOARD_BEHAVIOR}>
      <SubHeader title="고객지원" />
      <ScrollView ref={scroll} contentContainerStyle={{ padding: 24 }} keyboardShouldPersistTaps="handled" onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}>
        <View style={st.agent}>
          <View style={[st.dot, closed && { backgroundColor: C.muted }]} />
          <View>
            <Text style={{ fontWeight: '800', color: C.text }}>꿀픽 고객지원</Text>
            <Text style={{ fontSize: 12, color: C.sub }}>{closed ? '상담 종료' : conv?.agent_name ? `상담사 ${conv.agent_name} · 상담 중` : '상담사 연결 대기 중'}</Text>
          </View>
        </View>
        {messages.length === 0 && !closed && <Text style={st.empty}>궁금한 점을 남겨 주시면 상담사가 답변드려요.</Text>}
        {messages.map((m, index) => {
          const day = formatDate(m.created_at);
          const showDay = index === 0 || day !== formatDate(messages[index - 1].created_at);
          const mine = m.sender === 'member';
          return (
            <View key={m.message_id}>
              {showDay && <Text style={st.day}>{day}</Text>}
              <View style={{ alignItems: mine ? 'flex-end' : 'flex-start', marginBottom: 14 }}>
                {!mine && !!m.sender_name && <Text style={st.name}>{m.sender_name}</Text>}
                <View style={[st.bubble, mine && st.bubbleMe]}>
                  <Text style={{ color: mine ? '#fff' : C.text, fontSize: 14, lineHeight: 20 }}>{m.body}</Text>
                </View>
                <Text style={st.time}>{formatTime(m.created_at)}</Text>
              </View>
            </View>
          );
        })}
        {closed && (
          <View style={st.closed} accessibilityRole="text" accessibilityLiveRegion="polite">
            <View style={st.closedLine} />
            <Text style={st.closedText}>상담이 종료되었습니다.</Text>
            <View style={st.closedLine} />
          </View>
        )}
      </ScrollView>
      {error && (
        <View style={{ paddingHorizontal: 16 }}>
          <ErrorText>{error}</ErrorText>
        </View>
      )}
      {closed && (
        <View style={{ paddingHorizontal: 12, paddingTop: 8, backgroundColor: C.surface }}>
          <Button variant="outline" label="새 상담 시작하기" onPress={() => void startNew()} loading={starting} />
        </View>
      )}
      <View style={[st.inputRow, { paddingBottom: 12 + (keyboard ? 0 : insets.bottom) }]}>
        <TextInput
          style={[st.input, closed && st.inputOff]}
          placeholder={closed ? '상담이 종료되어 메시지를 보낼 수 없어요' : '메시지를 입력하세요'}
          placeholderTextColor={C.muted}
          value={text}
          onChangeText={setText}
          maxLength={10000}
          multiline
          editable={!closed && !!conv}
          accessibilityLabel="메시지"
          accessibilityState={{ disabled: closed }}
        />
        <Button label="전송" onPress={() => void send()} disabled={closed || !text.trim() || !conv} style={{ height: 48, paddingHorizontal: 20 }} />
      </View>
    </KeyboardAvoidingView>
  );
}

const st = StyleSheet.create({
  agent: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.surface, borderRadius: 12, padding: 14 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: C.success },
  empty: { textAlign: 'center', color: C.sub, paddingVertical: 32 },
  day: { textAlign: 'center', color: C.sub, fontSize: 12, marginVertical: 14 },
  name: { fontSize: 12, color: '#4A5465', marginBottom: 6 },
  bubble: { maxWidth: '80%', backgroundColor: C.surface, borderRadius: 16, padding: 12 },
  bubbleMe: { backgroundColor: C.primary },
  time: { fontSize: 11, color: C.sub, marginTop: 6 },
  closed: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 20, marginBottom: 8 },
  closedLine: { flex: 1, borderTopWidth: 1, borderStyle: 'dashed', borderColor: C.border },
  closedText: { fontSize: 12, color: C.sub },
  inputRow: { flexDirection: 'row', gap: 8, padding: 12, backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.border, alignItems: 'flex-end' },
  input: { flex: 1, minHeight: 48, maxHeight: 120, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: C.text },
  inputOff: { backgroundColor: C.surfaceMuted, color: C.muted },
});
