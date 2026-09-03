"""Tools that create and look up BMONI users."""

from __future__ import annotations

from typing import Optional

from .common import get_client, payload


async def bmoni_users_create(
    email: str,
    first_name: str,
    phone_number: str,
    bvn: Optional[str] = None,
    identity_id: Optional[str] = None,
    employer_name: Optional[str] = None,
    employee_id: Optional[str] = None,
    address_city: Optional[str] = None,
    address_country: Optional[str] = None,
    address_postal_code: Optional[str] = None,
    address_state: Optional[str] = None,
    address_street: Optional[str] = None,
) -> dict:
    """Create a BMONI user (the wallet holder) under your partner account.

    Args:
        email: User email address.
        first_name: User first name.
        phone_number: Phone number in E.164 format (e.g. +2348012345678).
        bvn: Nigerian BVN (11 digits). When provided, BMONI auto-fills the
            last name, middle name, address and date of birth from the BVN.
        identity_id: External identity id. Auto-generated UUID when omitted.
        employer_name: Employer name (for employee programmes).
        employee_id: Partner employee id.
        address_city: City.
        address_country: Country.
        address_postal_code: Postal code.
        address_state: State / province.
        address_street: Street address.

    Returns:
        The created user (UserOutput) on HTTP 201.
    """
    client = get_client()
    body = payload(
        email=email,
        firstName=first_name,
        phoneNumber=phone_number,
        bvn=bvn,
        identityId=identity_id,
        employerName=employer_name,
        employeeId=employee_id,
        addressCity=address_city,
        addressCountry=address_country,
        addressPostalCode=address_postal_code,
        addressState=address_state,
        addressStreet=address_street,
    )
    return await client.post("/v1/users", json_body=body)


async def bmoni_users_lookup_wallets_by_phone(phone_number: str) -> dict:
    """Resolve a phone number to a BMONI user and list their smart wallets.

    Args:
        phone_number: Phone number in E.164 format.

    Returns:
        The matched user and their smart wallets, if any.
    """
    client = get_client()
    return await client.get("/v1/smart-wallets/by-phone", params={"phoneNumber": phone_number})


TOOLS = [
    bmoni_users_create,
    bmoni_users_lookup_wallets_by_phone,
]
