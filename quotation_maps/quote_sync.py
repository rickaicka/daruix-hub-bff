"""Synchronize supplier bids with the editable buyer comparison.

The submitted TenderBid.offer is immutable by buyer actions; QuotationMap.quotes is
an independently editable comparison. All functions work on JSON snapshots.
"""
from copy import deepcopy


def _price(value):
    return None if value is None or str(value).strip() == "" else str(value)


def merge_supplier_bid(quotation, bid):
    """Apply a new supplier submission without undoing buyer overrides."""
    if not bid.offer:
        return False
    quotes = deepcopy(quotation.quotes)
    by_supplier = {int(q["supplier"]["id"]): q for q in quotes}
    existing = by_supplier.get(bid.supplier_id)
    if existing is None:
        # Avoid creating unexpected suppliers in a map.
        return False
    incoming = bid.offer
    offers = {int(o["item_id"]): o for o in existing["offers"]}
    for offered in incoming.get("offers", []):
        previous = offers.get(int(offered["item_id"]))
        if previous is None:
            continue
        last_price = _price(offered.get("unit_price"))
        previous["tender_unit_price"] = last_price
        previous["tender_notes"] = offered.get("notes", "")
        previous["tender_updated_at"] = bid.submitted_at.isoformat() if bid.submitted_at else None
        if not previous.get("manual_override", False):
            previous["unit_price"] = last_price
            previous["price_source"] = "TENDER"
            if not previous.get("manual_notes_override", False):
                previous["notes"] = offered.get("notes", "")
        else:
            if not previous.get("manual_notes_override", False):
                previous["notes"] = offered.get("notes", "")
            previous["price_source"] = "ADJUSTED"
        # Do not overwrite selected, buyer notes or items not included in this bid.
    # Commercial terms follow the supplier unless the buyer edited them separately.
    for field in ("payment", "delivery", "freight", "discount", "notes"):
        key = "manual_terms_" + field
        if not existing.get(key, False) and field in incoming:
            existing[field] = incoming[field]
    # A data é controlada pelo envio do fornecedor, não pelo comparativo manual.
    if incoming.get("quoted_on"):
        existing["quoted_on"] = incoming["quoted_on"]
    quotation.quotes = quotes
    return True


def merge_buyer_quotes(quotation, incoming_quotes):
    """Maintain provenance and allow explicit restoration of submitted prices."""
    originals = {int(q["supplier"]["id"]): q for q in quotation.quotes}
    bids = {b.supplier_id: b for b in quotation.tender_bids.filter(submitted_at__isnull=False)}
    result = []
    for quote in incoming_quotes:
        supplier_id = int(quote["supplier"]["id"])
        previous = originals.get(supplier_id, {})
        old_offers = {int(o["item_id"]): o for o in previous.get("offers", [])}
        offer_from_bid = {int(o["item_id"]): o for o in (bids[supplier_id].offer or {}).get("offers", [])} if supplier_id in bids else {}
        for offer in quote["offers"]:
            old = old_offers.get(int(offer["item_id"]), {})
            from_bid = offer_from_bid.get(int(offer["item_id"]))
            tender_price = _price(from_bid.get("unit_price")) if from_bid else old.get("tender_unit_price")
            old_value = _price(old.get("unit_price"))
            current = _price(offer.get("unit_price"))
            restore = offer.pop("restore_tender", False)
            offer["tender_unit_price"] = tender_price
            offer["tender_notes"] = from_bid.get("notes", "") if from_bid else old.get("tender_notes", "")
            offer["manual_notes_override"] = bool(old.get("manual_notes_override")) or (
                bool(from_bid or old.get("tender_updated_at")) and offer.get("notes", "") != old.get("notes", "")
            )
            offer["tender_updated_at"] = old.get("tender_updated_at")
            if restore and tender_price is not None:
                offer["unit_price"] = tender_price
                offer["manual_override"] = False
                offer["price_source"] = "TENDER"
            elif tender_price is not None:
                override = bool(old.get("manual_override")) or current != old_value
                offer["manual_override"] = override
                offer["price_source"] = "ADJUSTED" if override else "TENDER"
            else:
                offer["manual_override"] = False
                offer["price_source"] = "MANUAL"
        for field in ("payment", "delivery", "freight", "discount", "notes"):
            key = "manual_terms_" + field
            quote[key] = bool(previous.get(key, False)) or (
                field in previous and str(quote.get(field)) != str(previous.get(field))
            )
        # O comparativo não pode alterar/apagar a data registrada pelo fornecedor.
        # Inclusive se a tela omitir a propriedade, mantém a data persistida.
        quote["quoted_on"] = (
            bids[supplier_id].offer.get("quoted_on")
            if supplier_id in bids and bids[supplier_id].offer and bids[supplier_id].offer.get("quoted_on")
            else previous.get("quoted_on")
        )
        quote.pop("manual_terms_quoted_on", None)
        result.append(quote)
    return result
