import DateTimePicker from '@react-native-community/datetimepicker';
import { useState } from 'react';
import { Platform, Pressable, Text, View } from 'react-native';
import { todaySeoul } from '../shared/format';
import { s } from './components';
import { C } from './theme';

/** 생년월일(YYYY-MM-DD). 미래 날짜 선택 불가. */
export function BirthDateField({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string | null }) {
  const [show, setShow] = useState(false);
  const today = todaySeoul();
  const date = value ? new Date(`${value}T00:00:00`) : new Date(2000, 0, 1);
  return (
    <View style={s.field}>
      <Text style={s.label}>생년월일</Text>
      <Pressable style={[s.input, s.inputRow, !!error && { borderColor: C.danger }]} onPress={() => setShow(true)} accessibilityRole="button" accessibilityLabel="생년월일 선택">
        <Text style={{ color: value ? C.text : C.muted, fontSize: 14 }}>{value || '생년월일 선택'}</Text>
        {!!value && (
          <Pressable onPress={() => onChange('')} hitSlop={8} accessibilityLabel="생년월일 지우기">
            <Text style={{ color: C.sub }}>지우기</Text>
          </Pressable>
        )}
      </Pressable>
      {!!error && <Text style={s.error}>{error}</Text>}
      {show && (
        <DateTimePicker
          value={date}
          mode="date"
          maximumDate={new Date(`${today}T00:00:00`)}
          display={Platform.OS === 'ios' ? 'inline' : 'default'}
          onChange={(e, d) => {
            setShow(Platform.OS === 'ios');
            if (e.type === 'set' && d) {
              const y = d.getFullYear();
              const m = String(d.getMonth() + 1).padStart(2, '0');
              const day = String(d.getDate()).padStart(2, '0');
              onChange(`${y}-${m}-${day}`);
              if (Platform.OS === 'ios') setShow(false);
            } else if (e.type === 'dismissed') setShow(false);
          }}
        />
      )}
    </View>
  );
}
