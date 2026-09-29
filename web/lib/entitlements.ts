/**
 * The one place plan limits are decided. Every page and route that shows score data asks
 * here. Until accounts and billing exist (sub-project 4), everyone sees everything.
 */
export type Entitlements = {
  exactScores: boolean;
  marketDetail: boolean;
  compare: boolean;
  mapDetail: boolean;
  finderTopRanks: boolean;
};

const EVERYTHING: Entitlements = {
  exactScores: true,
  marketDetail: true,
  compare: true,
  mapDetail: true,
  finderTopRanks: true,
};

export async function getEntitlements(): Promise<Entitlements> {
  return EVERYTHING;
}
