import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ReplayConfirmModal from '../ReplayConfirmModal';

describe('ReplayConfirmModal', () => {
  beforeEach(() => {
    localStorage.setItem('lang', 'ko');
  });

  it('renders nothing when open is false', () => {
    const { container } = render(
      <ReplayConfirmModal
        open={false}
        displayLabel="04_13_Random_PPO_seoungmun_01"
        playerNames={['seoungmun']}
        playedDate="2026-04-13"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog content when open', () => {
    render(
      <ReplayConfirmModal
        open={true}
        displayLabel="04_13_Random_PPO_seoungmun_01"
        playerNames={['seoungmun']}
        playedDate="2026-04-13"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByText('04_13_Random_PPO_seoungmun_01')).toBeTruthy();
    expect(screen.getAllByText(/seoungmun/).length).toBeGreaterThan(0);
    expect(screen.getByText(/2026-04-13/)).toBeTruthy();
  });

  it('calls onConfirm when watch button clicked', async () => {
    const onConfirm = vi.fn();
    render(
      <ReplayConfirmModal
        open={true}
        displayLabel="x"
        playerNames={[]}
        playedDate="2026-04-13"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    );
    const buttons = screen.getAllByRole('button');
    // Second button is confirm (watch)
    await userEvent.click(buttons[1]);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when cancel button clicked', async () => {
    const onCancel = vi.fn();
    render(
      <ReplayConfirmModal
        open={true}
        displayLabel="x"
        playerNames={[]}
        playedDate="2026-04-13"
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    );
    const buttons = screen.getAllByRole('button');
    await userEvent.click(buttons[0]);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when backdrop clicked', async () => {
    const onCancel = vi.fn();
    render(
      <ReplayConfirmModal
        open={true}
        displayLabel="x"
        playerNames={[]}
        playedDate="2026-04-13"
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    );
    await userEvent.click(screen.getByTestId('replay-confirm-backdrop'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel on ESC key', async () => {
    const onCancel = vi.fn();
    render(
      <ReplayConfirmModal
        open={true}
        displayLabel="x"
        playerNames={[]}
        playedDate="2026-04-13"
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    );
    await userEvent.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
