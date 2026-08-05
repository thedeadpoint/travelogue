const EUROPE_CENTER = [50.5, 10];
const EUROPE_ZOOM = 4;
const SELECTED_TRIP_MAX_ZOOM = 8;
const FALLBACK_CATEGORY_SYMBOL = "📍";
const CATEGORY_SYMBOLS = {
  "Christmas Market": "🎄",
  Skiing: "⛷️",
  "Kid-Focused": "🛝",
  "Special Occasion": "⭐",
  City: "🏙️",
  "Long Weekend": "🧳",
  "Long Vacation": "🌍",
  "Day Trip": "☀️",
  Festival: "🎪",
  Groceries: "🛒",
};

const map = L.map("map").setView(EUROPE_CENTER, EUROPE_ZOOM);
const statusElement = document.querySelector("#status");
const markerLayer = L.layerGroup().addTo(map);
const filterForm = document.querySelector("#filters");
const tripsSidebar = document.querySelector("#trips-sidebar");
const tripsSidebarToggle = document.querySelector("#trips-sidebar-toggle");
const tripsList = document.querySelector("#trips-list");
const clearTripSelectionButton = document.querySelector(
  "#clear-trip-selection",
);
const filters = {
  year: document.querySelector("#year-filter"),
  country: document.querySelector("#country-filter"),
  category: document.querySelector("#category-filter"),
  travelMode: document.querySelector("#travel-mode-filter"),
};
let allTrips = [];
let tripMarkerGroups = new Map();
let tripListButtonsById = new Map();
let selectedTripId = null;

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

function countTravelDays(startDate, endDate) {
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);

  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return 0;
  }

  return Math.floor((end - start) / millisecondsPerDay) + 1;
}

function countryFromStopName(stopName) {
  const parts = stopName.split(",");
  return parts.length > 1 ? parts.at(-1).trim() : "";
}

function travelModesFromTrip(trip) {
  return trip.travel_mode
    .split(";")
    .map((mode) => mode.trim())
    .filter(Boolean);
}

function categorySymbol(category) {
  return CATEGORY_SYMBOLS[category] || FALLBACK_CATEGORY_SYMBOL;
}

function tripMonthYear(startDate) {
  const date = new Date(`${startDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return "Date unknown";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function selectedMarkerStyle() {
  return filterForm.elements.markerStyle.value;
}

function categoryIcon(category) {
  const symbol = categorySymbol(category);
  return L.divIcon({
    className: "category-marker-wrapper",
    html: `<span class="category-marker" aria-hidden="true"><span class="category-marker-symbol">${symbol}</span></span>`,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
    popupAnchor: [0, -18],
  });
}

function selectedTripIcon(category) {
  const content =
    selectedMarkerStyle() === "category"
      ? `<span class="category-marker-symbol">${categorySymbol(category)}</span>`
      : '<span class="selected-marker-dot"></span>';

  return L.divIcon({
    className: "category-marker-wrapper",
    html: `<span class="category-marker selected-trip-marker" aria-hidden="true">${content}</span>`,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
    popupAnchor: [0, -18],
  });
}

function populateCategoryLegend(trips) {
  const legend = document.querySelector("#category-legend");
  const items = document.querySelector("#category-legend-items");
  const categories = [...new Set(trips.map((trip) => trip.category))]
    .filter(Boolean)
    .sort((first, second) => first.localeCompare(second));

  items.replaceChildren();
  for (const category of categories) {
    const item = document.createElement("span");
    item.className = "category-legend-item";

    const symbol = document.createElement("span");
    symbol.className = "category-legend-symbol";
    symbol.textContent = categorySymbol(category);

    const label = document.createElement("span");
    label.textContent = category;
    item.append(symbol, label);
    items.append(item);
  }

  legend.hidden = selectedMarkerStyle() !== "category";
}

function addOptions(select, values) {
  const sortedValues = [...values].sort((first, second) =>
    first.localeCompare(second, undefined, { numeric: true }),
  );

  for (const value of sortedValues) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
}

function populateFilters(trips) {
  const years = new Set();
  const countries = new Set();
  const categories = new Set();
  const travelModes = new Set();

  for (const trip of trips) {
    if (trip.start_date) {
      years.add(trip.start_date.slice(0, 4));
    }
    if (trip.category) {
      categories.add(trip.category);
    }

    for (const mode of travelModesFromTrip(trip)) {
      travelModes.add(mode);
    }

    for (const stop of trip.stops) {
      const country = countryFromStopName(stop.name);
      if (country) {
        countries.add(country);
      }
    }
  }

  addOptions(filters.year, years);
  addOptions(filters.country, countries);
  addOptions(filters.category, categories);
  addOptions(filters.travelMode, travelModes);
}

function tripMatchesFilters(trip) {
  const matchesYear =
    !filters.year.value || trip.start_date.startsWith(filters.year.value);
  const matchesCountry =
    !filters.country.value ||
    trip.stops.some(
      (stop) => countryFromStopName(stop.name) === filters.country.value,
    );
  const matchesCategory =
    !filters.category.value || trip.category === filters.category.value;
  const matchesTravelMode =
    !filters.travelMode.value ||
    travelModesFromTrip(trip).includes(filters.travelMode.value);

  return (
    matchesYear && matchesCountry && matchesCategory && matchesTravelMode
  );
}

function updateStatistics(trips) {
  const countries = new Set();
  let stops = 0;
  let travelDays = 0;
  let bordersCrossed = 0;

  for (const trip of trips) {
    stops += trip.stops.length;
    travelDays += countTravelDays(trip.start_date, trip.end_date);
    bordersCrossed += Number(trip.borders_crossed) || 0;

    for (const stop of trip.stops) {
      const country = countryFromStopName(stop.name);
      if (country) {
        countries.add(country);
      }
    }
  }

  document.querySelector("#trips-total").textContent = trips.length;
  document.querySelector("#countries-total").textContent = countries.size;
  document.querySelector("#stops-total").textContent = stops;
  document.querySelector("#travel-days-total").textContent = travelDays;
  document.querySelector("#borders-total").textContent = bordersCrossed;
}

function addPopupContent(marker, trip, stop) {
  const popup = document.createElement("article");
  popup.className = "trip-popup";

  const title = document.createElement("h2");
  title.textContent = trip.title;
  popup.append(title);

  const details = [
    ["Stop", stop.name],
    ["Start date", trip.start_date],
    ["End date", trip.end_date],
    ["Travel mode", trip.travel_mode],
    ["Category", trip.category],
  ];

  const list = document.createElement("dl");
  for (const [label, value] of details) {
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value || "—";
    list.append(term, description);
  }

  popup.append(list);
  marker.bindPopup(popup);
}

function setTripGroupSelected(group, selected) {
  const icon = selected ? group.selectedIcon : group.defaultIcon;

  for (const marker of group.markers) {
    marker.setIcon(icon);
    marker.setOpacity(1);
  }
}

function updateTripButtonSelection(tripId, selected) {
  const button = tripListButtonsById.get(tripId);
  if (!button) {
    return;
  }

  button.classList.toggle("is-selected", selected);
  button.setAttribute("aria-pressed", String(selected));
}

function clearTripSelection() {
  if (!selectedTripId) {
    return;
  }

  const selectedGroup = tripMarkerGroups.get(selectedTripId);
  if (selectedGroup) {
    setTripGroupSelected(selectedGroup, false);
  }

  updateTripButtonSelection(selectedTripId, false);
  selectedTripId = null;
  clearTripSelectionButton.hidden = true;
}

function selectTrip(tripId) {
  if (selectedTripId === tripId) {
    clearTripSelection();
    return;
  }

  const nextGroup = tripMarkerGroups.get(tripId);
  if (!nextGroup?.markers.length) {
    return;
  }

  if (selectedTripId) {
    const previousGroup = tripMarkerGroups.get(selectedTripId);
    if (previousGroup) {
      setTripGroupSelected(previousGroup, false);
    }
    updateTripButtonSelection(selectedTripId, false);
  }

  selectedTripId = tripId;
  setTripGroupSelected(nextGroup, true);
  updateTripButtonSelection(tripId, true);
  clearTripSelectionButton.hidden = false;

  const bounds = L.latLngBounds(
    nextGroup.markers.map((marker) => marker.getLatLng()),
  );
  const sidebarOverlaysMap = window.matchMedia("(max-width: 36rem)").matches;
  const sidebarPadding =
    sidebarOverlaysMap && !tripsSidebar.classList.contains("is-collapsed")
      ? tripsSidebar.getBoundingClientRect().width + 30
      : 50;

  nextGroup.markers[0].openPopup();
  map.fitBounds(bounds, {
    paddingTopLeft: [sidebarPadding, 50],
    paddingBottomRight: [50, 50],
    maxZoom: SELECTED_TRIP_MAX_ZOOM,
  });
}

function restoreSelectionAfterRender() {
  if (!selectedTripId || !tripMarkerGroups.has(selectedTripId)) {
    selectedTripId = null;
    clearTripSelectionButton.hidden = true;
    return;
  }

  setTripGroupSelected(tripMarkerGroups.get(selectedTripId), true);
  clearTripSelectionButton.hidden = false;
}

function renderTripsSidebar(trips) {
  const chronologicalTrips = [...trips].sort((first, second) =>
    first.start_date.localeCompare(second.start_date),
  );

  tripsList.replaceChildren();
  tripListButtonsById = new Map();
  for (const trip of chronologicalTrips) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const date = document.createElement("span");
    const details = document.createElement("span");
    const icon = document.createElement("span");
    const title = document.createElement("span");

    button.className = "trip-list-button";
    button.type = "button";
    button.disabled = !tripMarkerGroups.has(trip.trip_id);
    button.setAttribute("aria-pressed", String(trip.trip_id === selectedTripId));
    button.classList.toggle("is-selected", trip.trip_id === selectedTripId);
    button.addEventListener("click", () => selectTrip(trip.trip_id));
    tripListButtonsById.set(trip.trip_id, button);

    date.className = "trip-list-date";
    date.textContent = tripMonthYear(trip.start_date);

    details.className = "trip-list-details";
    icon.className = "trip-list-icon";
    icon.textContent = categorySymbol(trip.category);
    icon.setAttribute("aria-label", trip.category || "Uncategorized");
    icon.title = trip.category || "Uncategorized";
    title.className = "trip-list-title";
    title.textContent = trip.title;

    details.append(icon, title);
    button.append(date, details);
    item.append(button);
    tripsList.append(item);
  }
}

function addTripStops(trips) {
  const markerBounds = [];
  markerLayer.clearLayers();
  tripMarkerGroups = new Map();

  for (const trip of trips) {
    const defaultIcon =
      selectedMarkerStyle() === "category"
        ? categoryIcon(trip.category)
        : new L.Icon.Default();
    const group = {
      trip,
      markers: [],
      defaultIcon,
      selectedIcon: selectedTripIcon(trip.category),
    };

    for (const stop of trip.stops) {
      if (
        typeof stop.latitude !== "number" ||
        typeof stop.longitude !== "number"
      ) {
        continue;
      }

      const coordinates = [stop.latitude, stop.longitude];
      const marker = L.marker(coordinates, { icon: defaultIcon }).addTo(
        markerLayer,
      );
      marker.on("click", () => selectTrip(trip.trip_id));
      addPopupContent(marker, trip, stop);
      group.markers.push(marker);
      markerBounds.push(coordinates);
    }

    if (group.markers.length) {
      tripMarkerGroups.set(trip.trip_id, group);
    }
  }

  if (markerBounds.length) {
    map.fitBounds(markerBounds, { padding: [30, 30] });
  } else {
    map.setView(EUROPE_CENTER, EUROPE_ZOOM);
  }

  restoreSelectionAfterRender();

  statusElement.textContent = "Map loaded.";
}

function renderFilteredTrips() {
  const filteredTrips = allTrips.filter(tripMatchesFilters);
  updateStatistics(filteredTrips);
  populateCategoryLegend(filteredTrips);
  addTripStops(filteredTrips);
  renderTripsSidebar(filteredTrips);
}

function setTripsSidebarCollapsed(collapsed) {
  tripsSidebar.classList.toggle("is-collapsed", collapsed);
  tripsSidebar.parentElement.classList.toggle("sidebar-collapsed", collapsed);
  tripsSidebarToggle.setAttribute("aria-expanded", String(!collapsed));
  tripsSidebarToggle.setAttribute(
    "aria-label",
    collapsed ? "Expand trips sidebar" : "Collapse trips sidebar",
  );
  tripsSidebarToggle.querySelector("span").textContent = collapsed ? "›" : "‹";
  window.setTimeout(() => map.invalidateSize(), 220);
}

async function loadTrips() {
  try {
    const response = await fetch("../output/trips.json");
    if (!response.ok) {
      throw new Error("Could not load trip data.");
    }

    allTrips = await response.json();
    populateFilters(allTrips);
    renderFilteredTrips();
  } catch (error) {
    console.error(error);
    statusElement.textContent = "The trip map could not be loaded.";
  }
}

filterForm.addEventListener("change", renderFilteredTrips);
document.querySelector("#reset-filters").addEventListener("click", () => {
  filters.year.value = "";
  filters.country.value = "";
  filters.category.value = "";
  filters.travelMode.value = "";
  renderFilteredTrips();
});
tripsSidebarToggle.addEventListener("click", () => {
  setTripsSidebarCollapsed(!tripsSidebar.classList.contains("is-collapsed"));
});
clearTripSelectionButton.addEventListener("click", clearTripSelection);

if (window.matchMedia("(max-width: 36rem)").matches) {
  setTripsSidebarCollapsed(true);
}

loadTrips();
