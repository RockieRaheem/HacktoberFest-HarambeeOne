export type Money = { amount: string; currency: 'UGX' | 'USD' | 'USDC' | string };
export type SettlementState = 'ALLOCATED'|'AUTHORISED'|'DISBURSEMENT_SUBMITTED'|'ONCHAIN_SENT'|'OFFRAMP_PROCESSING'|'FIAT_SETTLED'|'RECONCILED'|'FAILED'|'RETURNED'|'UNDER_REVIEW';
export const PRODUCT_RULES = {
  ai: 'AI assists; humans approve; deterministic services execute.',
  privacy: 'Personally identifiable learner data stays off-chain.',
  settlement: 'Student UGX debt changes only after the required settlement confirmation.'
} as const;
