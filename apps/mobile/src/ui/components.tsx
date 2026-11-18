import { router } from 'expo-router';
import { useEffect, useState, type ComponentRef, type ReactNode, type Ref } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Pressable,
  ScrollView,
  Switch,
  Text,
  TextInput,
  View,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ALLERGEN_GROUPS } from '../shared/allergens';
import { IconBack, IconCheck, IconChevronDown, IconForward } from './icons';
import { C } from './theme';
import { s } from './componentStyles';
import { KEYBOARD_BEHAVIOR, useKeyboardVisible } from './useKeyboard';

export function SubHeader({ title, onBack }: { title: string; onBack?: () => void }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[s.header, { paddingTop: insets.top }]}>
      <Pressable style={s.back} onPress={onBack ?? (() => router.back())} accessibilityRole="button" accessibilityLabel="뒤로" hitSlop={8}>
        <IconBack size={24} color={C.primary} />
      </Pressable>
      <Text style={s.headerTitle} accessibilityRole="header">
        {title}
      </Text>
    </View>
  );
}

/** 세로 스크롤 본문 + 하단 고정 액션 (Figma '본문 / 세로 스크롤', '하단 고정 액션') */
export function Page({
  children,
  footer,
  contentStyle,
  scrollRef,
}: {
  children: ReactNode;
  footer?: ReactNode;
  contentStyle?: ViewStyle;
  /** 화면에서 특정 위치로 스크롤해야 할 때(예: 필수 동의 항목) */
  scrollRef?: Ref<ComponentRef<typeof ScrollView>>;
}) {
  const insets = useSafeAreaInsets();
  const keyboard = useKeyboardVisible();
  return (
    <KeyboardAvoidingView style={s.page} behavior={KEYBOARD_BEHAVIOR}>
      <ScrollView ref={scrollRef} contentContainerStyle={[s.pageBody, contentStyle]} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
      {footer && <View style={[s.footer, { paddingBottom: 16 + (keyboard ? 0 : insets.bottom) }]}>{footer}</View>}
    </KeyboardAvoidingView>
  );
}

type BtnVariant = 'primary' | 'outline' | 'danger' | 'pill';
export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  loading,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: BtnVariant;
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
}) {
  const v = variant;
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!(disabled || loading) }} aria-disabled={!!(disabled || loading)}
      style={({ pressed }) => [
        s.btn,
        v === 'primary' && s.btnPrimary,
        v === 'danger' && s.btnDanger,
        v === 'outline' && s.btnOutline,
        v === 'pill' && s.btnPill,
        (disabled || loading) && { opacity: 0.45 },
        pressed && { opacity: 0.8 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={v === 'outline' || v === 'pill' ? C.primary : '#fff'} />
      ) : (
        <Text style={[s.btnText, (v === 'outline' || v === 'pill') && { color: C.primary }, v === 'pill' && { fontSize: 14 }]}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Field({ label, error, ...input }: { label: string; error?: string | null } & TextInputProps) {
  return (
    <View style={s.field}>
      <Text style={s.label}>{label}</Text>
      <TextInput placeholderTextColor={C.muted} style={[s.input, !!error && { borderColor: C.danger }]} accessibilityLabel={label} {...input} />
      {!!error && <Text style={s.error}>{error}</Text>}
    </View>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <View style={s.note}>
      <Text style={s.noteText}>{children}</Text>
    </View>
  );
}

export function H1({ children, style }: { children: ReactNode; style?: object }) {
  return (
    <Text style={[s.h1, style]} accessibilityRole="header">
      {children}
    </Text>
  );
}
export function H2({ children }: { children: ReactNode }) {
  return <Text style={s.h2}>{children}</Text>;
}
export function Desc({ children, style }: { children: ReactNode; style?: object }) {
  return <Text style={[s.desc, style]}>{children}</Text>;
}
export function ErrorText({ children }: { children: ReactNode }) {
  return <Text style={s.error}>{children}</Text>;
}

export function Toggle({ value, onChange, label, disabled }: { value: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <Switch
      value={value}
      onValueChange={onChange}
      disabled={disabled}
      accessibilityLabel={label}
      trackColor={{ true: C.primary, false: '#D5DAE3' }}
      thumbColor="#fff"
      ios_backgroundColor="#D5DAE3"
    />
  );
}

export function RowButton({ label, onPress, danger }: { label: string; onPress: () => void; danger?: boolean }) {
  return (
    <Pressable style={s.row} onPress={onPress} accessibilityRole="button">
      <Text style={[s.rowText, danger && { color: C.danger }]}>{label}</Text>
      {!danger && <IconForward size={20} color={C.sub} />}
    </Pressable>
  );
}

export function Checkbox({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <Pressable style={s.check} onPress={() => onChange(!checked)} accessibilityRole="checkbox" accessibilityState={{ checked }} aria-checked={checked} hitSlop={4}>
      <View style={[s.checkBox, checked && s.checkBoxOn]}>{checked && <IconCheck size={14} color="#fff" strokeWidth={3} />}</View>
      <Text style={s.checkLabel}>{label}</Text>
    </Pressable>
  );
}

export function AllergyPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({ [ALLERGEN_GROUPS[0].group]: true });
  const toggle = (code: string, on: boolean) => onChange(on ? [...value, code] : value.filter((c) => c !== code));
  return (
    <View style={s.allergy}>
      {ALLERGEN_GROUPS.map((g) => {
        const isOpen = !!open[g.group];
        const picked = g.items.filter((i) => value.includes(i.code)).length;
        return (
          <View key={g.group}>
            <Pressable style={s.allergyHead} onPress={() => setOpen({ ...open, [g.group]: !isOpen })} accessibilityRole="button" accessibilityState={{ expanded: isOpen }} aria-expanded={isOpen}>
              {isOpen ? <IconChevronDown size={16} /> : <IconForward size={16} />}
              <Text style={s.allergyHeadText}>{g.group}</Text>
              {picked > 0 && <Text style={s.allergyCount}>{picked}</Text>}
            </Pressable>
            {isOpen && g.items.map((i) => <Checkbox key={i.code} label={i.label} checked={value.includes(i.code)} onChange={(on) => toggle(i.code, on)} />)}
          </View>
        );
      })}
    </View>
  );
}

const GENDERS = [
  { v: 'female', l: '여성' },
  { v: 'male', l: '남성' },
  { v: 'prefer_not_to_say', l: '응답 안 함' },
];
export function GenderSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <View style={s.field}>
      <Text style={s.label}>성별</Text>
      <View style={s.chips} accessibilityRole="radiogroup">
        {GENDERS.map((g) => {
          const on = value === g.v;
          return (
            <Pressable key={g.v} onPress={() => onChange(on ? '' : g.v)} style={[s.chip, on && s.chipOn]} accessibilityRole="radio" accessibilityState={{ checked: on }} aria-checked={on}>
              <Text style={[s.chipText, on && { color: C.primary, fontWeight: '700' }]}>{g.l}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export { BirthDateField } from './BirthDateField';

export function ConfirmDialog({
  visible,
  title,
  body,
  confirmLabel,
  cancelLabel = '취소',
  onConfirm,
  onCancel,
  danger,
}: {
  visible: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  cancelLabel?: string | null;
  onConfirm: () => void;
  onCancel?: () => void;
  danger?: boolean;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel ?? onConfirm}>
      <View style={s.dim}>
        <View style={s.dialog} accessibilityViewIsModal>
          <Text style={s.dialogTitle}>{title}</Text>
          <View style={{ marginBottom: 20 }}>{typeof body === 'string' ? <Text style={s.dialogBody}>{body}</Text> : body}</View>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            {cancelLabel && onCancel && <Button variant="outline" label={cancelLabel} onPress={onCancel} style={{ flex: 1 }} />}
            <Button variant={danger ? 'danger' : 'primary'} label={confirmLabel} onPress={onConfirm} style={{ flex: 1 }} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onDone, 2600);
    return () => clearTimeout(t);
  }, [message, onDone]);
  if (!message) return null;
  return (
    <View style={s.toast} accessibilityLiveRegion="polite">
      <Text style={{ color: '#fff', fontSize: 13 }}>{message}</Text>
    </View>
  );
}

export { s } from './componentStyles';
