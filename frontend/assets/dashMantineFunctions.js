// Fonctions passées aux composants Dash Mantine (props « function »).
var dmcfuncs = (window.dashMantineFunctions = window.dashMantineFunctions || {});

// Suggestions d'adresses : déjà filtrées par le géocodeur, on les affiche toutes.
dmcfuncs.sansFiltre = function ({ options }) {
  return options;
};
