package com.conecta.billing.model;

import java.math.BigDecimal;

public record InvoiceLine(String lineId, String invoiceId, String conceptCode, String description,
                          BigDecimal amount, String refDate) {
}
