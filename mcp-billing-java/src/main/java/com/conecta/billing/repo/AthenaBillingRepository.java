package com.conecta.billing.repo;

import com.conecta.billing.model.Customer;
import com.conecta.billing.model.Invoice;
import com.conecta.billing.model.InvoiceLine;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.services.athena.AthenaClient;
import software.amazon.awssdk.services.athena.model.Datum;
import software.amazon.awssdk.services.athena.model.GetQueryResultsRequest;
import software.amazon.awssdk.services.athena.model.QueryExecutionState;
import software.amazon.awssdk.services.athena.model.Row;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Queries the Glue catalog tables over S3 through Athena. Parameters go through Athena execution
 * parameters, never string concatenation.
 */
@Repository
@Profile("aws")
public class AthenaBillingRepository implements BillingRepository {

    private final AthenaClient athena;
    private final String database;
    private final String workgroup;

    public AthenaBillingRepository(@Value("${billing.athena.database}") String database,
                                   @Value("${billing.athena.workgroup}") String workgroup) {
        this.athena = AthenaClient.create();
        this.database = database;
        this.workgroup = workgroup;
    }

    @Override
    public Optional<Customer> findCustomer(String customerId) {
        return query("SELECT customer_id, full_name, zone_id, plan_id, language, customer_since, segment "
                + "FROM customers WHERE customer_id = ?", customerId).stream()
                .map(r -> new Customer(r.get("customer_id"), r.get("full_name"), r.get("zone_id"), r.get("plan_id"),
                        r.get("language"), r.get("customer_since"), r.get("segment")))
                .findFirst();
    }

    @Override
    public List<Invoice> findInvoices(String customerId) {
        return query("SELECT * FROM invoices WHERE customer_id = ? ORDER BY period", customerId).stream()
                .map(r -> new Invoice(r.get("invoice_id"), r.get("customer_id"), r.get("period"), r.get("issue_date"),
                        r.get("due_date"), new BigDecimal(r.get("subtotal")), new BigDecimal(r.get("tax")),
                        new BigDecimal(r.get("total")), r.get("status"), r.get("paid_on"), List.of()))
                .toList();
    }

    @Override
    public List<InvoiceLine> findLines(String invoiceId) {
        return query("SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_id", invoiceId).stream()
                .map(r -> new InvoiceLine(r.get("line_id"), r.get("invoice_id"), r.get("concept_code"),
                        r.get("description"), new BigDecimal(r.get("amount")), r.get("ref_date")))
                .toList();
    }

    private List<Map<String, String>> query(String sql, String... params) {
        String id = athena.startQueryExecution(b -> b
                .queryString(sql)
                .executionParameters(List.of(params).stream().map(p -> "'" + p.replace("'", "''") + "'").toList())
                .queryExecutionContext(c -> c.database(database))
                .workGroup(workgroup)).queryExecutionId();
        waitFor(id);

        List<Map<String, String>> out = new ArrayList<>();
        List<String> columns = null;
        for (var page : athena.getQueryResultsPaginator(GetQueryResultsRequest.builder().queryExecutionId(id).build())) {
            if (columns == null) {
                columns = page.resultSet().resultSetMetadata().columnInfo().stream().map(c -> c.name()).toList();
            }
            for (Row row : page.resultSet().rows()) {
                List<String> values = row.data().stream().map(Datum::varCharValue).toList();
                if (values.equals(columns)) {
                    continue; // header row on the first page
                }
                Map<String, String> m = new HashMap<>();
                for (int i = 0; i < columns.size(); i++) {
                    m.put(columns.get(i), values.get(i) == null ? "" : values.get(i));
                }
                out.add(m);
            }
        }
        return out;
    }

    private void waitFor(String queryExecutionId) {
        for (int attempt = 0; attempt < 120; attempt++) {
            var status = athena.getQueryExecution(b -> b.queryExecutionId(queryExecutionId))
                    .queryExecution().status();
            QueryExecutionState state = status.state();
            if (state == QueryExecutionState.SUCCEEDED) {
                return;
            }
            if (state == QueryExecutionState.FAILED || state == QueryExecutionState.CANCELLED) {
                throw new IllegalStateException("Athena query " + state + ": " + status.stateChangeReason());
            }
            try {
                Thread.sleep(250);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        }
        throw new IllegalStateException("Athena query timed out: " + queryExecutionId);
    }
}
