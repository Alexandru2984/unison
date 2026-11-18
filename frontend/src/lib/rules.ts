import { mutations, type Mutation } from "./ideas.ts";
import type { MessageKey, Translate } from "./i18n.ts";

const known = new Set<string>(mutations.map((m) => m.id));
export const isKnownRule = (id: Mutation) => known.has(id);
export const ruleName = (t: Translate, id: Mutation) =>
  id === "base"
    ? t("rule.base")
    : known.has(id)
      ? t(`rule.${id}.name` as MessageKey)
      : id;
export const ruleDescription = (t: Translate, id: Mutation) =>
  known.has(id) ? t(`rule.${id}.desc` as MessageKey) : "";
/** Label for an idea's origin: seeds have no transformation. */
export const ideaLabel = (
  t: Translate,
  idea: { parent_id: number | null; mutation: Mutation },
) => (idea.parent_id === null ? t("idea.seed") : ruleName(t, idea.mutation));
export const shortId = (id: number) => `#${String(id).padStart(3, "0")}`;
