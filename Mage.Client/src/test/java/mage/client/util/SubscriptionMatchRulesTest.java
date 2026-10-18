package mage.client.util;

import mage.game.match.MatchOptions;
import mage.players.PlayerType;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SubscriptionMatchRulesTest {
    private MatchOptions match(String gameType, int players) {
        MatchOptions options = new MatchOptions("Subscription test", gameType, players > 2);
        options.setWinsNeeded(1);
        for (int index = 0; index < players; index++) {
            options.getPlayerTypes().add(PlayerType.HUMAN);
        }
        return options;
    }

    @Test
    void commanderDuelUsesTheNativeFormatRules() {
        MatchOptions options = match("Commander Two Player Duel", 2);
        options.setDeckType("Variant Magic - Duel Commander");
        assertDoesNotThrow(() -> SubscriptionMatchRules.validate(options));
    }

    @Test
    void multiplayerAndOtherGameModesAreNotDuelOnly() {
        for (String mode : new String[]{"Commander Free For All", "Free For All", "Brawl Free For All",
                "Freeform Commander Free For All", "Oathbreaker Free For All", "Momir Basic Free For All"}) {
            assertDoesNotThrow(() -> SubscriptionMatchRules.validate(match(mode, 4)), mode);
        }
        assertDoesNotThrow(() -> SubscriptionMatchRules.validate(match("Brawl Two Player Duel", 2)));
    }

    @Test
    void ratedIsNotAGameInterfaceLimitation() {
        MatchOptions options = match("Two Player Duel", 2);
        options.setRated(true);
        assertDoesNotThrow(() -> SubscriptionMatchRules.validate(options));
    }

    @Test
    void multipleGamesExplainTheActualMissingLifecycle() {
        MatchOptions options = match("Commander Two Player Duel", 2);
        options.setWinsNeeded(2);
        IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                () -> SubscriptionMatchRules.validate(options));
        assertTrue(error.getMessage().contains("sideboard"));
    }

    @Test
    void passwordExplainsTheActualMissingJoinSupport() {
        MatchOptions options = match("Commander Two Player Duel", 2);
        options.setPassword("local-test-table");
        IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                () -> SubscriptionMatchRules.validate(options));
        assertTrue(error.getMessage().contains("password"));
    }
}
