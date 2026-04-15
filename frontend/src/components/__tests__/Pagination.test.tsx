import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import Pagination, { buildPageList } from '../Pagination';

describe('buildPageList', () => {
  it('shows all pages when total <= 7', () => {
    expect(buildPageList(1, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(buildPageList(3, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it('inserts ellipsis when total > 7 and current is middle', () => {
    expect(buildPageList(5, 20)).toEqual([1, 'ellipsis', 3, 4, 5, 6, 7, 'ellipsis', 20]);
  });

  it('omits leading ellipsis when current is near start', () => {
    expect(buildPageList(1, 20)).toEqual([1, 2, 3, 'ellipsis', 20]);
  });

  it('omits trailing ellipsis when current is near end', () => {
    expect(buildPageList(18, 20)).toEqual([1, 'ellipsis', 16, 17, 18, 19, 20]);
  });
});

describe('Pagination component', () => {
  it('renders nothing when totalPages is 0', () => {
    const { container } = render(
      <Pagination page={1} totalPages={0} onPageChange={() => {}} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('hides << and < on first page', () => {
    render(<Pagination page={1} totalPages={5} onPageChange={() => {}} />);
    expect(screen.queryByLabelText('first-page')).toBeNull();
    expect(screen.queryByLabelText('prev-page')).toBeNull();
    expect(screen.getByLabelText('next-page')).toBeTruthy();
    expect(screen.getByLabelText('last-page')).toBeTruthy();
  });

  it('hides > and >> on last page', () => {
    render(<Pagination page={5} totalPages={5} onPageChange={() => {}} />);
    expect(screen.queryByLabelText('next-page')).toBeNull();
    expect(screen.queryByLabelText('last-page')).toBeNull();
    expect(screen.getByLabelText('first-page')).toBeTruthy();
    expect(screen.getByLabelText('prev-page')).toBeTruthy();
  });

  it('calls onPageChange with correct target', async () => {
    const onPageChange = vi.fn();
    render(<Pagination page={3} totalPages={10} onPageChange={onPageChange} />);

    await userEvent.click(screen.getByLabelText('first-page'));
    expect(onPageChange).toHaveBeenLastCalledWith(1);

    await userEvent.click(screen.getByLabelText('prev-page'));
    expect(onPageChange).toHaveBeenLastCalledWith(2);

    await userEvent.click(screen.getByLabelText('next-page'));
    expect(onPageChange).toHaveBeenLastCalledWith(4);

    await userEvent.click(screen.getByLabelText('last-page'));
    expect(onPageChange).toHaveBeenLastCalledWith(10);

    await userEvent.click(screen.getByLabelText('page-5'));
    expect(onPageChange).toHaveBeenLastCalledWith(5);
  });

  it('marks current page with aria-current', () => {
    render(<Pagination page={3} totalPages={5} onPageChange={() => {}} />);
    const current = screen.getByLabelText('page-3');
    expect(current.getAttribute('aria-current')).toBe('page');
  });
});
