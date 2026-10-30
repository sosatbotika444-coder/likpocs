// Lightweight UI sound effects synthesized with the Web Audio API (no audio files, no network).
// Sounds are opt-out per browser and respect the user's preference stored in localStorage.

export type SoundName = 'success' | 'error' | 'notify' | 'drop' | 'click' | 'open';

const STORAGE_KEY = 'rsbest.sound';
let context: AudioContext | null = null;
const listeners = new Set<(enabled: boolean) => void>();

export function soundEnabled(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== 'off';
}

export function setSoundEnabled(enabled: boolean) {
  localStorage.setItem(STORAGE_KEY, enabled ? 'on' : 'off');
  listeners.forEach((listener) => listener(enabled));
  if (enabled) playSound('click');
}

export function onSoundChange(listener: (enabled: boolean) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function audio(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  context ??= new Ctor();
  if (context.state === 'suspended') void context.resume();
  return context;
}

function tone(ctx: AudioContext, frequency: number, start: number, duration: number, type: OscillatorType = 'sine', volume = 0.08) {
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, ctx.currentTime + start);
  gain.gain.setValueAtTime(0.0001, ctx.currentTime + start);
  gain.gain.exponentialRampToValueAtTime(volume, ctx.currentTime + start + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + duration);
  oscillator.connect(gain).connect(ctx.destination);
  oscillator.start(ctx.currentTime + start);
  oscillator.stop(ctx.currentTime + start + duration + 0.02);
}

export function playSound(name: SoundName) {
  if (!soundEnabled()) return;
  try {
    const ctx = audio();
    if (!ctx) return;
    switch (name) {
      case 'success': tone(ctx, 660, 0, 0.12); tone(ctx, 880, 0.09, 0.14); tone(ctx, 1320, 0.18, 0.2, 'sine', 0.05); break;
      case 'error': tone(ctx, 220, 0, 0.16, 'triangle', 0.09); tone(ctx, 165, 0.12, 0.22, 'triangle', 0.08); break;
      case 'notify': tone(ctx, 988, 0, 0.1, 'sine', 0.06); tone(ctx, 1319, 0.1, 0.18, 'sine', 0.05); break;
      case 'drop': tone(ctx, 420, 0, 0.07, 'square', 0.025); tone(ctx, 630, 0.05, 0.09, 'sine', 0.05); break;
      case 'open': tone(ctx, 520, 0, 0.08, 'sine', 0.04); tone(ctx, 780, 0.05, 0.1, 'sine', 0.035); break;
      case 'click': tone(ctx, 1200, 0, 0.04, 'sine', 0.03); break;
    }
  } catch {
    // Audio is decorative; never break a workflow because of it.
  }
}
