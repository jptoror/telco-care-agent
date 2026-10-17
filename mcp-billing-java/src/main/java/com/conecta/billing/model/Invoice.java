package com.conecta.billing.model;

import java.math.BigDecimal;
import java.util.List;

public record Invoice(String invoiceId, String customerId, String period, String issueDate, String dueDate,
                      BigDecimal subtotal, BigDecimal tax, BigDecimal total, String status, String paidOn,
                      List<InvoiceLine> lines) {

    public Invoice withLines(List<InvoiceLine> lines) {
        return new Invoice(invoiceId, customerId, period, issueDate, dueDate, subtotal, tax, total, status, paidOn,
                lines);
    }
}
