/** The sheet index: every page of Polaris, its number and its section. One source for the nav, the title block and the home page. */
export type Sheet = { href: string; num: string; section: SectionId | "home"; label: string; title: string; asks: string };
export type SectionId = "carbon" | "air" | "earth" | "plan" | "evidence";

export const SECTIONS: { id: SectionId; label: string; verb: string; href: string; blurb: string }[] = [
  { id: "carbon", label: "Carbon", verb: "Measure", href: "/carbon", blurb: "Turn fuel, power and spend into Scope 1, 2 and 3 tonnes, with honest ranges." },
  { id: "air", label: "Air", verb: "Track", href: "/air/forecast", blurb: "Forecast the greenhouse gas already in the air over a city, and flag unusual days." },
  { id: "earth", label: "Earth", verb: "See", href: "/earth/forest", blurb: "Compare Sentinel-2 scenes to screen forest loss and lake water change." },
  { id: "plan", label: "Plan", verb: "Cut", href: "/plan/abatement", blurb: "Rank cuts by cost, plan which source runs each hour, and check the fuel lasts until delivery." },
  { id: "evidence", label: "Evidence", verb: "Check", href: "/evidence/carbon", blurb: "How every model was tested, where it breaks, and where each number comes from." },
];

export const SHEETS: Sheet[] = [
  { href: "/", num: "00", section: "home", label: "Overview", title: "Polaris", asks: "What is here, and what do the headline numbers say?" },
  { href: "/carbon", num: "01", section: "carbon", label: "Calculator", title: "What does this site emit in a year?", asks: "What does this site emit, and which factor is most uncertain?" },
  { href: "/carbon/estimate", num: "02", section: "carbon", label: "Estimator", title: "No meter data? Estimate it.", asks: "Can a model fill in a company with no metered data?" },
  { href: "/carbon/compare", num: "03", section: "carbon", label: "Compare", title: "Scenario A against scenario B.", asks: "How much does a change really move the footprint?" },
  { href: "/carbon/report", num: "—", section: "carbon", label: "Report", title: "Footprint statement", asks: "Can I hand an auditor one sheet?" },
  { href: "/air/forecast", num: "04", section: "air", label: "Air forecast", title: "What will the air hold next fortnight?", asks: "Where are regional CO\u2082 levels heading, and does the model beat a naive guess?" },
  { href: "/air/alerts", num: "05", section: "air", label: "Air alerts", title: "Which days were unusual?", asks: "Which recent days sat far above their own recent history?" },
  { href: "/plan/abatement", num: "06", section: "plan", label: "Abatement", title: "Which cuts pay for themselves?", asks: "Which cuts pay for themselves, and what do they add up to by 2050?" },
  { href: "/plan/dispatch", num: "07", section: "plan", label: "Dispatch", title: "Which source should power each hour?", asks: "Which source should power each hour, and what does planning ahead save?" },
  { href: "/plan/microgrid", num: "08", section: "plan", label: "Microgrid", title: "Can sun, wind and a battery carry the day?", asks: "What does an optimiser schedule for a grid-tied microgrid, and what happens when the grid fails?" },
  { href: "/plan/runway", num: "09", section: "plan", label: "Fuel runway", title: "Will the diesel last until the boat comes?", asks: "Will the diesel last until the next delivery?" },
  { href: "/earth/forest", num: "10", section: "earth", label: "Forest loss", title: "Where has the forest changed?", asks: "Where has tree cover dropped between two dates?" },
  { href: "/earth/lake", num: "11", section: "earth", label: "Lake water", title: "What changed in the water?", asks: "Did the lake's optical water signal change?" },
  { href: "/evidence/carbon", num: "12", section: "evidence", label: "Carbon models", title: "How the carbon models were tested", asks: "Do the footprint models hold up on unseen companies?" },
  { href: "/evidence/earth", num: "13", section: "evidence", label: "Earth models", title: "How the satellite models were tested", asks: "Does the forest model beat a simple rule, and how far?" },
  { href: "/evidence/method", num: "14", section: "evidence", label: "Method", title: "Sources, licences and limits", asks: "Where does every factor and dataset come from?" },
];
export const sheetFor = (path: string) => SHEETS.find((s) => s.href === path);
export const sectionOf = (path: string): SectionId | "home" => sheetFor(path)?.section ?? "home";
export const TOTAL_SHEETS = SHEETS.filter((s) => /^\d+$/.test(s.num) && s.num !== "00").length;
