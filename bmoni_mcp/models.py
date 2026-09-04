"""Pydantic models for nested request bodies.

Using these (instead of free-form dicts) gives AI agents an accurate JSON
Schema for the nested payloads the BMONI API expects. Model field names
match the API's camelCase keys exactly so bodies can be sent verbatim.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class KycAddress(BaseModel):
    streetLine1: Optional[str] = Field(None, description="Street address, line 1")
    streetLine2: Optional[str] = Field(None, description="Street address, line 2")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State / province")
    postalCode: Optional[str] = Field(None, description="Postal code")
    countryCode: Optional[str] = Field(None, description="ISO country code")


class KycEmployment(BaseModel):
    occupationCode: Optional[str] = Field(None, description="Occupation code from the KYC occupation search")
    employerName: Optional[str] = Field(None, description="Employer name")
    employmentStatus: Optional[str] = Field(None, description="Employment status (see KYC options)")


class KycIdentificationNumber(BaseModel):
    type: Optional[str] = Field(None, description="Identification type (see KYC options)")
    number: Optional[str] = Field(None, description="Identification number")
    issuingCountryCode: Optional[str] = Field(None, description="ISO country code that issued the ID")


class KycPersonalInfo(BaseModel):
    name: Optional[str] = Field(None, description="Full legal name")
    dob: Optional[str] = Field(None, description="Date of birth (ISO 8601, e.g. 1990-01-31)")
    gender: Optional[str] = Field(None, description="Gender (see KYC options)")
    contact: Optional[dict] = Field(None, description="Contact details object (e.g. phoneNumber, email)")


class EuCounterpartDetails(BaseModel):
    firstName: Optional[str] = Field(None, description="Counterparty first name")
    lastName: Optional[str] = Field(None, description="Counterparty last name")
    country: Optional[str] = Field(None, description="Counterparty country code")


class EuCounterpartIdentifier(BaseModel):
    """SEPA beneficiary account identifier (IBAN)."""

    iban: str = Field(..., description="Beneficiary IBAN (ISO 13616)")


class EuCounterpart(BaseModel):
    identifier: EuCounterpartIdentifier = Field(
        ..., description="Beneficiary IBAN identifier"
    )
    details: EuCounterpartDetails = Field(..., description="Beneficiary personal details")


class KycUpdateInput(BaseModel):
    """Partial update body for PATCH /v1/users/{userId}/kyc."""

    accountPurpose: Optional[str] = Field(
        None, description="Enum: personal, business, investment"
    )
    actingAsIntermediary: Optional[bool] = Field(
        None, description="Whether the user acts as an intermediary"
    )
    address: Optional[KycAddress] = Field(None, description="Residential address")
    employment: Optional[KycEmployment] = Field(None, description="Employment details")
    estimatedMonthlyVolume: Optional[float] = Field(
        None, description="Estimated monthly transaction volume"
    )
    identificationNumbers: Optional[list[KycIdentificationNumber]] = Field(
        None, description="Government-issued identification numbers"
    )
    personalInfo: Optional[KycPersonalInfo] = Field(None, description="Personal information")
    sourceOfFunds: Optional[str] = Field(
        None,
        description="Enum: salary, business, investments, pension, government, inheritance, savings",
    )


class CardCreateInput(BaseModel):
    """Create Card request (POST /v1/users/{userId}/cards)."""

    cardColor: str = Field(..., description="Card color as hex, e.g. #1A2B3C")
    cardName: str = Field(..., description="Card name (max 50 chars)")
    currency: str = Field(..., description="Card currency: NGN or USD")
    smartWalletId: str = Field(..., description="Smart wallet id (UUID) linked to the card")
    type: str = Field(..., description="physical or virtual")
    bvn: Optional[str] = Field(None, description="Nigerian BVN (optional)")
    nin: Optional[str] = Field(None, description="NIN, required for first-time card requests")
    ninIssueDate: Optional[str] = Field(None, description="NIN issue date (ISO 8601)")
    ninExpiryDate: Optional[str] = Field(None, description="NIN expiry date (ISO 8601)")
    pan: Optional[str] = Field(
        None,
        description="PAN for in-hand activation (Journey A). Omit for delivery (Journey B).",
    )
    deliveryAddress: Optional[dict] = Field(
        None, description="Delivery address object (required for Journey B)"
    )
    deliveryPhoneNumber: Optional[str] = Field(None, description="Delivery phone (Journey B)")
    deliveryState: Optional[str] = Field(None, description="Delivery state (Journey B)")


class BankPayoutDetails(BaseModel):
    bankId: str = Field(..., description="Bank identifier from the payout bank list")
    branchId: Optional[str] = Field(None, description="Branch identifier from the branch list")
    accountNumber: str = Field(..., description="Destination account number")
    accountHolderName: str = Field(..., description="Account holder name")
    routingNumber: Optional[str] = Field(None, description="Routing number when required")
    swiftCode: Optional[str] = Field(None, description="SWIFT/BIC when required")
    accountType: Optional[str] = Field(None, description="Account type when required")
