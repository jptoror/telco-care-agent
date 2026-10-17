package com.conecta.billing.policy;

import com.conecta.billing.model.Credit;
import com.conecta.billing.model.Invoice;
import com.conecta.billing.model.InvoiceLine;
import com.conecta.billing.policy.CreditDecision.LineVerdict;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * Deterministic rules that decide which invoice lines can be credited. The LLM never decides an amount:
 * it can only offer what this policy returns, and {@code apply_credit} re-checks it.
 */
@Component
public class CreditPolicy {

    public static final BigDecimal TAX_RATE = new BigDecimal("0.10");

    public CreditDecision evaluate(Invoice invoice, Optional<Invoice> previous, List<Credit> priorCredits) {
        Set<String> creditedLines = new HashSet<>();
        boolean premiumSmsCreditedBefore = false;
        for (Credit c : priorCredits) {
            creditedLines.addAll(c.lineIds());
            premiumSmsCreditedBefore |= c.reasonCode().equals("UNRECOGNIZED_PREMIUM_SMS");
        }

        List<LineVerdict> eligible = new ArrayList<>();
        List<LineVerdict> notEligible = new ArrayList<>();
        Set<String> seenPlanFee = new HashSet<>();

        for (InvoiceLine l : invoice.lines()) {
            if (l.conceptCode().equals("TAX")) {
                continue;
            }
            if (creditedLines.contains(l.lineId())) {
                notEligible.add(verdict(l, "ALREADY_CREDITED", "Esta linea ya fue acreditada antes."));
                continue;
            }
            switch (l.conceptCode()) {
                case "PLAN_FEE" -> {
                    if (seenPlanFee.add(l.description() + "|" + l.refDate())) {
                        notEligible.add(verdict(l, "VALID_CHARGE", "Cargo fijo del plan contratado."));
                    } else {
                        eligible.add(verdict(l, "DUPLICATE_CHARGE",
                                "El cargo fijo aparece dos veces para el mismo periodo."));
                    }
                }
                case "PREMIUM_SMS" -> {
                    if (premiumSmsCreditedBefore) {
                        notEligible.add(verdict(l, "PREMIUM_SMS_REPEAT",
                                "Ya se acredito SMS premium una vez; se debe bloquear el servicio."));
                    } else {
                        eligible.add(verdict(l, "UNRECOGNIZED_PREMIUM_SMS",
                                "Primer reclamo por suscripcion SMS premium no reconocida."));
                    }
                }
                case "LATE_FEE" -> {
                    if (previous.isPresent() && paidOnTime(previous.get())) {
                        eligible.add(verdict(l, "LATE_FEE_IN_ERROR",
                                "La factura anterior se pago a tiempo; el recargo no aplica."));
                    } else {
                        notEligible.add(verdict(l, "VALID_LATE_FEE", previous
                                .map(p -> "La factura " + p.period() + " vencia el " + p.dueDate()
                                        + " y se pago el " + (p.paidOn().isBlank() ? "(sin pago)" : p.paidOn()) + ".")
                                .orElse("No hay factura anterior para validar.")));
                    }
                }
                case "ROAMING" -> notEligible.add(verdict(l, "USAGE_CHARGE",
                        "Cargo por uso en el exterior; el plan no incluye roaming."));
                case "PRORATION" -> notEligible.add(verdict(l, "VALID_PRORATION",
                        "Prorrateo por cambio de plan a mitad de periodo."));
                case "DATA_PACK" -> notEligible.add(verdict(l, "PURCHASED_ADDON",
                        "Paquete adicional comprado por el cliente."));
                default -> notEligible.add(verdict(l, "NOT_COVERED", "Concepto sin regla de credito."));
            }
        }

        BigDecimal subtotal = eligible.stream().map(LineVerdict::amount).reduce(BigDecimal.ZERO, BigDecimal::add);
        BigDecimal tax = subtotal.multiply(TAX_RATE).setScale(2, RoundingMode.HALF_UP);
        return new CreditDecision(invoice.invoiceId(), eligible, notEligible, subtotal.setScale(2), tax,
                subtotal.add(tax).setScale(2, RoundingMode.HALF_UP));
    }

    private static boolean paidOnTime(Invoice inv) {
        return !inv.paidOn().isBlank() && !LocalDate.parse(inv.paidOn()).isAfter(LocalDate.parse(inv.dueDate()));
    }

    private static LineVerdict verdict(InvoiceLine l, String code, String explanation) {
        return new LineVerdict(l.lineId(), l.conceptCode(), l.description(), l.amount(), code, explanation);
    }
}
