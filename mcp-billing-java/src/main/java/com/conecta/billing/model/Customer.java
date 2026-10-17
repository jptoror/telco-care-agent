package com.conecta.billing.model;

public record Customer(String customerId, String fullName, String zoneId, String planId,
                       String language, String customerSince, String segment) {
}
