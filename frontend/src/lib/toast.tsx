// Toast notifications. `toast()` is a plain function so any module (including the
// query client's error handler) can raise one; <Toasts /> renders the live list.

import { useSyncExternalStore } from 'react';
import { Icon } from './icons';

interface ToastItem {
  id: number;
  message: string;
  error: boolean;
}

let items: ToastItem[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function toast(message: string, { error = false }: { error?: boolean } = {}): void {
  const item = { id: nextId++, message, error };
  items = [...items, item];
  emit();
  setTimeout(
    () => {
      items = items.filter((other) => other.id !== item.id);
      emit();
    },
    error ? 6500 : 3500,
  );
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function Toasts() {
  const list = useSyncExternalStore(subscribe, () => items);
  return (
    <div className="toast-region" id="toasts" aria-live="polite">
      {list.map((item) => (
        <div key={item.id} className={`toast${item.error ? ' error' : ''}`} role={item.error ? 'alert' : 'status'}>
          <Icon name={item.error ? 'alert' : 'check'} />
          <span>{item.message}</span>
        </div>
      ))}
    </div>
  );
}
