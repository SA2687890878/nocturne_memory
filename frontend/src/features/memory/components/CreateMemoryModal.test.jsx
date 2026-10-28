import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import CreateMemoryModal from './CreateMemoryModal';
import { createMemory } from '../../../lib/api';

vi.mock('../../../lib/api', () => ({
  createMemory: vi.fn(),
  default: { defaults: { headers: { common: {} } } },
}));

const fillRequiredFields = async (user) => {
  await user.type(screen.getByPlaceholderText('Memory content...'), 'body');
  await user.type(screen.getByPlaceholderText('When to recall this memory...'), 'when needed');
};

describe('CreateMemoryModal lifecycle status', () => {
  it('defaults to unspecified and sends it to the API', async () => {
    createMemory.mockResolvedValue({ uri: 'core://new' });
    const user = userEvent.setup();

    render(<CreateMemoryModal onClose={vi.fn()} onCreated={vi.fn()} parentPath="" currentDomain="core" />);

    const select = screen.getByLabelText(/^Status/);
    expect(select.value).toBe('unspecified');

    await fillRequiredFields(user);
    await user.click(screen.getByRole('button', { name: /create memory/i }));

    await waitFor(() => expect(createMemory).toHaveBeenCalledTimes(1));
    expect(createMemory.mock.calls[0][0].lifecycle_status).toBe('unspecified');
  });

  it('sends the selected status', async () => {
    createMemory.mockResolvedValue({ uri: 'core://new' });
    const user = userEvent.setup();

    render(<CreateMemoryModal onClose={vi.fn()} onCreated={vi.fn()} parentPath="" currentDomain="core" />);

    await user.selectOptions(screen.getByLabelText(/^Status/), 'completed');
    await fillRequiredFields(user);
    await user.click(screen.getByRole('button', { name: /create memory/i }));

    await waitFor(() => expect(createMemory).toHaveBeenCalledTimes(1));
    expect(createMemory.mock.calls[0][0].lifecycle_status).toBe('completed');
  });
});
