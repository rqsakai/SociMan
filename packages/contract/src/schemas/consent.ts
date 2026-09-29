import { z } from "zod";

// Categorias de consentimento LGPD. "essential" é sempre true (cookie de
// refresh é estritamente necessário — informado, sem opt-out).
export const consentCategoriesSchema = z.object({
  essential: z.literal(true),
  analytics: z.boolean(),
});
export type ConsentCategories = z.infer<typeof consentCategoriesSchema>;

export const consentRequestSchema = z.object({
  categories: consentCategoriesSchema,
  policyVersion: z.string().min(1),
  anonId: z.string().max(64).optional(),
});
export type ConsentRequest = z.infer<typeof consentRequestSchema>;
