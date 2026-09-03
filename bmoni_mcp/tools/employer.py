"""Partner employee (employer link) tools."""

from __future__ import annotations

from typing import Literal, Optional

from .common import get_client, payload


async def bmoni_employer_invite_employee(
    email: str,
    name: str,
    kyc_profile: Optional[dict] = None,
    kyc_activate: Optional[dict] = None,
) -> dict:
    """Invite an employee with a co-branded email + QR deep link.

    Args:
        email: Employee email.
        name: Employee name.
        kyc_profile: Optional KYC profile object to prefill.
        kyc_activate: Optional KYC activate object (level name).

    Returns:
        Invitation details.
    """
    client = get_client()
    kyc = payload(profile=kyc_profile, activate=kyc_activate) or None
    return await client.post(
        "/v1/partners/employees/invite",
        json_body=payload(email=email, name=name, kyc=kyc),
    )


async def bmoni_employer_batch_upsert(employees: list) -> dict:
    """Batch upsert employees without sending emails (max 500 rows).

    Rows are processed independently; a failed row does not fail the batch.

    Args:
        employees: Array of invite objects, each shaped like
            {email, name, kyc?: {profile?, activate?}}.

    Returns:
        Batch processing result with per-row outcomes.
    """
    client = get_client()
    return await client.post(
        "/v1/partners/employees/batch", json_body=payload(employees=employees)
    )


async def bmoni_employer_list(
    page: Optional[int] = None,
    limit: Optional[int] = None,
    status: Optional[Literal["INVITED", "LINKED", "UNLINKED"]] = None,
) -> dict:
    """List employee invitations.

    Args:
        page: Page number.
        limit: Page size.
        status: INVITED, LINKED or UNLINKED.

    Returns:
        Paginated employee invitations.
    """
    client = get_client()
    return await client.get(
        "/v1/partners/employees",
        params=payload(page=page, limit=limit, status=status),
    )


async def bmoni_employer_offboard(employee_id: str) -> dict:
    """Offboard an employee (cancels invite or marks UNLINKED).

    Args:
        employee_id: Employee id (UUID).

    Returns:
        Offboarding result. Emits an employee.unlinked webhook when linked.
    """
    client = get_client()
    return await client.delete(f"/v1/partners/employees/{employee_id}")


TOOLS = [
    bmoni_employer_invite_employee,
    bmoni_employer_batch_upsert,
    bmoni_employer_list,
    bmoni_employer_offboard,
]
