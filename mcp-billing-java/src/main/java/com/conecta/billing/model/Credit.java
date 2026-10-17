package com.conecta.billing.model;

import java.math.BigDecimal;
import java.util.List;

public record Credit(String creditId, String customerId, String invoiceId, List<String> lineIds,
                     String reasonCode, BigDecimal amount, String createdAt) {
}
