import { useSession } from '../session';
import { loadVisits, recordVisit, clearVisits, type Visit } from '../shared/accountData';
import { useEffect, useState } from 'react';
import { Animated, Easing, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { safeHttpUrl } from '../shared/format';
import { DEFAULT_SHORTCUTS, loadShortcuts, saveShortcuts, type Shortcut } from '../shared/shortcuts';
import { uuid } from '../shared/platform';
import { Button, Desc, ErrorText, Note, s as cs, Toast } from './components';
import { IconBack, IconForward, IconPlus } from './icons';
import { C } from './theme';
import { KEYBOARD_BEHAVIOR } from './useKeyboard';

// 쇼핑몰 바로가기(Figma 02): 브라우저 시작 화면. 이 기기에만 저장.
// 편집 모드에서 −로 삭제하고, ‹ › 버튼으로 순서를 바꾼다(드래그 대신 접근성 있는 방식).

export function ShortcutsHome({ onOpen }: { onOpen: (url: string) => void }) {
  const { me, loading } = useSession();
  if (loading) return null;
  return <AccountShortcuts key={me?.user_id ?? 'guest'} userId={me?.user_id} onOpen={onOpen} />;
}
function AccountShortcuts({ userId, onOpen }: { userId?: string; onOpen: (url: string) => void }) {
  const [list, setList] = useState<Shortcut[]>(DEFAULT_SHORTCUTS);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [visits, setVisits] = useState<Visit[]>([]);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let alive = true;
    void Promise.all([loadShortcuts(userId), loadVisits(userId)]).then(([saved, history]) => {
      if (alive) { setList(saved); setVisits(history); setReady(true); }
    });
    return () => { alive = false; };
  }, [userId]);
  const open = (url: string) => {
    void recordVisit(userId, url).then(() => loadVisits(userId)).then(setVisits);
    onOpen(url);
  };
  const clearHistory = async () => { await clearVisits(userId); setVisits([]); };


  const update = (next: Shortcut[]) => {
    if (!userId || !ready) return;
    setList(next);
    void saveShortcuts(next, userId);
  };
  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= list.length) return;
    const next = [...list];
    [next[i], next[j]] = [next[j], next[i]];
    update(next);
  };

  return (
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={{ padding: 24 }}>
        <View style={st.titleRow}>
          <Text style={st.title}>{editing ? '바로가기 편집' : '쇼핑몰 바로가기'}</Text>
          <Button variant={editing ? 'primary' : 'pill'} disabled={!userId || !ready} label={editing ? '완료' : '편집'} onPress={() => setEditing(!editing)} style={editing ? { height: 34, borderRadius: 999 } : undefined} />
        </View>
        <Desc>{editing ? '−를 눌러 삭제하고, 화살표로 순서를 바꿔요.' : '자주 가는 쇼핑몰을 직접 추가하고 정리할 수 있어요.'}</Desc>
        {!userId && <Note>로그인하면 나만의 바로가기와 방문 기록을 이 기기에 저장할 수 있어요.</Note>}
        <View style={st.grid}>
          {list.map((sc, i) => (
            <View key={sc.id} style={st.cell}>
              <Pressable
                onPress={() => !editing && open(sc.url)}
                style={[st.icon, editing && st.iconEditing]}
                accessibilityRole="button"
                accessibilityLabel={editing ? sc.name : `${sc.name} 열기`}
              >
                <Text style={st.iconText}>{sc.mark ?? sc.name.trim().charAt(0)}</Text>
              </Pressable>
              <Text style={st.name} numberOfLines={1}>
                {sc.name}
              </Text><Text style={{ fontSize: 10, color: C.sub }}>{DEFAULT_SHORTCUTS.some(d => d.id === sc.id) ? '기본 제공' : '내가 저장'}</Text>
              {editing && (
                <>
                  <Pressable style={st.remove} onPress={() => update(list.filter((x) => x.id !== sc.id))} accessibilityLabel={`${sc.name} 삭제`} hitSlop={6}>
                    <View style={st.removeBar} />
                  </Pressable>
                  <View style={st.moveRow}>
                    <Pressable onPress={() => move(i, -1)} accessibilityLabel={`${sc.name} 앞으로`} hitSlop={6} disabled={i === 0}>
                      <IconBack size={16} color={i === 0 ? C.border : C.sub} />
                    </Pressable>
                    <Pressable onPress={() => move(i, 1)} accessibilityLabel={`${sc.name} 뒤로`} hitSlop={6} disabled={i === list.length - 1}>
                      <IconForward size={16} color={i === list.length - 1 ? C.border : C.sub} />
                    </Pressable>
                  </View>
                </>
              )}
            </View>
          ))}
          <View style={st.cell}>
            <Pressable style={[st.icon, st.iconAdd]} disabled={!userId || !ready} onPress={() => setAdding(true)} accessibilityRole="button" accessibilityLabel="바로가기 추가">
              <IconPlus size={22} color={C.sub} />
            </Pressable>
            <Text style={[st.name, { color: C.sub }]}>추가</Text>
          </View>
        </View>
        <Note>{editing ? '변경한 바로가기는 현재 계정 전용으로 이 기기에 저장돼요.' : '바로가기를 누르면 앱 안 브라우저로 열리고, 상품 페이지에서 AI 추천이 화면에 표시돼요.'}</Note>
        <Text style={st.sheetTitle}>최근 방문 페이지</Text>
        <Desc>앱에서 직접 연 페이지를 최대 50개·30일간 이 기기에 보관해요. 바로가기와는 별개예요.</Desc>
        {visits[0] && <Button label="마지막 페이지 다시 열기" onPress={() => open(visits[0].url)} />}
        {visits.slice(0, 10).map(v => <Button key={v.url} variant="outline" label={v.url} onPress={() => open(v.url)} />)}
        {!visits.length && <Text>방문 기록이 없어요.</Text>}
        {!!visits.length && <Button label="방문 기록 삭제" onPress={() => void clearHistory()} />}
      </ScrollView>
      {adding && <AddSheet
        visible={adding}
        onCancel={() => setAdding(false)}
        onAdd={(sc) => {
          update([...list, sc]);
          setAdding(false);
          setToast(`'${sc.name}' 바로가기를 추가했어요.`);
        }}
      />}
      <Toast message={toast} onDone={() => setToast(null)} />
    </View>
  );
}

function AddSheet({ visible, onAdd, onCancel }: { visible: boolean; onAdd: (s: Shortcut) => void; onCancel: () => void }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [error, setError] = useState<string | null>(null);
  // 배경(dim)은 Modal의 fade로 제자리에서 나타나고, 흰 시트만 아래에서 올라온다.
  const [slide] = useState(() => new Animated.Value(0));

  useEffect(() => {
    if (visible) {
      slide.setValue(0);
      Animated.timing(slide, { toValue: 1, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: Platform.OS !== 'web' }).start();
    }
  }, [visible, slide]);

  const submit = () => {
    const n = name.trim();
    if (!n) return setError('쇼핑몰 이름을 입력해 주세요.');
    const raw = url.trim();
    const safe = safeHttpUrl(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!raw || !safe || !new URL(safe).hostname.includes('.')) return setError('올바른 주소를 입력해 주세요.');
    onAdd({ id: uuid(), name: n.slice(0, 20), url: safe });
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel} statusBarTranslucent navigationBarTranslucent>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={KEYBOARD_BEHAVIOR}>
        <Pressable style={st.sheetDim} onPress={onCancel} accessibilityLabel="닫기">
          <Animated.View style={{ transform: [{ translateY: slide.interpolate({ inputRange: [0, 1], outputRange: [400, 0] }) }] }}>
            <Pressable style={st.sheet} onPress={() => undefined}>
              <View style={st.handle} />
              <Text style={st.sheetTitle}>바로가기 추가</Text>
              <Desc>쇼핑몰 이름과 주소를 입력해 주세요.</Desc>
              <Text style={cs.label}>이름</Text>
              <TextInput
                style={[cs.input, { marginBottom: 16 }]}
                placeholder="예) 오아시스마켓"
                placeholderTextColor={C.muted}
                value={name}
                onChangeText={setName}
                accessibilityLabel="이름"
              />
              <Text style={cs.label}>주소 (URL)</Text>
              <TextInput
                style={cs.input}
                placeholder="https://www.oasis.co.kr"
                placeholderTextColor={C.muted}
                value={url}
                onChangeText={setUrl}
                autoCapitalize="none"
                keyboardType="url"
                accessibilityLabel="주소"
                onSubmitEditing={submit}
              />
              {error && <ErrorText>{error}</ErrorText>}
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 20 }}>
                <Button variant="outline" label="취소" onPress={onCancel} style={{ flex: 1 }} />
                <Button label="추가" onPress={submit} style={{ flex: 1 }} />
              </View>
            </Pressable>
          </Animated.View>
        </Pressable>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const st = StyleSheet.create({
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { fontSize: 26, fontWeight: '800', color: C.text },
  grid: { flexDirection: 'row', flexWrap: 'wrap', rowGap: 18, marginTop: 8 },
  cell: { width: '25%', alignItems: 'center' },
  icon: { width: 56, height: 56, borderRadius: 14, backgroundColor: C.primarySoft, alignItems: 'center', justifyContent: 'center' },
  iconEditing: { borderWidth: 1, borderColor: '#D7DEEF' },
  iconAdd: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: '#C9D0DC', borderStyle: 'dashed' },
  iconText: { color: C.primary, fontWeight: '800', fontSize: 18 },
  name: { fontSize: 12, color: C.text, marginTop: 6, maxWidth: 76 },
  remove: { position: 'absolute', top: -6, right: 6, width: 24, height: 24, borderRadius: 12, backgroundColor: C.danger, borderWidth: 2, borderColor: '#fff', alignItems: 'center', justifyContent: 'center' },
  removeBar: { width: 10, height: 2, backgroundColor: '#fff', borderRadius: 1 },
  moveRow: { flexDirection: 'row', gap: 14, marginTop: 4 },
  sheetDim: { flex: 1, backgroundColor: C.dim, justifyContent: 'flex-end' },
  sheet: { backgroundColor: C.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingTop: 12 },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: '#D5DAE3', alignSelf: 'center' },
  sheetTitle: { fontSize: 18, fontWeight: '800', color: C.text, marginTop: 12 },
});
