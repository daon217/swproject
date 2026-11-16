import { Redirect } from 'expo-router';
import { useEffect, useRef, useState, type ComponentRef } from 'react';
import { KeyboardAvoidingView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useSession } from '../session';
import { api } from '../shared/api';
import { formatDate, formatTime } from '../shared/format';
import { uuid } from '../shared/platform';
import type { SupportConversation, SupportMessage } from '../shared/types';
import { Button, ErrorText, SubHeader } from '../ui/components';
import { C } from '../ui/theme';
import { KEYBOARD_BEHAVIOR, useKeyboardVisible } from '../ui/useKeyboard';

// 고객지원 상담 채팅 (Figma 05)
export default function SupportScreen() {
  const insets = useSafeAreaInsets();
  const { me, loading } = useSession();
  const [conv, setConv] = useState<SupportConversation | null>(null);
  const [messages, setMessages] = useState<SupportMessage[]>([]);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const keyboard = useKeyboardVisible();
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);

  useEffect(() => {
    if (!me) return;
    let alive = true;
    let timer: ReturnType<typeof setInterval> | undefined;
    api
      .getSupportConversation()
      .then(async (c) => {
        if (!alive) return;
        setConv(c);
        const load = async () => {
          const m = await api.listSupportMessages(c.conversation_id).catch(() => null);
          if (alive && m) setMessages(m);
        };
        await load();
        timer = setInterval(load, 3000); // 실시간 채널 확정 전까지 폴링
      })
      .catch(() => setError('상담을 불러오지 못했어요.'));
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
    };
  }, [me]);

  if (!loading && !me) return <Redirect href="/login" />;

  const send = async () => {
    const body = text.trim();
    if (!body || !conv) return;
    setText('');
    try {
      const msg = await api.sendSupportMessage(conv.conversation_id, body, uuid());
      setMessages((prev) => (prev.some((m) => m.message_id === msg.message_id) ? prev : [...prev, msg]));
    } catch {
      setText(body);
      setError('메시지를 보내지 못했어요.');
    }
  };

  let lastDay = '';
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: C.surfaceMuted }} behavior={KEYBOARD_BEHAVIOR}>
      <SubHeader title="고객지원" />
      <ScrollView ref={scroll} contentContainerStyle={{ padding: 24 }} keyboardShouldPersistTaps="handled" onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}>
        <View style={st.agent}>
          <View style={st.dot} />
          <View>
            <Text style={{ fontWeight: '800', color: C.text }}>꿀픽 고객지원</Text>
            <Text style={{ fontSize: 12, color: C.sub }}>{conv?.agent_name ? `상담사 ${conv.agent_name} · 상담 중` : '상담사 연결 대기 중'}</Text>
          </View>
        </View>
        {messages.length === 0 && <Text style={st.empty}>궁금한 점을 남겨 주시면 상담사가 답변드려요.</Text>}
        {messages.map((m) => {
          const day = formatDate(m.created_at);
          const showDay = day !== lastDay;
          lastDay = day;
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
      </ScrollView>
      {error && (
        <View style={{ paddingHorizontal: 16 }}>
          <ErrorText>{error}</ErrorText>
        </View>
      )}
      <View style={[st.inputRow, { paddingBottom: 12 + (keyboard ? 0 : insets.bottom) }]}>
        <TextInput style={st.input} placeholder="메시지를 입력하세요" placeholderTextColor={C.muted} value={text} onChangeText={setText} maxLength={10000} multiline accessibilityLabel="메시지" />
        <Button label="전송" onPress={() => void send()} disabled={!text.trim() || !conv} style={{ height: 48, paddingHorizontal: 20 }} />
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
  inputRow: { flexDirection: 'row', gap: 8, padding: 12, backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.border, alignItems: 'flex-end' },
  input: { flex: 1, minHeight: 48, maxHeight: 120, borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: C.text },
});
