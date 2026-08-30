import React from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-[#1E1E1E] text-white hover:bg-[#333333]',
  secondary: 'border border-[#E8E2D8] text-[#6A6A6A] hover:bg-[#F7F4EF]',
  ghost: 'text-[#6A6A6A] hover:bg-[#F7F4EF]',
  danger: 'border border-[#B42318]/25 text-[#B42318] hover:bg-[#FDECEA]',
};

const Button: React.FC<ButtonProps> = ({ variant = 'primary', className = '', children, ...props }) => (
  <button
    {...props}
    className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${className}`}
  >
    {children}
  </button>
);

export default Button;
