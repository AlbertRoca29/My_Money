// Category stickers: small drawings with a black outline and a white die-cut border, slightly tilted.
// Keyed by the category's label (the part after the emoji); categories without one keep their emoji.
const B = "#0666EB", A = "#F5A524", G = "#00A86B", K = "#191C1F", R = "#E5484D", P = "#8E4EC6", T = "#12A5B0",
  M = "#D6409F", Y = "#7A8B99", N = "#064221", C = "#C2700B", W = "#fff";
const z = `stroke="${K}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"`;
const line = (n) => `fill="none" stroke="${K}" stroke-width="${n}" stroke-linecap="round" stroke-linejoin="round"`;

const ART = {
  "Groceries": `<path d="M8 18H18L26 52H60" ${line(4)}/><circle cx="34" cy="20" r="9" fill="${R}" ${z}/><rect x="42" y="13" width="12" height="17" rx="3" fill="${G}" ${z}/><path d="M20 28H66L60 46H25Z" fill="${B}" ${z}/><circle cx="30" cy="62" r="6" fill="${K}"/><circle cx="56" cy="62" r="6" fill="${K}"/>`,
  "Restaurants & Cafés": `<path d="M30 8q-5 6 0 12t0 12M42 6q-5 6 0 12t0 12" fill="none" stroke="#B9C2CB" stroke-width="3" stroke-linecap="round"/><ellipse cx="38" cy="66" rx="28" ry="6" fill="#E8EBEF" ${z}/><circle cx="58" cy="46" r="9" fill="none" stroke="${A}" stroke-width="6"/><path d="M16 34H60L56 58Q54 64 46 64H30Q22 64 20 58Z" fill="${A}" ${z}/><rect x="18" y="40" width="40" height="7" fill="${W}" opacity=".85"/>`,
  "Transportation": `<rect x="14" y="10" width="52" height="54" rx="10" fill="${T}" ${z}/><rect x="20" y="18" width="40" height="20" rx="4" fill="${W}" ${z}/><circle cx="24" cy="50" r="4" fill="${A}"/><circle cx="56" cy="50" r="4" fill="${A}"/><rect x="20" y="62" width="10" height="10" rx="3" fill="${K}"/><rect x="50" y="62" width="10" height="10" rx="3" fill="${K}"/>`,
  "Health & Personal Care": `<path d="M40 68C14 50 8 36 14 24C20 12 34 12 40 24C46 12 60 12 66 24C72 36 66 50 40 68Z" fill="${R}" ${z}/><path d="M20 40H32L36 32L42 50L47 40H60" fill="none" stroke="${W}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`,
  "Arts & Culture": `<path d="M40 10C20 10 8 24 8 40C8 58 22 70 38 70C46 70 46 62 42 58C38 54 40 48 48 48H58C66 48 72 42 72 34C72 20 58 10 40 10Z" fill="${C}" ${z}/><circle cx="24" cy="38" r="5" fill="${R}"/><circle cx="32" cy="24" r="5" fill="${A}"/><circle cx="48" cy="22" r="5" fill="${B}"/><circle cx="60" cy="32" r="5" fill="${G}"/>`,
  "Clothing": `<path d="M28 12L12 22L18 38L24 35V68H56V35L62 38L68 22L52 12Q40 22 28 12Z" fill="${P}" ${z}/><circle cx="40" cy="44" r="7" fill="${A}"/>`,
  "Parties & Nightlife": `<path d="M14 68L30 22L58 50Z" fill="${M}" ${z}/><path d="M22 46L44 36M18 58L50 44" stroke="${A}" stroke-width="5"/><circle cx="54" cy="18" r="4" fill="${B}"/><circle cx="66" cy="34" r="4" fill="${G}"/><rect x="44" y="8" width="5" height="9" fill="${R}" transform="rotate(30 46 12)"/>`,
  "Housing": `<path d="M12 38L40 12L68 38" ${line(7)}/><path d="M18 34V68H62V34L40 16Z" fill="${B}" ${z}/><rect x="34" y="46" width="12" height="22" rx="2" fill="${A}" ${z}/>`,
  "Miscellaneous": `<path d="M10 62L28 28L46 62Z" fill="${A}" ${z}/><rect x="36" y="36" width="30" height="30" rx="6" fill="${Y}" ${z} transform="rotate(12 51 51)"/><circle cx="50" cy="22" r="14" fill="${R}" ${z}/>`,
  "Job": `<rect x="28" y="12" width="24" height="16" rx="5" ${line(5)}/><rect x="8" y="24" width="64" height="44" rx="9" fill="${G}" ${z}/><path d="M8 42H72" stroke="rgba(0,0,0,.2)" stroke-width="3"/><rect x="34" y="36" width="12" height="12" rx="3" fill="${A}" ${z}/>`,
  "Investments": `<ellipse cx="40" cy="66" rx="22" ry="6" fill="${A}" ${z}/><ellipse cx="40" cy="58" rx="22" ry="6" fill="${A}" ${z}/><ellipse cx="40" cy="50" rx="22" ry="6" fill="${A}" ${z}/><path d="M40 44V24" ${line(4)}/><path d="M40 30Q20 30 18 12Q38 10 40 30Z" fill="${G}" ${z}/><path d="M40 26Q56 26 62 8Q42 6 40 26Z" fill="${G}" ${z}/>`,
  "Gifts": `<path d="M40 24C30 8 18 14 26 24M40 24C50 8 62 14 54 24" fill="none" stroke="${R}" stroke-width="5" stroke-linecap="round"/><rect x="12" y="34" width="56" height="34" rx="6" fill="${M}" ${z}/><rect x="8" y="24" width="64" height="14" rx="5" fill="${M}" ${z}/><rect x="35" y="24" width="10" height="44" fill="${A}" ${z} stroke-width="2"/>`,
  "Selling": `<path d="M40 10L70 24V56L40 70L10 56V24Z" fill="${C}" ${z}/><path d="M10 24L40 38L70 24M40 38V70" fill="none" stroke="rgba(0,0,0,.25)" stroke-width="3"/><path d="M25 17L55 31V42" fill="none" stroke="${A}" stroke-width="5"/>`,
  "Other": `<path d="M36 8L42 30L64 36L42 42L36 64L30 42L8 36L30 30Z" fill="${P}" ${z}/><path d="M60 52L63 60L71 63L63 66L60 74L57 66L49 63L57 60Z" fill="${A}" ${z} stroke-width="2"/><circle cx="62" cy="14" r="4" fill="${B}"/>`,
};
const TILT = [-8, 6, -4, 7, -6, 5, -7, 4];

// One shared filter (white border + soft drop), added to the page once.
const FILTER = `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <filter id="sticker" x="-25%" y="-25%" width="150%" height="150%">
    <feMorphology in="SourceAlpha" operator="dilate" radius="5" result="o"/><feFlood flood-color="#fff"/>
    <feComposite in2="o" operator="in" result="w"/><feOffset in="o" dx="1" dy="2" result="so"/>
    <feFlood flood-color="#000" flood-opacity=".2"/><feComposite in2="so" operator="in" result="sh"/>
    <feMerge><feMergeNode in="sh"/><feMergeNode in="w"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter></defs></svg>`;
document.body.insertAdjacentHTML("afterbegin", FILTER);

// The sticker <svg> for a category label, or "" when there's no drawing for it.
export function sticker(label) {
  const art = ART[label];
  if (!art) return "";
  const tilt = TILT[Object.keys(ART).indexOf(label) % TILT.length];
  return `<svg class="stk" viewBox="0 0 80 80" aria-hidden="true"><g transform="rotate(${tilt} 40 40) translate(13 13) scale(.66)" filter="url(#sticker)">${art}</g></svg>`;
}
