package com.conecta.billing.repo;

import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.RestController;

/** Local-only endpoint so the eval runner can start every scenario from the same state. */
@RestController
@Profile("!aws")
class LocalAdminController {

    private final InMemoryCreditStore credits;

    LocalAdminController(InMemoryCreditStore credits) {
        this.credits = credits;
    }

    @DeleteMapping("/local/credits")
    ResponseEntity<Void> clearCredits() {
        credits.clear();
        return ResponseEntity.noContent().build();
    }
}
