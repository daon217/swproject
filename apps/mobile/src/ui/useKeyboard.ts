import { useEffect, useState } from 'react';
import { Keyboard, Platform } from 'react-native';

// Android는 edge-to-edge라 키보드가 올라와도 창 크기가 줄지 않는다.
// 그래서 KeyboardAvoidingView는 두 플랫폼 모두 'padding'으로 쓰고,
// 키보드가 떠 있는 동안에는 하단 안전 영역 여백을 빼서 입력창이 키보드에 바로 붙게 한다.

export const KEYBOARD_BEHAVIOR = Platform.OS === 'web' ? undefined : ('padding' as const);

export function useKeyboardVisible(): boolean {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const show = Keyboard.addListener(Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow', () => setVisible(true));
    const hide = Keyboard.addListener(Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide', () => setVisible(false));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  return visible;
}
