import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import LifecycleBadge from './LifecycleBadge';

describe('LifecycleBadge', () => {
  it('renders a localized label for each lifecycle status', () => {
    const { rerender } = render(<LifecycleBadge status="active" />);
    expect(screen.getByText('Active')).toBeInTheDocument();

    rerender(<LifecycleBadge status="completed" />);
    expect(screen.getByText('Completed')).toBeInTheDocument();

    rerender(<LifecycleBadge status="obsolete" />);
    expect(screen.getByText('Obsolete')).toBeInTheDocument();

    rerender(<LifecycleBadge status="unspecified" />);
    expect(screen.getByText('Unspecified')).toBeInTheDocument();
  });

  it('renders nothing when status is missing', () => {
    const { container } = render(<LifecycleBadge />);
    expect(container).toBeEmptyDOMElement();
  });
});
