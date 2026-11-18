import { createContext, useContext } from "react";
import { translator, type Lang, type Translate } from "./i18n";

export interface I18n {
  lang: Lang;
  t: Translate;
}
export const I18nContext = createContext<I18n>({
  lang: "en",
  t: translator("en"),
});
export const useI18n = () => useContext(I18nContext);
