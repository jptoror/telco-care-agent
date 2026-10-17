package com.conecta.billing.repo;

import com.conecta.billing.model.Credit;

import java.util.List;

/** Credits issued to customers. In memory locally, DynamoDB on AWS. */
public interface CreditStore {

    List<Credit> findByCustomer(String customerId);

    void save(Credit credit);
}
