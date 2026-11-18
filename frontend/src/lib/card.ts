import type { Idea } from "./ideas.ts";

export interface CardLabels {
  tag: string;
  footer: string;
  meta: string;
}
const WIDTH = 1200,
  HEIGHT = 630,
  FONT =
    'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif';

/** Greedy word wrap that also breaks words longer than a full line. */
export function wrapText(
  text: string,
  maxWidth: number,
  measure: (value: string) => number,
  maxLines: number,
): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split("\n")) {
    let line = "";
    for (const word of paragraph.split(/\s+/u).filter(Boolean)) {
      let piece = word;
      while (measure(piece) > maxWidth && piece.length > 1) {
        let cut = piece.length - 1;
        while (cut > 1 && measure(piece.slice(0, cut)) > maxWidth) cut--;
        if (line) lines.push(line);
        lines.push(piece.slice(0, cut));
        line = "";
        piece = piece.slice(cut);
      }
      const next = line ? `${line} ${piece}` : piece;
      if (measure(next) <= maxWidth) line = next;
      else {
        lines.push(line);
        line = piece;
      }
    }
    lines.push(line);
  }
  const trimmed = lines.filter((line, index) => line || index > 0);
  if (trimmed.length <= maxLines) return trimmed;
  const visible = trimmed.slice(0, maxLines);
  let last = visible[maxLines - 1];
  while (last && measure(`${last}…`) > maxWidth) last = last.slice(0, -1);
  visible[maxLines - 1] = `${last.trimEnd()}…`;
  return visible;
}

/** Draws a shareable 1200×630 PNG of an idea entirely in the browser. */
export async function ideaCard(
  idea: Idea,
  labels: CardLabels,
  dark: boolean,
): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas is unavailable.");
  const palette = dark
    ? { bg: "#131c17", panel: "#1b2720", text: "#e1e8de", muted: "#a8b7aa", accent: "#c8e6ae", tag: "#354e38" }
    : { bg: "#eef3e8", panel: "#ffffff", text: "#24372c", muted: "#5b6a5f", accent: "#2b583e", tag: "#dceacb" };
  context.fillStyle = palette.bg;
  context.fillRect(0, 0, WIDTH, HEIGHT);
  context.fillStyle = palette.panel;
  context.beginPath();
  context.roundRect(48, 48, WIDTH - 96, HEIGHT - 96, 36);
  context.fill();
  // Brand mark.
  context.fillStyle = palette.tag;
  context.beginPath();
  context.roundRect(96, 92, 56, 56, 16);
  context.fill();
  context.strokeStyle = palette.accent;
  context.lineWidth = 3.5;
  context.strokeRect(116, 102, 16, 12);
  context.beginPath();
  context.moveTo(124, 114);
  context.lineTo(124, 124);
  context.moveTo(108, 132);
  context.lineTo(108, 124);
  context.lineTo(140, 124);
  context.lineTo(140, 132);
  context.stroke();
  context.fillStyle = palette.text;
  context.font = `700 30px ${FONT}`;
  context.textBaseline = "middle";
  context.fillText("idea evolution", 170, 120);
  // Transformation tag.
  context.font = `700 22px ${FONT}`;
  const tagWidth = context.measureText(labels.tag).width + 36;
  context.fillStyle = palette.tag;
  context.beginPath();
  context.roundRect(WIDTH - 96 - tagWidth, 98, tagWidth, 44, 12);
  context.fill();
  context.fillStyle = palette.accent;
  context.fillText(labels.tag, WIDTH - 96 - tagWidth + 18, 120);
  // Idea text, shrinking for longer ideas.
  context.textBaseline = "alphabetic";
  let size = 54,
    lines: string[] = [];
  for (; size >= 30; size -= 4) {
    context.font = `650 ${size}px ${FONT}`;
    lines = wrapText(
      idea.content,
      WIDTH - 192,
      (value) => context.measureText(value).width,
      Math.floor(300 / (size * 1.25)),
    );
    if (!lines.at(-1)?.endsWith("…")) break;
  }
  context.font = `650 ${size}px ${FONT}`;
  context.fillStyle = palette.text;
  lines.forEach((line, index) =>
    context.fillText(line, 96, 230 + size + index * size * 1.25),
  );
  context.font = `500 22px ${FONT}`;
  context.fillStyle = palette.muted;
  context.fillText(labels.meta, 96, HEIGHT - 96);
  const footer = `${labels.footer} · unison.micutu.com`;
  context.fillText(
    footer,
    WIDTH - 96 - context.measureText(footer).width,
    HEIGHT - 96,
  );
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Canvas export failed."))),
      "image/png",
    ),
  );
}
