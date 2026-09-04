"""Tools to verify a user's identity (KYC) and drive it to activation-ready."""

from __future__ import annotations

from typing import Literal, Optional

from ..config import get_settings
from ..models import KycUpdateInput
from ..uploads import validate_upload
from .common import get_client, payload

# Documented SumSub level names.
SumSubLevel = Literal[
    "id-only", "id-and-liveness", "idv-and-phone-verification", "bmoni-monerium"
]


def _multipart_file(
    name: str,
    content_base64: str,
    filename: str,
    allowed: Optional[set[str]] = None,
) -> tuple[str, tuple[str, bytes, str]]:
    """Validate (size + magic bytes) and prepare a multipart file part."""
    settings = get_settings()
    content, content_type = validate_upload(
        content_base64,
        filename=filename,
        max_mb=settings.upload_max_mb,
        allowed_types=allowed,
    )
    return name, (filename, content, content_type)


async def bmoni_kyc_options(user_id: str) -> dict:
    """Return the enum values used by the KYC form.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        Genders, employmentStatuses, fundsSources, identificationTypes,
        accountPurposes and estimatedMonthlyVolumeRanges.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/kyc/options")


async def bmoni_kyc_search_occupations(user_id: str, search: str) -> dict:
    """Search the active occupations available for KYC onboarding.

    Args:
        user_id: BMONI user id (UUID).
        search: Term to filter occupations by job title/alias.

    Returns:
        Matching occupations with their occupation codes.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/kyc/occupations", params={"search": search}
    )


async def bmoni_kyc_get_profile(user_id: str) -> dict:
    """Get the user's sectioned KYC profile.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        Basic, identity, address and work sections with verification status
        and presigned document URLs.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/kyc")


async def bmoni_kyc_update_profile(user_id: str, body: KycUpdateInput) -> dict:
    """Partially update a user's KYC profile.

    Args:
        user_id: BMONI user id (UUID).
        body: Sections to update (address, employment, personalInfo,
            identificationNumbers, sourceOfFunds, accountPurpose, etc.).

    Returns:
        Success status, saved sections, validation errors, activation
        readiness and any still-missing fields.
    """
    client = get_client()
    return await client.patch(
        f"/v1/users/{user_id}/kyc",
        json_body=body.model_dump(exclude_none=True),
    )


async def bmoni_kyc_bvn_lookup(user_id: str, bvn: str) -> dict:
    """Preview BVN data without saving it to the profile.

    Args:
        user_id: BMONI user id (UUID).
        bvn: 11-digit Nigerian BVN.

    Returns:
        Personal and residential details returned by the BVN provider.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/kyc/bvn-lookup/{bvn}")


async def bmoni_kyc_nin_lookup(user_id: str, nin: str) -> dict:
    """Preview NIN data (QoreID) without saving it to the profile.

    Args:
        user_id: BMONI user id (UUID).
        nin: 11-digit Nigerian NIN.

    Returns:
        QoreID identity data.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/kyc/nin-lookup/{nin}")


async def bmoni_kyc_readiness(user_id: str) -> dict:
    """Check whether the general KYC profile is ready for activation.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        Readiness flags for the profile.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/kyc/readiness")


async def bmoni_kyc_usd_readiness(user_id: str) -> dict:
    """Check whether the profile is ready for a USD virtual bank account.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        ``ready`` boolean plus the list of ``missing`` fields.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/kyc/usd-readiness")


async def bmoni_kyc_status(user_id: str) -> dict:
    """Get the latest KYC review status snapshot.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        Review status with rejection labels and moderation comments.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/kyc/status")


async def bmoni_kyc_retry(user_id: str, sumsub_level_name: SumSubLevel) -> dict:
    """Retry KYC verification when the state is action_required.

    Args:
        user_id: BMONI user id (UUID).
        sumsub_level_name: Verification level to request.

    Returns:
        Result of re-syncing documents and requesting a new review.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/kyc/retry",
        json_body=payload(sumsubLevelName=sumsub_level_name),
    )


async def bmoni_kyc_activate(
    user_id: str, sumsub_level_name: Optional[SumSubLevel] = None
) -> dict:
    """Activate the user's KYC profile (kicks off identity verification).

    Routes to PayTrie for Canada or SumSub for other regions. The level
    name is required everywhere except Canada.

    Args:
        user_id: BMONI user id (UUID).
        sumsub_level_name: id-only, id-and-liveness,
            idv-and-phone-verification or bmoni-monerium. Optional only for Canada.

    Returns:
        Activation result / workflow details.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/kyc/activate",
        json_body=payload(sumsubLevelName=sumsub_level_name),
    )


async def bmoni_kyc_upload_identification(
    user_id: str,
    type: str,
    file_base64: str,
    document_number: Optional[str] = None,
    issuing_country: Optional[str] = None,
    issue_date: Optional[str] = None,
    expiration_date: Optional[str] = None,
    filename: str = "front.jpg",
    back_file_base64: Optional[str] = None,
    back_filename: str = "back.jpg",
) -> dict:
    """Upload a government ID document for KYC verification.

    Args:
        user_id: BMONI user id (UUID).
        type: Document type (e.g. passport, national_id, drivers_license).
        file_base64: Base64-encoded image of the document front.
        document_number: Document number.
        issuing_country: ISO country code that issued the document.
        issue_date: Issue date (ISO 8601).
        expiration_date: Expiration date (ISO 8601).
        filename: Filename/extension hint for the front image.
        back_file_base64: Optional base64 image of the document back.
        back_filename: Filename/extension hint for the back image.

    Returns:
        Upload / verification result.
    """
    client = get_client()
    files = [_multipart_file("files", file_base64, filename)]
    if back_file_base64:
        files.append(_multipart_file("files", back_file_base64, back_filename))
    data = payload(
        type=type,
        documentNumber=document_number,
        issuingCountry=issuing_country,
        issueDate=issue_date,
        expirationDate=expiration_date,
    )
    return await client.post(
        f"/v1/users/{user_id}/kyc/documents/identification", data=data, files=files
    )


async def bmoni_kyc_upload_proof_of_address(
    user_id: str,
    type: str,
    file_base64: str,
    filename: str = "proof.jpg",
    second_file_base64: Optional[str] = None,
    second_filename: str = "second.jpg",
) -> dict:
    """Upload a proof-of-address document for KYC verification.

    Args:
        user_id: BMONI user id (UUID).
        type: Document type (e.g. utility_bill, bank_statement).
        file_base64: Base64-encoded image of the document (front).
        filename: Filename/extension hint for the image.
        second_file_base64: Optional second image.
        second_filename: Filename/extension hint for the second image.

    Returns:
        Upload / verification result.
    """
    client = get_client()
    files = [_multipart_file("files", file_base64, filename)]
    if second_file_base64:
        files.append(_multipart_file("files", second_file_base64, second_filename))
    return await client.post(
        f"/v1/users/{user_id}/kyc/documents/proof-of-address",
        data=payload(type=type),
        files=files,
    )


async def bmoni_kyc_upload_biometric(
    user_id: str,
    type: str,
    file_base64: str,
    filename: str = "selfie.jpg",
) -> dict:
    """Upload a biometric (selfie) for KYC verification.

    Args:
        user_id: BMONI user id (UUID).
        type: Biometric type (e.g. selfie).
        file_base64: Base64-encoded selfie image.
        filename: Filename/extension hint for the image.

    Returns:
        Upload / verification result.
    """
    client = get_client()
    files = [
        _multipart_file("files", file_base64, filename, allowed={"jpeg", "png"})
    ]
    return await client.post(
        f"/v1/users/{user_id}/kyc/documents/biometric",
        data=payload(type=type),
        files=files,
    )


TOOLS = [
    bmoni_kyc_options,
    bmoni_kyc_search_occupations,
    bmoni_kyc_get_profile,
    bmoni_kyc_update_profile,
    bmoni_kyc_bvn_lookup,
    bmoni_kyc_nin_lookup,
    bmoni_kyc_readiness,
    bmoni_kyc_usd_readiness,
    bmoni_kyc_status,
    bmoni_kyc_retry,
    bmoni_kyc_activate,
    bmoni_kyc_upload_identification,
    bmoni_kyc_upload_proof_of_address,
    bmoni_kyc_upload_biometric,
]
