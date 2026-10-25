"""Mobile Money (MoMo) SMS transaction parser for Ghanaian and regional operators."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ParsedMoMoTransaction:
    transaction_id: str
    transaction_date: str
    amount: float
    customer: str
    product: str
    category: str
    channel: str
    balance_after: float | None
    currency: str
    raw_text: str

    def to_record(self) -> dict[str, Any]:
        record = {
            "transaction_id": self.transaction_id,
            "transaction_date": self.transaction_date,
            "amount": self.amount,
            "customer": self.customer,
            "product": self.product,
            "category": self.category,
            "currency": self.currency,
            "channel": self.channel,
        }
        if self.balance_after is not None:
            record["balance_after"] = self.balance_after
        return record


class MoMoSMSParser:
    """Parses individual and batched SMS messages from MTN MoMo, Telecel Cash, and AirtelTigo."""

    # Regex patterns for amounts
    _AMOUNT_PATTERN = re.compile(
        r"(?:GHS|GH[¢c]|GHC)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)", re.IGNORECASE
    )
    _FEE_PATTERN = re.compile(
        r"(?:fee\s*(?:charged)?|charge)\s*[:of]?\s*(?:GHS|GH[¢c]|GHC)?\s*([0-9]+(?:\.[0-9]{1,2})?)",
        re.IGNORECASE,
    )
    _BALANCE_PATTERN = re.compile(
        r"(?:current\s*balance|new\s*balance|balance|bal)\s*[:is]?\s*(?:GHS|GH[¢c]|GHC)\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)",
        re.IGNORECASE,
    )
    _TXN_ID_PATTERN = re.compile(
        r"(?:financial\s*transaction\s*id|transaction\s*id|trans(?:action)?\s*id|txn\s*id)\s*[:is]\s*([a-zA-Z0-9_\-]+)",
        re.IGNORECASE,
    )
    _REFERENCE_PATTERN = re.compile(
        r"(?:reference|ref|for|memo)\s*[:is]\s*([^.\n,]+)", re.IGNORECASE
    )
    _DATE_PATTERN = re.compile(
        r"(?:date\s*[:is]\s*)?(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
        re.IGNORECASE,
    )

    @classmethod
    def _clean_amount(cls, text: str) -> float:
        return float(text.replace(",", "").strip())

    @classmethod
    def _parse_date(cls, text: str) -> str:
        date_match = cls._DATE_PATTERN.search(text)
        if date_match:
            raw_date = date_match.group(1).replace("/", "-").replace(".", "-")
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%d-%m-%y"):
                try:
                    return datetime.strptime(raw_date, fmt).date().isoformat()
                except ValueError:
                    continue
        return datetime.now().date().isoformat()

    @classmethod
    def _detect_channel(cls, text: str) -> str:
        low = text.lower()
        if "telecel" in low or "vodafone" in low or "voda" in low:
            return "Telecel Cash"
        if "airteltigo" in low or "tigo" in low or "airtel" in low:
            return "AirtelTigo Money"
        if "mtn" in low or "momo" in low or "mobile money" in low:
            return "MTN Mobile Money"
        if "financial transaction id" in low:
            return "MTN Mobile Money"
        if "trans id" in low:
            return "Telecel Cash"
        if "txn id" in low:
            return "AirtelTigo Money"

        # Check Ghanaian mobile number prefixes
        if re.search(r"\b(?:0|233)(?:24|54|55|59|53)[0-9]{7}\b", text):
            return "MTN Mobile Money"
        if re.search(r"\b(?:0|233)(?:20|50)[0-9]{7}\b", text):
            return "Telecel Cash"
        if re.search(r"\b(?:0|233)(?:27|57|26|56)[0-9]{7}\b", text):
            return "AirtelTigo Money"

        return "Mobile Money"

    @classmethod
    def parse_message(cls, text: str) -> ParsedMoMoTransaction | None:
        trimmed = text.strip()
        if not trimmed:
            return None

        # Check for amount
        amount_match = cls._AMOUNT_PATTERN.search(trimmed)
        if not amount_match:
            return None

        raw_amount = cls._clean_amount(amount_match.group(1))
        low = trimmed.lower()

        # Categorize transaction
        is_received = any(
            phrase in low
            for phrase in (
                "payment received",
                "received from",
                "you have received",
                "cash in",
                "transferred to you",
                "credited to your account",
            )
        )
        is_payment_made = any(
            phrase in low
            for phrase in (
                "payment of",
                "payment made",
                "you have paid",
                "paid to",
                "cash out",
                "sent to",
                "transferred to",
            )
        )

        if not is_received and not is_payment_made:
            # Check generic indicator
            if "balance" in low or "transaction" in low:
                is_received = True
            else:
                return None

        category = "momo_sale_received" if is_received else "momo_expense_paid"
        channel = cls._detect_channel(trimmed)

        # Extract balance after
        balance_match = cls._BALANCE_PATTERN.search(trimmed)
        balance_after = (
            cls._clean_amount(balance_match.group(1)) if balance_match else None
        )

        # Extract transaction ID
        txn_match = cls._TXN_ID_PATTERN.search(trimmed)
        txn_id = txn_match.group(1).strip() if txn_match else f"MOMO-{uuid.uuid4().hex[:10].upper()}"

        # Extract counterparty / customer
        customer = "Mobile Money Customer"
        # Check patterns like "from <NAME> (<PHONE>)" or "from <NAME>" or "from <PHONE> - <NAME>"
        from_match = re.search(
            r"from\s+([A-Za-z\s]+?)(?:\s*\(([0-9+]+)\)|\s*[-–]\s*([0-9+]+)|\s+on\b|\s+current\b|\s+ref\b|\.|$)",
            trimmed,
            re.IGNORECASE,
        )
        to_match = re.search(
            r"to\s+([A-Za-z\s]+?)(?:\s*\(([0-9+]+)\)|\s*[-–]\s*([0-9+]+)|\s+on\b|\s+current\b|\s+ref\b|\.|$)",
            trimmed,
            re.IGNORECASE,
        )

        party_match = from_match if is_received else to_match
        if party_match:
            name_part = party_match.group(1).strip()
            if len(name_part) > 1 and name_part.lower() not in {"ghs", "ghc", "momo", "your", "an"}:
                customer = name_part.title()
                phone_part = party_match.group(2) or party_match.group(3)
                if phone_part:
                    customer += f" ({phone_part.strip()})"
        else:
            phone_direct = re.search(r"\b(0[25][0-9]{8}|233[25][0-9]{8})\b", trimmed)
            if phone_direct:
                customer = f"Customer {phone_direct.group(1)}"

        # Extract product / reference memo
        ref_match = cls._REFERENCE_PATTERN.search(trimmed)
        reference = "Mobile Money Transaction"
        if ref_match:
            ref_text = ref_match.group(1).strip()
            # Clean up trailing tokens
            ref_clean = re.sub(
                r"\s*(?:financial\s*transaction\s*id|transaction\s*id|current\s*balance|balance|fee).*",
                "",
                ref_text,
                flags=re.IGNORECASE,
            ).strip()
            if ref_clean:
                reference = ref_clean

        product_label = (
            f"MoMo: {reference}"
            if reference != "Mobile Money Transaction"
            else f"MoMo {'Service/Sale' if is_received else 'Disbursement'}"
        )

        txn_date = cls._parse_date(trimmed)

        return ParsedMoMoTransaction(
            transaction_id=txn_id,
            transaction_date=txn_date,
            amount=raw_amount,
            customer=customer,
            product=product_label,
            category=category,
            channel=channel,
            balance_after=balance_after,
            currency="GHS",
            raw_text=trimmed,
        )

    @classmethod
    def parse_batch(cls, text: str) -> list[ParsedMoMoTransaction]:
        """Splits multi-message text blocks and extracts all valid MoMo transactions."""
        # Split by empty lines or numbered logs or delimiter markers
        blocks = re.split(r"\n\s*\n|(?<=\.)\s+(?=[A-Z][a-z]+ received|Payment received|You have received|You have paid)", text)
        results: list[ParsedMoMoTransaction] = []
        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            candidate = " ".join(lines)
            parsed = cls.parse_message(candidate)
            if parsed:
                results.append(parsed)
        return results
