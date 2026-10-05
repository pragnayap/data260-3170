#!/usr/bin/env python3
"""
HW5 Part 2A - TheMealDB tutorial MCP server.

A local FastMCP server exposing four tools over TheMealDB's public JSON API.
No API key is needed: the published test key is "1", which is baked into the
base URL below.

Run it in the Inspector (from the repo root):

    .venv/bin/mcp dev code/mcp_servers/meals_server.py

Then call each tool once and screenshot the input and the returned output.
Suggested inputs, which are the ones the assignment names:

    search_meals_by_name   query="Arrabiata"
    meals_by_ingredient    ingredient="chicken"
    random_meal            (no arguments)
    meal_details           id="52771"            <- Arrabiata's id

LOGGING RULE: this is a STDIO server, so stdout carries the JSON-RPC stream.
Writing to it corrupts the stream and the Inspector drops the connection.
Logging is configured to stderr below and there is no print() in this file.

A note on the return shape. The spec describes list outputs, and also asks
that a no-result response be "a clear, empty result with a short message". A
bare list has nowhere to put a message, so each tool returns a small object
with the list inside it: {query, count, meals[], message}. On a hit, message
is null; on a miss, meals is [] and message says so.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("meals-mcp")

import httpx  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

API_BASE = "https://www.themealdb.com/api/json/v1/1"
TIMEOUT_S = 10.0

mcp = FastMCP("meals")


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """One HTTP call against TheMealDB.

    Network and JSON failures are raised, not swallowed -- the spec asks for a
    clean error to reach the client, and the Inspector renders a raised
    exception as a tool error. "No results" is NOT a failure: TheMealDB
    answers {"meals": null} for that, and each tool turns it into an empty
    result with a message.
    """
    url = f"{API_BASE}/{path}"
    try:
        response = httpx.get(url, params=params, timeout=TIMEOUT_S)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        log.error("timeout calling %s: %s", url, exc)
        raise RuntimeError(f"TheMealDB timed out after {TIMEOUT_S}s") from exc
    except httpx.HTTPStatusError as exc:
        log.error("http %s from %s", exc.response.status_code, url)
        raise RuntimeError(
            f"TheMealDB returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        log.error("network error calling %s: %s", url, exc)
        raise RuntimeError(f"could not reach TheMealDB: {exc}") from exc

    try:
        return response.json()
    except ValueError as exc:
        log.error("non-JSON response from %s", url)
        raise RuntimeError("TheMealDB returned a response that was not JSON") from exc


def _card(meal: dict[str, Any]) -> dict[str, Any]:
    """Search-result shape: id, name, area, category, thumb."""
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "area": meal.get("strArea"),
        "category": meal.get("strCategory"),
        "thumb": meal.get("strMealThumb"),
    }


def _small_card(meal: dict[str, Any]) -> dict[str, Any]:
    """Ingredient-filter shape. filter.php returns only these three fields."""
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "thumb": meal.get("strMealThumb"),
    }


def _full(meal: dict[str, Any]) -> dict[str, Any]:
    """Full recipe shape, shared by meal_details and random_meal.

    TheMealDB stores ingredients as twenty flat pairs of columns --
    strIngredient1..20 alongside strMeasure1..20 -- with the unused slots left
    as "" or null. They are zipped back into a list here and the blanks
    dropped, so the client gets [{name, measure}] instead of forty keys.
    """
    ingredients = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        if name:
            ingredients.append({"name": name, "measure": measure})

    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource"),
        "youtube": meal.get("strYoutube"),
        "ingredients": ingredients,
    }


# --- tool 1 ----------------------------------------------------------------

@mcp.tool()
def search_meals_by_name(query: str, limit: int = 5) -> dict[str, Any]:
    """Search meals by name.

    Args:
        query: the dish name to search for, e.g. "Arrabiata".
        limit: how many meals to return, 1-25.

    Returns {query, count, meals[], message}. Each meal carries id, name,
    area, category and thumb; use the id with meal_details for the full recipe.
    """
    if not query or not query.strip():
        return {"query": query, "count": 0, "meals": [], "message": "query is required"}
    limit = max(1, min(int(limit), 25))

    payload = _get("search.php", {"s": query.strip()})
    meals = payload.get("meals")
    if not meals:
        log.info("search_meals_by_name %r -> no matches", query)
        return {
            "query": query,
            "count": 0,
            "meals": [],
            "message": f"no matches for {query!r}",
        }

    cards = [_card(m) for m in meals[:limit]]
    log.info("search_meals_by_name %r -> %d of %d", query, len(cards), len(meals))
    return {"query": query, "count": len(cards), "meals": cards, "message": None}


# --- tool 2 ----------------------------------------------------------------

@mcp.tool()
def meals_by_ingredient(ingredient: str, limit: int = 12) -> dict[str, Any]:
    """List meals that use a main ingredient.

    Args:
        ingredient: the main ingredient, e.g. "chicken".
        limit: how many meals to return, 1-25.

    Returns {ingredient, count, meals[], message}. The filter endpoint gives
    only id, name and thumb -- call meal_details for anything more.
    """
    if not ingredient or not ingredient.strip():
        return {
            "ingredient": ingredient,
            "count": 0,
            "meals": [],
            "message": "ingredient is required",
        }
    limit = max(1, min(int(limit), 25))

    payload = _get("filter.php", {"i": ingredient.strip()})
    meals = payload.get("meals")
    if not meals:
        log.info("meals_by_ingredient %r -> no matches", ingredient)
        return {
            "ingredient": ingredient,
            "count": 0,
            "meals": [],
            "message": f"no matches for {ingredient!r}",
        }

    cards = [_small_card(m) for m in meals[:limit]]
    log.info("meals_by_ingredient %r -> %d of %d", ingredient, len(cards), len(meals))
    return {
        "ingredient": ingredient,
        "count": len(cards),
        "meals": cards,
        "message": None,
    }


# --- tool 3 ----------------------------------------------------------------

@mcp.tool()
def random_meal() -> dict[str, Any]:
    """Return one random meal, in the same shape as meal_details.

    Takes no arguments.
    """
    payload = _get("random.php", {})
    meals = payload.get("meals")
    if not meals:
        log.info("random_meal -> empty response")
        return {"meal": None, "message": "TheMealDB returned no meal"}

    meal = _full(meals[0])
    log.info("random_meal -> %s (%s)", meal["name"], meal["id"])
    return {"meal": meal, "message": None}


# --- tool 4 ----------------------------------------------------------------

@mcp.tool()
def meal_details(id: str) -> dict[str, Any]:
    """Full recipe for one meal id.

    Args:
        id: the meal id from a search result, e.g. "52771".

    Returns {meal, message} where meal carries id, name, category, area,
    instructions, image, source, youtube and ingredients[{name, measure}].
    """
    meal_id = str(id).strip()
    if not meal_id:
        return {"meal": None, "message": "id is required"}

    payload = _get("lookup.php", {"i": meal_id})
    meals = payload.get("meals")
    if not meals:
        log.info("meal_details %r -> no match", meal_id)
        return {"meal": None, "message": f"no meal found with id {meal_id!r}"}

    meal = _full(meals[0])
    log.info("meal_details %s -> %s", meal_id, meal["name"])
    return {"meal": meal, "message": None}


if __name__ == "__main__":
    log.info("meals MCP server starting on STDIO (4 tools)")
    mcp.run()
