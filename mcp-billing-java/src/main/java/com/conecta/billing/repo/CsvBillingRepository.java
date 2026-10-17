package com.conecta.billing.repo;

import com.conecta.billing.model.Customer;
import com.conecta.billing.model.Invoice;
import com.conecta.billing.model.InvoiceLine;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** Loads the generated CSV tables (data/out) into memory. Used for local development and tests. */
@Repository
@Profile("!aws")
public class CsvBillingRepository implements BillingRepository {

    private final Map<String, Customer> customers = new HashMap<>();
    private final List<Invoice> invoices;
    private final List<InvoiceLine> lines;

    public CsvBillingRepository(@Value("${billing.data-dir:../data/out}") String dataDirPath) {
        Path dataDir = Path.of(dataDirPath);
        read(dataDir.resolve("customers.csv")).forEach(r -> customers.put(r.get("customer_id"),
                new Customer(r.get("customer_id"), r.get("full_name"), r.get("zone_id"), r.get("plan_id"),
                        r.get("language"), r.get("customer_since"), r.get("segment"))));
        invoices = read(dataDir.resolve("invoices.csv")).stream()
                .map(r -> new Invoice(r.get("invoice_id"), r.get("customer_id"), r.get("period"), r.get("issue_date"),
                        r.get("due_date"), new BigDecimal(r.get("subtotal")), new BigDecimal(r.get("tax")),
                        new BigDecimal(r.get("total")), r.get("status"), r.get("paid_on"), List.of()))
                .toList();
        lines = read(dataDir.resolve("invoice_lines.csv")).stream()
                .map(r -> new InvoiceLine(r.get("line_id"), r.get("invoice_id"), r.get("concept_code"),
                        r.get("description"), new BigDecimal(r.get("amount")), r.get("ref_date")))
                .toList();
    }

    @Override
    public Optional<Customer> findCustomer(String customerId) {
        return Optional.ofNullable(customers.get(customerId));
    }

    @Override
    public List<Invoice> findInvoices(String customerId) {
        return invoices.stream().filter(i -> i.customerId().equals(customerId))
                .sorted(Comparator.comparing(Invoice::period)).toList();
    }

    @Override
    public List<InvoiceLine> findLines(String invoiceId) {
        return lines.stream().filter(l -> l.invoiceId().equals(invoiceId)).toList();
    }

    /** Minimal RFC 4180 reader (quoted fields, doubled quotes); enough for the generated tables. */
    private static List<Map<String, String>> read(Path file) {
        try {
            List<String> rows = Files.readAllLines(file);
            List<String> header = split(rows.getFirst());
            return rows.stream().skip(1).filter(s -> !s.isBlank()).map(s -> {
                List<String> values = split(s);
                Map<String, String> row = new HashMap<>();
                for (int i = 0; i < header.size(); i++) {
                    row.put(header.get(i), i < values.size() ? values.get(i) : "");
                }
                return row;
            }).toList();
        } catch (IOException e) {
            throw new UncheckedIOException("Cannot read " + file + " (run data/generate.py first)", e);
        }
    }

    private static List<String> split(String line) {
        List<String> out = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (quoted) {
                if (c == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                    cur.append('"');
                    i++;
                } else if (c == '"') {
                    quoted = false;
                } else {
                    cur.append(c);
                }
            } else if (c == '"') {
                quoted = true;
            } else if (c == ',') {
                out.add(cur.toString());
                cur.setLength(0);
            } else {
                cur.append(c);
            }
        }
        out.add(cur.toString());
        return out;
    }
}
