import type { ReactNode } from 'react';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

type P = { size?: number; color?: string; strokeWidth?: number };

function Icon({ size = 20, color = '#1A2233', strokeWidth = 2, children }: P & { children: ReactNode }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
      {children}
    </Svg>
  );
}

export const IconSearch = (p: P) => (
  <Icon {...p}>
    <Circle cx="11" cy="11" r="7" />
    <Path d="m20 20-3.5-3.5" />
  </Icon>
);
export const IconClose = (p: P) => (
  <Icon {...p}>
    <Path d="M6 6l12 12M18 6 6 18" />
  </Icon>
);
export const IconBack = (p: P) => (
  <Icon {...p}>
    <Path d="m15 18-6-6 6-6" />
  </Icon>
);
export const IconForward = (p: P) => (
  <Icon {...p}>
    <Path d="m9 18 6-6-6-6" />
  </Icon>
);
export const IconChevronDown = (p: P) => (
  <Icon {...p}>
    <Path d="m6 9 6 6 6-6" />
  </Icon>
);
export const IconExternal = (p: P) => (
  <Icon {...p}>
    <Path d="M14 4h6v6M20 4l-9 9" />
    <Path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" />
  </Icon>
);
export const IconPrinter = (p: P) => (
  <Icon {...p}>
    <Path d="M7 8V4h10v4" />
    <Rect x="3" y="8" width="18" height="9" rx="2" />
    <Path d="M7 14h10v6H7z" />
  </Icon>
);
export const IconFood = (p: P) => (
  <Icon {...p}>
    <Rect x="5" y="4" width="14" height="17" rx="3" />
    <Path d="M5 8h14M12 11v6M9 14h6" />
  </Icon>
);
export const IconFilter = (p: P) => (
  <Icon {...p}>
    <Path d="M4 5h16l-6 7v6l-4 2v-8z" />
  </Icon>
);
export const IconPlus = (p: P) => (
  <Icon {...p}>
    <Path d="M12 5v14M5 12h14" />
  </Icon>
);
export const IconCheck = (p: P) => (
  <Icon {...p}>
    <Path d="m5 12 5 5L20 7" />
  </Icon>
);
export const IconWarning = (p: P) => (
  <Icon {...p}>
    <Path d="M12 3 2 20h20z" />
    <Path d="M12 10v4M12 17h.01" />
  </Icon>
);
export const IconClock = (p: P) => (
  <Icon {...p}>
    <Circle cx="12" cy="12" r="9" />
    <Path d="M12 7v5l3 2" />
  </Icon>
);
export const IconGlobe = (p: P) => (
  <Icon {...p}>
    <Circle cx="12" cy="12" r="9" />
    <Path d="M3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18" />
  </Icon>
);
export const IconGear = (p: P) => (
  <Icon {...p}>
    <Circle cx="12" cy="12" r="3" />
    <Path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </Icon>
);
export const IconHome = (p: P) => (
  <Icon {...p}>
    <Path d="M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" />
  </Icon>
);
export const IconReload = (p: P) => (
  <Icon {...p}>
    <Path d="M20 12a8 8 0 1 1-2.3-5.7L20 8" />
    <Path d="M20 3v5h-5" />
  </Icon>
);
export const IconLock = (p: P) => (
  <Icon {...p}>
    <Rect x="5" y="11" width="14" height="10" rx="2" />
    <Path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </Icon>
);
export const IconMoreVert = ({ size = 20, color = '#1A2233' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill={color}>
    <Circle cx="12" cy="5.5" r="1.8" />
    <Circle cx="12" cy="12" r="1.8" />
    <Circle cx="12" cy="18.5" r="1.8" />
  </Svg>
);
