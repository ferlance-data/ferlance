import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PageErrorBoundary, isChunkLoadError } from './PageErrorBoundary';

function Boom({ message }: { message: string }): never {
  throw new Error(message);
}

describe('PageErrorBoundary', () => {
  it('shows a recoverable message instead of blanking the app', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(
      <div>
        <p>sidebar</p>
        <PageErrorBoundary>
          <Boom message="Cannot read properties of undefined" />
        </PageErrorBoundary>
      </div>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('This page could not be displayed');
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
    expect(screen.getByText('sidebar')).toBeInTheDocument();
  });

  it('recognises stale-chunk failures from each browser', () => {
    expect(isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: /assets/Products-abc.js'))).toBe(true);
    expect(isChunkLoadError(new TypeError('Importing a module script failed.'))).toBe(true);
    expect(isChunkLoadError(new Error('error loading dynamically imported module'))).toBe(true);
    expect(isChunkLoadError(new Error('boom'))).toBe(false);
  });
});
