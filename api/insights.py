import os
import json
import time
import googlemaps
from typing import Optional, List, Dict


def handler(request):
    try:
        if request.method == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Content-Type": "application/json",
                },
                "body": json.dumps({"ok": True}),
            }

        if request.method != "POST":
            return {
                "statusCode": 405,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json",
                },
                "body": json.dumps({"ok": False, "error": "Method not allowed. Use POST."}),
            }

        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return {
                "statusCode": 500,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json",
                },
                "body": json.dumps({"ok": False, "error": "GOOGLE_MAPS_API_KEY not set"}),
            }

        try:
            data = request.get_json()  # Vercel passes JSON automatically
        except Exception:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json",
                },
                "body": json.dumps({"ok": False, "error": "Invalid JSON"}),
            }

        address = data.get("address")
        if not address:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json",
                },
                "body": json.dumps({"ok": False, "error": "Address is required"}),
            }

        # Main logic
        result = get_neighborhood_insights(address, api_key)

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            },
            "body": json.dumps(result),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            },
            "body": json.dumps({"ok": False, "error": str(e)}),
        }


def get_neighborhood_insights(address: str, api_key: str) -> Dict:
    """
    Collects multi-category neighborhood insights.
    """
    try:
        gmaps = googlemaps.Client(key=api_key)
    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to initialize Google Maps client: {str(e)}",
            "query": address,
        }

    default_cfg = {
        "radii": {
            "cafe": 1000,
            "school": 8000,
            "hospital": 5000,
            "pharmacy": 2000,
            "park": 1500,
            "gym": 2000,
            "shopping_mall": 5000,
            "subway_station": 2000,
        },
        "top_n": 5,
    }

    print(f"\n--- Getting insights for: {address} ---")
    geo = geocode_address(address, gmaps, region="tr")
    if not geo:
        msg = f"Could not geocode the address: {address}"
        print(msg)
        return {"ok": False, "error": msg, "query": address}

    lat, lng = geo["lat"], geo["lng"]
    formatted = geo["formatted_address"]
    print(f"Geocoded Location: {formatted} (Lat: {lat}, Lng: {lng})")

    insights: Dict = {
        "ok": True,
        "query": address,
        "address": formatted,
        "coordinates": {"lat": lat, "lng": lng},
        "source": geo.get("source", "google"),
        "social_life": {},
        "family_life": {},
        "transport": {},
        "summary": {},
    }

    top_n = default_cfg["top_n"]
    radii = default_cfg["radii"]

    # ---------- SOCIAL LIFE ----------
    cafes = find_places_nearby(lat, lng, "cafe", gmaps, radius=radii["cafe"])
    cafes_sorted = sorted(cafes, key=safe_sort_key, reverse=True)
    insights["social_life"]["cafes"] = {"count": len(cafes), "top": cafes_sorted[:top_n]}

    malls = find_places_nearby(lat, lng, "shopping_mall", gmaps, radius=radii["shopping_mall"])
    malls_filtered = [m for m in malls if "shopping_mall" in (m.get("types") or [])]
    malls_sorted = sorted(malls_filtered, key=safe_sort_key, reverse=True)
    insights["social_life"]["shopping_malls"] = {"count": len(malls_filtered), "top": malls_sorted[:top_n]}

    parks = find_places_nearby(lat, lng, "park", gmaps, radius=radii["park"])
    parks_sorted = sorted(parks, key=safe_sort_key, reverse=True)
    insights["social_life"]["parks"] = {"count": len(parks), "top": parks_sorted[:top_n]}

    gyms = find_places_nearby(lat, lng, "gym", gmaps, radius=radii["gym"])
    gyms_sorted = sorted(gyms, key=safe_sort_key, reverse=True)
    insights["social_life"]["gyms"] = {"count": len(gyms), "top": gyms_sorted[:top_n]}

    # ---------- FAMILY LIFE ----------
    schools = find_places_nearby(lat, lng, "school", gmaps, radius=radii["school"])
    schools_sorted = sorted(schools, key=safe_sort_key, reverse=True)
    insights["family_life"]["schools"] = {"count": len(schools), "top": schools_sorted[:top_n]}

    hospitals = find_places_nearby(lat, lng, "hospital", gmaps, radius=radii["hospital"])
    hospital_nearest = find_nearest_place(lat, lng, "hospital", gmaps)
    hospitals_sorted = sorted(hospitals, key=safe_sort_key, reverse=True)
    insights["family_life"]["hospitals"] = {
        "count": len(hospitals),
        "nearest": hospital_nearest.get("name") if hospital_nearest else None,
        "top": hospitals_sorted[:top_n],
    }

    pharmacies = find_places_nearby(lat, lng, "pharmacy", gmaps, radius=radii["pharmacy"])
    insights["family_life"]["pharmacies"] = {"count": len(pharmacies), "top": pharmacies[:top_n]}

    # ---------- TRANSPORT ----------
    metros = find_places_nearby(lat, lng, "subway_station", gmaps, radius=radii["subway_station"])
    metro_nearest = find_nearest_place(lat, lng, "subway_station", gmaps)
    insights["transport"]["subway"] = {
        "count": len(metros),
        "nearest": metro_nearest.get("name") if metro_nearest else None,
        "alternatives": metros[:top_n],
    }

    # ---------- SUMMARY ----------
    def summarize_list(lst: List[Dict], top: int = 3) -> List[str]:
        return [x.get("name", "") for x in lst[:top] if isinstance(x, dict)]

    insights["summary"] = {
        "headline": (
            f"{formatted}: {len(cafes)} cafes, {len(parks)} parks, {len(gyms)} gyms, "
            f"{len(schools)} schools, {len(hospitals)} hospitals, {len(malls_filtered)} malls nearby."
        ),
        "highlights": {
            "cafes_top": summarize_list(cafes_sorted, top=3),
            "schools_top": summarize_list(schools_sorted, top=3),
            "malls_top": summarize_list(malls_sorted, top=3),
            "nearest_hospital": hospital_nearest.get("name") if hospital_nearest else None,
            "nearest_subway": metro_nearest.get("name") if metro_nearest else None,
        },
    }

    return insights


def geocode_address(address: str, gmaps, region: str = "tr") -> Optional[dict]:
    """
    Geocodes an address into latitude and longitude coordinates using Google Maps API.
    """
    try:
        geocode_result = gmaps.geocode(address, region=region)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            formatted_address = geocode_result[0]['formatted_address']
            return {
                "lat": location['lat'],
                "lng": location['lng'],
                "formatted_address": formatted_address,
                "source": "google",
            }
        else:
            print(f"No geocoding result found for address: {address}")
            return None
    except Exception as e:
        print(f"Error during geocoding for address '{address}': {e}")
        return None


def find_places_nearby(latitude: float, longitude: float, place_type: str, gmaps, radius: int, max_pages: int = 2):
    """
    Finds places nearby using Google Places API, with pagination.
    """
    all_places = []
    try:
        response = gmaps.places_nearby(
            location=(latitude, longitude),
            radius=radius,
            type=place_type,
        )

        all_places.extend(response.get("results", []))

        # Pagination: up to 2 pages for performance
        pages = 1
        while "next_page_token" in response and pages < max_pages:
            time.sleep(2)  # required by Google before using next_page_token
            response = gmaps.places_nearby(
                location=(latitude, longitude),
                radius=radius,
                type=place_type,
                page_token=response["next_page_token"],
            )
            all_places.extend(response.get("results", []))
            pages += 1

        places = []
        for place in all_places:
            places.append({
                "name": place.get("name"),
                "rating": place.get("rating"),
                "user_ratings_total": place.get("user_ratings_total"),
                "types": place.get("types", []),
            })
        return places

    except Exception as e:
        print(f"Error finding places nearby (type: {place_type}): {e}")
        return []


def find_nearest_place(latitude: float, longitude: float, place_type: str, gmaps):
    """
    Finds the single nearest place of a given type using rank_by=distance.
    """
    try:
        response = gmaps.places_nearby(
            location=(latitude, longitude),
            type=place_type,
            rank_by="distance",
        )

        if response.get("results"):
            nearest_place = response["results"][0]
            return {
                "name": nearest_place.get("name"),
                "rating": nearest_place.get("rating"),
            }
        return None

    except Exception as e:
        print(f"Error finding nearest place (type: {place_type}): {e}")
        return None


def safe_sort_key(x: Dict) -> tuple:
    rating = x.get("rating") if x.get("rating") is not None else 0.0
    count = x.get("user_ratings_total") if x.get("user_ratings_total") is not None else 0
    return (rating, count)
