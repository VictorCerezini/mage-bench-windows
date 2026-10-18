package mage.client.util;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Tracks every local model seat in a table so cancellation stops all its workers. */
final class SubscriptionPlayerRegistry {
    private final Map<UUID, Map<Integer, Path>> tables = new ConcurrentHashMap<>();

    void register(UUID table, int seat, Path run) {
        Path previous = tables.computeIfAbsent(table, ignored -> new ConcurrentHashMap<>()).putIfAbsent(seat, run);
        if (previous != null) {
            throw new IllegalStateException("A subscription player already owns this table seat");
        }
    }

    void finished(UUID table, int seat) {
        tables.computeIfPresent(table, (ignored, players) -> {
            players.remove(seat);
            return players.isEmpty() ? null : players;
        });
    }

    void stop(UUID table) throws IOException {
        Map<Integer, Path> players = tables.get(table);
        if (players != null) {
            for (Path run : players.values()) {
                Files.writeString(run.resolve("cancel.requested"), "Table closed", StandardCharsets.UTF_8);
            }
        }
    }
}
