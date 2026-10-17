package com.conecta.billing.repo;

import com.conecta.billing.model.Customer;
import com.conecta.billing.model.Invoice;
import com.conecta.billing.model.InvoiceLine;

import java.util.List;
import java.util.Optional;

/** Read-only access to billing data. CSV files locally, Athena (Glue catalog over S3) on AWS. */
public interface BillingRepository {

    Optional<Customer> findCustomer(String customerId);

    /** Invoices of a customer, oldest first, without lines. */
    List<Invoice> findInvoices(String customerId);

    List<InvoiceLine> findLines(String invoiceId);
}
