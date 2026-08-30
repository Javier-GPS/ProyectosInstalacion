import React from 'react';

interface FieldProps {
  label: string;
  children: React.ReactNode;
  className?: string;
}

export const Field: React.FC<FieldProps> = ({ label, children, className = '' }) => (
  <label className={`block text-sm font-semibold text-[#6A6A6A] ${className}`}>
    {label}
    {children}
  </label>
);

interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export const TextInput: React.FC<TextInputProps> = ({ label, className = '', ...props }) => {
  const input = (
    <input
      {...props}
      className={`mt-1 w-full rounded-lg border border-[#E8E2D8] bg-white px-3 py-2 text-sm text-[#1E1E1E] outline-none focus:border-[#1E1E1E] focus:ring-2 focus:ring-[#1E1E1E]/10 ${className}`}
    />
  );
  if (!label) return input;
  return <label className="block text-sm font-semibold text-[#6A6A6A]">{label}{input}</label>;
};

interface SelectInputProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
}

export const SelectInput: React.FC<SelectInputProps> = ({ label, className = '', children, ...props }) => {
  const select = (
    <select
      {...props}
      className={`mt-1 w-full rounded-lg border border-[#E8E2D8] bg-white px-3 py-2 text-sm text-[#1E1E1E] outline-none focus:border-[#1E1E1E] focus:ring-2 focus:ring-[#1E1E1E]/10 ${className}`}
    >
      {children}
    </select>
  );
  if (!label) return select;
  return <label className="block text-sm font-semibold text-[#6A6A6A]">{label}{select}</label>;
};
