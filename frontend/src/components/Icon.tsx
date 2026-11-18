const paths = {
  flag: "M5 21V3m0 1c4-3 8 3 14 0v10c-6 3-10-3-14 0",
  search: "m21 21-4.5-4.5 M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  plus: "M12 5v14M5 12h14",
  graph: "M12 8v5M5 17v-4h14v4M9 3h6v5H9zM2 17h6v5H2zM16 17h6v5h-6z",
  list: "M9 6h12M9 12h12M9 18h12M3 6h1M3 12h1M3 18h1",
  star: "m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
  copy: "M9 9h12v12H9zM15 6V3H3v12h3",
  share:
    "M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm12 7a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM8.5 10.5l7-5M8.5 13.5l7 4",
  close: "M6 6l12 12M6 18 18 6",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  sun: "M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  moon: "M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z",
  help: "M9 9a3 3 0 0 1 6 0c0 2-3 2-3 5m0 3v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  refresh: "M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6",
  focus: "M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M8 12h8M12 8v8",
  branch:
    "M6 3v14a3 3 0 1 0 3 3M6 12c9 0 12-2 12-6M21 3a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  chevron: "m9 5 7 7-7 7",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z",
  lock: "M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4",
  check: "m5 12 4 4L19 6",
  drop: "M12 3c3.6 4.3 6 7.7 6 10.7a6 6 0 0 1-12 0C6 10.7 8.4 7.3 12 3Z",
  compass: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM15.5 8.5l-2 5-5 2 2-5z",
  dice: "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1ZM9 9h.01M15 15h.01M15 9h.01M9 15h.01M12 12h.01",
  play: "M8 5v14l11-7z",
  pause: "M8 5h3v14H8zM13 5h3v14h-3z",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15 9h.01",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0",
  leaf: "M5 21c0-9 5-15 15-16-1 10-7 15-15 16Zm0 0 8-8",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  history: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 3",
};
export type IconName = keyof typeof paths;
export default function Icon({
  name,
  size = 18,
}: {
  name: IconName;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
