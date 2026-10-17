package com.conecta.billing.policy;

import java.math.BigDecimal;
import java.util.List;

/**
 * Outcome of the credit policy for one invoice. {@code maxCredit} already includes the tax of the
 * eligible lines; it is the only amount the agent is allowed to offer.
 */
public record CreditDecision(String invoiceId, List<LineVerdict> eligible, List<LineVerdict> notEligible,
                             BigDecimal eligibleSubtotal, BigDecimal eligibleTax, BigDecimal maxCredit) {

    public record LineVerdict(String lineId, String conceptCode, String description, BigDecimal amount,
                              String reasonCode, String explanation) {
    }
}
