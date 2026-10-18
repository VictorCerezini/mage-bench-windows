package mage.client.util;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SubscriptionSupportTest {
    @TempDir
    Path folder;

    @Test
    void eachSignedInProviderBecomesItsOwnPlayerTypeWithItsOwnModels() throws Exception {
        Path catalog = folder.resolve("subscription-models.json");
        Files.writeString(catalog, "{\"providers\": ["
                + "{\"id\": \"chatgpt_subscription\", \"playerType\": \"ChatGPT subscription\", \"playerName\": \"ChatGPT\","
                + " \"models\": [{\"id\": \"gpt-6-astra\", \"name\": \"GPT-6 Astra\", \"efforts\": [\"medium\"],"
                + " \"defaultEffort\": \"medium\", \"isDefault\": true}]},"
                + "{\"id\": \"claude_subscription\", \"playerType\": \"Claude subscription\", \"playerName\": \"Claude\","
                + " \"models\": [{\"id\": \"claude-opus-5-5\", \"name\": \"Claude Opus 5.5\", \"efforts\": [\"medium\", \"max\"],"
                + " \"defaultEffort\": \"medium\", \"isDefault\": true}]}],"
                + " \"unavailable\": []}", StandardCharsets.UTF_8);
        System.setProperty("xmage.subscription.catalog", catalog.toString());
        try {
            List<SubscriptionSupport.Provider> providers = SubscriptionSupport.providers();
            assertEquals(List.of("ChatGPT subscription", "Claude subscription"),
                    providers.stream().map(Object::toString).collect(Collectors.toList()));
            SubscriptionSupport.Provider claude = SubscriptionSupport.providerById("claude_subscription");
            assertSame(claude, SubscriptionSupport.provider(claude));
            assertEquals("claude-opus-5-5", claude.models.get(0).id);
            assertEquals(List.of("medium", "max"), claude.models.get(0).efforts);
            // Native XMage player types are not subscription providers.
            assertNull(SubscriptionSupport.provider("Human"));
            assertNull(SubscriptionSupport.providerById("missing_subscription"));
        } finally {
            System.clearProperty("xmage.subscription.catalog");
        }
    }

    @Test
    void stoppedPlayerDialogShowsTheRecordedReasonWrapped() throws Exception {
        assertEquals("", SubscriptionSupport.failureReason(folder));
        String reason = "OpenRouter stopped before a confirmed game result: [Google AI Studio] model is temporarily"
                + " rate-limited upstream. Free models are often busy: choose another free model, or try again later.";
        Files.writeString(folder.resolve("manifest.json"), "{\"status\": \"failed\", \"error\": \"" + reason + "\"}",
                StandardCharsets.UTF_8);
        String shown = SubscriptionSupport.failureReason(folder);
        assertEquals(reason, shown.replace('\n', ' ').trim());
        assertTrue(shown.lines().allMatch(line -> line.length() <= 100));
        assertTrue(shown.endsWith("\n"));
    }
}
