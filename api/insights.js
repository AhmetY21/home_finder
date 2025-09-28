import { Client } from "@googlemaps/google-maps-services-js";

const gmaps = new Client({});

// Main handler for Vercel
export default async function handler(req, res) {
  try {
    // Handle CORS preflight
    if (req.method === "OPTIONS") {
      return res.status(200).setHeader("Access-Control-Allow-Origin", "*")
        .setHeader("Access-Control-Allow-Methods", "POST, OPTIONS")
        .setHeader("Access-Control-Allow-Headers", "Content-Type")
        .json({ ok: true });
    }

    if (req.method !== "POST") {
      return res.status(405).setHeader("Access-Control-Allow-Origin", "*")
        .json({ ok: false, error: "Method not allowed. Use POST." });
    }

    const apiKey = process.env.GOOGLE_MAPS_API_KEY;
    if (!apiKey) {
      return res.status(500).setHeader("Access-Control-Allow-Origin", "*")
        .json({ ok: false, error: "GOOGLE_MAPS_API_KEY not set" });
    }

    const { address } = req.body || {};
    if (!address) {
      return res.status(400).setHeader("Access-Control-Allow-Origin", "*")
        .json({ ok: false, error: "Address is required" });
    }

    // Main logic
    const insights = await getNeighborhoodInsights(address, apiKey);

    return res.status(200).setHeader("Access-Control-Allow-Origin", "*")
      .json(insights);

  } catch (err) {
    return res.status(500).setHeader("Access-Control-Allow-Origin", "*")
      .json({ ok: false, error: err.message });
  }
}

// ----------------- Helpers -----------------

async function getNeighborhoodInsights(address, apiKey) {
  try {
    const geo = await geocodeAddress(address, apiKey);
    if (!geo) {
      return { ok: false, error: `Could not geocode address: ${address}`, query: address };
    }

    const { lat, lng, formatted_address } = geo;

    const radii = {
      cafe: 1000,
      school: 8000,
      hospital: 5000,
      pharmacy: 2000,
      park: 1500,
      gym: 2000,
      shopping_mall: 5000,
      subway_station: 2000,
    };
    const topN = 5;

    // Example: cafes
    const cafes = await findPlacesNearby(lat, lng, "cafe", apiKey, radii.cafe);
    const cafesSorted = cafes.sort(sortPlaces).slice(0, topN);

    // Example: hospitals (nearest)
    const hospitals = await findPlacesNearby(lat, lng, "hospital", apiKey, radii.hospital);
    const hospitalNearest = await findNearestPlace(lat, lng, "hospital", apiKey);

    return {
      ok: true,
      query: address,
      address: formatted_address,
      coordinates: { lat, lng },
      social_life: {
        cafes: { count: cafes.length, top: cafesSorted }
      },
      family_life: {
        hospitals: {
          count: hospitals.length,
          nearest: hospitalNearest?.name || null,
          top: hospitals.sort(sortPlaces).slice(0, topN)
        }
      }
    };
  } catch (err) {
    return { ok: false, error: err.message, query: address };
  }
}

async function geocodeAddress(address, apiKey) {
  try {
    const response = await gmaps.geocode({
      params: { address, region: "tr", key: apiKey }
    });
    if (response.data.results.length > 0) {
      const loc = response.data.results[0].geometry.location;
      return {
        lat: loc.lat,
        lng: loc.lng,
        formatted_address: response.data.results[0].formatted_address,
        source: "google"
      };
    }
    return null;
  } catch (err) {
    console.error("Geocode error:", err.message);
    return null;
  }
}

async function findPlacesNearby(lat, lng, type, apiKey, radius) {
  try {
    const response = await gmaps.placesNearby({
      params: { location: { lat, lng }, radius, type, key: apiKey }
    });
    return response.data.results.map(place => ({
      name: place.name,
      rating: place.rating,
      user_ratings_total: place.user_ratings_total,
      types: place.types
    }));
  } catch (err) {
    console.error(`Error finding places (${type}):`, err.message);
    return [];
  }
}

async function findNearestPlace(lat, lng, type, apiKey) {
  try {
    const response = await gmaps.placesNearby({
      params: { location: { lat, lng }, rankby: "distance", type, key: apiKey }
    });
    if (response.data.results.length > 0) {
      const nearest = response.data.results[0];
      return { name: nearest.name, rating: nearest.rating };
    }
    return null;
  } catch (err) {
    console.error(`Error finding nearest ${type}:`, err.message);
    return null;
  }
}

function sortPlaces(a, b) {
  const ratingA = a.rating || 0;
  const ratingB = b.rating || 0;
  const countA = a.user_ratings_total || 0;
  const countB = b.user_ratings_total || 0;
  // Sort by rating, then by user ratings
  return (ratingB - ratingA) || (countB - countA);
}
