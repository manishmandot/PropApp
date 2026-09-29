import type { Coverage, State } from "@/lib/types";

export type Sort = "propapp" | "fundamentals" | "name";

export type Filters = {
  state?: State;
  priceMin?: number;
  priceMax?: number;
  yieldMin?: number;
  scoreMin?: number;
  scoreMax?: number;
  coverage?: Coverage;
  sort: Sort;
  page: number;
};

export const PAGE_SIZE = 50;
