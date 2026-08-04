/* MigrationFlow OSINT — rutas migratorias principales (aproximadas) */
const MIGRATION_ROUTES = [
  {
    id: "darien",
    name: "Darién · Sudamérica → Norteamérica",
    color: "#8b5cf6",
    points: [
      [8.50, -77.60], [8.98, -79.52], [9.90, -84.10], [12.10, -85.70],
      [14.00, -87.20], [14.60, -90.50], [17.00, -92.50], [19.40, -99.10],
      [23.20, -106.40], [28.00, -111.30], [31.30, -110.50],
    ],
  },
  {
    id: "caribe",
    name: "Caribe → Florida",
    color: "#0ea5e9",
    points: [
      [18.50, -72.30], [21.50, -78.50], [24.30, -77.90], [25.80, -80.20],
      [22.70, -82.00], [21.50, -81.50], [20.00, -77.50],
    ],
  },
  {
    id: "med_occ",
    name: "Mediterráneo occidental (Marruecos → España)",
    frontex: ["ROUTE_WMED"],
    color: "#f59e0b",
    points: [
      [35.00, -6.00], [35.90, -5.30], [36.30, -5.50], [36.70, -4.40],
      [35.90, -5.90], [35.00, -6.00],
    ],
  },
  {
    id: "med_cent",
    name: "Mediterráneo central (Libia/Túnez → Italia)",
    frontex: ["ROUTE_CMED"],
    color: "#ef4444",
    points: [
      [32.90, 13.20], [34.50, 11.20], [35.90, 14.50], [35.50, 12.60],
      [36.80, 11.10], [37.50, 15.10],
    ],
  },
  {
    id: "med_est",
    name: "Mediterráneo oriental y Balcanes",
    frontex: ["ROUTE_EMED", "ROUTE_WBAL"],
    color: "#10b981",
    points: [
      [38.60, 26.50], [39.30, 26.00], [40.60, 22.90], [41.60, 22.00],
      [42.00, 21.40], [43.90, 20.20], [45.90, 16.00], [46.50, 16.40],
    ],
  },
  {
    id: "atlantica",
    name: "Ruta atlántica → Canarias",
    frontex: ["ROUTE_WAF"],
    color: "#f43f5e",
    points: [
      [14.70, -17.40], [16.90, -25.00], [22.30, -16.50], [24.00, -15.60],
      [28.10, -15.40],
    ],
  },
  {
    id: "aden",
    name: "Cuerno de África → Yemen (Golfo de Adén)",
    color: "#eab308",
    points: [
      [11.60, 43.10], [12.90, 45.00], [13.10, 45.30],
    ],
  },
  {
    id: "ven_col",
    name: "Venezuela → Colombia",
    color: "#f97316",
    points: [
      [10.50, -66.90], [8.00, -72.40], [4.60, -74.10],
    ],
  },
  {
    id: "andina",
    name: "Ruta andina (Colombia → Chile)",
    color: "#d946ef",
    points: [
      [4.60, -74.10], [0.20, -78.50], [-12.00, -77.00], [-18.50, -70.30],
      [-33.40, -70.60],
    ],
  },
  {
    id: "rohingya",
    name: "Myanmar → Bangladesh (Rohingya)",
    color: "#22c55e",
    points: [
      [20.70, 92.30], [21.10, 92.20], [21.40, 92.10],
    ],
  },
  {
    id: "surafrica",
    name: "Cuerno de África → Sudáfrica",
    color: "#64748b",
    points: [
      [9.00, 38.70], [-1.30, 36.80], [-6.80, 39.30], [-15.40, 35.30],
      [-25.90, 32.60], [-26.20, 28.00],
    ],
  },
];
