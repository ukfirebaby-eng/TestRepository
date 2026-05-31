export type FocusAnimationState = {
  key: string | null;
  frames: number;
  active: boolean;
};

export function advanceFocusAnimation(
  state: FocusAnimationState,
  focusKey: string | null,
  maxFrames = 90,
): FocusAnimationState {
  if (!focusKey) return { key: null, frames: 0, active: false };
  if (state.key !== focusKey) return { key: focusKey, frames: 1, active: true };
  if (!state.active) return state;

  const frames = state.frames + 1;
  return { key: focusKey, frames, active: frames <= maxFrames };
}
