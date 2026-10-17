package com.conecta.billing.tools;

import com.conecta.billing.model.Credit;
import com.conecta.billing.model.Customer;
import com.conecta.billing.model.Invoice;
import com.conecta.billing.model.InvoiceLine;
import com.conecta.billing.policy.CreditDecision;
import com.conecta.billing.policy.CreditPolicy;
import com.conecta.billing.repo.BillingRepository;
import com.conecta.billing.repo.CreditStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springaicommunity.mcp.annotation.McpTool;
import org.springaicommunity.mcp.annotation.McpToolParam;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Component
public class BillingTools {

    private static final Logger log = LoggerFactory.getLogger(BillingTools.class);

    private final BillingRepository repo;
    private final CreditStore credits;
    private final CreditPolicy policy;

    public BillingTools(BillingRepository repo, CreditStore credits, CreditPolicy policy) {
        this.repo = repo;
        this.credits = credits;
        this.policy = policy;
    }

    @McpTool(name = "get_customer_profile",
            description = "Customer profile: name, zone, current plan, preferred language and customer since.")
    public Customer getCustomerProfile(@McpToolParam(description = "Customer id, e.g. C1001") String customerId) {
        return customer(customerId);
    }

    @McpTool(name = "list_invoices", description = "Invoice summaries for a customer (period, total, status), oldest first.")
    public List<Invoice> listInvoices(@McpToolParam(description = "Customer id") String customerId) {
        customer(customerId);
        return repo.findInvoices(customerId);
    }

    @McpTool(name = "get_invoice",
            description = "Full invoice with every line item. Use the line amounts exactly as returned.")
    public Invoice getInvoice(@McpToolParam(description = "Customer id") String customerId,
                              @McpToolParam(description = "Period YYYY-MM; omit for the latest invoice",
                                      required = false) String period) {
        return invoice(customerId, period);
    }

    @McpTool(name = "compare_with_previous_invoice",
            description = "Explains why an invoice changed: total difference and the line items that are new "
                    + "or missing compared with the previous period.")
    public Map<String, Object> compareWithPrevious(@McpToolParam(description = "Customer id") String customerId,
                                                   @McpToolParam(description = "Period YYYY-MM; omit for latest",
                                                           required = false) String period) {
        Invoice current = invoice(customerId, period);
        Optional<Invoice> prev = previous(current);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("invoice_id", current.invoiceId());
        out.put("period", current.period());
        out.put("total", current.total());
        if (prev.isEmpty()) {
            out.put("previous", null);
            return out;
        }
        Invoice p = prev.get();
        out.put("previous_period", p.period());
        out.put("previous_total", p.total());
        out.put("difference", current.total().subtract(p.total()));
        out.put("new_or_extra_lines", diff(current.lines(), p.lines()));
        out.put("missing_lines", diff(p.lines(), current.lines()));
        return out;
    }

    @McpTool(name = "check_credit_eligibility",
            description = "Runs the deterministic credit policy on an invoice. Returns which lines can be "
                    + "credited and max_credit (tax included). Never offer an amount that is not returned here.")
    public CreditDecision checkCreditEligibility(@McpToolParam(description = "Customer id") String customerId,
                                                 @McpToolParam(description = "Invoice id, e.g. INV-C1001-202610")
                                                 String invoiceId) {
        Invoice inv = invoiceById(customerId, invoiceId);
        return policy.evaluate(inv, previous(inv), credits.findByCustomer(customerId));
    }

    @McpTool(name = "apply_credit",
            description = "Applies a credit to an invoice ONLY after the customer agreed. The server re-checks the "
                    + "policy: every line must be eligible and amount must equal those lines plus tax.")
    public Map<String, Object> applyCredit(@McpToolParam(description = "Customer id") String customerId,
                                           @McpToolParam(description = "Invoice id") String invoiceId,
                                           @McpToolParam(description = "Eligible line ids to credit") List<String> lineIds,
                                           @McpToolParam(description = "Amount including tax") BigDecimal amount) {
        CreditDecision decision = checkCreditEligibility(customerId, invoiceId);
        Map<String, CreditDecision.LineVerdict> eligible = decision.eligible().stream()
                .collect(Collectors.toMap(CreditDecision.LineVerdict::lineId, v -> v));
        Set<String> requested = new HashSet<>(lineIds);
        if (requested.isEmpty() || !eligible.keySet().containsAll(requested)) {
            log.warn("credit rejected customer={} invoice={} lines={} reason=NOT_ELIGIBLE", customerId, invoiceId, lineIds);
            return Map.of("status", "REJECTED", "reason", "Some lines are not eligible",
                    "eligible_line_ids", eligible.keySet());
        }
        BigDecimal subtotal = requested.stream().map(id -> eligible.get(id).amount())
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        BigDecimal expected = subtotal.add(subtotal.multiply(CreditPolicy.TAX_RATE)).setScale(2,
                RoundingMode.HALF_UP);
        if (amount == null || expected.compareTo(amount) != 0) {
            log.warn("credit rejected customer={} invoice={} amount={} expected={}", customerId, invoiceId, amount, expected);
            return Map.of("status", "REJECTED", "reason", "Amount does not match policy", "expected_amount", expected);
        }
        String reason = eligible.get(requested.iterator().next()).reasonCode();
        Credit credit = new Credit("CR-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase(), customerId,
                invoiceId, List.copyOf(requested), reason, expected, OffsetDateTime.now().toString());
        credits.save(credit);
        log.info("credit applied id={} customer={} invoice={} amount={}", credit.creditId(), customerId, invoiceId, expected);
        return Map.of("status", "APPLIED", "credit_id", credit.creditId(), "amount", expected,
                "reflected_on", "next invoice");
    }

    // ------------------------------------------------------------------ helpers

    private Customer customer(String customerId) {
        return repo.findCustomer(customerId)
                .orElseThrow(() -> new IllegalArgumentException("Unknown customer " + customerId));
    }

    private Invoice invoice(String customerId, String period) {
        List<Invoice> all = repo.findInvoices(customerId);
        Invoice inv = (period == null || period.isBlank())
                ? all.stream().reduce((a, b) -> b).orElseThrow(() -> new IllegalArgumentException("No invoices"))
                : all.stream().filter(i -> i.period().equals(period)).findFirst()
                .orElseThrow(() -> new IllegalArgumentException("No invoice for period " + period));
        return inv.withLines(repo.findLines(inv.invoiceId()));
    }

    private Invoice invoiceById(String customerId, String invoiceId) {
        Invoice inv = repo.findInvoices(customerId).stream().filter(i -> i.invoiceId().equals(invoiceId)).findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Invoice " + invoiceId + " not found for " + customerId));
        return inv.withLines(repo.findLines(invoiceId));
    }

    private Optional<Invoice> previous(Invoice inv) {
        return repo.findInvoices(inv.customerId()).stream()
                .filter(i -> i.period().compareTo(inv.period()) < 0)
                .reduce((a, b) -> b)
                .map(p -> p.withLines(repo.findLines(p.invoiceId())));
    }

    /** Lines of {@code a} not matched (by concept + description + amount) in {@code b}, counting duplicates. */
    private static List<InvoiceLine> diff(List<InvoiceLine> a, List<InvoiceLine> b) {
        List<String> pool = new ArrayList<>(b.stream().filter(l -> !l.conceptCode().equals("TAX"))
                .map(BillingTools::key).toList());
        return a.stream().filter(l -> !l.conceptCode().equals("TAX")).filter(l -> !pool.remove(key(l))).toList();
    }

    private static String key(InvoiceLine l) {
        return l.conceptCode() + "|" + l.description() + "|" + l.amount();
    }
}
