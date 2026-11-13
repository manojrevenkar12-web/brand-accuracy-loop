// Every number the components use lives here or in tokens.css.
export const motion = {
  markDraw: 0.45, // seconds for a claim's underline to draw
  markStagger: 0.07,
  note: 0.22,
  ease: [0.22, 0.9, 0.3, 1] as [number, number, number, number],
};

export const skeletonStep = 11; // each placeholder line this many percent shorter than the last

export const chart = {
  width: 560,
  height: 260,
  pad: { top: 16, right: 150, bottom: 30, left: 40 },
  label: 12,
  yMax: 12, // percent of claims wrong
  yTicks: [0, 4, 8, 12],
  dot: 3,
};

export const verdictWords: Record<string, string> = {
  accurate: "Right",
  inaccurate: "Wrong",
  unverifiable: "Not verified by the brand",
  review: "Sent to a person",
};

export const ticketWords: Record<string, string> = {
  brand_page: "Fix the brand's page",
  publisher: "Ask the publisher",
  engine_feed: "Send to the engine's feed",
};

export const seriesShort: Record<string, string> = {
  none: "No corrections",
  first_citation: "First citation",
  closest_citation: "Closest citation",
  value_match: "Value-matched",
};
