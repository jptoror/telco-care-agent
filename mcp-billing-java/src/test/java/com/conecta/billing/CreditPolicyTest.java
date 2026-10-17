package com.conecta.billing;

import com.conecta.billing.model.Credit;
import com.conecta.billing.model.Invoice;
import com.conecta.billing.model.InvoiceLine;
import com.conecta.billing.policy.CreditDecision;
import com.conecta.billing.policy.CreditPolicy;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class CreditPolicyTest {

    private final CreditPolicy policy = new CreditPolicy();

    @Test
    void duplicatePlanFeeIsEligibleWithTax() {
        Invoice inv = invoice("2026-10", "", line("L1", "PLAN_FEE", "45.00"), line("L2", "PLAN_FEE", "45.00"));
        CreditDecision d = policy.evaluate(inv, Optional.empty(), List.of());
        assertThat(d.eligible()).extracting(CreditDecision.LineVerdict::lineId).containsExactly("L2");
        assertThat(d.maxCredit()).isEqualByComparingTo("49.50");
    }

    @Test
    void premiumSmsOnlyOnFirstDispute() {
        Invoice inv = invoice("2026-10", "", line("L1", "PREMIUM_SMS", "4.99"), line("L2", "PREMIUM_SMS", "4.99"));
        assertThat(policy.evaluate(inv, Optional.empty(), List.of()).maxCredit()).isEqualByComparingTo("10.98");

        Credit earlier = new Credit("CR-1", "C1", "INV-OLD", List.of("L0"), "UNRECOGNIZED_PREMIUM_SMS",
                new BigDecimal("5.49"), "2026-09-01");
        assertThat(policy.evaluate(inv, Optional.empty(), List.of(earlier)).eligible()).isEmpty();
    }

    @Test
    void lateFeeStandsWhenPreviousInvoiceWasPaidLate() {
        Invoice prev = new Invoice("INV-9", "C1", "2026-09", "2026-09-01", "2026-09-16", BigDecimal.ZERO,
                BigDecimal.ZERO, BigDecimal.ZERO, "PAID", "2026-09-27", List.of());
        Invoice inv = invoice("2026-10", "", line("L1", "LATE_FEE", "5.00"));
        assertThat(policy.evaluate(inv, Optional.of(prev), List.of()).eligible()).isEmpty();
    }

    @Test
    void lateFeeIsCreditedWhenPreviousInvoiceWasPaidOnTime() {
        Invoice prev = new Invoice("INV-9", "C1", "2026-09", "2026-09-01", "2026-09-16", BigDecimal.ZERO,
                BigDecimal.ZERO, BigDecimal.ZERO, "PAID", "2026-09-10", List.of());
        Invoice inv = invoice("2026-10", "", line("L1", "LATE_FEE", "5.00"));
        assertThat(policy.evaluate(inv, Optional.of(prev), List.of()).maxCredit()).isEqualByComparingTo("5.50");
    }

    @Test
    void usageChargesAndAlreadyCreditedLinesAreNotEligible() {
        Invoice inv = invoice("2026-10", "", line("L1", "ROAMING", "63.00"), line("L2", "PLAN_FEE", "45.00"),
                line("L3", "PLAN_FEE", "45.00"));
        Credit done = new Credit("CR-1", "C1", "INV-1", List.of("L3"), "DUPLICATE_CHARGE",
                new BigDecimal("49.50"), "2026-10-17");
        assertThat(policy.evaluate(inv, Optional.empty(), List.of(done)).eligible()).isEmpty();
    }

    private static Invoice invoice(String period, String paidOn, InvoiceLine... lines) {
        return new Invoice("INV-1", "C1", period, period + "-01", period + "-16", BigDecimal.ZERO, BigDecimal.ZERO,
                BigDecimal.ZERO, "OPEN", paidOn, List.of(lines));
    }

    private static InvoiceLine line(String id, String code, String amount) {
        return new InvoiceLine(id, "INV-1", code, code + " charge", new BigDecimal(amount), "2026-10-01");
    }
}
