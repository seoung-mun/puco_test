import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import AvailablePlantations from '../AvailablePlantations';

function InteractionLockHarness() {
  const [saving, setSaving] = useState(false);
  const [pickCount, setPickCount] = useState(0);
  const [haciendaCount, setHaciendaCount] = useState(0);

  return (
    <div>
      <AvailablePlantations
        plantations={{
          face_up: [{ type: 'corn', action_index: 8 }],
          draw_pile: {
            corn: 1,
            indigo: 1,
            sugar: 1,
            tobacco: 1,
            coffee: 1,
          },
        }}
        quarrySupplyRemaining={8}
        onPick={!saving ? () => setPickCount((count) => count + 1) : undefined}
        canUseHacienda={!saving}
        onUseHacienda={!saving ? () => {
          setHaciendaCount((count) => count + 1);
          setSaving(true);
        } : undefined}
      />
      <span>{`hacienda:${haciendaCount}`}</span>
      <span>{`pick:${pickCount}`}</span>
    </div>
  );
}

describe('AvailablePlantations', () => {
  it('stops plantation clicks once a hacienda request is already in flight', async () => {
    const user = userEvent.setup();

    render(<InteractionLockHarness />);

    await user.click(screen.getByText('하시엔다'));
    await user.click(screen.getByText('옥수수'));

    expect(screen.getByText('hacienda:1')).toBeTruthy();
    expect(screen.getByText('pick:0')).toBeTruthy();
  });
});
