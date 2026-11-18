import type { Lang, MessageKey } from "./i18n.ts";

export const starters: { key: MessageKey; text: Record<Lang, string> }[] = [
  {
    key: "starter.community",
    text: {
      en: "Turn empty city rooftops into shared neighborhood gardens.",
      ro: "Acoperișurile goale ale orașului devin grădini comune de cartier.",
    },
  },
  {
    key: "starter.learning",
    text: {
      en: "A library where people borrow skills instead of books.",
      ro: "O bibliotecă în care oamenii împrumută abilități în loc de cărți.",
    },
  },
  {
    key: "starter.climate",
    text: {
      en: "Make repairing everyday objects easier than replacing them.",
      ro: "Să fie mai ușor să reparăm obiectele de zi cu zi decât să le înlocuim.",
    },
  },
  {
    key: "starter.technology",
    text: {
      en: "Build a calmer internet that rewards curiosity and collaboration.",
      ro: "Un internet mai calm, care răsplătește curiozitatea și colaborarea.",
    },
  },
  {
    key: "starter.creativity",
    text: {
      en: "A museum of unfinished ideas that anyone can continue.",
      ro: "Un muzeu al ideilor neterminate pe care oricine le poate continua.",
    },
  },
  {
    key: "starter.everyday",
    text: {
      en: "Create tiny adventures for people on their daily commute.",
      ro: "Mici aventuri pentru oamenii care fac zilnic naveta.",
    },
  },
];
