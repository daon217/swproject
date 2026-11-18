import { Text, View } from 'react-native';
import { todaySeoul } from '../shared/format';
import { s } from './componentStyles';
import { C } from './theme';

// 웹 미리보기용 생년월일 입력. 네이티브 날짜 선택기 대신 브라우저 기본 date 입력을 쓴다.
export function BirthDateField({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string | null }) {
  return (
    <View style={s.field}>
      <Text style={s.label}>생년월일</Text>
      <input
        type="date"
        aria-label="생년월일"
        max={todaySeoul()}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          height: 48,
          border: `1px solid ${error ? C.danger : C.border}`,
          borderRadius: 10,
          padding: '0 16px',
          fontSize: 14,
          color: value ? C.text : C.muted,
          fontFamily: 'inherit',
          background: C.surface,
        }}
      />
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}
