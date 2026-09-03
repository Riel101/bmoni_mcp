"""Read-only tools that report platform/geographic information about BMONI."""

from __future__ import annotations

from .common import get_client


async def bmoni_info_health() -> dict:
    """Check the BMONI API health.

    Returns:
        Health status payload.
    """
    client = get_client()
    return await client.get("/v1/health")


async def bmoni_info_location_countries() -> dict:
    """List countries supported by BMONI (used by SEPA onboarding).

    Returns:
        Each country's alpha3/alpha2 codes, name, postal code format and
        national id types.
    """
    client = get_client()
    return await client.get("/v1/location/countries")


async def bmoni_info_location_country(country_code: str) -> dict:
    """Get a country with its subdivisions.

    Args:
        country_code: alpha2 or alpha3 code (e.g. US/USA, NG/NGA).

    Returns:
        Country details plus subdivisions.
    """
    client = get_client()
    return await client.get(f"/v1/location/countries/{country_code}")


async def bmoni_info_location_subdivisions(country_code: str) -> dict:
    """List the subdivisions (states/provinces) of a country.

    Args:
        country_code: alpha2 or alpha3 code (e.g. US, NGA).

    Returns:
        List of subdivisions.
    """
    client = get_client()
    return await client.get(f"/v1/location/countries/{country_code}/subdivisions")


async def bmoni_info_location_cities(subdivision_code: str) -> dict:
    """List cities for a subdivision.

    Args:
        subdivision_code: ISO 3166-2 code without the country prefix
            (e.g. JAL for Jalisco, CMX for Mexico City). Returns 404 when
            the region has no city list - fall back to free text.

    Returns:
        List of cities.
    """
    client = get_client()
    return await client.get(f"/v1/location/subdivisions/{subdivision_code}/cities")


TOOLS = [
    bmoni_info_health,
    bmoni_info_location_countries,
    bmoni_info_location_country,
    bmoni_info_location_subdivisions,
    bmoni_info_location_cities,
]
