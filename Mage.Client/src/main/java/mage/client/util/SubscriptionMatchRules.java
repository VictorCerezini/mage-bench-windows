package mage.client.util;

import mage.game.match.MatchOptions;

/** Restrictions of the local subscription supervisor, separate from XMage format rules. */
public final class SubscriptionMatchRules {
    private SubscriptionMatchRules() {
    }

    public static void validate(MatchOptions options) {
        if (options.getWinsNeeded() != 1) {
            throw new IllegalArgumentException(
                    "Set Wins to 1 for subscription play. The subscription player does not yet handle sideboarding "
                            + "and starting the next game of a multi-game match.");
        }
        if (!options.getPassword().isEmpty()) {
            throw new IllegalArgumentException(
                    "Leave the table password empty for subscription play. The local game bridge does not yet send a table password.");
        }
    }
}
