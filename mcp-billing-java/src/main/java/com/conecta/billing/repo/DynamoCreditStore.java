package com.conecta.billing.repo;

import com.conecta.billing.model.Credit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/** Table keyed by customer_id (hash) + credit_id (range). */
@Repository
@Profile("aws")
public class DynamoCreditStore implements CreditStore {

    private final DynamoDbClient dynamo = DynamoDbClient.create();
    private final String table;

    public DynamoCreditStore(@Value("${billing.credits-table}") String table) {
        this.table = table;
    }

    @Override
    public List<Credit> findByCustomer(String customerId) {
        return dynamo.query(b -> b.tableName(table)
                        .keyConditionExpression("customer_id = :c")
                        .expressionAttributeValues(Map.of(":c", AttributeValue.fromS(customerId))))
                .items().stream()
                .map(i -> new Credit(i.get("credit_id").s(), customerId, i.get("invoice_id").s(), i.get("line_ids").ss(),
                        i.get("reason_code").s(), new BigDecimal(i.get("amount").n()), i.get("created_at").s()))
                .toList();
    }

    @Override
    public void save(Credit c) {
        dynamo.putItem(b -> b.tableName(table).item(Map.of(
                "customer_id", AttributeValue.fromS(c.customerId()),
                "credit_id", AttributeValue.fromS(c.creditId()),
                "invoice_id", AttributeValue.fromS(c.invoiceId()),
                "line_ids", AttributeValue.fromSs(c.lineIds()),
                "reason_code", AttributeValue.fromS(c.reasonCode()),
                "amount", AttributeValue.fromN(c.amount().toPlainString()),
                "created_at", AttributeValue.fromS(c.createdAt()))));
    }
}
