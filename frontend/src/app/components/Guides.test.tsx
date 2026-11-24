import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { TOUR_KEY } from '../../lib/guides';
import { Router } from '../../lib/router';
import { WelcomeTour } from './Guides';

beforeAll(() => {
  // jsdom does not implement modal dialogs.
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.open = true;
  };
});

beforeEach(() => localStorage.clear());

describe('WelcomeTour', () => {
  it('shows once, and remembers when dismissed', () => {
    const { unmount } = render(
      <Router>
        <WelcomeTour />
      </Router>,
    );
    expect(screen.getByRole('heading', { name: 'Welcome to Ferlance' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Not now' }));
    expect(screen.queryByRole('heading', { name: 'Welcome to Ferlance' })).toBeNull();
    expect(localStorage.getItem(TOUR_KEY)).toBe('1');
    unmount();
    render(
      <Router>
        <WelcomeTour />
      </Router>,
    );
    expect(screen.queryByRole('heading', { name: 'Welcome to Ferlance' })).toBeNull();
  });
});
