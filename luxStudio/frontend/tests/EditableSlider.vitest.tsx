import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import EditableSlider from '../src/components/ui/EditableSlider';

describe('EditableSlider', () => {
  it('renders label and value', () => {
    render(<EditableSlider label="Power" value={100} min={0} max={500} step={1} unit="W" onChange={() => {}} />);
    expect(screen.getByText('Power')).toBeInTheDocument();
    expect(screen.getByDisplayValue('100,0')).toBeInTheDocument();
  });

  it('calls onChange when slider changes', () => {
    const onChange = vi.fn();
    render(<EditableSlider label="Height" value={9} min={4} max={20} step={0.5} onChange={onChange} />);
    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '12' } });
    expect(onChange).toHaveBeenCalledWith(12);
  });

  it('shows unit suffix when provided', () => {
    render(<EditableSlider label="Spacing" value={30} min={5} max={50} step={1} unit="m" onChange={() => {}} />);
    expect(screen.getByText('m')).toBeInTheDocument();
  });

  it('clamps value to min/max on text input blur', () => {
    const onChange = vi.fn();
    render(<EditableSlider label="Tilt" value={5} min={0} max={15} step={1} onChange={onChange} />);
    const input = screen.getByRole('textbox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: '20' } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledWith(15);
  });

  it('disables both input and slider when disabled', () => {
    render(<EditableSlider label="Power" value={100} min={0} max={500} step={1} onChange={() => {}} disabled />);
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(screen.getByRole('slider')).toBeDisabled();
  });

  it('renders marks when provided', () => {
    render(<EditableSlider label="Test" value={5} min={0} max={10} step={1} marks={['Low', 'Mid', 'High']} onChange={() => {}} />);
    expect(screen.getByText('Low')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('renders dense variant with reduced padding', () => {
    const { container } = render(<EditableSlider label="Dense" value={5} min={0} max={10} step={1} onChange={() => {}} dense />);
    expect(container.querySelector('.p-2')).toBeTruthy();
  });
});
