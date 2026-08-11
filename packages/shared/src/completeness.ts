export interface CompletenessInput {
  identity: unknown[];
  auction: unknown[];
  condition: unknown[];
  registration: unknown[];
  fees: unknown[];
  media: unknown[];
}

const weights = { identity: 0.2, auction: 0.25, condition: 0.15, registration: 0.2, fees: 0.1, media: 0.1 };

function present(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "UNKNOWN" && value !== "" && (!Array.isArray(value) || value.length > 0);
}

export function calculateCompleteness(input: CompletenessInput) {
  const groups = Object.fromEntries(Object.entries(input).map(([name, values]) => [
    name,
    values.length === 0 ? 0 : Math.round((values.filter(present).length / values.length) * 100),
  ])) as Record<keyof CompletenessInput, number>;
  const overall = Math.round(Object.entries(weights).reduce((sum, [name, weight]) => sum + groups[name as keyof CompletenessInput] * weight, 0));
  return { overall, groups };
}
