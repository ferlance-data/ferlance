import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Donut, foldSlices } from './Donut';
import { RadialProgress } from './RadialProgress';

const items = ['A', 'B', 'C', 'D', 'E', 'F', 'G'].map((label, index) => ({ label, value: 70 - index * 10 }));

describe('foldSlices', () => {
  it('keeps five named slices in order with fixed colours, folds the rest into Other', () => {
    const slices = foldSlices(items);
    expect(slices.map((slice) => slice.label)).toEqual(['A', 'B', 'C', 'D', 'E', 'Other']);
    expect(slices.map((slice) => slice.color)).toEqual([1, 2, 3, 4, 5].map((n) => `var(--chart-cat-${n})`).concat('var(--chart-other)'));
    expect(slices.at(-1)?.value).toBe(30); // 20 + 10
    expect(slices.reduce((sum, slice) => sum + slice.share, 0)).toBeCloseTo(1);
  });
  it('drops non-positive values and uses a given total for shares', () => {
    const slices = foldSlices([{ label: 'A', value: 50 }, { label: 'Loss', value: -10 }], 5, 200);
    expect(slices.map((slice) => [slice.label, slice.share])).toEqual([['A', 0.25], ['Other', 0.75]]);
    expect(foldSlices([{ label: 'A', value: 0 }])).toEqual([]);
  });
});

describe('Donut', () => {
  it('has a text alternative and a legend table with values and shares', () => {
    render(<Donut title="Share of revenue" items={items.slice(0, 2)} centerLabel="Revenue" centerValue="GH₵130" formatValue={(value) => `GH₵${value}`} />);
    expect(screen.getByRole('img', { name: /Share of revenue: A 54%, B 46%/ })).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Share of revenue' });
    const rowA = within(table).getByRole('row', { name: /A/ });
    expect(rowA).toHaveTextContent('GH₵70');
    expect(rowA).toHaveTextContent('54%');
  });
  it('shows the hovered slice in the centre', () => {
    const { container } = render(<Donut title="Mix" items={items.slice(0, 2)} centerLabel="Revenue" centerValue="GH₵130" />);
    fireEvent.pointerEnter(container.querySelectorAll('.donut-slice')[1] as Element);
    expect(container.querySelector('.donut-center')).toHaveTextContent('B46%');
  });
});

describe('RadialProgress', () => {
  it('is a labelled meter with its value printed', () => {
    render(<RadialProgress value={3} max={4} label="Setup steps complete" display="3/4" />);
    const meter = screen.getByRole('meter', { name: 'Setup steps complete' });
    expect(meter).toHaveAttribute('aria-valuenow', '3');
    expect(meter).toHaveAttribute('aria-valuetext', '3/4');
    expect(meter).toHaveTextContent('3/4');
  });
  it('clamps out-of-range values', () => {
    render(<RadialProgress value={140} label="Cost recorded" />);
    expect(screen.getByRole('meter')).toHaveTextContent('100%');
  });
});

describe('RadialProgress rounding', () => {
  it('never shows 100% unless complete', () => {
    render(<RadialProgress value={99.8} label="Cost recorded" />);
    expect(screen.getByRole('meter')).toHaveTextContent('99%');
  });
});
