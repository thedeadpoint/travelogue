const EUROPE_CENTER = [50.5, 10];
const EUROPE_ZOOM = 4;

const map = L.map("map").setView(EUROPE_CENTER, EUROPE_ZOOM);
const statusElement = document.querySelector("#status");

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

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

  for (const trip of trips) {
    for (const stop of trip.stops) {
      if (
        typeof stop.latitude !== "number" ||
        typeof stop.longitude !== "number"
      ) {
        continue;
      }

      const coordinates = [stop.latitude, stop.longitude];
      const marker = L.marker(coordinates).addTo(map);
      addPopupContent(marker, trip, stop);
      markerBounds.push(coordinates);
    }
  }

  if (markerBounds.length) {
    map.fitBounds(markerBounds, { padding: [30, 30] });
  }

  statusElement.textContent = "Map loaded.";
}

async function loadTrips() {
  try {
    const response = await fetch("../output/trips.json");
    if (!response.ok) {
      throw new Error("Could not load trip data.");
    }

    const trips = await response.json();
    addTripStops(trips);
  } catch (error) {
    console.error(error);
    statusElement.textContent = "The trip map could not be loaded.";
  }
}

loadTrips();
