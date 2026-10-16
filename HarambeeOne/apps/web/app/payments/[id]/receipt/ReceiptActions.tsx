'use client';

import { Printer } from 'lucide-react';

export default function ReceiptActions() {
  return <button className="btn primary no-print" onClick={() => window.print()}><Printer size={16}/>Print receipt</button>;
}
