const EUROPE_CENTER = [50.5, 10];
const EUROPE_ZOOM = 4;

const map = L.map("map").setView(EUROPE_CENTER, EUROPE_ZOOM);
const statusElement = document.querySelector("#status");
const markerLayer = L.layerGroup().addTo(map);
const filterForm = document.querySelector("#filters");
const filters = {
  year: document.querySelector("#year-filter"),
  country: document.querySelector("#country-filter"),
  category: document.querySelector("#category-filter"),
  travelMode: document.querySelector("#travel-mode-filter"),
};
let allTrips = [];

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

function addTripStops(trips) {
  const markerBounds = [];
  markerLayer.clearLayers();

  for (const trip of trips) {
    for (const stop of trip.stops) {
      if (
        typeof stop.latitude !== "number" ||
        typeof stop.longitude !== "number"
      ) {
        continue;
      }

      const coordinates = [stop.latitude, stop.longitude];
      const marker = L.marker(coordinates).addTo(markerLayer);
      addPopupContent(marker, trip, stop);
      markerBounds.push(coordinates);
    }
  }

  if (markerBounds.length) {
    map.fitBounds(markerBounds, { padding: [30, 30] });
  } else {
    map.setView(EUROPE_CENTER, EUROPE_ZOOM);
  }

  statusElement.textContent = "Map loaded.";
}

function renderFilteredTrips() {
  const filteredTrips = allTrips.filter(tripMatchesFilters);
  updateStatistics(filteredTrips);
  addTripStops(filteredTrips);
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
  filterForm.reset();
  renderFilteredTrips();
});

loadTrips();
