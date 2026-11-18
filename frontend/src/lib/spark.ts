import type { Lang } from "./i18n.ts";

// Gentle open prompts; one per UTC day, identical for every visitor.
const sparks: Record<Lang, string[]> = {
  en: [
    "A neighborhood tool library that lends time as well as tools.",
    "What if every bus stop taught one useful skill?",
    "A school subject about repairing things instead of replacing them.",
    "Turn waiting rooms into places where strangers swap stories.",
    "A city map of quiet places for people who need a pause.",
    "Plant a tree for every promise a city keeps.",
    "A festival where the audience writes the program.",
    "A kitchen where retired cooks teach recipes that are not written down.",
    "An app that rewards switching your phone off together.",
    "Libraries that lend musical instruments and practice rooms.",
    "A museum where every object answers a question from a child.",
    "Swap one car lane for a slow lane for walking and talking.",
    "A weekly market for things people fixed themselves.",
    "Letters from the future that a town writes to itself.",
    "A public wall where neighbors offer one hour of help.",
    "Rooftop cinemas powered by the sun.",
    "A game that teaches climate choices through cooking.",
    "Night schools taught by teenagers for their grandparents.",
    "A park designed by the dogs who use it.",
    "Every new building keeps one room for the community.",
    "A radio station that only plays sounds of the city.",
  ],
  ro: [
    "O bibliotecă de cartier care împrumută unelte și timp.",
    "Ce-ar fi dacă fiecare stație de autobuz ar preda o abilitate utilă?",
    "O materie la școală despre reparat lucruri în loc să le înlocuim.",
    "Sălile de așteptare devin locuri unde străinii își spun povești.",
    "O hartă a orașului cu locuri liniștite pentru cine are nevoie de o pauză.",
    "Un copac plantat pentru fiecare promisiune ținută de primărie.",
    "Un festival în care publicul scrie programul.",
    "O bucătărie unde bucătari pensionari predau rețete nescrise.",
    "O aplicație care te răsplătește când închizi telefonul împreună cu prietenii.",
    "Biblioteci care împrumută instrumente muzicale și săli de repetiții.",
    "Un muzeu în care fiecare obiect răspunde la întrebarea unui copil.",
    "O bandă de mașini transformată în bandă lentă pentru plimbări și povești.",
    "Un târg săptămânal pentru lucruri reparate de oameni cu mâna lor.",
    "Scrisori din viitor pe care un oraș și le scrie singur.",
    "Un panou public unde vecinii oferă o oră de ajutor.",
    "Cinematografe pe acoperiș alimentate de soare.",
    "Un joc care predă alegeri bune pentru climă prin gătit.",
    "Cursuri serale ținute de adolescenți pentru bunicii lor.",
    "Un parc proiectat de câinii care îl folosesc.",
    "Fiecare clădire nouă păstrează o cameră pentru comunitate.",
    "Un post de radio care difuzează doar sunetele orașului.",
  ],
};

export function dailySpark(lang: Lang, now = new Date()): string {
  const day = Math.floor(now.getTime() / 86_400_000);
  const list = sparks[lang];
  return list[((day % list.length) + list.length) % list.length];
}
export const sparkCount = (lang: Lang) => sparks[lang].length;
