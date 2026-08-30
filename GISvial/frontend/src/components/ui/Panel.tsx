import React from 'react';

interface PanelProps {
  className?: string;
  children: React.ReactNode;
}

const Panel: React.FC<PanelProps> = ({ className = '', children }) => (
  <div className={`flex max-h-full flex-col overflow-hidden rounded-xl border border-[#E8E2D8] bg-white shadow-sm ${className}`}>
    {children}
  </div>
);

export default Panel;
