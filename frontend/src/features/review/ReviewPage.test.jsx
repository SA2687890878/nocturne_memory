import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ReviewPage from './ReviewPage';
import { getGroups, getGroupDiff } from '../../lib/api';
import i18n from '../../i18n/index';

vi.mock('../../lib/api', () => ({
  getGroups: vi.fn(),
  getGroupDiff: vi.fn(),
  rollbackGroup: vi.fn(),
  approveGroup: vi.fn(),
  clearAll: vi.fn(),
  default: { defaults: { headers: { common: {} } } },
}));

const change = {
  node_uuid: 'node-1',
  display_uri: 'core://agent/example',
  top_level_table: 'nodes',
  action: 'modified',
  row_count: 1,
  namespaces: [''],
};

describe('ReviewPage lifecycle metadata', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
    getGroups.mockResolvedValue([change]);
  });

  it('renders a lifecycle-only change with localized labels', async () => {
    getGroupDiff.mockResolvedValue({
      action: 'modified',
      has_changes: true,
      path_changes: [],
      glossary_changes: [],
      before_meta: { priority: 0, disclosure: 'when needed', lifecycle_status: 'active' },
      current_meta: { priority: 0, disclosure: 'when needed', lifecycle_status: 'obsolete' },
      before_content: 'same body',
      current_content: 'same body',
    });

    render(<ReviewPage />);

    expect(await screen.findByText(/Edge Metadata/)).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Obsolete')).toBeInTheDocument();
    expect(screen.queryByText('Priority')).not.toBeInTheDocument();
    expect(screen.queryByText('Disclosure')).not.toBeInTheDocument();
  });

  it('renders unspecified status on creation', async () => {
    getGroupDiff.mockResolvedValue({
      action: 'created',
      has_changes: true,
      path_changes: [],
      glossary_changes: [],
      before_meta: { priority: null, disclosure: null, lifecycle_status: null },
      current_meta: { priority: 0, disclosure: 'when needed', lifecycle_status: 'unspecified' },
      before_content: '',
      current_content: 'new body',
    });

    render(<ReviewPage />);

    expect(await screen.findByText('Unspecified')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
  });
});
