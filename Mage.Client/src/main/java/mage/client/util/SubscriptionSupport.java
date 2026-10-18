package mage.client.util;

import com.google.gson.Gson;
import mage.client.MageFrame;
import mage.client.SessionHandler;
import mage.game.match.MatchOptions;

import javax.swing.JOptionPane;
import javax.swing.Timer;
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Local subscription player integration. Authentication stays with each provider's CLI (Codex or Claude Code). */
public final class SubscriptionSupport {
    private static final Gson JSON = new Gson();
    private static Catalog catalog;
    private static final SubscriptionPlayerRegistry activePlayers = new SubscriptionPlayerRegistry();

    private SubscriptionSupport() {
    }

    public static final class Model {
        public String id;
        public String name;
        public List<String> efforts;
        public String defaultEffort;
        public boolean isDefault;

        @Override
        public String toString() {
            return name;
        }
    }

    /** One signed-in subscription CLI, shown as its own player type. */
    public static final class Provider {
        public String id;
        public String playerType;
        public String playerName;
        public List<Model> models;

        @Override
        public String toString() {
            return playerType;
        }
    }

    private static final class Catalog {
        List<Provider> providers;
    }

    public static boolean isConfigured() {
        return System.getProperty("xmage.subscription.catalog") != null;
    }

    public static synchronized List<Provider> providers() {
        if (catalog == null) {
            try (Reader reader = Files.newBufferedReader(Path.of(requiredProperty("catalog")), StandardCharsets.UTF_8)) {
                Catalog loaded = JSON.fromJson(reader, Catalog.class);
                if (loaded == null || loaded.providers == null || loaded.providers.isEmpty()
                        || loaded.providers.stream().anyMatch(provider -> provider.models == null || provider.models.isEmpty())) {
                    throw new IllegalStateException("The subscription model catalog is empty or invalid");
                }
                catalog = loaded;
            } catch (IOException error) {
                throw new IllegalStateException("Could not read the subscription model catalog", error);
            }
        }
        return catalog.providers;
    }

    /** The provider for a player type combo box item, or null for native XMage player types. */
    public static Provider provider(Object playerTypeItem) {
        if (!isConfigured() || playerTypeItem == null) {
            return null;
        }
        return providers().stream().filter(provider -> provider == playerTypeItem).findFirst().orElse(null);
    }

    public static Provider providerById(String id) {
        return providers().stream().filter(provider -> provider.id.equals(id)).findFirst().orElse(null);
    }

    private static String requiredProperty(String name) {
        String value = System.getProperty("xmage.subscription." + name);
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException("Open this client with windows/Play-vs-LLM.cmd first");
        }
        return value;
    }

    public static void validate(Provider provider, String deck, Model model, String effort) {
        if (provider == null || !isConfigured() || !"127.0.0.1".equals(SessionHandler.getSession().getServerHost())) {
            throw new IllegalArgumentException("Subscription play requires the isolated local Windows launcher");
        }
        if (deck.isEmpty() || !Files.isRegularFile(Path.of(deck))) {
            throw new IllegalArgumentException("Select a deck file for the " + provider.playerName + " opponent");
        }
        if (model == null || !provider.models.contains(model) || !model.efforts.contains(effort)) {
            throw new IllegalArgumentException("Select an available " + provider.playerName + " model and supported reasoning level");
        }
    }

    public static void start(Provider provider, UUID tableId, int seat, String deck, Model model, String effort,
                             MatchOptions options) throws IOException {
        validate(provider, deck, model, effort);
        Path run = Path.of(requiredProperty("runs")).resolve(tableId + "-seat-" + seat);
        Files.createDirectories(run);
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("provider", provider.id);
        request.put("table_id", tableId.toString());
        request.put("server_port", Integer.parseInt(requiredProperty("serverPort")));
        request.put("deck", Path.of(deck).toAbsolutePath().toString());
        request.put("model", model.id);
        request.put("reasoning", effort);
        request.put("seat", seat);
        request.put("game_type", options.getGameType());
        request.put("deck_type", options.getDeckType());
        request.put("player_count", options.getPlayerTypes().size());
        request.put("username", provider.playerName + " " + seat);
        request.put("owner_pid", ProcessHandle.current().pid());
        request.put("run", run.toString());
        request.put("catalog", requiredProperty("catalog"));
        ProcessBuilder builder = new ProcessBuilder(requiredProperty("python"), "-u", "-m", "windows.gui_player");
        builder.directory(Path.of(requiredProperty("repo")).toFile());
        builder.redirectErrorStream(true);
        builder.redirectOutput(run.resolve("supervisor.log").toFile());
        Process process = builder.start();
        activePlayers.register(tableId, seat, run);
        try (var input = process.getOutputStream()) {
            input.write(JSON.toJson(request).getBytes(StandardCharsets.UTF_8));
        }
        Timer monitor = new Timer(1000, null);
        monitor.addActionListener(event -> {
            if (!process.isAlive()) {
                monitor.stop();
                activePlayers.finished(tableId, seat);
                if (process.exitValue() != 0) {
                    JOptionPane.showMessageDialog(MageFrame.getDesktop(),
                            "The " + provider.playerName + " player stopped. Close this table before trying again.\n"
                                    + "Details: " + run.resolve("supervisor.log"),
                            provider.playerName + " player", JOptionPane.ERROR_MESSAGE);
                }
            }
        });
        monitor.start();
    }

    public static void stop(UUID tableId) {
        try {
            activePlayers.stop(tableId);
        } catch (IOException error) {
            throw new IllegalStateException("Could not stop the subscription players for this table", error);
        }
    }
}
