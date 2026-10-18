package mage.client.util;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SubscriptionPlayerRegistryTest {
    @TempDir
    Path root;

    @Test
    void cancellationReachesEveryModelInTheTable() throws Exception {
        SubscriptionPlayerRegistry registry = new SubscriptionPlayerRegistry();
        UUID table = UUID.randomUUID();
        Path second = Files.createDirectory(root.resolve("second"));
        Path third = Files.createDirectory(root.resolve("third"));
        registry.register(table, 2, second);
        registry.register(table, 3, third);
        registry.stop(table);
        assertTrue(Files.exists(second.resolve("cancel.requested")));
        assertTrue(Files.exists(third.resolve("cancel.requested")));
    }

    @Test
    void finishingOnePlayerDoesNotLoseTheOthers() throws Exception {
        SubscriptionPlayerRegistry registry = new SubscriptionPlayerRegistry();
        UUID table = UUID.randomUUID();
        Path second = Files.createDirectory(root.resolve("second"));
        Path third = Files.createDirectory(root.resolve("third"));
        registry.register(table, 2, second);
        registry.register(table, 3, third);
        registry.finished(table, 2);
        registry.stop(table);
        assertFalse(Files.exists(second.resolve("cancel.requested")));
        assertTrue(Files.exists(third.resolve("cancel.requested")));
    }

    @Test
    void duplicateSeatsAreRejected() {
        SubscriptionPlayerRegistry registry = new SubscriptionPlayerRegistry();
        UUID table = UUID.randomUUID();
        registry.register(table, 2, root);
        assertThrows(IllegalStateException.class, () -> registry.register(table, 2, root));
    }
}
