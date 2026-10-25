from backend.sms_parser import MoMoSMSParser


def test_momo_parser_extracts_mtn_payment_received():
    sms = (
        "Payment received for GHS 150.00 from Kojo Mensah (0244123456). "
        "Current Balance: GHS 2,450.00. Reference: 5 bags maize. "
        "Financial Transaction Id: 18293048591. Date: 2026-03-15"
    )
    tx = MoMoSMSParser.parse_message(sms)
    assert tx is not None
    assert tx.amount == 150.0
    assert tx.channel == "MTN Mobile Money"
    assert "Kojo Mensah" in tx.customer
    assert tx.transaction_id == "18293048591"
    assert tx.balance_after == 2450.0
    assert tx.transaction_date == "2026-03-15"
    assert "maize" in tx.product


def test_momo_parser_extracts_telecel_cash():
    sms = (
        "You have received GHS 85.50 from 233201234567 - KWAME ASANTE. "
        "Trans ID: 0092837482. Balance: GHS 1,120.00. Date: 2026-02-18"
    )
    tx = MoMoSMSParser.parse_message(sms)
    assert tx is not None
    assert tx.amount == 85.50
    assert tx.channel == "Telecel Cash"
    assert tx.transaction_id == "0092837482"
    assert tx.balance_after == 1120.0


def test_momo_parser_handles_batch_sms():
    batch = """
    Payment received for GHS 200.00 from Ama Osei (0244999888). Current Balance: GHS 1,200.00. Reference: Catering. Transaction ID: MTN-001. Date: 2026-04-01

    You have received GHS 350.00 from Esi Mensah. Trans ID: TC-002. Balance: GHS 1,550.00. Date: 2026-04-02
    """
    transactions = MoMoSMSParser.parse_batch(batch)
    assert len(transactions) == 2
    assert transactions[0].amount == 200.0
    assert transactions[1].amount == 350.0
