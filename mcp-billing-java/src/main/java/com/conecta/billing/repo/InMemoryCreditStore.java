package com.conecta.billing.repo;

import com.conecta.billing.model.Credit;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

@Repository
@Profile("!aws")
public class InMemoryCreditStore implements CreditStore {

    private final List<Credit> credits = new CopyOnWriteArrayList<>();

    @Override
    public List<Credit> findByCustomer(String customerId) {
        return credits.stream().filter(c -> c.customerId().equals(customerId)).toList();
    }

    @Override
    public void save(Credit credit) {
        credits.add(credit);
    }

    void clear() {
        credits.clear();
    }
}
