// Formateurs utilisés par les colonnes AG Grid (valeurs triables, affichage FR).
var dagfuncs = (window.dashAgGridFunctions = window.dashAgGridFunctions || {});

const nf0 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

dagfuncs.entier = (v) => (v === null || v === undefined ? "–" : nf0.format(v));
dagfuncs.euros = (v) =>
  v === null || v === undefined ? "–" : nf0.format(v) + " €";
dagfuncs.eurM2 = (v) =>
  v === null || v === undefined ? "–" : nf0.format(v) + " €/m²";
dagfuncs.m2 = (v) =>
  v === null || v === undefined ? "–" : nf0.format(v) + " m²";
dagfuncs.pct = (v) =>
  v === null || v === undefined ? "–" : nf0.format(v * 100) + " %";
dagfuncs.pctSigne = (v) => {
  if (v === null || v === undefined) return "–";
  const s = (v * 100).toFixed(1).replace(".", ",").replace("-", "−");
  return (v > 0 ? "+" : "") + s + " %";
};
dagfuncs.dateFr = (v) => {
  if (!v) return "–";
  const [y, m, d] = String(v).slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};
dagfuncs.metres = (v) =>
  v === null || v === undefined ? "–" : nf0.format(v) + "\u202fm";
